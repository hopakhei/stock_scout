"""Configuration loading: YAML files + environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(os.environ.get("STOCK_SCOUT_CONFIG_DIR", Path(__file__).parents[2] / "config"))


@dataclass
class Settings:
    sources: dict[str, Any] = field(default_factory=dict)
    scoring: dict[str, Any] = field(default_factory=dict)

    # secrets, all from env
    database_url: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    anthropic_api_key: str = ""
    slack_bot_token: str = ""
    slack_channel_id: str = ""

    @classmethod
    def load(cls, config_dir: Path | None = None) -> "Settings":
        cfg = config_dir or CONFIG_DIR
        with open(cfg / "sources.yaml") as f:
            sources = yaml.safe_load(f)
        with open(cfg / "scoring.yaml") as f:
            scoring = yaml.safe_load(f)
        return cls(
            sources=sources,
            scoring=scoring,
            database_url=os.environ.get("DATABASE_URL", ""),
            reddit_client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
            reddit_client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            slack_bot_token=os.environ.get("SLACK_BOT_TOKEN", ""),
            slack_channel_id=os.environ.get("SLACK_CHANNEL_ID", ""),
        )

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise RuntimeError(f"Missing required environment settings: {', '.join(missing)}")
