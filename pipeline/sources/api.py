"""JSON adapter with explicit completeness and bounded offset pagination."""
from __future__ import annotations
import json
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import pandas as pd
from .http import SourceError, assert_robots_allowed, get_json

CANON = {"report_id", "reported_at", "department", "service", "location", "upazila",
         "district", "division", "amount", "outcome"}

def _dig(obj, path):
    cur = obj
    for part in path.split(".") if path else []:
        if not isinstance(cur, dict) or part not in cur:
            raise SourceError(f"Configured JSON field is missing: {path}")
        cur = cur[part]
    return cur

def page_url(url, params):
    p = urlsplit(url)
    query = dict(parse_qsl(p.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(query), ""))

def load_api(url: str, mapping_path: str | Path, token=None):
    config = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    fields = config.get("fields", {})
    if not fields or set(fields) - CANON or not {"report_id", "reported_at", "department"}.issubset(fields):
        raise SourceError("API mapping needs canonical ID, date and department fields.")
    if not ({"upazila", "location"} & set(fields)):
        raise SourceError("API mapping needs an upazila or location field.")
    assert_robots_allowed(url)
    paging = config.get("pagination", {})
    mode = paging.get("mode")
    if mode not in {"none", "offset"}:
        raise SourceError("Declare pagination.mode as none or offset; never assume a complete first page.")
    if mode == "none" and config.get("complete_snapshot") is not True:
        raise SourceError("Single-response mode requires complete_snapshot=true.")
    size = int(paging.get("page_size", 100))
    max_pages = int(paging.get("max_pages", 1000))
    if not 1 <= size <= 1000 or not 1 <= max_pages <= 1000:
        raise SourceError("Invalid pagination bounds.")
    out, seen, expected, offset = [], set(), None, 0
    for page in range(max_pages):
        request_url = url
        if mode == "offset":
            request_url = page_url(url, {paging.get("offset_param", "offset"): offset,
                                         paging.get("limit_param", "limit"): size})
        assert_robots_allowed(request_url) if page == 0 and request_url != url else None
        payload = get_json(request_url, token=token)
        rows = _dig(payload, config.get("records_path", ""))
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise SourceError("records_path must resolve to a list of objects.")
        if mode == "offset":
            total = _dig(payload, paging.get("total_path", "total"))
            if type(total) is not int or total < 0:
                raise SourceError("Pagination total must be a nonnegative integer.")
            if expected is not None and total != expected:
                raise SourceError("Source changed during pagination; retry at the next scheduled run.")
            expected = total
        for row in rows:
            mapped = {dst: _dig(row, src) for dst, src in fields.items()}
            raw_id = mapped.get("report_id")
            rid = "" if raw_id is None else str(raw_id).strip()
            if not rid or rid in seen:
                raise SourceError("Missing or repeated report ID; refusing incomplete/unstable pagination.")
            seen.add(rid)
            out.append(mapped)
        if mode == "none" or len(out) == expected:
            return pd.DataFrame(out, columns=list(fields))
        if not rows or len(out) > expected:
            raise SourceError("Pagination ended before the declared total.")
        offset += len(rows)
        time.sleep(max(1.0, float(paging.get("delay_seconds", 1))))
    raise SourceError("Pagination limit reached before completion.")
