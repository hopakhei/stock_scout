"""Composite scoring (SPEC.md §5). Pure functions — no I/O — so they are unit-testable."""

from __future__ import annotations

import statistics

from ..models import ScoreBreakdown, TickerFacts


def velocity_zscore(today_weighted: float, baseline: list[float], cap: float) -> float:
    """z-score of today's weighted mentions vs the ticker's own rolling baseline."""
    if len(baseline) < 2:
        return 0.0
    mean = statistics.mean(baseline)
    std = statistics.pstdev(baseline)
    z = (today_weighted - mean) / max(std, 0.5)  # floor the std so quiet names don't explode
    return min(max(z, 0.0), cap)


def manipulation_risk_v1(facts: TickerFacts, base_risk: float) -> float:
    """Phase 1: only the penny/OTC base risk. Phase 3 adds behavioural components."""
    risk = 0.0
    if facts.is_otc or (facts.price is not None and facts.price < 1.0):
        risk += base_risk
    return min(risk, 1.0)


def composite_score(
    *,
    velocity_z: float,
    novelty: float,
    cross_source: int,
    author_quality: float,
    action_signal: float,
    mainstream_flag: bool,
    manipulation_risk: float,
    weights: dict,
) -> ScoreBreakdown:
    total = (
        weights["velocity"] * velocity_z
        + weights["novelty"] * novelty
        + weights["cross_source"] * min(cross_source, 5)
        + weights["author_quality"] * author_quality
        + weights["action_signal"] * action_signal
        - weights["mainstream_penalty"] * (1.0 if mainstream_flag else 0.0)
        - weights["manipulation_risk"] * manipulation_risk
    )
    return ScoreBreakdown(
        velocity_z=velocity_z,
        novelty=novelty,
        cross_source=cross_source,
        author_quality=author_quality,
        action_signal=action_signal,
        mainstream_flag=mainstream_flag,
        manipulation_risk=manipulation_risk,
        total=total,
    )
