"""Inspect allowed public HTML/scripts; record endpoint paths, never report payloads.

No browser is launched, no discovered endpoint is called, and no credentials or
query strings are retained. This is discovery only, not permission to ingest.
Run: python -m pipeline.sources.ghush_discovery
"""
from __future__ import annotations
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.sources.http import assert_robots_allowed, get_bytes

ROOT = Path(__file__).resolve().parents[2]

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
    def handle_starttag(self, tag, attrs):
        if tag == "script":
            src = dict(attrs).get("src")
            if src:
                self.paths.append(src)

def discover(url="https://www.ghush.site/"):
    assert_robots_allowed(url)
    parser = Scripts()
    parser.feed(get_bytes(url, accept="text/html").decode("utf-8"))
    paths = set()
    for src in parser.paths[:20]:
        script_url = urljoin(url, src)
        if urlsplit(script_url).netloc != urlsplit(url).netloc:
            continue
        assert_robots_allowed(script_url)
        body = get_bytes(script_url, accept="text/javascript").decode("utf-8")
        for match in re.finditer(r'/api/[A-Za-z0-9_/-]+', body):
            paths.add(match.group())
    result = {"page": url, "candidate_paths": sorted(paths),
              "notice": "Candidates from public client code only; not called or verified. Check permission and robots before use."}
    out = ROOT / "data/debug/ghush_json_candidates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Found {len(paths)} candidate paths; saved metadata only, no raw responses.")
    return result

if __name__ == "__main__":
    discover()
