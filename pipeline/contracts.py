"""Public contract validation, independent of GeoPandas (also used by Pages CI)."""
from __future__ import annotations
import json
import math
from pathlib import Path

METRICS = {"report_count", "total_amount", "median_amount", "refusal_rate", "paid_rate",
           "pending_rate", "reports_per_100k", "gi_z", "gi_p", "moran_cluster", "suppressed"}
PROPERTIES = {"shapeID", "shapeName", "shapeType", "demo", "slices"}

def validate(geo, summary):
    if set(geo) - {"type", "schema_version", "data_id", "features"}:
        raise ValueError("Unexpected GeoJSON fields.")
    if geo.get("type") != "FeatureCollection" or not geo.get("features"):
        raise ValueError("Expected a nonempty FeatureCollection.")
    if geo.get("schema_version") != 2 or summary.get("meta", {}).get("schema_version") != 2:
        raise ValueError("Unsupported public schema version.")
    if geo.get("data_id") != summary["meta"].get("data_id"):
        raise ValueError("Mismatched data versions.")
    if set(summary) != {"meta", "departments", "periods", "slice_totals", "global_spatial"}:
        raise ValueError("Unexpected public summary fields.")
    allowed_meta = {"schema_version", "source", "demo", "privacy_k", "report_count", "total_amount",
                    "privacy_policy", "statistics_basis", "boundaries", "data_id", "generated_at"}
    if set(summary["meta"]) - allowed_meta:
        raise ValueError("Unexpected public metadata; raw QA belongs in private logs.")
    k = summary["meta"]["privacy_k"]
    if type(k) is not int or k < 3:
        raise ValueError("Public privacy threshold must be >= 3.")
    if any(not isinstance(d, str) or not d or "|" in d or d == "ALL" for d in summary["departments"]):
        raise ValueError("Invalid department label.")
    keys = {f"{p}|{d}" for p in summary["periods"] for d in ["ALL", *summary["departments"]]}
    if "ALL|ALL" not in keys or keys != set(summary["slice_totals"]):
        raise ValueError("Incomplete summary slice matrix.")
    ids = set()
    counts = dict.fromkeys(keys, 0)
    for feature in geo["features"]:
        if set(feature) != {"type", "geometry", "properties"} or feature["type"] != "Feature":
            raise ValueError("Unexpected feature fields.")
        p = feature["properties"]
        if set(p) != PROPERTIES or p["shapeID"] in ids or p["shapeType"] != "ADM3":
            raise ValueError("Invalid public feature properties/IDs.")
        if not isinstance(p["shapeID"], str) or not p["shapeID"] or not isinstance(p["shapeName"], str):
            raise ValueError("Invalid administrative identity.")
        if p["demo"] is not summary["meta"]["demo"]:
            raise ValueError("Demo/real flags disagree.")
        ids.add(p["shapeID"])
        geometry = feature["geometry"]
        if set(geometry) != {"type", "coordinates"}:
            raise ValueError("Unexpected geometry fields.")
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Individual points are forbidden in public data.")
        def coords(value):
            if isinstance(value, list) and value and isinstance(value[0], (int, float)):
                if len(value) != 2 or not all(math.isfinite(v) for v in value):
                    raise ValueError("Invalid polygon coordinate.")
                if not 87 <= value[0] <= 94 or not 20 <= value[1] <= 28:
                    raise ValueError("Public polygon is outside Bangladesh.")
            elif isinstance(value, (list, tuple)) and value:
                for part in value:
                    coords(part)
            else:
                raise ValueError("Invalid polygon coordinate nesting.")
        # Normalize Shapely tuples to plain GeoJSON arrays.
        coords(json.loads(json.dumps(geometry["coordinates"])))
        from shapely.geometry import shape
        try:
            polygon=shape(geometry)
            if polygon.is_empty or not polygon.is_valid:
                raise ValueError('Invalid public administrative polygon.')
        except (TypeError,IndexError) as exc:
            raise ValueError('Malformed public polygon rings.') from exc
        if set(p["slices"]) != keys:
            raise ValueError("Incomplete feature slice matrix.")
        flags = {m["suppressed"] for m in p["slices"].values()}
        if len(flags) != 1:
            raise ValueError("Mixed suppression permits cross-slice reconstruction.")
        for key, m in p["slices"].items():
            if set(m) != METRICS or type(m["suppressed"]) is not bool:
                raise ValueError("Invalid metric fields.")
            if m["suppressed"]:
                if any(m[field] is not None for field in METRICS - {"suppressed"}):
                    raise ValueError("Suppressed metrics must all be null.")
            else:
                n = m["report_count"]
                if type(n) is not int or n < 0 or 0 < n < k:
                    raise ValueError("Unsuppressed low count.")
                counts[key] += n
                for field in METRICS - {"suppressed", "moran_cluster"}:
                    v = m[field]
                    if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
                        raise ValueError("Non-finite/non-numeric metric.")
                for field in ("paid_rate", "refusal_rate", "pending_rate", "gi_p"):
                    if m[field] is not None and not 0 <= m[field] <= 1:
                        raise ValueError("Rate/p-value out of range.")
    for key, n in counts.items():
        total = summary["slice_totals"][key]
        if set(total) != METRICS or total["report_count"] != n:
            raise ValueError("Summary includes hidden reports.")
        visible = [f["properties"]["slices"][key] for f in geo["features"]
                   if not f["properties"]["slices"][key]["suppressed"]
                   and f["properties"]["slices"][key]["report_count"] > 0]
        for field in ("total_amount", "paid_rate", "refusal_rate", "pending_rate"):
            expected = None
            if visible and all(m[field] is not None for m in visible):
                expected = sum(m[field] if field == "total_amount" else m[field] * m["report_count"] for m in visible)
                if field != "total_amount":
                    expected /= n
            actual = total[field]
            if (expected is None) != (actual is None) or (expected is not None and not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)):
                raise ValueError("Summary reveals hidden amount/outcome metrics or disagrees with areas.")
    if summary["meta"]["report_count"] != counts["ALL|ALL"]:
        raise ValueError("Public metadata count disagrees.")
    if summary["meta"]["total_amount"] != summary["slice_totals"]["ALL|ALL"]["total_amount"]:
        raise ValueError("Public metadata amount disagrees.")
    for key, stat in summary["global_spatial"].items():
        if key not in keys or set(stat) != {"moran_i", "p_sim", "permutations", "basis"}:
            raise ValueError("Unexpected public spatial statistic fields.")
    # JSON must be interoperable, never Python's NaN/Infinity extensions.
    json.dumps([geo, summary], allow_nan=False)
    return True

