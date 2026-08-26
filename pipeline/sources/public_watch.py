"""Daily owner-safe watch for newly exposed, robots-allowed export links.

This module does NOT call Ghush API candidates, does not launch a browser, does
not fetch report payloads, and does not bypass robots, authentication, rate
limits, anti-bot controls, or alternate backends. It only inspects the allowed
public homepage and a small bounded set of same-origin JavaScript assets for
literal candidate export URLs, then checks candidate paths against one cached
robots policy without requesting those candidate payloads.

It is deliberately a source-availability monitor, not a live-data connector.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from protego import Protego

from pipeline.sources.http import SourceError, USER_AGENT, get_bytes, validate_url

ROOT_URL = "https://www.ghush.site/"
MAX_SCRIPT_ASSETS = 12
MAX_CANDIDATES = 64
EXPORT_RE = re.compile(
    r"(?P<url>(?:https?://[^\"'\s<>]+|/[^\"'\s<>]+)"
    r"(?:\.csv(?:\?[^\"'\s<>]*)?|\.json(?:\?[^\"'\s<>]*)?|"
    r"/(?:export|download)(?=$|[/?#])(?:/[^\"'\s<>]*)?))",
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


def _has_export_segment(path: str) -> bool:
    segments = [segment for segment in path.lower().split("/") if segment]
    return any(segment in {"export", "download"} for segment in segments)


def _looks_like_candidate(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith((".csv", ".json")) or _has_export_segment(path)


def _is_javascript_asset(url: str) -> bool:
    """Fail closed: only fetch conventional same-origin JS asset paths."""
    path = urlsplit(url).path.lower()
    return path.endswith((".js", ".mjs"))


def _candidate_urls(text: str, root: str, limit: int = MAX_CANDIDATES) -> set[str]:
    found: set[str] = set()
    if limit <= 0:
        return found
    for match in EXPORT_RE.finditer(text):
        raw = match.group("url")
        url = urljoin(root, raw).split("#", 1)[0]
        if _same_origin(root, url) and _looks_like_candidate(url):
            found.add(url)
            if len(found) >= limit:
                break
    return found


def _robots_policy(root: str) -> Protego:
    p = validate_url(root)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    body = get_bytes(robots_url, accept="text/plain", attempts=1).decode("utf-8-sig")
    if "user-agent:" not in body.lower():
        raise SourceError("No readable robots policy; obtain a documented export route.")
    return Protego.parse(body)


def _require_allowed(policy: Protego, url: str) -> None:
    validate_url(url)
    if not policy.can_fetch(url, USER_AGENT):
        raise SourceError(
            "robots.txt disallows this route. Request an allowed owner-provided export; do not bypass it."
        )


def watch(root: str = ROOT_URL) -> dict:
    policy = _robots_policy(root)
    _require_allowed(policy, root)
    html = get_bytes(root, accept="text/html", attempts=1).decode("utf-8", errors="replace")
    parser = PublicAssets()
    parser.feed(html)

    candidates = _candidate_urls(html, root)
    inspected_assets = 0
    skipped_payload_like_scripts = 0

    # Only successfully inspectable same-origin JavaScript assets consume the
    # request budget. Cross-origin, non-JS, and payload-like script tags do not.
    for src in parser.scripts:
        if len(candidates) >= MAX_CANDIDATES or inspected_assets >= MAX_SCRIPT_ASSETS:
            break

        script_url = urljoin(root, src).split("#", 1)[0]
        if not _same_origin(root, script_url):
            continue

        # A script tag can point at JSONP/config/export resources. Never fetch it
        # when it is payload-like; record it only for cached robots classification.
        if _looks_like_candidate(script_url):
            if len(candidates) < MAX_CANDIDATES:
                candidates.add(script_url)
            skipped_payload_like_scripts += 1
            continue
        if not _is_javascript_asset(script_url):
            continue

        try:
            _require_allowed(policy, script_url)
            body = get_bytes(script_url, accept="text/javascript", attempts=1).decode(
                "utf-8", errors="replace"
            )
        except Exception:
            continue

        inspected_assets += 1
        remaining = MAX_CANDIDATES - len(candidates)
        candidates.update(_candidate_urls(body, root, remaining))

    # Bound deterministically even if homepage/script candidates overlap oddly.
    candidates = set(sorted(candidates)[:MAX_CANDIDATES])

    allowed: list[str] = []
    blocked: list[str] = []
    for url in sorted(candidates):
        try:
            # Cached robots-policy check only. The candidate itself is NOT requested.
            _require_allowed(policy, url)
            allowed.append(url)
        except Exception:
            blocked.append(url)

    result = {
        "status": "candidate_export_available" if allowed else "no_allowed_export_discovered",
        "page": root,
        "same_origin_javascript_assets_inspected": inspected_assets,
        "payload_like_script_urls_not_fetched": skipped_payload_like_scripts,
        "script_asset_limit": MAX_SCRIPT_ASSETS,
        "candidate_limit": MAX_CANDIDATES,
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
