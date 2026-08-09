"""US ticker universe: symbols from Nasdaq Trader symbol directory files.

Cached on disk for 7 days. Symbols not in the universe are never treated as
tickers, which is the first line of defence against false extractions.
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
CACHE_TTL_SECONDS = 7 * 24 * 3600

# Real tickers that are far more often ordinary words/acronyms in forum text.
# A cashtag ($ALL) always overrides this blacklist.
BLACKLIST = {
    "A", "AI", "ALL", "AM", "AN", "ANY", "APP", "ARE", "AT", "BE", "BEST", "BIG",
    "BUY", "BY", "CAN", "CEO", "CFO", "COST", "DD", "DO", "EOD", "EPS", "ETF",
    "EV", "EVER", "FAST", "FDA", "FOR", "FREE", "FUN", "GAIN", "GDP", "GO",
    "GOOD", "HAS", "HE", "HOLD", "HOPE", "HUGE", "IF", "IMO", "IPO", "IRS",
    "IS", "IT", "ITM", "JOB", "LIFE", "LOL", "LOVE", "LOW", "MAIN", "MAN",
    "ME", "MY", "NEW", "NEXT", "NICE", "NOW", "OK", "ON", "ONE", "OP", "OPEN",
    "OR", "OTM", "OUT", "PLAY", "PM", "POST", "PS", "PT", "REAL", "RH", "RIDE",
    "RUN", "SAFE", "SAVE", "SEC", "SEE", "SO", "SPAC", "STAY", "TA", "TELL",
    "THE", "TLDR", "TRUE", "TURN", "TWO", "UK", "UP", "US", "USA", "VERY",
    "WELL", "WSB", "YOLO", "YOU",
}


def _parse_symbol_file(text: str, symbol_col: int) -> dict[str, str]:
    out: dict[str, str] = {}
    lines = text.strip().splitlines()
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) <= symbol_col + 1:
            continue
        symbol, name = parts[symbol_col].strip(), parts[symbol_col + 1].strip()
        # skip test issues, units/warrants with special chars
        if not symbol or not symbol.isalpha() or len(symbol) > 5:
            continue
        out[symbol.upper()] = name
    return out


def load_universe(cache_dir: Path) -> dict[str, str]:
    """Returns {symbol: company_name}. Uses a 7-day disk cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / "universe.txt"
    if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL_SECONDS:
        return dict(
            line.split("\t", 1) for line in cache.read_text().splitlines() if "\t" in line
        )

    symbols: dict[str, str] = {}
    for url in (NASDAQ_LISTED, OTHER_LISTED):
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        symbols.update(_parse_symbol_file(resp.text, symbol_col=0))

    cache.write_text("\n".join(f"{s}\t{n}" for s, n in sorted(symbols.items())))
    return symbols
