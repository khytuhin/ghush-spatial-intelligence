from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]

def test_workflows_and_no_token_retrigger_dependency():
    for path in (ROOT/".github/workflows").glob("*.yml"):
        workflow=yaml.safe_load(path.read_text())
        assert workflow["jobs"]
    release=yaml.safe_load((ROOT/".github/workflows/refresh-data.yml").read_text())
    # YAML 1.1 treats the key 'on' as True; GitHub uses YAML 1.2.
    events=release.get("on",release.get(True))
    assert events["schedule"][0]["cron"]=="17 */12 * * *"
    assert release["concurrency"]["cancel-in-progress"] is False
    assert release["jobs"]["deploy"]["needs"]=="build"
    assert release["jobs"]["deploy"]["permissions"]=={"pages":"write","id-token":"write"}
    text=(ROOT/".github/workflows/refresh-data.yml").read_text()
    assert "git diff --cached --quiet" in text
    assert "path: site" in text
    assert "continue-on-error" not in text

def test_public_directory_has_no_raw_data():
    public=list((ROOT/"site").rglob("*"))
    assert not any(p.suffix in {".jsonl",".py"} for p in public)
    assert {p.relative_to(ROOT/'site').as_posix() for p in public if p.suffix=='.csv'}=={'data/weekly_summary.csv'}
    assert not any(p.name==".env" for p in public)
