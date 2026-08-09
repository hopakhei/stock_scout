"""Deterministic fixture data for --dry-run and tests. No network, no secrets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .models import RawPost, TickerFacts

# Fixed clock so fixture posts never straddle a UTC midnight relative to "today"
FIXTURE_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

FIXTURE_UNIVERSE = {
    "ABCD": "Alpha Biotech Corp",
    "WXYZ": "Western XYZ Industries",
    "TSLA": "Tesla Inc",
    "GME": "GameStop Corp",
    "ALL": "Allstate Corp",
}

FIXTURE_MAINSTREAM = {"TSLA", "GME"}

FIXTURE_FACTS = {
    "ABCD": TickerFacts(symbol="ABCD", name="Alpha Biotech Corp", exchange="NMS",
                        market_cap=800_000_000, price=12.5, avg_dollar_volume=5_000_000),
    "WXYZ": TickerFacts(symbol="WXYZ", name="Western XYZ Industries", exchange="PNK",
                        market_cap=45_000_000, price=0.8, avg_dollar_volume=300_000,
                        is_otc=True),
    "GME": TickerFacts(symbol="GME", name="GameStop Corp", exchange="NYQ",
                       market_cap=12_000_000_000, price=28.0, avg_dollar_volume=900_000_000),
}


def fixture_posts(now: datetime | None = None) -> list[RawPost]:
    now = now or FIXTURE_NOW

    def post(source, tier, ext_id, title, body, author, hours_ago, upvotes):
        return RawPost(
            source_kind="reddit", source_name=source, tier=tier, external_id=ext_id,
            url=f"https://reddit.com/r/{source}/comments/{ext_id}", title=title, body=body,
            author_handle=author, posted_at=now - timedelta(hours=hours_ago), upvotes=upvotes)

    return [
        # ABCD: 4 mentions, 3 unique authors, 2 leading sources -> should alert
        post("SecurityAnalysis", "leading", "t1", "Deep dive on $ABCD",
             "Wrote up my thesis on $ABCD ahead of the Phase 2 readout in September. "
             "Cash covers 2 years of burn.", "value_vet", 5, 120),
        post("SecurityAnalysis", "leading", "t2", "",
             "Agree on $ABCD. The market is pricing zero probability of success here, "
             "insider bought 50k shares last week.", "bio_analyst", 4, 45),
        post("Biotechplays", "leading", "t3", "ABCD readout timing",
             "$ABCD readout expected Q3. Comparable deals in this mechanism went for 3-5x.",
             "catalyst_hunter", 8, 60),
        post("Biotechplays", "leading", "t4", "",
             "Careful with ABCD dilution risk, they will need to raise after the readout.",
             "value_vet", 3, 20),
        # WXYZ: penny/OTC single-author chatter -> risk-flagged, likely below threshold
        post("pennystocks", "leading", "t5", "WXYZ about to run",
             "$WXYZ big volume coming, load up before it rips!", "moon_boi", 2, 15),
        # GME: mass-forum noise -> mainstream, must NOT alert
        post("wallstreetbets", "lagging", "t6", "GME to the moon",
             "$GME $GME $GME lets go", "wsb_degen", 1, 3000),
        # blacklist trap: ALL as a plain word must not be extracted
        post("stocks", "lagging", "t7", "Market thoughts",
             "ALL of this is priced in, the market knows IT already.", "macro_guy", 6, 10),
    ]


FIXTURE_STORY = {
    "thesis": "測試故事：Phase 2 讀數前市場定價過低，資金足夠兩年（dry-run 模擬，未調用 LLM）",
    "catalyst": "Q3 臨床數據讀出",
    "bear_case": "讀數後可能需要配股攤薄",
    "risks": "臨床失敗風險；小盤股流動性",
    "who_is_talking": "以基本面分析型作者為主",
    "manipulation_notes": "未見協同推廣跡象",
}
