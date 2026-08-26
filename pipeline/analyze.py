from __future__ import annotations
import json
import logging
import math
import re
import unicodedata
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import mapping
from pipeline.logging_utils import counts

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger(__name__)
CANON = ["report_id", "reported_at", "department", "service", "location", "upazila",
         "district", "division", "amount", "outcome"]
NUMERIC = ["report_count", "total_amount", "median_amount", "refusal_rate", "paid_rate",
           "pending_rate", "reports_per_100k", "gi_z", "gi_p"]

def load_config():
    cfg = json.loads((ROOT / "config/project.json").read_text(encoding="utf-8"))
    if cfg["privacy"].get("suppress_low_counts") is not True or cfg["privacy"]["minimum_public_reports"] < 3:
        raise ValueError("Public suppression is mandatory with k >= 3.")
    if any(type(d) is not int or d <= 0 for d in cfg.get("periods", {}).values()):
        raise ValueError("Periods must be positive integer day windows.")
    return cfg

def text(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()

def norm_name(value):
    value = unicodedata.normalize("NFKC", text(value)).casefold()
    # Sadar is a meaningful part of a place name, not a removable suffix.
    value = re.sub(r"\b(upazila|upazilla|upa-zila|thana)\b", " ", value)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\u0980-\u09ff]+", " ", value)).strip()

def parse_amount(value):
    raw = text(value).translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))
    raw = re.sub(r"(?i)^(BDT|TK\.?|টাকা|৳)\s*|\s*(BDT|TK\.?|টাকা|৳)$", "", raw).strip()
    # Accept conventional international or South Asian grouping, never guess
    # decimal commas or malformed repeated separators.
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(\.\d{1,2})?", raw):
        return np.nan
    result = float(raw.replace(',', ''))
    return result if math.isfinite(result) and 0 <= result <= 1e12 else np.nan

def normalize_outcome(value):
    raw = norm_name(value)
    values = {"paid": "paid", "পরিশোধিত": "paid", "পরিশোধ": "paid",
              "refused": "refused", "rejected": "refused", "প্রত্যাখ্যাত": "refused",
              "pending": "pending", "demand pending": "pending", "দাবি মুলতুবি": "pending"}
    return values.get(raw, "unknown")

def normalize_reports(df, cfg=None):
    cfg = cfg or load_config()
    if df.empty:
        raise ValueError("Source returned no reports; refusing to replace published data.")
    if "report_id" not in df or not ({"upazila", "location"} & set(df.columns)):
        raise ValueError("Reports require stable report_id and an upazila/location field.")
    df = df.reindex(columns=CANON).copy()
    df["report_id"] = df["report_id"].map(text)
    if (df["report_id"] == "").any():
        raise ValueError("Missing report IDs; cannot safely deduplicate.")
    duplicates = int(df["report_id"].duplicated().sum())
    # Identical duplicate IDs are safe to deduplicate; conflicting copies fail.
    if df[df["report_id"].duplicated(keep=False)].groupby("report_id").nunique(dropna=False).gt(1).any().any():
        raise ValueError("Conflicting copies of a report ID.")
    df = df.drop_duplicates("report_id").sort_values("report_id").reset_index(drop=True)
    df["reported_at"] = pd.to_datetime(df["reported_at"], utc=True, errors="coerce", format="mixed")
    df["amount"] = df["amount"].map(parse_amount)
    allowed = {norm_name(d): d for d in cfg["departments"]}
    aliases = {norm_name(k): v for k, v in cfg.get("department_aliases", {}).items()}
    df["department"] = df["department"].map(lambda v: aliases.get(norm_name(v), allowed.get(norm_name(v), "Other public service")))
    df["outcome"] = df["outcome"].map(normalize_outcome)
    counts(normalized=len(df), duplicates_removed=duplicates,
           invalid_dates=int(df.reported_at.isna().sum()), unknown_amounts=int(df.amount.isna().sum()))
    return df

