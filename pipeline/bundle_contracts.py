"""Strict schema-3 validation, including rollups, weekly cells and the exact CSV."""
import copy
import json
import math
from datetime import date
from pipeline.contracts import METRICS, validate
from pipeline.products import SCHEMA, NAMES, JSON_NAMES, BANDS, csv_text, trend
from pipeline.geography import DIVISIONS

def require(condition,message):
    if not condition: raise ValueError(message)

def metric(m,k):
    require(set(m)==METRICS and type(m['suppressed']) is bool,'Invalid metric contract.')
    if m['suppressed']:
        require(all(v is None for key,v in m.items() if key!='suppressed'),'Suppressed cell contains values.')
        return
    n=m['report_count']
    require(type(n) is int and (n==0 or n>=k),'Published count below privacy threshold.')
    for field,value in m.items():
        if field in {'moran_cluster','suppressed'}: continue
        require(value is None or type(value) in {int,float} and math.isfinite(value),'Non-finite metric.')
        if value is not None and field!='gi_z': require(value>=0,'Negative metric.')
    for key in ('refusal_rate','paid_rate','pending_rate','gi_p'):
        require(m[key] is None or 0<=m[key]<=1,'Invalid rate.')
    require(m['moran_cluster'] in {None,'High–High','Low–High','Low–Low','High–Low'},'Unknown cluster.')
    if n==0:
        require(all(m[f] is None for f in ('total_amount','median_amount','refusal_rate','paid_rate','pending_rate')),'Empty cell has report metrics.')

def close(actual,expected):
    return actual is None and expected is None or (type(actual) in {int,float} and type(expected) in {int,float} and math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-6))

def rollup(parent,children):
    children=[c for c in children if not c['suppressed'] and c['report_count']]
    n=sum(c['report_count'] for c in children)
    require(parent['report_count']==n,'Rollup includes hidden or missing reports.')
    for field in ('total_amount','paid_rate','refusal_rate','pending_rate'):
        expected=None
        if children and all(c[field] is not None for c in children):
            expected=sum(c[field] if field=='total_amount' else c[field]*c['report_count'] for c in children)
            if field!='total_amount': expected/=n
        require(close(parent[field],expected),'Rollup reveals hidden metrics or disagrees with children.')

def legacy_pair(geo,summary):
    g,s=copy.deepcopy(geo),copy.deepcopy(summary)
    g['schema_version']=s['meta']['schema_version']=2
    for f in g['features']:
        for key in ('districtID','district','division'): f['properties'].pop(key,None)
    for key in ('district_boundaries','hierarchy_source'): s['meta'].pop(key,None)
    for key in ('population','amount_bands','district_global_spatial','trends'): s.pop(key,None)
    return g,s

