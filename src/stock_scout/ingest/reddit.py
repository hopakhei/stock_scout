"""Reddit ingestion.

Two interchangeable transports:
  1. Public JSON endpoints (reddit.com/r/<sub>/new.json) — no app, no
     credentials. Rate limit is per-IP and tight (~10 req/min), so requests
     are spaced out and comment fetches are capped per subreddit. Fine for
     a twice-daily batch job.
  2. PRAW (official OAuth API) — used automatically when
     REDDIT_CLIENT_ID/SECRET are set; higher rate limits.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

import requests

from ..config import Settings
from ..models import RawPost

log = logging.getLogger(__name__)

MIN_COMMENT_LENGTH = 30
USER_AGENT = "stock-scout/0.1 (personal research tool)"
BASE = "https://www.reddit.com"


def fetch_reddit_posts(settings: Settings) -> list[RawPost]:
    cfg = settings.sources["reddit"]
    cutoff = datetime.now(UTC) - timedelta(hours=cfg.get("lookback_hours", 36))

    if settings.reddit_client_id and settings.reddit_client_secret:
        fetch_one = _praw_fetcher(settings, cfg, cutoff)
    else:
        log.info("no Reddit credentials; using public JSON endpoints")
        fetch_one = _json_fetcher(cfg, cutoff)

    out: list[RawPost] = []
    for sub_cfg in cfg["subreddits"]:
        if not sub_cfg.get("enabled", True):
            continue
        try:
            out.extend(fetch_one(sub_cfg["name"], sub_cfg["tier"]))
        except Exception:  # one bad source must not kill the run (FR-1.6)
            log.exception("subreddit %s failed", sub_cfg["name"])
    return out


# -- transport 1: public JSON, no credentials ---------------------------------

class _JsonClient:
    """Serialised GETs with spacing and a single 429 back-off."""

    def __init__(self, delay_seconds: float):
        self.delay = delay_seconds
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last_request = 0.0

    def get(self, path: str, **params) -> dict | list | None:
        wait = self._last_request + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        for attempt in (1, 2):
            self._last_request = time.monotonic()
            resp = self.session.get(f"{BASE}{path}", params=params, timeout=30)
            if resp.status_code == 429 and attempt == 1:
                retry_after = float(resp.headers.get("retry-after", 30))
                log.warning("reddit 429; backing off %.0fs", retry_after)
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            return resp.json()
        return None


def _json_fetcher(cfg: dict, cutoff: datetime):
    client = _JsonClient(cfg.get("request_delay_seconds", 6))
    per_sub = cfg.get("posts_per_subreddit", 100)
    comment_posts = cfg.get("comment_posts_per_subreddit", 10)
    comments_per_post = cfg.get("comments_per_post", 30)

    def fetch(name: str, tier: str) -> list[RawPost]:
        posts: list[RawPost] = []
        listing = client.get(f"/r/{name}/new.json", limit=min(per_sub, 100)) or {}
        for child in listing.get("data", {}).get("children", []):
            d = child["data"]
            posted = datetime.fromtimestamp(d["created_utc"], tz=UTC)
            if posted < cutoff:
                continue
            posts.append(RawPost(
                source_kind="reddit", source_name=name, tier=tier,
                external_id=d["id"], url=f"{BASE}{d['permalink']}",
                title=d.get("title") or "", body=d.get("selftext") or "",
                author_handle=d.get("author") or "[deleted]",
                posted_at=posted, upvotes=d.get("score", 0),
                num_comments=d.get("num_comments", 0),
            ))
        # comments are an extra request each; only the most-discussed posts
        discussed = sorted((p for p in posts if p.num_comments > 0),
                           key=lambda p: p.num_comments, reverse=True)
        for p in discussed[:comment_posts]:
            posts.extend(_json_comments(client, p, name, tier, comments_per_post))
        return posts

    return fetch


def _json_comments(client: _JsonClient, post: RawPost, sub_name: str, tier: str,
                   limit: int) -> list[RawPost]:
    out: list[RawPost] = []
    try:
        thread = client.get(f"/comments/{post.external_id}.json", limit=limit, depth=1)
    except Exception:  # noqa: BLE001 — comments are optional extras
        log.warning("comment fetch failed for %s", post.external_id)
        return out
    if not isinstance(thread, list) or len(thread) < 2:
        return out
    for child in thread[1].get("data", {}).get("children", []):
        if child.get("kind") != "t1":
            continue
        d = child["data"]
        body = d.get("body") or ""
        if len(body) < MIN_COMMENT_LENGTH:
            continue
        out.append(RawPost(
            source_kind="reddit", source_name=sub_name, tier=tier,
            external_id=d["id"], url=f"{BASE}{d.get('permalink', '')}",
            title="", body=body, author_handle=d.get("author") or "[deleted]",
            posted_at=datetime.fromtimestamp(d["created_utc"], tz=UTC),
            upvotes=d.get("score", 0), num_comments=0,
        ))
    return out


# -- transport 2: PRAW (when credentials are configured) -----------------------

def _praw_fetcher(settings: Settings, cfg: dict, cutoff: datetime):
    import praw

    reddit = praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=USER_AGENT,
    )
    reddit.read_only = True

    def fetch(name: str, tier: str) -> list[RawPost]:
        return _fetch_subreddit(reddit, name, tier, cfg, cutoff)

    return fetch


def _fetch_subreddit(reddit, name: str, tier: str, cfg: dict, cutoff: datetime) -> list[RawPost]:
    sub = reddit.subreddit(name)
    posts: list[RawPost] = []
    seen: set[str] = set()

    listings = list(sub.new(limit=cfg.get("posts_per_subreddit", 100)))
    listings += list(sub.hot(limit=cfg.get("posts_per_subreddit", 100) // 2))

    for s in listings:
        if s.id in seen:
            continue
        seen.add(s.id)
        posted = datetime.fromtimestamp(s.created_utc, tz=UTC)
        if posted < cutoff:
            continue
        author = s.author.name if s.author else "[deleted]"
        posts.append(RawPost(
            source_kind="reddit", source_name=name, tier=tier,
            external_id=s.id, url=f"https://reddit.com{s.permalink}",
            title=s.title or "", body=s.selftext or "",
            author_handle=author, author_created_at=None,
            posted_at=posted, upvotes=s.score, num_comments=s.num_comments,
        ))
        posts.extend(_fetch_comments(s, name, tier, cfg))
    return posts


def _fetch_comments(submission, sub_name: str, tier: str, cfg: dict) -> list[RawPost]:
    out: list[RawPost] = []
    try:
        submission.comments.replace_more(limit=0)
        top_level = submission.comments[: cfg.get("comments_per_post", 30)]
    except Exception:  # noqa: BLE001 — comments are optional extras
        return out
    for c in top_level:
        body = getattr(c, "body", "") or ""
        if len(body) < MIN_COMMENT_LENGTH:
            continue
        author = c.author.name if c.author else "[deleted]"
        out.append(RawPost(
            source_kind="reddit", source_name=sub_name, tier=tier,
            external_id=c.id, url=f"https://reddit.com{c.permalink}",
            title="", body=body, author_handle=author,
            posted_at=datetime.fromtimestamp(c.created_utc, tz=UTC),
            upvotes=getattr(c, "score", 0), num_comments=0,
        ))
    return out
