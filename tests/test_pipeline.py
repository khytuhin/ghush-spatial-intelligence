import copy
import json
import numpy as np
import pandas as pd
import pytest
from pipeline.analyze import (build_products, normalize_reports, norm_name, parse_amount,
    period_mask, match_reports_to_adm3, add_spatial_statistics)
from pipeline.contracts import validate, validate_directory
from pipeline.publication import publish
from pipeline.run import main

@pytest.mark.parametrize("value,expected",[("৳১,২৩৪.৫০",1234.5),("BDT 100",100),("0",0),
    ("1e6",None),("-50",None),("100-200",None),("paid 500",None),(float("inf"),None),(None,None),
    ("1,00,000",100000),("1,2",None),("1,,000",None),("1BDT00",None)])
def test_amount(value,expected):
    result=parse_amount(value)
    assert np.isnan(result) if expected is None else result==expected

def products(rows,boundaries,cfg,as_of):
    return build_products(rows,boundaries,cfg=cfg,as_of=as_of)

def test_private_fields_never_serialized(reports,boundaries,cfg,as_of):
    rows=reports(2);rows["description"]="PRIVATE SENTINEL";rows["latitude"]=23.987
    rows["location"]="PERSON HOME SENTINEL"
    geo,summary=products(rows,boundaries,cfg,as_of)
    serialized=json.dumps([geo,summary])
    assert "SENTINEL" not in serialized and "unmatched_examples" not in summary
    assert summary["meta"]["report_count"]==0
    assert summary["slice_totals"]["ALL|ALL"]["total_amount"] is None
    assert all(m["suppressed"] and m["report_count"] is None for m in geo["features"][0]["properties"]["slices"].values())

def test_temporal_department_complements_hidden(reports,boundaries,cfg,as_of):
    rows=pd.concat([reports(5),reports(1,department="BRTA",age=60,start=100)])
    geo,summary=products(rows,boundaries,cfg,as_of)
    assert all(m["suppressed"] for m in geo["features"][0]["properties"]["slices"].values())
    assert all(m["report_count"]==0 for m in summary["slice_totals"].values())

def test_safe_k_and_zero(reports,boundaries,cfg,as_of):
    geo,summary=products(reports(5),boundaries,cfg,as_of)
    assert summary["meta"]["report_count"]==5
    assert geo["features"][0]["properties"]["slices"]["ALL|ALL"]["report_count"]==5
    assert geo["features"][1]["properties"]["slices"]["ALL|ALL"]["report_count"]==0
    assert geo["features"][0]["properties"]["slices"]["ALL|ALL"]["reports_per_100k"] is None

def test_single_amount_and_outcome_not_exposed(reports,boundaries,cfg,as_of):
    rows=reports(5,amount=None);rows.loc[0,"amount"]=9000;rows.loc[0,"outcome"]="refused"
    geo,summary=products(rows,boundaries,cfg,as_of)
    for product in [geo["features"][0]["properties"]["slices"]["ALL|ALL"],summary["slice_totals"]["ALL|ALL"]]:
        assert product["total_amount"] is None and product["refusal_rate"] is None
        assert product["report_count"]==5

def test_unknown_date_not_all_periods(reports,cfg,as_of):
    rows=reports(5);rows["reported_at"]=None
    rows=normalize_reports(rows,cfg)
    assert not period_mask(rows,30,as_of).any()
    assert period_mask(rows,None,as_of).all()

def test_duplicate_and_conflict(reports,cfg):
    rows=reports()
    assert len(normalize_reports(pd.concat([rows,rows]),cfg))==5
    conflicting=rows.copy();conflicting.loc[0,"amount"]=99
    with pytest.raises(ValueError,match="Conflicting"):
        normalize_reports(pd.concat([rows,conflicting]),cfg)

def test_empty_and_missing_ids(reports,cfg):
    with pytest.raises(ValueError):normalize_reports(pd.DataFrame(),cfg)
    with pytest.raises(ValueError):normalize_reports(reports().drop(columns="report_id"),cfg)

def test_ambiguous_name_and_sadar(reports,boundaries,cfg):
    boundaries.loc[1,"shapeName"]="Area 0"
    rows=normalize_reports(reports(),cfg)
    assert match_reports_to_adm3(rows,boundaries,overrides={}).shapeID.isna().all()
    assert match_reports_to_adm3(rows,boundaries,overrides={"area 0":"A1"}).shapeID.eq("A1").all()
    assert norm_name("Gazipur Sadar")!=norm_name("Gazipur")

