import copy
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box
from pipeline.analyze import load_config

@pytest.fixture
def cfg():
    config=copy.deepcopy(load_config())
    config["statistics"]["enabled"]=False
    return config

@pytest.fixture
def as_of():
    return pd.Timestamp("2026-08-26T00:00:00Z")

@pytest.fixture
def boundaries():
    return gpd.GeoDataFrame([{"shapeID":f"A{i}","shapeName":f"Area {i}",
        "geometry":box(89+i%3*.1,23+i//3*.1,89+(i%3+1)*.1,23+(i//3+1)*.1)} for i in range(9)], crs=4326)

@pytest.fixture
def reports(as_of):
    def build(count=5, area="Area 0", department="Land Office", age=10, start=0, amount=1000, outcome="paid"):
        return pd.DataFrame([{"report_id":f"r-{start+i}","reported_at":as_of-pd.Timedelta(days=age),
            "department":department,"upazila":area,"amount":amount,"outcome":outcome} for i in range(count)])
    return build
