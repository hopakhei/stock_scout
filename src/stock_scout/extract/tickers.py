"""Ticker extraction from post text.

Precedence:
  1. cashtags ($TSLA)   -> confidence 0.99, overrides the word blacklist
  2. bare uppercase     -> must be in universe AND not blacklisted, confidence 0.7
LLM disambiguation of ambiguous cases upgrades/creates mentions with method "llm".
"""

from __future__ import annotations

import re

from ..models import Mention, RawPost
from .universe import BLACKLIST

CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})\b")
BARE_RE = re.compile(r"\b([A-Z]{2,5})\b")


def extract_mentions(post: RawPost, universe: dict[str, str]) -> list[Mention]:
    found: dict[str, Mention] = {}
    text = post.text

    for m in CASHTAG_RE.finditer(text):
        sym = m.group(1).upper()
        if sym in universe:
            found[sym] = Mention(post.external_id, sym, "cashtag", 0.99)

    for m in BARE_RE.finditer(text):
        sym = m.group(1)
        if sym in found or sym not in universe or sym in BLACKLIST:
            continue
        found[sym] = Mention(post.external_id, sym, "exact", 0.7)

    return list(found.values())