def validate_directory(directory):
    directory = Path(directory)
    def reject_constant(value):
        raise ValueError(f"Non-standard JSON constant: {value}")
    geo = json.loads((directory / "adm3_metrics.geojson").read_text(encoding="utf-8"), parse_constant=reject_constant)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"), parse_constant=reject_constant)
    if summary.get('meta',{}).get('schema_version') == 3:
        from pipeline.products import JSON_NAMES
        from pipeline.bundle_contracts import validate_bundle
        from pipeline.publication import bundle_id
        bundle={name:json.loads((directory/name).read_text(encoding='utf-8'),parse_constant=reject_constant) for name in JSON_NAMES}
        bundle['weekly_summary.csv']=(directory/'weekly_summary.csv').read_bytes().decode('utf-8')
        validate_bundle(bundle)
        if geo.get('data_id') != bundle_id(bundle):
            raise ValueError('Bundle content hash mismatch.')
        from datetime import datetime
        if datetime.fromisoformat(summary['meta']['generated_at']).tzinfo is None:
            raise ValueError('Publication timestamp must have a timezone.')
        return geo,summary
    validate(geo, summary)
    from datetime import datetime
    stamp = datetime.fromisoformat(summary["meta"]["generated_at"])
    if stamp.tzinfo is None:
        raise ValueError("Publication timestamp must have a timezone.")
    from pipeline.publication import content_id
    if geo.get("data_id") != content_id(geo, summary):
        raise ValueError("Content hash mismatch.")
    return geo, summary

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default=str(Path(__file__).resolve().parents[1] / "site/data"))
    _,summary=validate_directory(parser.parse_args().directory)
    if summary['meta']['schema_version']!=3:
        raise ValueError('The deployed dashboard requires the complete schema-3 bundle.')
    print("Public bundle geometry, privacy, rollup, CSV and content-hash checks passed.")