def validate_bundle(bundle):
    require(set(bundle)==set(NAMES),'Incomplete publication bundle.')
    g=bundle['adm3_metrics.geojson'];dg=bundle['district_metrics.geojson'];s=bundle['summary.json']
    divisions=bundle['division_summary.json'];w=bundle['weekly_summary.json']
    ids=[bundle[n]['meta'].get('data_id') if n=='summary.json' else bundle[n].get('data_id') for n in JSON_NAMES]
    require(len(set(ids))==1,'Mixed publication versions.')
    require(all((bundle[n]['meta'] if n=='summary.json' else bundle[n]).get('schema_version')==SCHEMA for n in JSON_NAMES),'Unsupported bundle schema.')
    validate(*legacy_pair(g,s))
    k=s['meta']['privacy_k'];keys=set(s['slice_totals']);depts=['ALL',*s['departments']]
    require(set(s)=={'meta','departments','periods','slice_totals','global_spatial','population','amount_bands','district_global_spatial','trends'},'Unexpected summary fields.')
    require(set(s['population'])=={'available','total','basis','sources','boundary_id'},'Unexpected population fields.')
    require(type(s['population']['available']) is bool,'Invalid population availability.')
    for n in ('adm3_metrics.geojson','district_metrics.geojson'):
        require(set(bundle[n])<= {'type','schema_version','data_id','features'},'Unexpected GeoJSON fields.')
    require(dg['type']=='FeatureCollection' and bool(dg['features']),'Missing district geometry.')
    # Reuse the polygon validator on district geometry without allowing point shortcuts.
    proxy=copy.deepcopy(dg);proxy['schema_version']=2
    for f in proxy['features']:
        p=f['properties'];f['properties']={key:p[key] for key in ('shapeID','shapeName','demo','slices')}
        f['properties']['shapeType']='ADM3'
    validate(proxy,legacy_pair(g,s)[1])
    districts={f['properties']['shapeID']:f['properties'] for f in dg['features']}
    require(len(districts)==len(dg['features']),'Duplicate districts.')
    require(set(divisions)<= {'schema_version','data_id','divisions'},'Unexpected division fields.')
    by_div={d['name']:d for d in divisions['divisions']}
    require(set(by_div)==set(DIVISIONS) and len(divisions['divisions'])==8,'All eight divisions are required.')
    for f in g['features']:
        p=f['properties']
        require(set(p)=={'shapeID','shapeName','shapeType','demo','slices','districtID','district','division'},'Unexpected upazila fields.')
        parent=districts.get(p['districtID'])
        require(parent is not None and p['district']==parent['shapeName'] and p['division']==parent['division'],'Broken parent link.')
    def entity(e,allowed):
        require(set(e)==allowed,'Unexpected aggregate fields.')
        require(set(e['slices'])==keys,'Incomplete aggregate matrix.')
        pop=e['population']
        require(pop is None or type(pop) in {int,float} and math.isfinite(pop) and pop>0,'Invalid population denominator.')
        require((pop is not None)==s['population']['available'],'Partial population coverage is not a national bias denominator.')
        for m in e['slices'].values():
            metric(m,k)
            require(close(m['reports_per_100k'],m['report_count']/pop*100000 if pop else None),'Invalid population rate.')
    for sid,d in districts.items():
        entity(d,{'shapeID','shapeName','shapeType','demo','division','population','slices','trends'})
        require(d['shapeType']=='ADM2' and d['division'] in DIVISIONS,'Invalid district identity.')
        children=[f['properties'] for f in g['features'] if f['properties']['districtID']==sid]
        for key in keys: rollup(d['slices'][key],[c['slices'][key] for c in children])
    for name,d in by_div.items():
        entity(d,{'name','population','slices','trends','amount_bands'})
        children=[v for v in districts.values() if v['division']==name]
        for key in keys: rollup(d['slices'][key],[v['slices'][key] for v in children])
        if d['population'] is not None: require(close(d['population'],sum(v['population'] for v in children)),'Division population mismatch.')
    if s['population']['available']:
        require(bool(s['population']['sources']) and all(isinstance(v,str) and 0<len(v)<=1000 for v in s['population']['sources'])
                and s['population']['boundary_id']==s['meta']['boundaries'].get('boundaryID'),'Population provenance is missing or incompatible.')
        require(close(s['population']['total'],sum(d['population'] for d in by_div.values())),'National population mismatch.')
    else: require(s['population']['total'] is None and s['population']['sources']==[] and s['population']['boundary_id'] is None,'Unavailable population must be null.')
    for key in keys:
        metric(s['slice_totals'][key],k)
        rollup(s['slice_totals'][key],[d['slices'][key] for d in by_div.values()])
    require(set(w)<= {'schema_version','data_id','weeks','complete_through','current_week','national','divisions','districts'},'Unexpected weekly fields.')
    weeks=w['weeks']
    require(3<=len(weeks)<=53 and weeks==sorted(set(weeks)),'Invalid weekly range.')
    for week in weeks: require(date.fromisoformat(week).weekday()==0,'Weeks must start Monday UTC.')
    require(all((date.fromisoformat(b)-date.fromisoformat(a)).days==7 for a,b in zip(weeks,weeks[1:])),'Weekly gaps.')
    require(w['current_week']==weeks[-1] and w['complete_through']==weeks[-2],'Incorrect complete week.')
    week_keys={f'{week}|{d}' for week in weeks for d in depts}
    require(set(w['districts'])==set(districts) and set(w['divisions'])==set(DIVISIONS),'Missing weekly geography.')
    for series in [w['national'],*w['districts'].values(),*w['divisions'].values()]:
        require(set(series)==week_keys,'Incomplete weekly matrix.')
        for m in series.values(): metric(m,k)
        for week in weeks: rollup(series[f'{week}|ALL'],[series[f'{week}|{d}'] for d in depts if d!='ALL'])
    for key in week_keys:
        for name in DIVISIONS:
            rollup(w['divisions'][name][key],[w['districts'][sid][key] for sid,d in districts.items() if d['division']==name])
        rollup(w['national'][key],[w['divisions'][name][key] for name in DIVISIONS])
    for entity_data,series in [(s,w['national']),*[(d,w['districts'][sid]) for sid,d in districts.items()],*[(d,w['divisions'][name]) for name,d in by_div.items()]]:
        slices=entity_data.get('slices',s['slice_totals'])
        require(set(entity_data['trends'])==set(depts),'Incomplete trend matrix.')
        for dept in depts:
            require(sum(series[f'{week}|{dept}']['report_count'] for week in weeks)<=slices[f'ALL|{dept}']['report_count'],'Weekly data exceeds published population.')
            expected=trend(series[f'{weeks[-2]}|{dept}'],series[f'{weeks[-3]}|{dept}'],k)
            require(entity_data['trends'][dept]==expected,'Invalid trend or sparse inference.')
    band_flags=set()
    for entity_data in [s,*by_div.values()]:
        require(set(entity_data['amount_bands'])==keys,'Incomplete amount-band matrix.')
        for key,groups in entity_data['amount_bands'].items():
            require([v.get('band') for v in groups]==list(BANDS),'Invalid amount bands.')
            for b in groups:
                require(set(b)=={'band','metrics'},'Unexpected amount-band fields.')
                metric(b['metrics'],k);band_flags.add(b['metrics']['suppressed'])
            if not groups[0]['metrics']['suppressed']:
                total=entity_data.get('slices',s['slice_totals'])[key]['report_count']
                require(sum(v['metrics']['report_count'] for v in groups)==total,'Band totals disagree with published counts.')
    require(len(band_flags)==1,'Partial band withholding permits reconstruction.')
    for key,stat in s['district_global_spatial'].items():
        require(key in keys and set(stat)=={'moran_i','p_sim','permutations','basis'},'Invalid district spatial statistic.')
        require(type(stat['moran_i']) in {int,float} and math.isfinite(stat['moran_i']) and 0<=stat['p_sim']<=1
                and type(stat['permutations']) is int and stat['permutations']>0,'Invalid spatial values.')
    require(bundle['weekly_summary.csv']==csv_text(w,list(districts.values())),'CSV differs from validated weekly cells.')
    json.dumps(bundle,allow_nan=False)
    return True
