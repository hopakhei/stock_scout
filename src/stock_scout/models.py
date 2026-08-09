"""Shared dataclasses passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawPost:
    source_kind: str          # reddit | x | rss | ...
    source_name: str          # subreddit / feed name
    tier: str                 # leading | lagging | action
    external_id: str
    url: str
    title: str
    body: str
    author_handle: str
    posted_at: datetime
    author_created_at: datetime | None = None
    upvotes: int = 0
    num_comments: int = 0

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}"


@dataclass
class Mention:
    external_id: str          # post external id (joined to DB post id at persist time)
    symbol: str
    method: str               # cashtag | exact | llm
    confidence: float


@dataclass
class TickerFacts:
    symbol: str
    name: str = ""
    exchange: str = ""
    market_cap: int | None = None
    price: float | None = None
    avg_dollar_volume: float | None = None
    is_otc: bool = False
    sector: str = ""


@dataclass
class ScoreBreakdown:
    velocity_z: float = 0.0
    novelty: float = 0.0
    cross_source: int = 0
    author_quality: float = 0.5
    action_signal: float = 0.0
    mainstream_flag: bool = False
    manipulation_risk: float = 0.0
    total: float = 0.0

    def as_dict(self) -> dict:
        return {
            "velocity_z": round(self.velocity_z, 2),
            "novelty": self.novelty,
            "cross_source": self.cross_source,
            "author_quality": round(self.author_quality, 2),
            "action_signal": self.action_signal,
            "mainstream_flag": self.mainstream_flag,
            "manipulation_risk": round(self.manipulation_risk, 2),
            "total": round(self.total, 2),
        }


@dataclass
class Candidate:
    symbol: str
    facts: TickerFacts
    breakdown: ScoreBreakdown
    top_posts: list[RawPost] = field(default_factory=list)
    story: dict | None = None
    slack_message_ts: str | None = None

    @property
    def risk_label(self) -> str:
        r = self.breakdown.manipulation_risk
        if r >= 0.6:
            return "High"
        if r >= 0.3:
            return "Med"
        return "Low"
