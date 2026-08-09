"""ApeWisdom free API: aggregated Reddit mention rankings.

Used for the mainstream/already-viral flag (top N) and baseline warm start.
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

API_URL = "https://apewisdom.io/api/v1.0/filter/{filter}/page/1"


def fetch_top_symbols(filter_name: str = "all-stocks", top_n: int = 50) -> set[str]:
    """Returns the set of currently most-mentioned symbols on mass Reddit."""
    try:
        resp = requests.get(API_URL.format(filter=filter_name), timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return {r["ticker"].upper() for r in results[:top_n] if r.get("ticker")}
    except Exception:
        log.exception("apewisdom fetch failed; mainstream flag degraded this run")
        return set()
