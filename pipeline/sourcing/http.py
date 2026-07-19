"""
One shared HTTP client.

SEC's fair-access policy caps automated traffic at 10 requests/second and
requires a User-Agent that identifies who is asking. We stay well under the
cap and always identify ourselves. The job-board APIs are unauthenticated
and public, but they get the same politeness.
"""

from __future__ import annotations

import os
import time

import requests

_MIN_INTERVAL = 0.2  # seconds between requests; 5/s, half SEC's cap
_last_request = 0.0


def make_session(cfg: dict) -> requests.Session:
    ua = cfg["user_agent"]
    s = requests.Session()
    s.headers["User-Agent"] = f"{ua['name']} {ua['email']}"
    # Managed environments re-terminate TLS; honor their CA bundle if set.
    bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if bundle and os.path.exists(bundle):
        s.verify = bundle
    return s


def get(session: requests.Session, url: str, *, timeout: int = 30) -> requests.Response | None:
    """Rate-limited GET. Returns None on 404 (a normal miss when probing
    job-board tokens); raises on transport errors after 3 attempts."""
    global _last_request
    for attempt in range(3):
        wait = _MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            resp = session.get(url, timeout=timeout)
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2 ** (attempt + 1))
            continue
        resp.raise_for_status()
        return resp
    return None