def load_boundaries(path):
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError("Boundary CRS is missing.")
    gdf = gdf.to_crs(4326)
    if not {"shapeID", "shapeName"}.issubset(gdf.columns):
        raise ValueError("Boundaries require stable shapeID and shapeName fields.")
    gdf["shapeID"] = gdf.shapeID.map(text)
    if gdf.empty or gdf.shapeID.duplicated().any() or (gdf.shapeID == "").any():
        raise ValueError("Empty/duplicate boundary IDs.")
    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any() or not gdf.geometry.is_valid.all():
        raise ValueError("Invalid or empty administrative geometry.")
    if not gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Only administrative polygon geometry is allowed.")
    bounds = gdf.total_bounds
    if bounds[0] < 87 or bounds[2] > 94 or bounds[1] < 20 or bounds[3] > 28:
        raise ValueError("Boundary extent is not Bangladesh.")
    gdf = gdf.sort_values("shapeID").reset_index(drop=True)
    metadata_path = Path(path).with_suffix(".metadata.json")
    gdf.attrs["boundary_metadata"] = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    return gdf

def match_reports_to_adm3(df, gdf, cutoff=95, overrides=None, allow_fuzzy=False):
    from rapidfuzz import fuzz, process
    if overrides is None:
        overrides = json.loads((ROOT / "config/location_overrides.json").read_text(encoding="utf-8"))
    overrides = {norm_name(k): v for k, v in overrides.items() if not k.startswith("_")}
    choices = {}
    for row in gdf.itertuples():
        choices.setdefault(norm_name(row.shapeName), []).append(row.shapeID)
    by_id = gdf.set_index("shapeID")
    ids, methods = [], []
    for row in df.itertuples():
        query = norm_name(text(row.upazila) or text(row.location).split(",")[0])
        target = overrides.get(query)
        if target in by_id.index:
            ids.append(target); methods.append("override"); continue
        query = norm_name(target) if target else query
        hits = choices.get(query, [])
        # Disambiguate only using explicit district metadata when available.
        if len(hits) > 1 and "district" in gdf:
            hits = [sid for sid in hits if norm_name(by_id.loc[sid, "district"]) == norm_name(row.district)]
        method = "exact"
        if not hits and allow_fuzzy and query:
            best = process.extract(query, list(choices), scorer=fuzz.ratio, limit=2)
            if best and best[0][1] >= cutoff and (len(best) == 1 or best[0][1] - best[1][1] >= 8):
                hits, method = choices[best[0][0]], "fuzzy"
        ids.append(hits[0] if len(hits) == 1 else None)
        methods.append(method if len(hits) == 1 else "unmatched")
    result = df.copy()
    result["shapeID"], result["match_method"] = ids, methods
    return result

def metric_row(rows, *, amount_allowed=True, outcome_allowed=True):
    n = len(rows)
    amounts = rows.amount.dropna()
    return {"report_count": n,
            "total_amount": round(float(amounts.sum()), 2) if n and len(amounts) and amount_allowed else None,
            "median_amount": float(amounts.median()) if n and len(amounts) and amount_allowed else None,
            "refusal_rate": float((rows.outcome == "refused").mean()) if n and outcome_allowed else None,
            "paid_rate": float((rows.outcome == "paid").mean()) if n and outcome_allowed else None,
            "pending_rate": float((rows.outcome == "pending").mean()) if n and outcome_allowed else None,
            "reports_per_100k": None, "gi_z": None, "gi_p": None, "moran_cluster": None, "suppressed": False}

def suppressed_metrics():
    return {**{key: None for key in NUMERIC}, "moran_cluster": None, "suppressed": True}

def period_mask(df, days, as_of=None):
    if days is None:
        return pd.Series(True, index=df.index)
    as_of = as_of or pd.Timestamp.now(tz="UTC")
    return df.reported_at.notna() & (df.reported_at > as_of - pd.Timedelta(days=days)) & (df.reported_at <= as_of)

def load_population(gdf):
    path = ROOT / "data/reference/population_adm3.csv"
    if not path.exists():
        return {}
    pop = pd.read_csv(path, dtype={"shapeID": str})
    if not {"shapeID", "population", "source", "boundary_id"}.issubset(pop):
        raise ValueError("Population needs shapeID,population,source,boundary_id; name-only joins are unsafe.")
    if pop.shapeID.duplicated().any() or not set(pop.shapeID).issubset(set(gdf.shapeID)):
        raise ValueError("Population has duplicate or unknown shapeIDs.")
    meta = gdf.attrs.get("boundary_metadata", {})
    if not meta.get("boundaryID") or not pop.boundary_id.eq(meta["boundaryID"]).all():
        raise ValueError("Population boundary vintage does not match.")
    if pop.source.isna().any() or (pop.source.astype(str).str.strip() == "").any():
        raise ValueError("Population source citation is required.")
    values = pd.to_numeric(pop.population, errors="raise")
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Invalid population values.")
    gdf.attrs['population_metadata']={'sources':sorted(set(pop.source.astype(str))), 'boundary_id':meta['boundaryID']}
    return dict(zip(pop.shapeID, values))

