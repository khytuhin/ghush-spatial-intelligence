import copy
import csv
import io
import json
import pandas as pd
import pytest
from pipeline.products import build_bundle,trend,amount_band,BANDS,NAMES
from pipeline.bundle_contracts import validate_bundle
from pipeline.publication import publish_bundle
from pipeline.contracts import validate_directory
from pipeline.geography import DIVISIONS,parent_ids

@pytest.fixture
def hierarchy(boundaries):
    u=boundaries.copy()
    u['districtID']=['D0','D0',*[f'D{i}' for i in range(1,8)]]
    u['district']=u.districtID.map(lambda d:'District '+d)
    u['division']=u.districtID.map({f'D{i}':v for i,v in enumerate(DIVISIONS)})
    d=u.dissolve(by='districtID').reset_index()
    d['shapeID']=d.districtID;d['shapeName']=d.district
    return u,d

def build(rows,hierarchy,cfg,as_of):
    return build_bundle(rows,*hierarchy,cfg=cfg,as_of=as_of,demo=True)

def test_district_division_and_pooled_median(reports,hierarchy,cfg,as_of):
    rows=pd.concat([reports(5,amount=500),reports(10,area='Area 1',amount=10000,start=100)])
    b=build(rows,hierarchy,cfg,as_of);validate_bundle(b)
    d=b['district_metrics.geojson']['features'][0]['properties']['slices']['ALL|ALL']
    assert d['report_count']==15 and d['median_amount']==10000 and d['total_amount']==102500
    assert b['division_summary.json']['divisions'][0]['slices']['ALL|ALL']['median_amount']==10000
    assert len(b['division_summary.json']['divisions'])==8

def test_weekly_partition_blocks_small_complements(reports,hierarchy,cfg,as_of):
    rows=pd.concat([reports(3,age=3),reports(2,age=10,start=100)])
    b=build(rows,hierarchy,cfg,as_of);validate_bundle(b)
    assert b['summary.json']['meta']['report_count']==0
    assert all(m['report_count']==0 for m in b['weekly_summary.json']['national'].values())
    assert len(list(csv.DictReader(io.StringIO(b['weekly_summary.csv']))))==0

def test_hidden_only_department_not_disclosed(reports,hierarchy,cfg,as_of):
    rows=pd.concat([reports(5),reports(1,area='Area 1',department='BRTA',start=100)])
    b=build(rows,hierarchy,cfg,as_of);validate_bundle(b)
    assert b['summary.json']['departments']==['Land Office']

def test_unsafe_amount_bands_withheld_as_whole_table(reports,hierarchy,cfg,as_of):
    rows=reports(5);rows.loc[0,'amount']=7500
    b=build(rows,hierarchy,cfg,as_of);validate_bundle(b)
    assert b['summary.json']['meta']['report_count']==5
    assert all(g['metrics']['suppressed'] for groups in b['summary.json']['amount_bands'].values() for g in groups)

def test_band_edges_and_unknown():
    assert [amount_band(v) for v in [0,999.99,1000,5000,10000,25000,50000,None]]==[BANDS[i] for i in [0,0,1,2,3,4,5,6]]

def test_sparse_trend_and_direction():
    assert trend({'report_count':5},{'report_count':10})=={'category':'insufficient','change':None}
    assert trend({'report_count':20},{'report_count':10})['category']=='rising'
    assert trend({'report_count':10},{'report_count':20})['category']=='declining'
    assert trend({'report_count':11},{'report_count':10})['category']=='stable'

def test_weekly_export_uses_safe_complete_cells_only(reports,hierarchy,cfg,as_of):
    rows=pd.concat([reports(10,age=3),reports(20,age=10,start=100),reports(5,age=1,start=200)])
    rows['description']='PRIVATE_SENTINEL';rows['latitude']=23.456
    b=build(rows,hierarchy,cfg,as_of);validate_bundle(b)
    exported=list(csv.DictReader(io.StringIO(b['weekly_summary.csv'])))
    assert sum(int(r['published_reports']) for r in exported)==30
    assert all(r['department']!='ALL' and r['week_start']<=b['weekly_summary.json']['complete_through'] for r in exported)
    assert 'PRIVATE_SENTINEL' not in json.dumps(b) and 'latitude' not in json.dumps(b)
    assert b['summary.json']['trends']['ALL']['category']=='declining'

def test_unknown_dates_only_in_all_time(reports,hierarchy,cfg,as_of):
    rows=reports(5);rows['reported_at']=None
    b=build(rows,hierarchy,cfg,as_of);validate_bundle(b)
    assert b['summary.json']['meta']['report_count']==5
    assert all(m['report_count']==0 for m in b['weekly_summary.json']['national'].values())

