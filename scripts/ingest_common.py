"""Shared helpers for the network ingesters (social, Wayback preservation).

Stdlib-only (``urllib``). Provides a polite, throttled JSON/GET fetcher with
exponential backoff on 429/5xx and a delay between calls, so the ingesters obey
the project's ingestion guidance (throttle, be idempotent, preserve provenance).

These scripts run where outbound network access is available — e.g. GitHub
Actions runners — NOT the agent/CI sandbox, whose network policy denies egress
to social APIs and web.archive.org.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = "unosw.plus-ingester/1.0 (+https://unosw.plus; open knowledge platform)"


def http_get(url: str, headers: dict | None = None, timeout: float = 30.0,
             retries: int = 4, backoff: float = 2.0, pause: float = 1.0) -> tuple[int, dict, bytes]:
    """GET a URL with retries/backoff on 429/5xx and a polite delay after success.

    Returns (status_code, response_headers, body_bytes). Raises only on a final
    network error (not on HTTP error codes, which are returned).
    """
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                if pause:
                    time.sleep(pause)
                return resp.status, dict(resp.headers), body
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(backoff ** (attempt + 1))
                continue
            return exc.code, dict(exc.headers or {}), body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(backoff ** (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err
    return 0, {}, b""


def get_json(url: str, **kwargs: Any) -> tuple[int, dict, Any]:
    """GET and parse JSON. Returns (status, headers, parsed_or_None)."""
    status, headers, body = http_get(url, **kwargs)
    if status != 200 or not body:
        return status, headers, None
    try:
        return status, headers, json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return status, headers, None