def test_low_match_rejects(reports,boundaries,cfg,as_of):
    with pytest.raises(ValueError,match="Too few"):
        products(reports(area="unknown"),boundaries,cfg,as_of)

def test_future_date_rejects(reports,boundaries,cfg,as_of):
    with pytest.raises(ValueError,match="future"):
        products(reports(age=-1),boundaries,cfg,as_of)

def test_unknown_department_canonical(reports,cfg):
    assert normalize_reports(reports(department="PERSON PRIVATE"),cfg).department.eq("Other public service").all()

def test_deterministic_publication(reports,boundaries,cfg,as_of,tmp_path):
    geo,summary=products(reports(),boundaries,cfg,as_of)
    assert publish(geo,summary,tmp_path,as_of=as_of)
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    assert not publish(*products(reports(),boundaries,cfg,as_of),tmp_path,as_of=as_of+pd.Timedelta(hours=12))
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    validate_directory(tmp_path)

def test_failed_serialization_preserves_pair(reports,boundaries,cfg,as_of,tmp_path):
    geo,summary=products(reports(),boundaries,cfg,as_of)
    publish(geo,summary,tmp_path,as_of=as_of)
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    geo["features"][0]["properties"]["slices"]["ALL|ALL"]["total_amount"]=float("nan")
    with pytest.raises(ValueError):publish(geo,summary,tmp_path)
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}

def test_second_replace_failure_rolls_back(reports,boundaries,cfg,as_of,tmp_path,monkeypatch):
    import pipeline.publication as module
    publish(*products(reports(),boundaries,cfg,as_of),tmp_path,as_of=as_of)
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    original=module.os.replace
    def fail_second(src,dst):
        if str(dst).endswith("summary.json"):raise OSError("simulated disk failure")
        return original(src,dst)
    monkeypatch.setattr(module.os,"replace",fail_second)
    with pytest.raises(OSError):publish(*products(reports(6),boundaries,cfg,as_of),tmp_path)
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}

def test_contract_rejects_coordinates_and_summary_leak(reports,boundaries,cfg,as_of):
    geo,summary=products(reports(),boundaries,cfg,as_of)
    bad=copy.deepcopy(geo);bad["features"][0]["geometry"]={"type":"Point","coordinates":[90,23]}
    with pytest.raises(ValueError):validate(bad,summary)
    bad=copy.deepcopy(summary);bad["slice_totals"]["ALL|ALL"]["report_count"]+=1
    with pytest.raises(ValueError):validate(geo,bad)
    bad=copy.deepcopy(summary);bad["slice_totals"]["ALL|ALL"]["total_amount"]+=99
    with pytest.raises(ValueError):validate(geo,bad)

def test_spatial_determinism_and_hidden_independence(boundaries):
    def metrics():
        return {f"A{i}":{"report_count":5+i*3,"suppressed":False} for i in range(9)}
    first,second=metrics(),metrics()
    a=add_spatial_statistics(boundaries,first,9,20)
    b=add_spatial_statistics(boundaries,second,9,20)
    assert a==b and first==second and a is not None
    first,second=metrics(),metrics()
    first["A0"]={"report_count":2,"suppressed":True}
    second["A0"]={"report_count":2000,"suppressed":True}
    a=add_spatial_statistics(boundaries,first,9,20)
    b=add_spatial_statistics(boundaries,second,9,20)
    assert a==b and first["A1"]==second["A1"]

def test_cli_failed_source_preserves_existing(tmp_path):
    sentinel=tmp_path/"summary.json";sentinel.write_text("unchanged")
    assert main(["--source","snapshot","--input",str(tmp_path/"missing.csv"),"--output-dir",str(tmp_path)])==1
    assert sentinel.read_text()=="unchanged"

def test_public_logs_do_not_reveal_hidden_totals(monkeypatch,caplog):
    from pipeline.logging_utils import counts
    monkeypatch.setenv("GITHUB_ACTIONS","true")
    with caplog.at_level("INFO"):
        counts(fetched=13,matched=13,suppressed=3,published=10)
    assert "suppressed=private" in caplog.text and "published=10" in caplog.text
    assert "13" not in caplog.text
