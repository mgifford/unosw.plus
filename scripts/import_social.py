#!/usr/bin/env python3
"""Ingest public social posts about UN Open Source Week (Phase 12, social layer).

Queries Bluesky (public ``searchPosts``) and Mastodon (public tag timelines) for
the conference's hashtag variants and phrases — configured under ``social`` in
``conferences/<id>.json`` — and writes a deduped, provenanced
``data/<id>/social.json``.

Only PUBLIC posts are collected. Per GOVERNANCE, social posts are third-party
content: each record stores metadata (author, date, platform, matched hashtags)
plus the permalink and a short excerpt — never full content under a licence
claim, and never treated as an authoritative fact. Throttled, idempotent
(existing posts are kept, new ones merged), and resumable.

Runs where outbound access to bsky.app / Mastodon instances is allowed
(e.g. GitHub Actions) — NOT the agent sandbox, whose network policy denies it.

    python scripts/import_social.py --conference unosw --limit 100 --max-pages 3
"""

from __future__ import annotations

import argparse
import html as htmlmod
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

import ingest_common as ic

REPO_ROOT = Path(__file__).resolve().parent.parent
HASHTAG_RE = re.compile(r"#(\w+)")
TAG_STRIP_RE = re.compile(r"<[^>]+>")
EXCERPT_LEN = 280


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT_LEN else text[:EXCERPT_LEN - 1].rstrip() + "…"


def _matches(text: str, tags: list[str], wanted_tags: set[str], wanted_phrases: list[str]) -> bool:
    """Keep a post only if it genuinely references the conference."""
    low = text.lower()
    if any(t.lower() in wanted_tags for t in tags):
        return True
    return any(p.lower() in low for p in wanted_phrases)


def parse_bluesky_posts(posts: list[dict], wanted_tags: set[str], wanted_phrases: list[str],
                        retrieved: str) -> list[dict[str, Any]]:
    """Bluesky ``app.bsky.feed.searchPosts`` posts → normalized social records."""
    out = []
    for p in posts:
        record = p.get("record") or {}
        text = record.get("text", "") or ""
        author = p.get("author") or {}
        handle = author.get("handle", "")
        tags = [t.lower() for t in HASHTAG_RE.findall(text)]
        if not handle or not _matches(text, tags, wanted_tags, wanted_phrases):
            continue
        rkey = str(p.get("uri", "")).rsplit("/", 1)[-1]
        if not rkey:
            continue
        out.append({
            "id": f"bluesky:{handle}:{rkey}",
            "platform": "bluesky",
            "url": f"https://bsky.app/profile/{handle}/post/{rkey}",
            "author": f"@{handle}",
            "author_name": author.get("displayName", "") or handle,
            "author_url": f"https://bsky.app/profile/{handle}",
            "posted": record.get("createdAt", "") or p.get("indexedAt", ""),
            "excerpt": _excerpt(text),
            "hashtags": sorted(set(tags)),
            "retrieved": retrieved,
            "method": "automated-ingestion",
        })
    return out


def parse_mastodon_statuses(statuses: list[dict], wanted_tags: set[str], wanted_phrases: list[str],
                            retrieved: str) -> list[dict[str, Any]]:
    """Mastodon public tag-timeline statuses → normalized social records."""
    out = []
    for s in statuses:
        text = htmlmod.unescape(TAG_STRIP_RE.sub(" ", s.get("content", "") or ""))
        tags = [t.get("name", "").lower() for t in s.get("tags", []) if t.get("name")]
        account = s.get("account") or {}
        url = s.get("url") or s.get("uri") or ""
        if not url or not _matches(text, tags, wanted_tags, wanted_phrases):
            continue
        out.append({
            "id": f"mastodon:{url}",
            "platform": "mastodon",
            "url": url,
            "author": account.get("acct", ""),
            "author_name": account.get("display_name", "") or account.get("acct", ""),
            "author_url": account.get("url", ""),
            "posted": s.get("created_at", ""),
            "excerpt": _excerpt(text),
            "hashtags": sorted(set(tags)),
            "retrieved": retrieved,
            "method": "automated-ingestion",
        })
    return out


def _fetch_bluesky(terms: list[str], wanted_tags, wanted_phrases, retrieved, limit, max_pages):
    records = []
    for term in terms:
        cursor = None
        for _ in range(max_pages):
            url = (f"https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
                   f"?q={quote(term)}&limit={min(limit, 100)}")
            if cursor:
                url += f"&cursor={quote(cursor)}"
            status, _h, data = ic.get_json(url)
            if status != 200 or not data:
                print(f"  bluesky '{term}': HTTP {status}")
                break
            batch = parse_bluesky_posts(data.get("posts", []), wanted_tags, wanted_phrases, retrieved)
            records.extend(batch)
            print(f"  bluesky '{term}': +{len(batch)}")
            cursor = data.get("cursor")
            if not cursor:
                break
    return records


def _fetch_mastodon(instances, hashtags, wanted_tags, wanted_phrases, retrieved, limit, max_pages):
    records = []
    for instance in instances:
        for tag in hashtags:
            max_id = None
            for _ in range(max_pages):
                url = f"https://{instance}/api/v1/timelines/tag/{quote(tag)}?limit={min(limit, 40)}"
                if max_id:
                    url += f"&max_id={max_id}"
                status, _h, data = ic.get_json(url)
                if status != 200 or not isinstance(data, list) or not data:
                    break
                batch = parse_mastodon_statuses(data, wanted_tags, wanted_phrases, retrieved)
                records.extend(batch)
                print(f"  mastodon {instance} #{tag}: +{len(batch)}")
                max_id = data[-1].get("id")
                if not max_id:
                    break
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conference", default="unosw")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--limit", type=int, default=100, help="Max results per request.")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages per query/source.")
    parser.add_argument("--offline", action="store_true", help="Skip network; just re-sort existing data.")
    args = parser.parse_args()

    root = Path(args.repo_root)
    conf = json.loads((root / "conferences" / f"{args.conference}.json").read_text())
    social = conf.get("social", {})
    hashtags = social.get("hashtags", [])
    phrases = social.get("phrases", [])
    instances = social.get("mastodon_instances", [])
    wanted_tags = {t.lower() for t in hashtags}
    retrieved = date.today().isoformat()

    out_path = root / "data" / args.conference / "social.json"
    existing: dict[str, dict] = {}
    if out_path.exists():
        for rec in json.loads(out_path.read_text()):
            existing[rec["id"]] = rec

    new_records: list[dict] = []
    if not args.offline:
        terms = [f"#{t}" for t in hashtags] + phrases
        new_records += _fetch_bluesky(terms, wanted_tags, phrases, retrieved, args.limit, args.max_pages)
        new_records += _fetch_mastodon(instances, hashtags, wanted_tags, phrases, retrieved,
                                       args.limit, args.max_pages)

    added = 0
    for rec in new_records:
        if rec["id"] not in existing:
            existing[rec["id"]] = rec
            added += 1

    merged = sorted(existing.values(), key=lambda r: r.get("posted", ""), reverse=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"social.json: {len(merged)} posts ({added} new) → {out_path}")


if __name__ == "__main__":
    main()
