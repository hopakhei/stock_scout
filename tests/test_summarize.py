"""Story summarisation: provider routing and DeepSeek response handling."""

import json
from pathlib import Path
from unittest.mock import patch

from stock_scout.config import Settings
from stock_scout.models import Candidate, ScoreBreakdown, TickerFacts
from stock_scout.summarize import story
from stock_scout.summarize.budget import Budget

CONFIG_DIR = Path(__file__).parents[1] / "config"

STORY = {"thesis": "低估", "catalyst": "Q3", "bear_case": "怕", "risks": "稀釋",
         "who_is_talking": "分析派", "manipulation_notes": "冇"}


def _candidate():
    return Candidate(symbol="ABCD", facts=TickerFacts(symbol="ABCD", name="Abcd Corp"),
                     breakdown=ScoreBreakdown())


def test_llm_api_key_follows_provider():
    settings = Settings.load(CONFIG_DIR)  # provider: deepseek
    settings.deepseek_api_key, settings.anthropic_api_key = "dsk", "ant"
    assert story.llm_api_key(settings) == "dsk"

    settings.scoring["llm"]["provider"] = "anthropic"
    assert story.llm_api_key(settings) == "ant"


def test_summarize_via_deepseek_parses_json_and_records_budget():
    settings = Settings.load(CONFIG_DIR)
    settings.deepseek_api_key = "dsk"
    budget = Budget(1.0)

    class Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": json.dumps(STORY)}}],
                    "usage": {"prompt_tokens": 900, "completion_tokens": 250}}

    with patch.object(story.requests, "post", return_value=Resp()) as post:
        result = story.summarize_candidate(_candidate(), settings, budget)

    assert result == STORY
    assert budget.spent_usd > 0
    body = post.call_args.kwargs["json"]
    assert body["model"] == "deepseek-chat"
    assert body["response_format"] == {"type": "json_object"}


def test_summarize_failure_returns_none():
    settings = Settings.load(CONFIG_DIR)
    settings.deepseek_api_key = "dsk"

    with patch.object(story.requests, "post", side_effect=RuntimeError("boom")):
        assert story.summarize_candidate(_candidate(), settings, Budget(1.0)) is None
