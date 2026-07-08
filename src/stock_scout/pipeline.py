"""Pipeline orchestrator: feedback -> ingest -> extract -> score -> summarize -> report.

Designed to be idempotent within a day: posts/mentions dedupe on
(source, external_id), daily_stats upsert, and alerts are unique per
(date, symbol) so the second daily run only adds *new* candidates.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import Settings
from .fixtures import (FIXTURE_FACTS, FIXTURE_MAINSTREAM, FIXTURE_NOW,
                       FIXTURE_STORY, FIXTURE_UNIVERSE, fixture_posts)
from .models import Candidate, RawPost, TickerFacts
from .score.composite import composite_score, manipulation_risk_v1, velocity_zscore
from .summarize.budget import Budget

log = logging.getLogger(__name__)

DIGEST_DIR = Path(__file__).parents[2] / "digests"


def run_pipeline(settings: Settings, repo, *, dry_run: bool = False,
                 slot: str = "premarket", today: date | None = None) -> dict:
    if today is None:
        today = FIXTURE_NOW.date() if dry_run else datetime.now(timezone.utc).date()
    run_id = repo.start_run()
    budget = Budget(settings.scoring["llm"].get("run_budget_usd", 1.0))
    stats: dict = {"slot": slot, "dry_run": dry_run}

    try:
        slack = _slack_client(settings) if not dry_run else None

        if slack:
            _collect_feedback(repo, slack, today)

        posts = fixture_posts() if dry_run else _fetch_posts(settings)
        stats["posts"] = len(posts)
        stats["subreddits"] = len({p.source_name for p in posts})

        universe = FIXTURE_UNIVERSE if dry_run else _load_universe()
        posts_by_symbol = _persist_and_extract(repo, posts, universe)
        stats["symbols_mentioned"] = len(posts_by_symbol)

        mainstream = FIXTURE_MAINSTREAM if dry_run else _fetch_mainstream(settings)

        candidates = _score(settings, repo, today, posts_by_symbol, mainstream, dry_run)
        stats["alerts"] = len(candidates)

        for c in candidates:
            c.story = FIXTURE_STORY if dry_run else _summarize(c, settings, budget)

        alert_ids = _record_alerts(repo, today, candidates)
        _report(settings, repo, slack, today, slot, candidates, alert_ids, stats, dry_run)
        _record_prices(repo, today, candidates)

        repo.finish_run(run_id, "ok", stats, budget.spent_usd)
        return stats
    except Exception:
        repo.finish_run(run_id, "failed", stats, budget.spent_usd)
        raise


# -- stage helpers ------------------------------------------------------------

def _slack_client(settings: Settings):
    from .report.slack import SlackClient
    if settings.slack_bot_token and settings.slack_channel_id:
        return SlackClient(settings.slack_bot_token, settings.slack_channel_id)
    log.warning("Slack credentials missing; digest will only be written to digests/")
    return None


def _collect_feedback(repo, slack, today: date) -> None:
    """Read 👍/👎 reactions left on recent digest messages since the last run (FR-8.3)."""
    from .report.slack import feedback_from_reactions
    for alert in repo.pending_feedback_alerts(today - timedelta(days=7)):
        reactions = slack.get_reactions(alert["slack_message_ts"])
        fb = feedback_from_reactions(reactions)
        if fb:
            repo.set_feedback(alert["id"], fb)


def _fetch_posts(settings: Settings) -> list[RawPost]:
    from .ingest.reddit import fetch_reddit_posts
    settings.require("reddit_client_id", "reddit_client_secret")
    return fetch_reddit_posts(settings)


def _load_universe() -> dict[str, str]:
    from .extract.universe import load_universe
    return load_universe(Path.home() / ".cache" / "stock_scout")


def _fetch_mainstream(settings: Settings) -> set[str]:
    from .ingest.apewisdom import fetch_top_symbols
    ape = settings.sources.get("apewisdom", {})
    if not ape.get("enabled", True):
        return set()
    return fetch_top_symbols(ape.get("filter", "all-stocks"), ape.get("top_n_mainstream", 50))


def _persist_and_extract(repo, posts: list[RawPost],
                         universe: dict[str, str]) -> dict[str, list[RawPost]]:
    from .extract.tickers import extract_mentions
    posts_by_symbol: dict[str, list[RawPost]] = defaultdict(list)
    for p in posts:
        source_id = repo.upsert_source(p.source_kind, p.source_name, p.tier)
        author_id = repo.upsert_author(p.source_kind, p.author_handle, p.author_created_at)
        post_id = repo.insert_post(source_id, author_id, p)
        if post_id is None:  # already ingested by an earlier run
            continue
        for m in extract_mentions(p, universe):
            repo.ensure_ticker(m.symbol, universe.get(m.symbol, ""))
            repo.insert_mention(post_id, m.symbol, m.method, m.confidence)
            posts_by_symbol[m.symbol].append(p)
    return posts_by_symbol


def _score(settings: Settings, repo, today: date, posts_by_symbol: dict[str, list[RawPost]],
           mainstream: set[str], dry_run: bool) -> list[Candidate]:
    cfg = settings.scoring
    weights = cfg["weights"]
    vel_cfg, nov_cfg = cfg["velocity"], cfg["novelty"]
    mains_cfg = cfg["mainstream"]

    rows = repo.today_symbol_stats(today)
    leading = {r["symbol"]: r for r in rows if r["tier"] == "leading"}
    lagging = {r["symbol"]: r for r in rows if r["tier"] == "lagging"}

    # persist daily_stats + compute velocity for every symbol seen today
    provisional: list[tuple[float, str, dict]] = []
    for sym, r in leading.items():
        baseline = repo.baseline(sym, "leading", today, vel_cfg["baseline_days"])
        vz = 0.0
        if len(baseline) >= vel_cfg["min_history_days"]:
            vz = velocity_zscore(r["weighted_mentions"], baseline, vel_cfg["zscore_cap"])
        repo.upsert_daily_stats(today, sym, "leading", r["mention_count"],
                                r["unique_authors"], r["weighted_mentions"], vz)
        novelty = 1.0 if (repo.history_days(sym, today) == 0
                          and r["unique_authors"] >= nov_cfg["min_unique_authors"]) else 0.0
        pre = (weights["velocity"] * vz + weights["novelty"] * novelty
               + weights["cross_source"] * min(r["distinct_sources"], 5)
               + weights["author_quality"] * r["avg_reputation"])
        provisional.append((pre, sym, {"velocity_z": vz, "novelty": novelty, "row": r}))
    for sym, r in lagging.items():
        repo.upsert_daily_stats(today, sym, "lagging", r["mention_count"],
                                r["unique_authors"], r["weighted_mentions"], None)

    # enrich only the strongest pre-scored names (runtime + API courtesy)
    provisional.sort(reverse=True, key=lambda t: t[0])
    top = provisional[: cfg["candidates"]["max_enriched"]]

    candidates: list[Candidate] = []
    for _pre, sym, parts in top:
        facts = FIXTURE_FACTS.get(sym, TickerFacts(symbol=sym)) if dry_run \
            else _enrich(sym)
        if not _passes_prefilter(facts, cfg["prefilter"]):
            continue
        repo.update_ticker_facts(facts)

        r = parts["row"]
        mainstream_flag = (sym in mainstream
                           or lagging.get(sym, {}).get("mention_count", 0)
                           >= mains_cfg["lagging_mentions_threshold"])
        risk = manipulation_risk_v1(facts, cfg["manipulation"]["penny_otc_base_risk"])
        breakdown = composite_score(
            velocity_z=parts["velocity_z"], novelty=parts["novelty"],
            cross_source=r["distinct_sources"], author_quality=r["avg_reputation"],
            action_signal=0.0, mainstream_flag=mainstream_flag,
            manipulation_risk=risk, weights=weights)

        if breakdown.total >= cfg["alerts"]["threshold"]:
            candidates.append(Candidate(symbol=sym, facts=facts, breakdown=breakdown,
                                        top_posts=posts_by_symbol.get(sym, [])))

    candidates.sort(key=lambda c: c.breakdown.total, reverse=True)
    return candidates[: cfg["alerts"]["max_per_day"]]


def _enrich(symbol: str) -> TickerFacts:
    from .enrich.market_data import enrich_ticker
    return enrich_ticker(symbol)


def _passes_prefilter(facts: TickerFacts, prefilter: dict) -> bool:
    from .enrich.market_data import passes_prefilter
    return passes_prefilter(facts, prefilter)


def _summarize(candidate: Candidate, settings: Settings, budget: Budget) -> dict | None:
    from .summarize.story import summarize_candidate
    if not settings.anthropic_api_key:
        return None
    return summarize_candidate(candidate, settings, budget)


def _record_alerts(repo, today: date, candidates: list[Candidate]) -> dict[str, int]:
    """Insert alerts; drop candidates already alerted today (second run dedupe)."""
    alert_ids: dict[str, int] = {}
    kept: list[Candidate] = []
    for c in candidates:
        aid = repo.insert_alert(today, c.symbol, c.breakdown.total,
                                c.breakdown.as_dict(), c.breakdown.manipulation_risk, c.story)
        if aid is not None:
            alert_ids[c.symbol] = aid
            kept.append(c)
    candidates[:] = kept
    return alert_ids


def _report(settings: Settings, repo, slack, today: date, slot: str,
            candidates: list[Candidate], alert_ids: dict[str, int],
            stats: dict, dry_run: bool) -> None:
    from .report.digest import candidate_slack_blocks, header_text, render_markdown

    md = render_markdown(today, slot, candidates, stats)
    if dry_run:
        print(md)
        return

    DIGEST_DIR.mkdir(exist_ok=True)
    (DIGEST_DIR / f"{today.isoformat()}-{slot}.md").write_text(md)

    if slack:
        slack.post_message(header_text(today, slot, len(candidates), stats))
        for i, c in enumerate(candidates, 1):
            ts = slack.post_message(f"${c.symbol} — score {c.breakdown.total:.1f}",
                                    blocks=candidate_slack_blocks(i, c))
            if ts and c.symbol in alert_ids:
                repo.set_alert_slack_ts(alert_ids[c.symbol], ts)


def _record_prices(repo, today: date, candidates: list[Candidate]) -> None:
    for c in candidates:
        f = c.facts
        if f.price is not None or f.market_cap is not None:
            repo.insert_price(today, c.symbol, f.price, None, f.market_cap)