def test_population_unavailable_not_fabricated(reports,hierarchy,cfg,as_of):
    b=build(reports(),hierarchy,cfg,as_of)
    assert b['summary.json']['population']['available'] is False
    assert all(d['population'] is None for d in b['division_summary.json']['divisions'])
    assert all(m['reports_per_100k'] is None for d in b['division_summary.json']['divisions'] for m in d['slices'].values())

def test_complete_population_rates_and_provenance(reports,hierarchy,cfg,as_of,monkeypatch):
    import pipeline.analyze as analyze
    import pipeline.products as products
    u,d=hierarchy
    u.attrs['boundary_metadata']={'boundaryID':'TEST-ONLY'}
    u.attrs['population_metadata']={'boundary_id':'TEST-ONLY','sources':['Unit test denominator, not for publication']}
    loader=lambda g:{sid:100 for sid in g.shapeID}
    monkeypatch.setattr(analyze,'load_population',loader);monkeypatch.setattr(products,'load_population',loader)
    b=build(reports(10),hierarchy,cfg,as_of);validate_bundle(b)
    assert b['summary.json']['population']['total']==900
    assert b['division_summary.json']['divisions'][0]['slices']['ALL|ALL']['reports_per_100k']==5000

def test_incomplete_population_does_not_invent_national_ratio(reports,hierarchy,cfg,as_of,monkeypatch):
    import pipeline.analyze as analyze
    import pipeline.products as products
    monkeypatch.setattr(analyze,'load_population',lambda g:{'A0':100})
    monkeypatch.setattr(products,'load_population',lambda g:{'A0':100})
    b=build(reports(10),hierarchy,cfg,as_of);validate_bundle(b)
    assert b['summary.json']['population']['available'] is False
    assert all(m['reports_per_100k'] is None for f in b['adm3_metrics.geojson']['features'] for m in f['properties']['slices'].values())

def test_csv_formula_labels_rejected(reports,hierarchy,cfg,as_of):
    u,d=hierarchy;u.loc[u.districtID=='D0','district']='=FORMULA';d.loc[d.shapeID=='D0','shapeName']='=FORMULA'
    with pytest.raises(ValueError,match='spreadsheet'):build(reports(10),hierarchy,cfg,as_of)

@pytest.mark.parametrize('mutation',['csv','district','division','weekly','point','version','extra','band','trend','polygon'])
def test_bundle_rejects_leaks_and_mismatches(mutation,reports,hierarchy,cfg,as_of):
    b=build(reports(10),hierarchy,cfg,as_of)
    if mutation=='csv': b['weekly_summary.csv']+='PRIVATE_SENTINEL\n'
    if mutation=='district':b['district_metrics.geojson']['features'][0]['properties']['slices']['ALL|ALL']['report_count']+=1
    if mutation=='division':b['division_summary.json']['divisions'][0]['slices']['ALL|ALL']['total_amount']+=1
    if mutation=='weekly':next(iter(b['weekly_summary.json']['national'].values()))['report_count']=1
    if mutation=='point':b['district_metrics.geojson']['features'][0]['geometry']={'type':'Point','coordinates':[90,23]}
    if mutation=='polygon':b['district_metrics.geojson']['features'][0]['geometry']={'type':'Polygon','coordinates':[[[90,23],[90,23],[90,23],[90,23]]]}
    if mutation=='version':b['weekly_summary.json']['data_id']='different'
    if mutation=='extra':b['division_summary.json']['divisions'][0]['raw_rows']=[]
    if mutation=='band':b['summary.json']['amount_bands']['ALL|ALL'][0]['metrics']['report_count']=1
    if mutation=='trend':b['summary.json']['trends']['ALL']={'category':'rising','change':99}
    with pytest.raises(ValueError):validate_bundle(b)

def test_bundle_noop_and_late_write_rollback(reports,hierarchy,cfg,as_of,tmp_path,monkeypatch):
    import pipeline.publication as publication
    b=build(reports(10),hierarchy,cfg,as_of)
    assert publish_bundle(b,tmp_path,as_of=as_of)
    before={n:(tmp_path/n).read_bytes() for n in NAMES}
    assert not publish_bundle(copy.deepcopy(b),tmp_path,as_of=as_of+pd.Timedelta(hours=12))
    original=publication.os.replace
    def fail(src,dst):
        if str(dst).endswith('weekly_summary.csv'):raise OSError('simulated late failure')
        return original(src,dst)
    monkeypatch.setattr(publication.os,'replace',fail)
    with pytest.raises(OSError):publish_bundle(build(reports(15),hierarchy,cfg,as_of),tmp_path,as_of=as_of)
    assert before=={n:(tmp_path/n).read_bytes() for n in NAMES}
    validate_directory(tmp_path)

def test_geography_rejects_ambiguous_parent(hierarchy):
    u,d=hierarchy
    assert parent_ids(u,d)==dict(zip(u.shapeID,u.districtID))
    d.loc[1,'geometry']=d.loc[0,'geometry']
    with pytest.raises(ValueError,match='ambiguous'):parent_ids(u,d)
