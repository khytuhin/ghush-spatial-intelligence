import json
import pytest
from pipeline.sources import api
from pipeline.sources.http import SourceError, assert_robots_allowed, get_bytes

@pytest.fixture
def mapping(tmp_path):
    path=tmp_path/"mapping.json"
    cfg={"records_path":"reports","fields":{"report_id":"id","reported_at":"date","department":"dept","upazila":"area"},
         "pagination":{"mode":"offset","page_size":2,"max_pages":3,"total_path":"total"}}
    path.write_text(json.dumps(cfg));return path

def record(i):return {"id":str(i),"date":"2026-01-01","dept":"BRTA","area":"Savar"}

def setup(monkeypatch, pages):
    monkeypatch.setattr(api,"assert_robots_allowed",lambda *args,**kw:None)
    monkeypatch.setattr(api.time,"sleep",lambda _:None)
    calls=[]
    def get(url,**kw):
        calls.append(url)
        return pages.pop(0)
    monkeypatch.setattr(api,"get_json",get)
    return calls

def test_offset_pagination(mapping,monkeypatch):
    calls=setup(monkeypatch,[{"reports":[record(1),record(2)],"total":3},{"reports":[record(3)],"total":3}])
    assert len(api.load_api("https://example.org/feed",mapping))==3
    assert "offset=2" in calls[1]

@pytest.mark.parametrize("second",[
    {"reports":[],"total":3},{"reports":[record(2)],"total":3},
    {"reports":[record(3)],"total":4},
    {"reports":[{"id":"3"}],"total":3}
])
def test_incomplete_or_drifting_source_fails(mapping,monkeypatch,second):
    setup(monkeypatch,[{"reports":[record(1),record(2)],"total":3},second])
    with pytest.raises(SourceError):api.load_api("https://example.org/feed",mapping)

def test_page_cap_fails(mapping,monkeypatch):
    cfg=json.loads(mapping.read_text());cfg["pagination"]["max_pages"]=1;mapping.write_text(json.dumps(cfg))
    setup(monkeypatch,[{"reports":[record(1)],"total":3}])
    with pytest.raises(SourceError,match="limit"):api.load_api("https://example.org/feed",mapping)

def test_undeclared_pagination_fails(mapping,monkeypatch):
    cfg=json.loads(mapping.read_text());cfg.pop("pagination");mapping.write_text(json.dumps(cfg))
    setup(monkeypatch,[])
    with pytest.raises(SourceError,match="Declare"):api.load_api("https://example.org/feed",mapping)

def test_robots_blocks_api(monkeypatch):
    import pipeline.sources.http as http
    monkeypatch.setattr(http,"get_bytes",lambda *a,**k:b"User-Agent: *\nAllow: /\nDisallow: /api/\n")
    with pytest.raises(SourceError,match="disallows"):assert_robots_allowed("https://www.ghush.site/api/reports")

@pytest.mark.parametrize("status",[401,403,429,302])
def test_transport_stops_without_retry(status):
    class Response:
        status_code=status
        def __enter__(self):return self
        def __exit__(self,*args):pass
    class Session:
        calls=0
        def get(self,*args,**kw):
            self.calls+=1
            assert kw["allow_redirects"] is False
            return Response()
    session=Session()
    with pytest.raises(SourceError):get_bytes("https://example.org/feed",session=session)
    assert session.calls==1

def test_scraper_disabled():
    from pipeline.sources.scrape import load_scrape
    with pytest.raises(RuntimeError,match="disabled"):load_scrape("https://example.org","unused")

def test_zero_is_a_valid_report_id(mapping,monkeypatch):
    row=record(0);row["id"]=0
    setup(monkeypatch,[{"reports":[row],"total":1}])
    assert len(api.load_api("https://example.org/feed",mapping))==1

def test_server_requested_delay_is_respected():
    class Response:
        status_code=503
        headers={"Retry-After":"600"}
        def __enter__(self):return self
        def __exit__(self,*args):pass
    class Session:
        calls=0
        def get(self,*args,**kwargs):
            self.calls+=1
            return Response()
    session=Session()
    with pytest.raises(SourceError,match="deferred retry"):
        get_bytes("https://example.org/feed",session=session)
    assert session.calls==1

def test_hosted_csv_adapter(monkeypatch):
    from pipeline.sources import csv_feed
    monkeypatch.setattr(csv_feed,"assert_robots_allowed",lambda url:None)
    monkeypatch.setattr(csv_feed,"get_bytes",lambda *a,**kw:b"report_id,upazila,amount\n0001,Savar,1000\n")
    frame=csv_feed.load_csv_feed("https://example.org/export.csv")
    assert frame.iloc[0].report_id=="0001" and frame.iloc[0].upazila=="Savar"

def test_complete_json_export(mapping,monkeypatch):
    cfg=json.loads(mapping.read_text());cfg["pagination"]={"mode":"none"};cfg["complete_snapshot"]=True
    mapping.write_text(json.dumps(cfg))
    setup(monkeypatch,[{"reports":[record(1)]}])
    assert len(api.load_api("https://example.org/export.json",mapping))==1
