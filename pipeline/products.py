"""Schema 3: safe geographic, department and temporal products from one release population."""
from __future__ import annotations
import csv
import io
import pandas as pd
from shapely.geometry import mapping
from pipeline.analyze import (build_products, normalize_reports, match_reports_to_adm3,
    privacy_sets, period_mask, metric_row, suppressed_metrics, load_population, load_config,
    add_spatial_statistics)
from pipeline.geography import DIVISIONS

SCHEMA = 3
BANDS = ('Under ৳1,000','৳1,000–4,999','৳5,000–9,999','৳10,000–24,999','৳25,000–49,999','৳50,000+','Unknown amount')
CSV_FIELDS = ('week_start','division','district','department','published_reports','reported_amount','median_amount','refusal_rate')
JSON_NAMES = ('adm3_metrics.geojson','district_metrics.geojson','summary.json','division_summary.json','weekly_summary.json')
NAMES = (*JSON_NAMES, 'weekly_summary.csv')

def week_start(value):
    value = pd.Timestamp(value)
    return (value.normalize()-pd.Timedelta(days=value.dayofweek)).strftime('%Y-%m-%d')

def amount_band(value):
    if pd.isna(value): return BANDS[-1]
    for limit, label in zip((1000,5000,10000,25000,50000,float('inf')), BANDS):
        if value < limit: return label

def trend(current, previous, k=5):
    a, b = current.get('report_count'), previous.get('report_count')
    if a is None or b is None or min(a,b) < max(10,2*k):
        return {'category':'insufficient','change':None}
    change=(a-b)/b
    label = 'stable'
    if abs(a-b)>=k and abs(change)>=.2:
        label='rising' if change>0 else 'declining'
    return {'category':label,'change':change}

def csv_text(weekly, districts):
    out=io.StringIO(newline='')
    writer=csv.writer(out, lineterminator='\n'); writer.writerow(CSV_FIELDS)
    for district in sorted(districts, key=lambda d:(d['division'],d['shapeName'])):
        for key,m in sorted(weekly['districts'][district['shapeID']].items()):
            week,department=key.split('|')
            if department=='ALL' or week>weekly['complete_through'] or not m['report_count'] or m['suppressed']:
                continue
            if any(str(v).lstrip().startswith(('=','+','-','@')) for v in (district['division'],district['shapeName'],department)):
                raise ValueError('Unsafe spreadsheet label; refusing formula-like CSV content.')
            writer.writerow([week,district['division'],district['shapeName'],department,m['report_count'],
                             m['total_amount'],m['median_amount'],m['refusal_rate']])
    return out.getvalue()

