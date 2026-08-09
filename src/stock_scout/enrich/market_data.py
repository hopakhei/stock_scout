"""Market data enrichment via yfinance: price, market cap, liquidity, OTC flag."""

from __future__ import annotations

import logging

from ..models import TickerFacts

log = logging.getLogger(__name__)

OTC_EXCHANGES = {"PNK", "OTC", "OQB", "OQX", "OEM"}


def enrich_ticker(symbol: str) -> TickerFacts:
    import yfinance as yf

    facts = TickerFacts(symbol=symbol)
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        facts.price = float(info.last_price) if info.last_price else None
        facts.market_cap = int(info.market_cap) if info.market_cap else None
        exchange = (getattr(info, "exchange", "") or "").upper()
        facts.exchange = exchange
        facts.is_otc = exchange in OTC_EXCHANGES

        hist = t.history(period="1mo", auto_adjust=True)
        if len(hist) > 0:
            facts.avg_dollar_volume = float((hist["Close"] * hist["Volume"]).mean())
    except Exception:  # noqa: BLE001 — enrichment is best-effort, never fatal
        log.warning("yfinance enrichment failed for %s", symbol)
    return facts


def passes_prefilter(facts: TickerFacts, prefilter: dict) -> bool:
    adv_min = prefilter.get("avg_dollar_volume_min", 0) or 0
    if adv_min and facts.avg_dollar_volume is not None and facts.avg_dollar_volume < adv_min:
        return False
    cap_min = prefilter.get("market_cap_min", 0) or 0
    if cap_min and facts.market_cap is not None and facts.market_cap < cap_min:
        return False
    cap_max = prefilter.get("market_cap_max")
    if cap_max and facts.market_cap is not None and facts.market_cap > cap_max:
        return False
    price_min = prefilter.get("price_min", 0) or 0
    if price_min and facts.price is not None and facts.price < price_min:
        return False
    return not (prefilter.get("exclude_otc") and facts.is_otc)
