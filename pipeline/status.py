"""Add a deployment heartbeat without a timestamp-only Git commit."""
import json
from pathlib import Path
from pipeline.contracts import validate_directory

def main():
    directory = Path(__file__).resolve().parents[1] / "site/data"
    geo, summary = validate_directory(directory)
    target = directory / "refresh.json"
    if not target.exists():
        target.write_text(json.dumps({"status":"snapshot", "data_id":geo["data_id"],
            "checked_at":summary["meta"]["generated_at"]})+"\n",encoding="utf-8")

if __name__ == "__main__":
    main()