def build_bundle(reports, upazilas, districts, *, cfg=None, as_of=None, demo=False, source_label='approved source'):
    cfg=cfg or load_config(); as_of=pd.Timestamp(as_of or pd.Timestamp.now(tz='UTC'))
    if as_of.tzinfo is None: raise ValueError('Refresh time must be timezone aware.')
    if not {'districtID','district','division'}.issubset(upazilas):
        raise ValueError('A verified upazila/district/division hierarchy is required.')
    if upazilas.shapeID.duplicated().any() or districts.shapeID.duplicated().any():
        raise ValueError('Duplicate administrative IDs.')
    if not set(upazilas.districtID).issubset(set(districts.shapeID)) or not set(districts.division).issubset(DIVISIONS):
        raise ValueError('Invalid geographic parent links.')
    geo, summary = build_products(reports, upazilas, cfg=cfg, as_of=as_of, demo=demo, source_label=source_label)
    normalized=normalize_reports(reports,cfg)
    matched=match_reports_to_adm3(normalized,upazilas,cutoff=cfg['matching']['fuzzy_cutoff'],allow_fuzzy=cfg['matching'].get('allow_fuzzy',False))
    matched=matched[matched.shapeID.notna()].copy()
    k=cfg['privacy']['minimum_public_reports']
    hidden,no_amounts,no_outcomes=privacy_sets(matched,cfg['periods'],k,as_of)
    rows=matched[~matched.shapeID.isin(hidden)].copy()
    parents=upazilas.set_index('shapeID')
    rows['districtID']=rows.shapeID.map(parents.districtID)
    rows['division']=rows.shapeID.map(parents.division)
    rows['_week']=rows.reported_at.map(lambda d: week_start(d) if pd.notna(d) else 'unknown')
    rows['_band']=rows.amount.map(amount_band)
    # Band counts are withheld as a complete table if any nonempty band/time/department
    # atom is rare. This prevents total-minus-bands reconstruction, including unknowns.
    age=(as_of-rows.reported_at).dt.total_seconds()/86400
    rows['_bin']=age.map(lambda a:-1 if pd.isna(a) else sum(a>=d for d in sorted(cfg['periods'].values())))
    band_counts=rows.groupby(['shapeID','department','_week','_bin','_band']).size()
    bands_allowed=not ((band_counts>0)&(band_counts<k)).any()
    depts=['ALL',*summary['departments']]
    periods={'ALL':None,**cfg['periods']}
    population=load_population(upazilas)
    # A national representation ratio needs complete, compatible denominator coverage.
    pop_complete=len(population)==len(upazilas) and bool(population)
    national_population=float(sum(population.values())) if pop_complete else None
    district_pop={sid:float(sum(population[u] for u in upazilas[upazilas.districtID==sid].shapeID))
                  if pop_complete else None for sid in districts.shapeID}
    division_pop={name:float(sum(district_pop[sid] for sid in districts[districts.division==name].shapeID))
                  if pop_complete else None for name in DIVISIONS}
    empty=rows.iloc[:0]
    def aggregate(group, pop=None):
        m=metric_row(group, amount_allowed=not group.shapeID.isin(no_amounts).any(),
                     outcome_allowed=not group.shapeID.isin(no_outcomes).any())
        if pop: m['reports_per_100k']=m['report_count']/pop*100000
        return m
    def slices(group,pop=None):
        return {f'{period}|{dept}':aggregate(sub if dept=='ALL' else sub[sub.department==dept],pop)
                for period,days in periods.items() for sub in [group[period_mask(group,days,as_of)]] for dept in depts}
    def bands(group):
        return {f'{p}|{d}':[{ 'band':b, 'metrics':aggregate(sub[sub._band==b]) if bands_allowed else suppressed_metrics()}
                           for b in BANDS]
                for p,days in periods.items() for filtered in [group[period_mask(group,days,as_of)]]
                for d in depts for sub in [filtered if d=='ALL' else filtered[filtered.department==d]]}
    current_week=week_start(as_of)
    complete=week_start(as_of-pd.Timedelta(days=7))
    previous=week_start(as_of-pd.Timedelta(days=14))
    first=rows.loc[rows._week!='unknown','_week'].min() if not rows.empty else None
    start=max(str(first) if isinstance(first,str) else previous, week_start(as_of-pd.Timedelta(weeks=52)))
    start=min(start,previous)
    weeks=[w.strftime('%Y-%m-%d') for w in pd.date_range(start,current_week,freq='W-MON')]
    def weekly_slices(group,pop=None):
        by_week={w:g for w,g in group.groupby('_week')}
        return {f'{w}|{d}':aggregate(sub if d=='ALL' else sub[sub.department==d],pop)
                for w in weeks for sub in [by_week.get(w,empty)] for d in depts}
    def trends(week_metrics):
        return {d:trend(week_metrics[f'{complete}|{d}'],week_metrics[f'{previous}|{d}'],k) for d in depts}
    district_features=[]; week_districts={}
    for r in districts.itertuples():
        group=rows[rows.districtID==r.shapeID]
        w=weekly_slices(group,district_pop[r.shapeID]);week_districts[r.shapeID]=w
        district_features.append({'type':'Feature','geometry':mapping(r.geometry),'properties':{
            'shapeID':r.shapeID,'shapeName':r.shapeName,'shapeType':'ADM2','division':r.division,'demo':demo,
            'population':district_pop[r.shapeID], 'slices':slices(group,district_pop[r.shapeID]),'trends':trends(w)}})
    division_rows=[]; week_divisions={}
    for name in DIVISIONS:
        group=rows[rows.division==name]
        w=weekly_slices(group,division_pop[name]);week_divisions[name]=w
        division_rows.append({'name':name,'population':division_pop[name], 'slices':slices(group,division_pop[name]),
                              'trends':trends(w),'amount_bands':bands(group)})
    district_spatial={}
    if cfg['statistics']['enabled']:
        for key in summary['slice_totals']:
            metrics={f['properties']['shapeID']:f['properties']['slices'][key] for f in district_features}
            stat=add_spatial_statistics(districts,metrics,cfg['statistics']['live_permutations'],cfg['statistics']['minimum_reports_for_spatial_test'])
            if stat: district_spatial[key]=stat
    for f in geo['features']:
        p=f['properties'];r=parents.loc[p['shapeID']]
        p.update(districtID=r.districtID,district=r.district,division=r.division)
        if not pop_complete:
            for m in p['slices'].values(): m['reports_per_100k']=None
    geo['schema_version']=summary['meta']['schema_version']=SCHEMA
    summary['meta']['privacy_policy']='whole-upazila suppression across department × week × rolling-window atoms; complete band-table withholding'
    summary['meta']['boundaries']=upazilas.attrs.get('boundary_metadata',{})
    summary['meta']['district_boundaries']=districts.attrs.get('boundary_metadata',{})
    summary['meta']['hierarchy_source']='https://bangladesh.gov.bd/views/district-list/'
    summary['population']={'available':bool(pop_complete),'total':national_population,
        'basis':'Complete ADM3 population with source citation and matching boundary ID required. No estimated denominators.',
        'sources':upazilas.attrs.get('population_metadata',{}).get('sources',[]) if pop_complete else [],
        'boundary_id':upazilas.attrs.get('population_metadata',{}).get('boundary_id') if pop_complete else None}
    summary['amount_bands']=bands(rows)
    summary['district_global_spatial']=district_spatial
    summary['slice_totals']=slices(rows,national_population)
    summary['trends']=trends(weekly_slices(rows))
    weekly={'schema_version':SCHEMA,'weeks':weeks,'complete_through':complete,'current_week':current_week,
            'national':weekly_slices(rows,national_population),'divisions':week_divisions,'districts':week_districts}
    bundle={'adm3_metrics.geojson':geo,'summary.json':summary,
        'district_metrics.geojson':{'type':'FeatureCollection','schema_version':SCHEMA,'features':district_features},
        'division_summary.json':{'schema_version':SCHEMA,'divisions':division_rows},'weekly_summary.json':weekly}
    bundle['weekly_summary.csv']=csv_text(weekly,[f['properties'] for f in district_features])
    return bundle
