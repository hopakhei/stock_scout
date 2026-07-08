"""Reddit ingestion via PRAW (official API, free tier)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..config import Settings
from ..models import RawPost

log = logging.getLogger(__name__)

MIN_COMMENT_LENGTH = 30


def fetch_reddit_posts(settings: Settings) -> list[RawPost]:
    import praw

    cfg = settings.sources["reddit"]
    lookback = timedelta(hours=cfg.get("lookback_hours", 36))
    cutoff = datetime.now(timezone.utc) - lookback

    reddit = praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent="stock-scout/0.1 (personal research tool)",
    )
    reddit.read_only = True

    out: list[RawPost] = []
    for sub_cfg in cfg["subreddits"]:
        if not sub_cfg.get("enabled", True):
            continue
        name, tier = sub_cfg["name"], sub_cfg["tier"]
        try:
            out.extend(_fetch_subreddit(reddit, name, tier, cfg, cutoff))
        except Exception:  # one bad source must not kill the run (FR-1.6)
            log.exception("subreddit %s failed", name)
    return out


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
        posted = datetime.fromtimestamp(s.created_utc, tz=timezone.utc)
        if posted < cutoff:
            continue
        author = s.author.name if s.author else "[deleted]"
        author_created = None
        posts.append(RawPost(
            source_kind="reddit", source_name=name, tier=tier,
            external_id=s.id, url=f"https://reddit.com{s.permalink}",
            title=s.title or "", body=s.selftext or "",
            author_handle=author, author_created_at=author_created,
            posted_at=posted, upvotes=s.score, num_comments=s.num_comments,
        ))
        posts.extend(_fetch_comments(s, name, tier, cfg))
    return posts


def _fetch_comments(submission, sub_name: str, tier: str, cfg: dict) -> list[RawPost]:
    out: list[RawPost] = []
    try:
        submission.comments.replace_more(limit=0)
        top_level = submission.comments[: cfg.get("comments_per_post", 30)]
    except Exception:
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
            posted_at=datetime.fromtimestamp(c.created_utc, tz=timezone.utc),
            upvotes=getattr(c, "score", 0), num_comments=0,
        ))
    return out
