"""Verified polygon hierarchy; never infer administrative parents from report text."""
from __future__ import annotations
import json
from pathlib import Path
import geopandas as gpd
from pipeline.analyze import load_boundaries, norm_name
from pipeline.fetch_boundaries import fetch_adm3, download_geometry
from pipeline.sources.http import get_json

ROOT = Path(__file__).resolve().parents[1]
DIVISIONS = ('Dhaka', 'Chattogram', 'Rajshahi', 'Khulna', 'Barishal', 'Sylhet', 'Rangpur', 'Mymensingh')
ALIASES = {'chittagong':'Chattogram', 'barisal':'Barishal', 'rajshani':'Rajshahi'}

def division_name(name):
    result = ALIASES.get(norm_name(name), next((d for d in DIVISIONS if norm_name(d)==norm_name(name)), None))
    if result is None:
        raise ValueError('Unrecognized division boundary name.')
    return result

def fetch_level(level, force=False):
    if level == 'ADM3':
        return fetch_adm3(force)
    if level not in {'ADM1', 'ADM2'}:
        raise ValueError('Unsupported administrative level.')
    target = ROOT / f'data/boundaries/bgd_{level.lower()}.geojson'
    if target.exists() and not force:
        return target
    meta = get_json(f'https://www.geoboundaries.org/api/current/gbOpen/BGD/{level}/')
    if not isinstance(meta, dict) or meta.get('boundaryType') != level:
        raise ValueError('Invalid parent boundary metadata.')
    payload = download_geometry(meta.get('simplifiedGeometryGeoJSON') or meta['gjDownloadURL'])
    if len(payload.get('features', [])) != {'ADM1':8,'ADM2':64}[level]:
        raise ValueError('Incomplete Bangladesh administrative coverage.')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_suffix('.tmp.geojson')
    stage.write_text(json.dumps(payload, allow_nan=False), encoding='utf-8')
    load_boundaries(stage)
    stage.replace(target)
    keys = ('boundaryID','boundaryName','boundaryYearRepresented','boundarySource','boundaryLicense','licenseSource','buildDate')
    target.with_suffix('.metadata.json').write_text(json.dumps({k:meta.get(k) for k in keys}), encoding='utf-8')
    return target

def parent_ids(children, parents, minimum_overlap=.95):
    """Maximum projected intersection, with a coverage threshold and ambiguity check."""
    child = children.to_crs(6933)
    parent = parents.to_crs(6933)
    result = {}
    for row in child.itertuples():
        candidates = list(parent.sindex.query(row.geometry, predicate='intersects'))
        overlaps = sorted(((row.geometry.intersection(parent.iloc[i].geometry).area / row.geometry.area,
                            parent.iloc[i].shapeID) for i in candidates), reverse=True)
        if not overlaps or overlaps[0][0] < minimum_overlap or (len(overlaps)>1 and overlaps[1][0]>.1):
            raise ValueError('Administrative parent overlap is insufficient or ambiguous; review boundary vintages.')
        result[row.shapeID] = overlaps[0][1]
    return result

def load_hierarchy(adm3=None, adm2=None, force=False):
    upazilas = load_boundaries(adm3 or fetch_level('ADM3', force))
    districts = load_boundaries(adm2 or fetch_level('ADM2', force))
    crosswalk = json.loads((ROOT / 'config/district_divisions.json').read_text(encoding='utf-8'))
    membership = {district:division for division, names in crosswalk['divisions'].items() for district in names}
    if (len(districts)!=64 or len(membership)!=64 or set(membership)!=set(districts.shapeName)
            or set(crosswalk['divisions'])!=set(DIVISIONS)
            or districts.attrs['boundary_metadata'].get('boundaryID')!=crosswalk['boundary_id']):
        raise ValueError('District crosswalk does not match the boundary version; review before publishing.')
    u_to_d = parent_ids(upazilas, districts, .95)
    districts['division'] = districts.shapeName.map(membership)
    district_names = districts.set_index('shapeID').shapeName.to_dict()
    district_divisions = districts.set_index('shapeID').division.to_dict()
    upazilas['districtID'] = upazilas.shapeID.map(u_to_d)
    upazilas['district'] = upazilas.districtID.map(district_names)
    upazilas['division'] = upazilas.districtID.map(district_divisions)
    return upazilas, districts
