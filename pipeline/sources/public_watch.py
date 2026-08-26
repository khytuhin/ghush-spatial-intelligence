"""Daily owner-safe watch for newly exposed, robots-allowed export links.

This module does NOT call Ghush API candidates, does not launch a browser, does
not fetch report payloads, and does not bypass robots, authentication, rate
limits, anti-bot controls, or alternate backends. It only inspects the allowed
public homepage and same-origin public scripts for literal candidate export URLs,
then checks robots permission for the candidate PATH without requesting it.

It is deliberately a source-availability monitor, not a live-data connector.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from pipeline.sources.http import assert_robots_allowed, get_bytes

ROOT_URL = "https://www.ghush.site/"
EXPORT_RE = re.compile(
    r"(?P<url>(?:https?://[^\"'\s<>]+|/[^\"'\s<>]+)"
    r"(?:\.csv(?:\?[^\"'\s<>]*)?|\.json(?:\?[^\"'\s<>]*)?|"
    r"/export(?:/[^\"'\s<>]*)?|/download(?:/[^\"'\s<>]*)?))",
    re.IGNORECASE,
)


class PublicAssets(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            src = dict(attrs).get("src")
            if src:
                self.scripts.append(src)


def _same_origin(root: str, candidate: str) -> bool:
    return urlsplit(root).netloc == urlsplit(candidate).netloc


def _candidate_urls(text: str, root: str) -> set[str]:
    found: set[str] = set()
    for match in EXPORT_RE.finditer(text):
        raw = match.group("url")
        url = urljoin(root, raw)
        if _same_origin(root, url):
            found.add(url.split("#", 1)[0])
    return found


def watch(root: str = ROOT_URL) -> dict:
    assert_robots_allowed(root)
    html = get_bytes(root, accept="text/html").decode("utf-8", errors="replace")
    parser = PublicAssets()
    parser.feed(html)

    candidates = _candidate_urls(html, root)
    inspected_assets = 0
    for src in parser.scripts[:20]:
        script_url = urljoin(root, src)
        if not _same_origin(root, script_url):
            continue
        try:
            assert_robots_allowed(script_url)
            body = get_bytes(script_url, accept="text/javascript").decode("utf-8", errors="replace")
        except Exception:
            continue
        inspected_assets += 1
        candidates.update(_candidate_urls(body, root))

    allowed: list[str] = []
    blocked: list[str] = []
    for url in sorted(candidates):
        try:
            # Permission check only. The candidate export itself is NOT requested.
            assert_robots_allowed(url)
            allowed.append(url)
        except Exception:
            blocked.append(url)

    result = {
        "status": "candidate_export_available" if allowed else "no_allowed_export_discovered",
        "page": root,
        "same_origin_public_assets_inspected": inspected_assets,
        "allowed_candidate_paths": [urlsplit(u).path for u in allowed],
        "blocked_candidate_paths": [urlsplit(u).path for u in blocked],
        "notice": (
            "No candidate payload was requested. An allowed path is only a discovery signal, "
            "not permission to republish or proof that it contains a complete report export."
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    watch()
