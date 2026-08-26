from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))
from pipeline.products import build_bundle
from pipeline.geography import load_hierarchy
from pipeline.publication import publish_bundle
from pipeline.logging_utils import counts
from pipeline.sources.api import load_api
from pipeline.sources.csv_feed import load_csv_feed
from pipeline.sources.snapshot import load_snapshot

def main(argv=None):
    parser = argparse.ArgumentParser(description="Build validated privacy-safe public GIS artifacts.")
    parser.add_argument("--source", choices=["snapshot", "api", "csv"], required=True)
    parser.add_argument("--input", type=Path, default=ROOT / "data/raw/ghush_snapshot.csv")
    parser.add_argument("--api-url", default=os.getenv("GHUSH_API_URL"))
    parser.add_argument("--api-mapping", type=Path, default=ROOT / "config/api_mapping.json")
    parser.add_argument("--csv-url", default=os.getenv("GHUSH_CSV_URL"))
    parser.add_argument("--boundaries", type=Path)
    parser.add_argument("--district-boundaries", type=Path)
    parser.add_argument("--force-boundaries", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "site/data")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.source != "snapshot" and os.getenv("GHUSH_AUTOMATION_APPROVED", "").lower() != "true":
            raise ValueError("Confirm automated access and public reuse permission, then set GHUSH_AUTOMATION_APPROVED=true.")
        if args.source == "snapshot":
            reports = load_snapshot(args.input)
        elif args.source == "api":
            if not args.api_url:
                raise ValueError("Set GHUSH_API_URL to the approved endpoint.")
            reports = load_api(args.api_url, args.api_mapping, os.getenv("GHUSH_API_TOKEN"))
        else:
            if not args.csv_url:
                raise ValueError("Set GHUSH_CSV_URL to an approved complete CSV export.")
            reports = load_csv_feed(args.csv_url, os.getenv("GHUSH_API_TOKEN"))
        counts(fetched=len(reports))
        logging.info("source=%s", args.source)
        boundaries,districts = load_hierarchy(args.boundaries,args.district_boundaries,force=args.force_boundaries)
        is_example = args.source == "snapshot" and ".example." in args.input.name
        bundle = build_bundle(reports, boundaries, districts,
                                      source_label="synthetic example" if is_example else f"approved {args.source}",
                                      demo=is_example)
        changed = publish_bundle(bundle, args.output_dir)
        # Operational heartbeat is deployed, but deliberately not committed.
        status = {"checked_at": datetime.now(timezone.utc).isoformat(),
                  "data_id": bundle['summary.json']['meta']['data_id'], "status": "ok"}
        (args.output_dir / "refresh.json").write_text(json.dumps(status) + "\n", encoding="utf-8")
        logging.info("refresh=success changed=%s", str(changed).lower())
        return 0
    except Exception as exc:
        # Known validation errors never contain raw rows, URLs or tokens.
        if isinstance(exc, (ValueError, RuntimeError, FileNotFoundError)):
            logging.error("refresh=failed %s", str(exc))
        else:
            logging.error("refresh=failed error_type=%s; inspect locally, previous publication retained.", type(exc).__name__)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
