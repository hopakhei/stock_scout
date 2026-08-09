"""Ingestion transports parse fixtures correctly without hitting the network."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from stock_scout.config import Settings
from stock_scout.ingest import x as x_mod
from stock_scout.ingest.reddit import _json_comments, _json_fetcher

CONFIG_DIR = Path(__file__).parents[1] / "config"
NOW = datetime.now(timezone.utc)


def _listing(children):
    return {"data": {"children": children}}


def _post_child(post_id, created, num_comments=0):
    return {"data": {
        "id": post_id, "permalink": f"/r/test/comments/{post_id}/x/",
        "title": "DD on $ABCD", "selftext": "long thesis",
        "author": "someone", "created_utc": created.timestamp(),
        "score": 12, "num_comments": num_comments,
    }}


class FakeJsonClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, **params):
        self.calls.append(path)
        return self.responses.get(path)


def test_reddit_json_fetcher_parses_posts_and_caps_comment_fetches():
    cfg = {"posts_per_subreddit": 100, "comments_per_post": 30,
           "comment_posts_per_subreddit": 1, "request_delay_seconds": 0}
    fresh, stale = NOW - timedelta(hours=1), NOW - timedelta(days=5)
    client = FakeJsonClient({
        "/r/test/new.json": _listing([
            _post_child("aaa", fresh, num_comments=5),
            _post_child("bbb", fresh, num_comments=9),
            _post_child("old", stale, num_comments=99),
        ]),
        "/comments/bbb.json": [
            _listing([]),
            _listing([{"kind": "t1", "data": {
                "id": "c1", "permalink": "/r/test/comments/bbb/x/c1/",
                "body": "a comment easily longer than the minimum length",
                "author": "commenter", "created_utc": fresh.timestamp(), "score": 3,
            }}]),
        ],
    })
    with patch("stock_scout.ingest.reddit._JsonClient", return_value=client):
        fetch = _json_fetcher(cfg, NOW - timedelta(hours=36))
        posts = fetch("test", "leading")

    ids = {p.external_id for p in posts}
    assert ids == {"aaa", "bbb", "c1"}          # stale post dropped, comment kept
    # only the single most-discussed fresh post got a comments request
    assert client.calls == ["/r/test/new.json", "/comments/bbb.json"]
    assert all(p.source_kind == "reddit" and p.tier == "leading" for p in posts)


def test_reddit_json_comments_skips_short_and_non_comments():
    client = FakeJsonClient({"/comments/p1.json": [
        _listing([]),
        _listing([
            {"kind": "t1", "data": {"id": "s", "body": "short", "author": "a",
                                    "created_utc": NOW.timestamp(), "score": 0}},
            {"kind": "more", "data": {}},
        ]),
    ]})
    from stock_scout.models import RawPost
    p = RawPost(source_kind="reddit", source_name="test", tier="leading",
                external_id="p1", url="", title="", body="", author_handle="a",
                posted_at=NOW, num_comments=2)
    assert _json_comments(client, p, "test", "leading", 30) == []


def _x_payload():
    return {
        "data": [{
            "id": "190001", "author_id": "u1",
            "text": "Under the radar deep dive: $ABCD looks mispriced",
            "created_at": "2026-08-08T12:00:00.000Z",
            "public_metrics": {"like_count": 7, "reply_count": 2},
        }],
        "includes": {"users": [{
            "id": "u1", "username": "smallcapfan",
            "created_at": "2019-05-01T00:00:00.000Z",
        }]},
        "meta": {"next_token": "t2"},  # must NOT be followed once budget spent
    }


def test_x_disabled_or_missing_token_returns_empty():
    settings = Settings.load(CONFIG_DIR)  # x.enabled is false by default
    settings.x_bearer_token = "tok"
    assert x_mod.fetch_x_posts(settings) == []

    settings.sources["x"]["enabled"] = True
    settings.x_bearer_token = ""
    assert x_mod.fetch_x_posts(settings) == []


def test_x_search_respects_request_budget():
    settings = Settings.load(CONFIG_DIR)
    settings.x_bearer_token = "tok"
    settings.sources["x"]["enabled"] = True
    settings.sources["x"]["max_requests_per_run"] = 1

    class Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return _x_payload()

    with patch.object(x_mod.requests, "get", return_value=Resp()) as get:
        posts = x_mod.fetch_x_posts(settings)

    assert get.call_count == 1                   # pagination stopped by budget
    assert len(posts) == 1
    p = posts[0]
    assert p.source_kind == "x" and p.author_handle == "smallcapfan"
    assert p.upvotes == 7 and p.num_comments == 2
    assert p.author_created_at is not None
    assert "$ABCD" in p.body


def test_x_429_stops_gracefully():
    settings = Settings.load(CONFIG_DIR)
    settings.x_bearer_token = "tok"
    settings.sources["x"]["enabled"] = True

    class Resp:
        status_code = 429
        headers = {}
        def raise_for_status(self): raise AssertionError("must not raise on 429")
        def json(self): return {}

    with patch.object(x_mod.requests, "get", return_value=Resp()):
        assert x_mod.fetch_x_posts(settings) == []
