from datetime import date

from stock_scout.models import Candidate, ScoreBreakdown, TickerFacts
from stock_scout.report.digest import header_text, render_markdown
from stock_scout.report.slack import feedback_from_reactions


def make_candidate() -> Candidate:
    return Candidate(
        symbol="ABCD",
        facts=TickerFacts(symbol="ABCD", name="Alpha Biotech", market_cap=800_000_000,
                          price=12.5),
        breakdown=ScoreBreakdown(velocity_z=4.0, novelty=1.0, cross_source=2,
                                 author_quality=0.6, total=14.2),
        story={"thesis": "低估", "catalyst": "Q3 讀數", "bear_case": "攤薄",
               "risks": "臨床失敗", "who_is_talking": "基本面作者",
               "manipulation_notes": "未見異常"},
    )


def test_render_markdown_contains_candidate_and_disclaimer():
    md = render_markdown(date(2026, 7, 8), "premarket", [make_candidate()],
                         {"subreddits": 11, "posts": 500})
    assert "$ABCD" in md
    assert "14.2" in md
    assert "非投資建議" in md
    assert "Q3 讀數" in md


def test_empty_day_header():
    text = header_text(date(2026, 7, 8), "postclose", 0, {"subreddits": 11, "posts": 480})
    assert "今日無發現" in text


def test_penny_warning_shown():
    c = make_candidate()
    c.facts.price = 0.5
    c.breakdown.manipulation_risk = 0.2
    md = render_markdown(date(2026, 7, 8), "premarket", [c], {})
    assert "Penny/OTC" in md


def test_feedback_mapping():
    assert feedback_from_reactions({"+1": 1}) == "up"
    assert feedback_from_reactions({"-1": 2, "+1": 1}) == "down"
    assert feedback_from_reactions({"eyes": 3}) is None
    assert feedback_from_reactions({}) is None
