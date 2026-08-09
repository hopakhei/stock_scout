"""X (Twitter) ingestion via API v2 recent search.

Quota reality check (2026 pricing):
  - Free tier: ~100 post reads/month, no meaningful search -> leave disabled.
  - Basic tier: recent search available, ~10-15K post reads/month. At two
    runs/day that is ~150-250 tweets per run, so this module enforces a hard
    per-run request cap (max_requests_per_run) and stops early on HTTP 429
    instead of failing the pipeline.

Queries deliberately avoid the cashtag/$ search operator (Pro+ only on some
plans); ticker extraction happens downstream from tweet text, which already
understands $TSLA-style cashtags.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import requests

from ..config import Settings
from ..models import RawPost

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


def fetch_x_posts(settings: Settings) -> list[RawPost]:
    cfg = settings.sources.get("x", {})
    if not cfg.get("enabled", False):
        return []
    if not settings.x_bearer_token:
        log.warning("x source enabled but X_BEARER_TOKEN missing; skipping")
        return []

    lookback = timedelta(hours=cfg.get("lookback_hours", 36))
    # recent search only covers ~7 days; start_time must also be >= 10s ago
    start = datetime.now(UTC) - min(lookback, timedelta(days=6))
    budget = _RequestBudget(cfg.get("max_requests_per_run", 2))

    out: list[RawPost] = []
    for q in cfg.get("queries", []):
        if not q.get("enabled", True):
            continue
        if budget.exhausted:
            log.info("x request budget spent; skipping remaining queries")
            break
        try:
            out.extend(_search(settings.x_bearer_token, q, cfg, start, budget))
        except Exception:  # one bad source must not kill the run (FR-1.6)
            log.exception("x query %s failed", q.get("name"))
    return out


class _RequestBudget:
    def __init__(self, max_requests: int):
        self.remaining = max_requests

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def spend(self) -> None:
        self.remaining -= 1


def _search(token: str, q: dict, cfg: dict, start: datetime,
            budget: _RequestBudget) -> list[RawPost]:
    params = {
        "query": q["query"],
        "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "max_results": min(cfg.get("max_results_per_request", 100), 100),
        "tweet.fields": "created_at,public_metrics,author_id,lang",
        "expansions": "author_id",
        "user.fields": "username,created_at",
    }
    posts: list[RawPost] = []
    next_token = None

    while not budget.exhausted:
        if next_token:
            params["next_token"] = next_token
        budget.spend()
        resp = requests.get(SEARCH_URL, params=params, timeout=30,
                            headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 429:
            log.warning("x rate limited (429); stopping this run's X ingestion")
            budget.remaining = 0
            break
        resp.raise_for_status()
        payload = resp.json()

        users = {u["id"]: u for u in payload.get("includes", {}).get("users", [])}
        posts.extend(_to_post(t, users, q) for t in payload.get("data", []))

        next_token = payload.get("meta", {}).get("next_token")
        if not next_token:
            break
    return posts


def _to_post(tweet: dict, users: dict, q: dict) -> RawPost:
    user = users.get(tweet.get("author_id"), {})
    metrics = tweet.get("public_metrics", {})
    author_created = None
    if user.get("created_at"):
        author_created = datetime.fromisoformat(user["created_at"])
    return RawPost(
        source_kind="x", source_name=q["name"], tier=q.get("tier", "leading"),
        external_id=tweet["id"],
        url=f"https://x.com/i/web/status/{tweet['id']}",
        title="", body=tweet.get("text", ""),
        author_handle=user.get("username", tweet.get("author_id", "")),
        author_created_at=author_created,
        posted_at=datetime.fromisoformat(tweet["created_at"]),
        upvotes=metrics.get("like_count", 0),
        num_comments=metrics.get("reply_count", 0),
    )
