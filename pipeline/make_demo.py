"""Reproducible synthetic preview using the same privacy/serialization path as production."""
from __future__ import annotations
import argparse
import copy
import logging
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))
import geopandas as gpd
import pandas as pd
from shapely.geometry import box
from pipeline.analyze import load_config
from pipeline.geography import load_hierarchy
from pipeline.products import build_bundle
from pipeline.publication import publish_bundle

def make_demo(directory):
    import json
    existing=Path(directory)/'summary.json'
    if existing.exists() and not json.loads(existing.read_text(encoding='utf-8'))['meta']['demo']:
        raise ValueError('Refusing to overwrite live data with demo. Choose a separate --output-dir.')
    boundaries,districts=load_hierarchy()
    rows=[]
    as_of=pd.Timestamp("2026-08-26T00:00:00Z")
    monday=as_of.normalize()-pd.Timedelta(days=as_of.dayofweek)
    for i,district in enumerate(districts.itertuples()):
        choices=boundaries[boundaries.districtID==district.shapeID]
        area=choices.iloc[0]
        for week in range(1,13):
            for j,dept in enumerate(['Land Office','BRTA','Passport Office']):
                amount=[500,2500,7500,15000,35000,75000][(i+j)%6]
                groups=2+(i*3+j*2)%4
                if week==1: groups=max(2,groups+(i%3-1)*2)
                refused=1+(i+j)%2
                for n in range(groups*5):
                    rows.append({'report_id':f'synthetic-{len(rows)}','reported_at':monday-pd.Timedelta(weeks=week)+pd.Timedelta(days=2),
                        'department':dept,'upazila':area.shapeName,'district':area.district,
                        'amount':amount,'outcome':'refused' if n<min(refused,groups)*5 else 'paid'})
        if i==0 and len(choices)>1:
            area=choices.iloc[1]
            for _ in range(2):
                rows.append({'report_id':f'synthetic-{len(rows)}','reported_at':as_of-pd.Timedelta(days=10),
                    'department':'Land Office','upazila':area.shapeName,'district':area.district,'amount':700,'outcome':'paid'})
    cfg=copy.deepcopy(load_config())
    bundle=build_bundle(pd.DataFrame(rows),boundaries,districts,cfg=cfg,as_of=as_of,demo=True,source_label='synthetic reports; real administrative boundaries')
    publish_bundle(bundle,directory,as_of=as_of)

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",type=Path,default=ROOT/"site/data")
    args=parser.parse_args()
    import json
    existing=args.output_dir/"summary.json"
    if existing.exists() and not json.loads(existing.read_text(encoding="utf-8"))["meta"]["demo"]:
        raise SystemExit("Refusing to overwrite live data with demo. Choose a separate --output-dir.")
    logging.basicConfig(level=logging.INFO,format="%(levelname)s %(message)s")
    make_demo(args.output_dir)
