"""LLM story summarisation for each alert (FR-6)."""

from __future__ import annotations

import json
import logging

from ..models import Candidate
from .budget import Budget, BudgetExceeded

log = logging.getLogger(__name__)

SYSTEM = (
    "You are an equity research assistant. You are given forum posts that mention a stock. "
    "Summarise the discussion faithfully. Do not invent facts not present in the posts. "
    "This is research triage, not investment advice."
)

PROMPT = """Ticker: {symbol} ({name})

Forum posts mentioning this ticker (most engaged first):

{posts}

Return ONLY a JSON object with these keys (values in Traditional Chinese,
keep tickers/company names/technical terms in English):
- "thesis": the bull case being made, 2-3 sentences
- "catalyst": the catalyst(s) and expected timeline, 1-2 sentences
- "bear_case": counter-arguments or skepticism seen in the posts, 1-2 sentences
- "risks": main risks, 1-2 sentences
- "who_is_talking": what kind of posters (deep-dive analysts / momentum traders / etc), 1 sentence
- "manipulation_notes": any signs the discussion could be promotional or coordinated, 1 sentence
"""


def summarize_candidate(candidate: Candidate, settings, budget: Budget) -> dict | None:
    import anthropic

    llm_cfg = settings.scoring["llm"]
    model = llm_cfg["summary_model"]
    max_posts = llm_cfg.get("summary_max_posts", 8)

    posts = sorted(candidate.top_posts, key=lambda p: p.upvotes, reverse=True)[:max_posts]
    posts_text = "\n\n---\n\n".join(
        f"[r/{p.source_name}, {p.upvotes} upvotes] {p.title}\n{p.body[:1500]}" for p in posts
    )

    try:
        budget.check()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM,
            messages=[{"role": "user", "content": PROMPT.format(
                symbol=candidate.symbol, name=candidate.facts.name, posts=posts_text)}],
        )
        budget.record(model, resp.usage.input_tokens, resp.usage.output_tokens)
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        return json.loads(text)
    except BudgetExceeded:
        log.warning("budget exhausted; skipping summary for %s", candidate.symbol)
        return None
    except Exception:
        log.exception("summary failed for %s", candidate.symbol)
        return None
