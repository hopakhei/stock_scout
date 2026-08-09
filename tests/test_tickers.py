from datetime import UTC, datetime

from stock_scout.extract.tickers import extract_mentions
from stock_scout.models import RawPost

UNIVERSE = {"TSLA": "Tesla", "ABCD": "Alpha Biotech", "ALL": "Allstate", "IT": "Gartner"}


def post(text: str) -> RawPost:
    return RawPost(source_kind="reddit", source_name="stocks", tier="lagging",
                   external_id="x1", url="", title="", body=text,
                   author_handle="u", posted_at=datetime.now(UTC))


def symbols(text: str) -> dict[str, str]:
    return {m.symbol: m.method for m in extract_mentions(post(text), UNIVERSE)}


def test_cashtag_extracted():
    assert symbols("I like $TSLA a lot") == {"TSLA": "cashtag"}


def test_bare_uppercase_in_universe():
    assert symbols("ABCD had a great readout") == {"ABCD": "exact"}


def test_blacklisted_word_not_extracted():
    # ALL and IT are real tickers but common words; bare form must be ignored
    assert symbols("ALL of this is priced in, IT is over") == {}


def test_cashtag_overrides_blacklist():
    assert symbols("long $ALL here") == {"ALL": "cashtag"}


def test_unknown_symbol_ignored():
    assert symbols("$ZZZZZ is not a real ticker") == {}


def test_dedupe_keeps_cashtag_method():
    result = extract_mentions(post("$TSLA TSLA $TSLA"), UNIVERSE)
    assert len(result) == 1
    assert result[0].method == "cashtag"
    assert result[0].confidence == 0.99
