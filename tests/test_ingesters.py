"""Offline unit tests for the network ingesters' pure logic.

These exercise parsing and URL-collection with fixtures only — no network — so
they run in CI even though the ingesters themselves must run where outbound
access is available.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import import_social as S       # noqa: E402
import import_wayback as W      # noqa: E402


class SocialParsingTests(unittest.TestCase):
    def test_bluesky_filters_and_normalizes(self):
        posts = [
            {"uri": "at://did:plc:x/app.bsky.feed.post/abc123",
             "author": {"handle": "alice.bsky.social", "displayName": "Alice"},
             "record": {"text": "Loved #UNOSW DPI day! #opensource", "createdAt": "2026-06-24T10:00:00Z"}},
            {"uri": "at://did/app.bsky.feed.post/nope",
             "author": {"handle": "bob"}, "record": {"text": "totally unrelated"}},
        ]
        recs = S.parse_bluesky_posts(posts, {"unosw", "opensourceweek"}, ["UN Open Source Week"], "2026-07-02")
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["url"], "https://bsky.app/profile/alice.bsky.social/post/abc123")
        self.assertEqual(r["id"], "bluesky:alice.bsky.social:abc123")
        self.assertIn("unosw", r["hashtags"])
        self.assertEqual(r["method"], "automated-ingestion")

    def test_bluesky_matches_phrase_without_hashtag(self):
        posts = [{"uri": "at://d/app.bsky.feed.post/p1", "author": {"handle": "c"},
                  "record": {"text": "Heading to UN Open Source Week in NYC", "createdAt": "2026-06-20"}}]
        recs = S.parse_bluesky_posts(posts, {"unosw"}, ["UN Open Source Week"], "2026-07-02")
        self.assertEqual(len(recs), 1)

    def test_mastodon_strips_html_and_filters(self):
        statuses = [
            {"url": "https://mastodon.social/@carol/123",
             "account": {"acct": "carol", "display_name": "Carol", "url": "https://mastodon.social/@carol"},
             "created_at": "2026-06-25T09:00:00Z",
             "content": "<p>Great <a href='#'>#unosw</a> panel</p>", "tags": [{"name": "unosw"}]},
            {"url": "https://mastodon.social/@dave/9", "account": {"acct": "dave"},
             "created_at": "2026-06-25", "content": "<p>cat pictures</p>", "tags": [{"name": "cats"}]},
        ]
        recs = S.parse_mastodon_statuses(statuses, {"unosw"}, [], "2026-07-02")
        self.assertEqual(len(recs), 1)
        self.assertNotIn("<", recs[0]["excerpt"])
        self.assertEqual(recs[0]["platform"], "mastodon")

    def test_excerpt_is_bounded(self):
        long = "word " * 200
        self.assertLessEqual(len(S._excerpt(long)), S.EXCERPT_LEN)


class WaybackCollectionTests(unittest.TestCase):
    def test_collect_urls_excludes_own_site_and_github(self):
        datasets = {2025: {
            "sessions": [{"video_url": "https://webtv.un.org/x",
                          "official_url": "https://unosw.plus/self.html",
                          "transcript_url": "https://github.com/a/b.md"}],
            "references": [{"url": "https://www.un.org/gdc"}],
            "organizations": [{"website": "https://openforumeurope.org/"}],
            "speakers": [], "projects": [],
        }}
        urls = W.collect_urls(datasets, ["https://www.unopensource.org/"], "unosw.plus")
        self.assertIn("https://webtv.un.org/x", urls)
        self.assertIn("https://www.unopensource.org/", urls)
        self.assertNotIn("https://unosw.plus/self.html", urls)   # own site
        self.assertNotIn("https://github.com/a/b.md", urls)      # already durable
        self.assertEqual(len(urls), len(set(urls)))              # deduped

    def test_freshness(self):
        self.assertTrue(W._is_fresh("20260701000000", 90))
        self.assertFalse(W._is_fresh("20200101000000", 90))
        self.assertFalse(W._is_fresh("", 90))


if __name__ == "__main__":
    unittest.main()
