"""Persistence layer.

`Repo` talks to Supabase (Postgres) via psycopg. `FakeRepo` is an in-memory
stand-in with the same interface, used by --dry-run and unit tests.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from ..models import RawPost, TickerFacts

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Repo:
    def __init__(self, database_url: str):
        import psycopg

        self.conn = psycopg.connect(database_url, autocommit=True)

    def close(self) -> None:
        self.conn.close()

    def init_db(self) -> None:
        self.conn.execute(SCHEMA_PATH.read_text())

    # -- runs ---------------------------------------------------------------

    def start_run(self) -> int:
        row = self.conn.execute(
            "INSERT INTO runs (started_at) VALUES (now()) RETURNING id"
        ).fetchone()
        return row[0]

    def finish_run(self, run_id: int, status: str, stats: dict, llm_cost_usd: float) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=now(), status=%s, stats_json=%s, llm_cost_usd=%s "
            "WHERE id=%s",
            (status, json.dumps(stats), llm_cost_usd, run_id),
        )

    # -- ingestion ----------------------------------------------------------

    def upsert_source(self, kind: str, name: str, tier: str, url: str = "") -> int:
        row = self.conn.execute(
            "INSERT INTO sources (kind, name, url, tier) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (kind, name) DO UPDATE SET tier=EXCLUDED.tier RETURNING id",
            (kind, name, url, tier),
        ).fetchone()
        return row[0]

    def upsert_author(self, source_kind: str, handle: str, created_at: datetime | None) -> int:
        row = self.conn.execute(
            "INSERT INTO authors (source_kind, handle, account_created_at) VALUES (%s,%s,%s) "
            "ON CONFLICT (source_kind, handle) DO UPDATE SET "
            "account_created_at=COALESCE(authors.account_created_at, EXCLUDED.account_created_at) "
            "RETURNING id",
            (source_kind, handle, created_at),
        ).fetchone()
        return row[0]

    def insert_post(self, source_id: int, author_id: int | None, p: RawPost) -> int | None:
        """Returns post id, or None when the post was already stored (dedupe)."""
        row = self.conn.execute(
            "INSERT INTO posts (source_id, external_id, url, title, body, author_id, "
            "posted_at, upvotes, num_comments) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (source_id, external_id) DO NOTHING RETURNING id",
            (source_id, p.external_id, p.url, p.title, p.body, author_id,
             p.posted_at, p.upvotes, p.num_comments),
        ).fetchone()
        return row[0] if row else None

    def ensure_ticker(self, symbol: str, name: str = "") -> None:
        self.conn.execute(
            "INSERT INTO tickers (symbol, name) VALUES (%s,%s) ON CONFLICT (symbol) DO NOTHING",
            (symbol, name),
        )

    def update_ticker_facts(self, f: TickerFacts) -> None:
        self.conn.execute(
            "UPDATE tickers SET name=COALESCE(NULLIF(%s,''), name), exchange=%s, "
            "sector=%s, market_cap=%s, is_otc=%s WHERE symbol=%s",
            (f.name, f.exchange, f.sector, f.market_cap, f.is_otc, f.symbol),
        )

    def insert_mention(self, post_id: int, symbol: str, method: str, confidence: float) -> None:
        self.conn.execute(
            "INSERT INTO mentions (post_id, symbol, method, confidence) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (post_id, symbol) DO NOTHING",
            (post_id, symbol, method, confidence),
        )

    # -- aggregates for scoring ---------------------------------------------

    def today_symbol_stats(self, day: date) -> list[dict]:
        """Per (symbol, tier) aggregates for one day, across all runs of that day."""
        rows = self.conn.execute(
            """
            SELECT m.symbol, s.tier,
                   COUNT(*)                          AS mention_count,
                   COUNT(DISTINCT p.author_id)       AS unique_authors,
                   SUM(COALESCE(a.reputation, 0.5))  AS weighted_mentions,
                   COUNT(DISTINCT s.name)            AS distinct_sources,
                   AVG(COALESCE(a.reputation, 0.5))  AS avg_reputation
            FROM mentions m
            JOIN posts p   ON p.id = m.post_id
            JOIN sources s ON s.id = p.source_id
            LEFT JOIN authors a ON a.id = p.author_id
            WHERE p.posted_at::date = %s
            GROUP BY m.symbol, s.tier
            """,
            (day,),
        ).fetchall()
        return [
            {"symbol": r[0], "tier": r[1], "mention_count": r[2], "unique_authors": r[3],
             "weighted_mentions": float(r[4] or 0), "distinct_sources": r[5],
             "avg_reputation": float(r[6] or 0.5)}
            for r in rows
        ]

    def upsert_daily_stats(self, day: date, symbol: str, tier: str, mention_count: int,
                           unique_authors: int, weighted_mentions: float,
                           velocity_z: float | None) -> None:
        self.conn.execute(
            "INSERT INTO daily_stats (date, symbol, tier, mention_count, unique_authors, "
            "weighted_mentions, velocity_z) VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (date, symbol, tier) DO UPDATE SET "
            "mention_count=EXCLUDED.mention_count, unique_authors=EXCLUDED.unique_authors, "
            "weighted_mentions=EXCLUDED.weighted_mentions, velocity_z=EXCLUDED.velocity_z",
            (day, symbol, tier, mention_count, unique_authors, weighted_mentions, velocity_z),
        )

    def baseline(self, symbol: str, tier: str, before: date, days: int) -> list[float]:
        rows = self.conn.execute(
            "SELECT weighted_mentions FROM daily_stats "
            "WHERE symbol=%s AND tier=%s AND date < %s AND date >= %s - make_interval(days => %s) "
            "ORDER BY date",
            (symbol, tier, before, before, days),
        ).fetchall()
        return [float(r[0]) for r in rows]

    def history_days(self, symbol: str, before: date) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT date) FROM daily_stats WHERE symbol=%s AND date < %s",
            (symbol, before),
        ).fetchone()
        return row[0]

    # -- alerts / feedback ----------------------------------------------------

    def insert_alert(self, day: date, symbol: str, score: float, components: dict,
                     manipulation_risk: float, story: dict | None) -> int | None:
        row = self.conn.execute(
            "INSERT INTO alerts (date, symbol, score, components_json, manipulation_risk, "
            "story_json) VALUES (%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (date, symbol) DO NOTHING RETURNING id",
            (day, symbol, score, json.dumps(components), manipulation_risk,
             json.dumps(story) if story else None),
        ).fetchone()
        return row[0] if row else None

    def set_alert_slack_ts(self, alert_id: int, ts: str) -> None:
        self.conn.execute("UPDATE alerts SET slack_message_ts=%s WHERE id=%s", (ts, alert_id))

    def pending_feedback_alerts(self, since: date) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, slack_message_ts FROM alerts "
            "WHERE feedback IS NULL AND slack_message_ts IS NOT NULL AND date >= %s",
            (since,),
        ).fetchall()
        return [{"id": r[0], "slack_message_ts": r[1]} for r in rows]

    def set_feedback(self, alert_id: int, feedback: str) -> None:
        self.conn.execute("UPDATE alerts SET feedback=%s WHERE id=%s", (feedback, alert_id))

    def insert_price(self, day: date, symbol: str, close: float | None,
                     volume: int | None, market_cap: int | None) -> None:
        self.conn.execute(
            "INSERT INTO prices (date, symbol, close, volume, market_cap) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (date, symbol) DO UPDATE SET "
            "close=EXCLUDED.close, volume=EXCLUDED.volume, market_cap=EXCLUDED.market_cap",
            (day, symbol, close, volume, market_cap),
        )


class FakeRepo:
    """In-memory Repo with the same interface (dry-run / tests)."""

    def __init__(self):
        self.sources: dict[tuple[str, str], dict] = {}
        self.authors: dict[tuple[str, str], dict] = {}
        self.posts: dict[tuple[int, str], dict] = {}
        self.tickers: dict[str, dict] = {}
        self.mentions: list[dict] = []
        self.daily_stats: dict[tuple[date, str, str], dict] = {}
        self.alerts: list[dict] = []
        self.runs: list[dict] = []
        self.prices: list[dict] = []
        self._next_id = 1

    def _nid(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def close(self) -> None:
        pass

    def init_db(self) -> None:
        pass

    def start_run(self) -> int:
        rid = self._nid()
        self.runs.append({"id": rid, "started_at": datetime.now(UTC)})
        return rid

    def finish_run(self, run_id, status, stats, llm_cost_usd) -> None:
        for r in self.runs:
            if r["id"] == run_id:
                r.update(status=status, stats=stats, llm_cost_usd=llm_cost_usd)

    def upsert_source(self, kind, name, tier, url="") -> int:
        key = (kind, name)
        if key not in self.sources:
            self.sources[key] = {"id": self._nid(), "kind": kind, "name": name, "tier": tier}
        return self.sources[key]["id"]

    def upsert_author(self, source_kind, handle, created_at) -> int:
        key = (source_kind, handle)
        if key not in self.authors:
            self.authors[key] = {"id": self._nid(), "handle": handle,
                                 "account_created_at": created_at, "reputation": 0.5}
        return self.authors[key]["id"]

    def insert_post(self, source_id, author_id, p: RawPost) -> int | None:
        key = (source_id, p.external_id)
        if key in self.posts:
            return None
        pid = self._nid()
        self.posts[key] = {"id": pid, "source_id": source_id, "author_id": author_id, "raw": p}
        return pid

    def ensure_ticker(self, symbol, name="") -> None:
        self.tickers.setdefault(symbol, {"symbol": symbol, "name": name})

    def update_ticker_facts(self, f: TickerFacts) -> None:
        self.tickers.setdefault(f.symbol, {})["facts"] = f

    def insert_mention(self, post_id, symbol, method, confidence) -> None:
        if any(m["post_id"] == post_id and m["symbol"] == symbol for m in self.mentions):
            return
        self.mentions.append({"post_id": post_id, "symbol": symbol,
                              "method": method, "confidence": confidence})

    def today_symbol_stats(self, day: date) -> list[dict]:
        posts_by_id = {v["id"]: v for v in self.posts.values()}
        sources_by_id = {v["id"]: v for v in self.sources.values()}
        authors_by_id = {v["id"]: v for v in self.authors.values()}
        agg: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"mention_count": 0, "authors": set(), "weighted": 0.0,
                     "sources": set(), "reps": []})
        for m in self.mentions:
            post = posts_by_id[m["post_id"]]
            if post["raw"].posted_at.date() != day:
                continue
            src = sources_by_id[post["source_id"]]
            rep = authors_by_id.get(post["author_id"], {}).get("reputation", 0.5)
            a = agg[(m["symbol"], src["tier"])]
            a["mention_count"] += 1
            a["authors"].add(post["author_id"])
            a["weighted"] += rep
            a["sources"].add(src["name"])
            a["reps"].append(rep)
        return [
            {"symbol": sym, "tier": tier, "mention_count": a["mention_count"],
             "unique_authors": len(a["authors"]), "weighted_mentions": a["weighted"],
             "distinct_sources": len(a["sources"]),
             "avg_reputation": statistics.mean(a["reps"]) if a["reps"] else 0.5}
            for (sym, tier), a in agg.items()
        ]

    def upsert_daily_stats(self, day, symbol, tier, mention_count, unique_authors,
                           weighted_mentions, velocity_z) -> None:
        self.daily_stats[(day, symbol, tier)] = {
            "mention_count": mention_count, "unique_authors": unique_authors,
            "weighted_mentions": weighted_mentions, "velocity_z": velocity_z}

    def baseline(self, symbol, tier, before, days) -> list[float]:
        vals = [(d, v["weighted_mentions"]) for (d, s, t), v in self.daily_stats.items()
                if s == symbol and t == tier and d < before and (before - d).days <= days]
        return [v for _, v in sorted(vals)]

    def history_days(self, symbol, before) -> int:
        return len({d for (d, s, _t) in self.daily_stats if s == symbol and d < before})

    def insert_alert(self, day, symbol, score, components, manipulation_risk, story):
        if any(a["date"] == day and a["symbol"] == symbol for a in self.alerts):
            return None
        aid = self._nid()
        self.alerts.append({"id": aid, "date": day, "symbol": symbol, "score": score,
                            "components": components, "manipulation_risk": manipulation_risk,
                            "story": story, "slack_message_ts": None, "feedback": None})
        return aid

    def set_alert_slack_ts(self, alert_id, ts) -> None:
        for a in self.alerts:
            if a["id"] == alert_id:
                a["slack_message_ts"] = ts

    def pending_feedback_alerts(self, since) -> list[dict]:
        return [{"id": a["id"], "slack_message_ts": a["slack_message_ts"]}
                for a in self.alerts
                if a["feedback"] is None and a["slack_message_ts"] and a["date"] >= since]

    def set_feedback(self, alert_id, feedback) -> None:
        for a in self.alerts:
            if a["id"] == alert_id:
                a["feedback"] = feedback

    def insert_price(self, day, symbol, close, volume, market_cap) -> None:
        self.prices.append({"date": day, "symbol": symbol, "close": close,
                            "volume": volume, "market_cap": market_cap})
