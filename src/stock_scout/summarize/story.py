"""LLM story summarisation for each alert (FR-6).

Provider is chosen in scoring.yaml (llm.provider): "deepseek" (official
OpenAI-compatible API, DEEPSEEK_API_KEY) or "anthropic" (ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import json
import logging

import requests

from ..models import Candidate
from .budget import Budget, BudgetExceeded

log = logging.getLogger(__name__)

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

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


def llm_api_key(settings) -> str:
    """The API key for the configured provider ('' when not configured)."""
    provider = settings.scoring["llm"].get("provider", "deepseek")
    if provider == "anthropic":
        return settings.anthropic_api_key
    return settings.deepseek_api_key


def summarize_candidate(candidate: Candidate, settings, budget: Budget) -> dict | None:
    llm_cfg = settings.scoring["llm"]
    provider = llm_cfg.get("provider", "deepseek")
    model = llm_cfg["summary_model"]
    max_posts = llm_cfg.get("summary_max_posts", 8)

    posts = sorted(candidate.top_posts, key=lambda p: p.upvotes, reverse=True)[:max_posts]
    posts_text = "\n\n---\n\n".join(
        f"[{p.source_name}, {p.upvotes} upvotes] {p.title}\n{p.body[:1500]}" for p in posts
    )
    prompt = PROMPT.format(symbol=candidate.symbol, name=candidate.facts.name, posts=posts_text)

    try:
        budget.check()
        if provider == "anthropic":
            text, tokens_in, tokens_out = _call_anthropic(settings, model, prompt)
        else:
            text, tokens_in, tokens_out = _call_deepseek(settings, model, prompt)
        budget.record(model, tokens_in, tokens_out)
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        return json.loads(text)
    except BudgetExceeded:
        log.warning("budget exhausted; skipping summary for %s", candidate.symbol)
        return None
    except Exception:
        log.exception("summary failed for %s", candidate.symbol)
        return None


def _call_deepseek(settings, model: str, prompt: str) -> tuple[str, int, int]:
    resp = requests.post(
        DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
        json={
            "model": model,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    return (data["choices"][0]["message"]["content"].strip(),
            usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def _call_anthropic(settings, model: str, prompt: str) -> tuple[str, int, int]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip(), resp.usage.input_tokens, resp.usage.output_tokens