def privacy_sets(rows, periods, k, as_of):
    data = rows.copy()
    # Each displayed time window is a union of disjoint bins. Suppress an
    # entire area if any department x time-bin is rare, including unknown dates.
    age = (as_of - data.reported_at).dt.total_seconds() / 86400
    edges = sorted(set(periods.values()))
    data["_bin"] = age.map(lambda a: -1 if pd.isna(a) else sum(a >= d for d in edges))
    data["_week"] = (data.reported_at.dt.normalize() - pd.to_timedelta(data.reported_at.dt.dayofweek, unit="D")).dt.strftime("%Y-%m-%d").fillna("unknown")
    hidden, no_amounts, no_outcomes = set(), set(), set()
    # Week and rolling-window intersections share a single release population.
    # A small weekly cell cannot be recovered by subtracting either time view.
    for (sid, _, _, _), group in data.groupby(["shapeID", "department", "_bin", "_week"]):
        if len(group) < k:
            hidden.add(sid)
        if group.amount.notna().sum() < k:
            no_amounts.add(sid)
        if any(0 < count < k for count in group.outcome.value_counts()):
            no_outcomes.add(sid)
        for _, band in group.groupby(pd.cut(group.amount, [-1,999.999,4999.999,9999.999,24999.999,49999.999,float('inf')], labels=False), dropna=False):
            if any(0 < count < k for count in band.outcome.value_counts()):
                no_outcomes.add(sid)
    return hidden, no_amounts, no_outcomes

def add_spatial_statistics(gdf, metrics, permutations, min_reports):
    # Only public counts enter public statistics: hidden counts cannot leak
    # through a neighbouring area's Gi* score or a global statistic.
    visible = gdf[gdf.shapeID.map(lambda sid: not metrics[sid]["suppressed"])].copy()
    y = np.array([metrics[sid]["report_count"] for sid in visible.shapeID], dtype=float)
    if len(y) < 4 or y.sum() < min_reports or np.allclose(y, y[0]):
        return None
    from libpysal.weights import Queen
    from esda.getisord import G_Local
    from esda.moran import Moran, Moran_Local
    w = Queen.from_dataframe(visible, ids=visible.shapeID.tolist(), silence_warnings=True)
    if not any(w.cardinalities.values()):
        LOG.info("spatial_skipped=no_contiguous_neighbours")
        return None
    w.transform = "R"
    old_rng = np.random.get_state()
    try:
        np.random.seed(42)
        gm = Moran(y, w, permutations=permutations)
        gi_weights = Queen.from_dataframe(visible, ids=visible.shapeID.tolist(), silence_warnings=True)
        gi_weights.transform = "B"
        with np.errstate(divide="ignore", invalid="ignore"):
            gl = G_Local(y, gi_weights, transform="R", star=True, permutations=permutations,
                         seed=42, n_jobs=1, alternative="two-sided")
            ml = Moran_Local(y, w, permutations=permutations, seed=42, n_jobs=1, alternative="two-sided")
    finally:
        np.random.set_state(old_rng)
    labels = {1: "High–High", 2: "Low–High", 3: "Low–Low", 4: "High–Low"}
    for i, sid in enumerate(visible.shapeID):
        if sid in w.islands:
            continue
        metrics[sid]["gi_z"] = float(gl.Zs[i]) if np.isfinite(gl.Zs[i]) else None
        metrics[sid]["gi_p"] = float(gl.p_sim[i]) if permutations and np.isfinite(gl.p_sim[i]) else None
        metrics[sid]["moran_cluster"] = labels[int(ml.q[i])] if permutations and ml.p_sim[i] <= .05 else None
    return {"moran_i": float(gm.I), "p_sim": float(gm.p_sim), "permutations": permutations,
            "basis": "published counts only; exploratory, no multiple-testing correction"}

