"""Conservative, bounded HTTP transport. No credentials or response bodies in errors."""
from __future__ import annotations
import json
import time
from urllib.parse import urlsplit
from protego import Protego
import requests

USER_AGENT = "GhushSpatialIntelligence/1.0 (+public aggregate research)"
MAX_BYTES = 50_000_000

class SourceError(RuntimeError):
    pass

def validate_url(url):
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.fragment:
        raise SourceError("Source URL must be HTTPS without embedded credentials or a fragment.")
    if p.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise SourceError("Remote source must not point to localhost.")
    return p

def get_bytes(url, *, token=None, session=None, accept="application/json", attempts=3):
    validate_url(url)
    session = session or requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(attempts):
        try:
            with session.get(url, headers=headers, timeout=(10, 60), stream=True,
                             allow_redirects=False) as response:
                status = response.status_code
                if status in {401, 403, 429}:
                    raise SourceError(f"Source returned HTTP {status}; stopped. No bypass or rate-limit retries.")
                if status in {500, 502, 503, 504} and attempt + 1 < attempts:
                    if response.headers.get("Retry-After"):
                        raise SourceError("Source requested a deferred retry; wait until a later run.")
                    time.sleep(2 ** attempt)
                    continue
                if status != 200:
                    raise SourceError(f"Source returned HTTP {status}; redirects require explicit configuration.")
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise SourceError("Source response exceeded the size limit.")
                    chunks.append(chunk)
                return b"".join(chunks)
        except requests.RequestException:
            if attempt + 1 == attempts:
                raise SourceError("Source network/TLS request failed; previous publication preserved.") from None
            time.sleep(2 ** attempt)
    raise SourceError("Source unavailable.")

def get_json(url, **kwargs):
    try:
        return json.loads(get_bytes(url, **kwargs))
    except (ValueError, UnicodeError):
        raise SourceError("Source did not return valid JSON.") from None

def assert_robots_allowed(url, *, session=None):
    p = validate_url(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    # Missing, inaccessible, or malformed robots policy fails closed.
    body = get_bytes(robots_url, session=session, accept="text/plain").decode("utf-8-sig")
    if "user-agent:" not in body.lower():
        raise SourceError("No readable robots policy; obtain a documented export route.")
    policy = Protego.parse(body)
    if not policy.can_fetch(url, USER_AGENT):
        raise SourceError("robots.txt disallows this route. Request an allowed owner-provided export; do not bypass it.")
