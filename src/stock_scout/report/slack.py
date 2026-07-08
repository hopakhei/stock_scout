"""Slack delivery via bot token (chat.postMessage) and reaction reading (reactions.get).

A bot token is required rather than an incoming webhook because webhooks
cannot read reactions, which power the 👍/👎 feedback loop (FR-8.3).
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

API = "https://slack.com/api"


class SlackClient:
    def __init__(self, bot_token: str, channel_id: str):
        self.channel_id = channel_id
        self.headers = {"Authorization": f"Bearer {bot_token}"}

    def post_message(self, text: str, blocks: list[dict] | None = None) -> str | None:
        """Returns the message ts on success."""
        payload: dict = {"channel": self.channel_id, "text": text}
        if blocks:
            payload["blocks"] = blocks
        resp = requests.post(f"{API}/chat.postMessage", headers=self.headers,
                             json=payload, timeout=30)
        data = resp.json()
        if not data.get("ok"):
            log.error("slack post failed: %s", data.get("error"))
            return None
        return data.get("ts")

    def get_reactions(self, message_ts: str) -> dict[str, int]:
        """Returns {reaction_name: count} for one message."""
        resp = requests.get(
            f"{API}/reactions.get", headers=self.headers,
            params={"channel": self.channel_id, "timestamp": message_ts}, timeout=30)
        data = resp.json()
        if not data.get("ok"):
            return {}
        reactions = data.get("message", {}).get("reactions", [])
        return {r["name"]: r["count"] for r in reactions}


UP_REACTIONS = {"+1", "thumbsup"}
DOWN_REACTIONS = {"-1", "thumbsdown"}


def feedback_from_reactions(reactions: dict[str, int]) -> str | None:
    up = sum(c for n, c in reactions.items() if n in UP_REACTIONS)
    down = sum(c for n, c in reactions.items() if n in DOWN_REACTIONS)
    if up == 0 and down == 0:
        return None
    return "up" if up >= down else "down"
