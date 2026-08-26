from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.sources.http import get_json, validate_url, USER_AGENT

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/boundaries/bgd_adm3.geojson"
API = "https://www.geoboundaries.org/api/current/gbOpen/BGD/ADM3/"

def download_geometry(url):
    import requests
    hosts = {"github.com", "raw.githubusercontent.com", "media.githubusercontent.com",
             "release-assets.githubusercontent.com", "objects.githubusercontent.com", "www.geoboundaries.org"}
    for _ in range(5):
        if validate_url(url).hostname not in hosts:
            raise ValueError("Unexpected geoBoundaries download host; review before trusting a new host.")
        with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(10, 120),
                          allow_redirects=False, stream=True) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > 100_000_000:
                    raise ValueError("Boundary download exceeds size limit.")
            return json.loads(data)
    raise ValueError("Too many boundary download redirects.")

def fetch_adm3(force=False):
    if OUT.exists() and not force:
        return OUT
    meta = get_json(API)
    if isinstance(meta, list) and len(meta) == 1:
        meta = meta[0]
    if not isinstance(meta, dict):
        raise ValueError("Invalid geoBoundaries metadata.")
    url = meta.get("simplifiedGeometryGeoJSON") or meta.get("gjDownloadURL")
    if not url:
        raise ValueError("geoBoundaries did not provide a download URL.")
    payload = download_geometry(url)
    if payload.get("type") != "FeatureCollection" or len(payload.get("features", [])) < 400:
        raise ValueError("Incomplete Bangladesh ADM3 boundary collection.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    staged = OUT.with_suffix(".tmp.geojson")
    staged.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    from pipeline.analyze import load_boundaries
    load_boundaries(staged)
    os.replace(staged, OUT)
    provenance = {k: meta.get(k) for k in ("boundaryID", "boundaryName", "boundaryYearRepresented",
                  "boundarySource", "boundaryLicense", "licenseDetail", "licenseSource", "buildDate")}
    OUT.with_suffix(".metadata.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return OUT

if __name__ == "__main__":
    print(fetch_adm3())
