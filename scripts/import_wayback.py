#!/usr/bin/env python3
"""Preserve the platform's authoritative external links via the Wayback Machine.

Collects the external, authoritative URLs the datasets link to (UN Web TV
recordings, un.org pages, official session/speaker pages, organization and
project websites, standards/reference URLs), checks each against the Wayback
Machine, and — when there is no recent snapshot — submits it to "Save Page Now".
Results are written to ``data/<id>/preservation.json`` (original URL, archived
snapshot URL, timestamp, status).

No media is stored; only snapshot URLs + status. "Save Page Now" is heavily
rate-limited, so this throttles hard and caps work per run (``--limit``); it is
idempotent (already-archived URLs are skipped) and resumable across runs.

Runs where outbound access to web.archive.org is allowed (e.g. GitHub Actions) —
NOT the agent sandbox, whose network policy denies it.

    python scripts/import_wayback.py --conference unosw --limit 40 --freshness-days 90
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import ingest_common as ic

REPO_ROOT = Path(__file__).resolve().parent.parent
# URL fields to preserve, per dataset.
URL_FIELDS = {
    "sessions": ("video_url", "transcript_url", "official_url"),
    "references": ("url",),
    "organizations": ("website",),
    "speakers": ("official_url", "website"),
    "projects": ("website",),
}
# Hosts we do NOT submit (already durable / our own site).
SKIP_HOSTS = {"github.com", "raw.githubusercontent.com"}


def collect_urls(datasets_by_year: dict[int, dict], official_urls: list[str], site_host: str) -> list[str]:
    """Pure: gather the distinct external http(s) URLs worth preserving."""
    urls: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = (u or "").strip()
        if not u.lower().startswith(("http://", "https://")):
            return
        host = urlsplit(u).netloc.lower().split(":")[0]
        if host == site_host or host in SKIP_HOSTS:
            return
        if u not in seen:
            seen.add(u)
            urls.append(u)

    for u in official_urls:
        add(u)
    for datasets in datasets_by_year.values():
        for name, fields in URL_FIELDS.items():
            for record in datasets.get(name, []):
                for field in fields:
                    add(record.get(field, ""))
    return sorted(urls)


def _snapshot_url(url: str, timeout: float = 30.0) -> dict | None:
    """Return the closest existing Wayback snapshot for a URL, or None."""
    api = f"https://archive.org/wayback/available?url={url}"
    status, _h, data = ic.get_json(api, timeout=timeout, pause=1.0)
    if status != 200 or not isinstance(data, dict):
        return None
    closest = (data.get("archived_snapshots") or {}).get("closest")
    if closest and closest.get("available"):
        return closest
    return None


def _is_fresh(timestamp: str, freshness_days: int) -> bool:
    try:
        snap = datetime.strptime(timestamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False
    return (datetime.now(timezone.utc) - snap).days <= freshness_days


def _save_now(url: str) -> str | None:
    """Trigger a Save Page Now capture; return the archived URL if discoverable."""
    status, headers, _body = ic.http_get(f"https://web.archive.org/save/{url}",
                                          timeout=60.0, retries=2, pause=3.0)
    loc = headers.get("Content-Location") or headers.get("content-location")
    if loc and loc.startswith("/web/"):
        return "https://web.archive.org" + loc
    if status in (200, 301, 302):
        return None  # submitted; snapshot URL not returned in headers
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conference", default="unosw")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--limit", type=int, default=40, help="Max Save-Page-Now submissions per run.")
    parser.add_argument("--freshness-days", type=int, default=90,
                        help="Treat a snapshot newer than this as up to date.")
    parser.add_argument("--offline", action="store_true", help="Only collect/print URLs; no network.")
    args = parser.parse_args()

    root = Path(args.repo_root)
    conf = json.loads((root / "conferences" / f"{args.conference}.json").read_text())
    site_host = urlsplit(conf.get("site_base_url", "")).netloc.lower().split(":")[0]

    datasets_by_year: dict[int, dict] = {}
    data_dir = root / "data" / args.conference
    for year in conf.get("data_years", []):
        year_dir = data_dir / str(year)
        ds = {}
        for name in URL_FIELDS:
            f = year_dir / f"{name}.json"
            ds[name] = json.loads(f.read_text()) if f.exists() else []
        datasets_by_year[year] = ds

    urls = collect_urls(datasets_by_year, conf.get("official_urls", []), site_host)
    print(f"{len(urls)} external URLs to preserve")

    out_path = data_dir / "preservation.json"
    existing: dict[str, dict] = {}
    if out_path.exists():
        for rec in json.loads(out_path.read_text()):
            existing[rec["url"]] = rec

    retrieved = date.today().isoformat()
    submitted = 0
    if not args.offline:
        for url in urls:
            prev = existing.get(url)
            if prev and prev.get("status") == "archived" and _is_fresh(prev.get("archived_at", ""),
                                                                        args.freshness_days):
                continue
            snap = _snapshot_url(url)
            if snap and _is_fresh(snap.get("timestamp", ""), args.freshness_days):
                existing[url] = {"url": url, "archived_url": snap.get("url", ""),
                                 "archived_at": snap.get("timestamp", ""), "status": "archived",
                                 "retrieved": retrieved, "method": "automated-ingestion"}
                continue
            if submitted >= args.limit:
                continue
            submitted += 1
            archived = _save_now(url)
            after = _snapshot_url(url)
            if after:
                existing[url] = {"url": url, "archived_url": archived or after.get("url", ""),
                                 "archived_at": after.get("timestamp", ""), "status": "archived",
                                 "retrieved": retrieved, "method": "automated-ingestion"}
            else:
                existing[url] = {"url": url, "archived_url": archived or "", "archived_at": "",
                                 "status": "submitted", "retrieved": retrieved,
                                 "method": "automated-ingestion"}

    merged = sorted(existing.values(), key=lambda r: r["url"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archived_n = sum(1 for r in merged if r.get("status") == "archived")
    print(f"preservation.json: {len(merged)} URLs ({archived_n} archived, {submitted} submitted this run) → {out_path}")


if __name__ == "__main__":
    main()