def build_products(reports, gdf, out_geojson=None, out_summary=None, source_label="approved source",
                   *, cfg=None, as_of=None, demo=False):
    cfg, as_of = cfg or load_config(), as_of or pd.Timestamp.now(tz="UTC")
    fetched = len(reports)
    reports = normalize_reports(reports, cfg)
    if (reports.reported_at > as_of).any():
        raise ValueError("Source has future-dated reports; verify timestamps.")
    reports = match_reports_to_adm3(reports, gdf, cutoff=cfg["matching"]["fuzzy_cutoff"],
                                    allow_fuzzy=cfg["matching"].get("allow_fuzzy", False))
    matched = reports[reports.shapeID.notna()].copy()
    if matched.empty or len(matched) / len(reports) < cfg.get("quality", {}).get("minimum_match_rate", .8):
        raise ValueError("Too few unambiguous ADM3 matches; review mappings locally. Publication unchanged.")
    k = int(cfg["privacy"]["minimum_public_reports"])
    periods = {"ALL": None, **cfg.get("periods", {})}
    hidden, no_amounts, no_outcomes = privacy_sets(matched, cfg.get("periods", {}), k, as_of)
    population = load_population(gdf)
    # Only canonical configured labels are public, never arbitrary source text.
    depts = sorted(set(matched.loc[~matched.shapeID.isin(hidden), 'department']))
    all_slices = {sid: {} for sid in gdf.shapeID}
    totals, spatial = {}, {}
    for period, days in periods.items():
        for dept in ["ALL", *depts]:
            key = f"{period}|{dept}"
            sub = matched[period_mask(matched, days, as_of)]
            if dept != "ALL":
                sub = sub[sub.department == dept]
            by_id = {}
            for sid in gdf.shapeID:
                group = sub[sub.shapeID == sid]
                m = suppressed_metrics() if sid in hidden else metric_row(
                    group, amount_allowed=sid not in no_amounts, outcome_allowed=sid not in no_outcomes)
                if not m["suppressed"] and sid in population:
                    m["reports_per_100k"] = m["report_count"] / population[sid] * 100_000
                by_id[sid] = m
                all_slices[sid][key] = m
            if cfg["statistics"]["enabled"]:
                stat = add_spatial_statistics(gdf, by_id, cfg["statistics"]["live_permutations"],
                                               cfg["statistics"]["minimum_reports_for_spatial_test"])
                if stat:
                    spatial[key] = stat
            public_rows = sub[~sub.shapeID.isin(hidden)]
            # A summary is derived only from visible areas. Do not fill an
            # amount/outcome hidden in an area via the national KPI.
            visible_metrics = [m for m in by_id.values() if not m["suppressed"] and m["report_count"]]
            total = metric_row(public_rows,
                amount_allowed=all(m["total_amount"] is not None for m in visible_metrics),
                outcome_allowed=all(m["refusal_rate"] is not None for m in visible_metrics))
            totals[key] = total
    features = [{"type": "Feature", "geometry": mapping(r.geometry),
                 "properties": {"shapeID": r.shapeID, "shapeName": r.shapeName,
                                "shapeType": "ADM3", "demo": demo, "slices": all_slices[r.shapeID]}}
                for r in gdf.itertuples()]
    geo = {"type": "FeatureCollection", "schema_version": 2, "features": features}
    summary = {"meta": {"schema_version": 2, "source": source_label, "demo": demo, "privacy_k": k,
                       "report_count": totals["ALL|ALL"]["report_count"],
                       "total_amount": totals["ALL|ALL"]["total_amount"],
                       "privacy_policy": "whole-area suppression across disjoint department/time cells",
                       "statistics_basis": "published counts only"},
               "departments": depts, "periods": list(periods), "slice_totals": totals, "global_spatial": spatial}
    provenance = gdf.attrs.get("boundary_metadata")
    if not demo and provenance:
        summary["meta"]["boundaries"] = provenance
    hidden_reports = int(matched.shapeID.isin(hidden).sum())
    counts(fetched=fetched, normalized=len(reports), matched=len(matched),
           unmatched=len(reports)-len(matched), suppressed=hidden_reports,
           published=len(matched)-hidden_reports, suppressed_areas=len(hidden))
    if out_geojson is not None and out_summary is not None:
        from pipeline.publication import publish
        publish(geo, summary, Path(out_geojson).parent, as_of=as_of)
    return geo, summary
