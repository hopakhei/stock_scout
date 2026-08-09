"""Digest rendering: markdown archive + Slack Block Kit messages (SPEC.md §6)."""

from __future__ import annotations

from datetime import date

from ..models import Candidate

DISCLAIMER = "⚠️ 本 digest 為研究線索，非投資建議。"
RISK_EMOJI = {"Low": "🟢", "Med": "🟡", "High": "🔴"}


def _fmt_cap(cap: int | None) -> str:
    if not cap:
        return "市值 N/A"
    if cap >= 1_000_000_000:
        return f"市值 ${cap / 1e9:.1f}B"
    return f"市值 ${cap / 1e6:.0f}M"


def _candidate_lines(rank: int, c: Candidate) -> list[str]:
    b = c.breakdown
    lines = [
        f"🎯 #{rank}  ${c.symbol} — {c.facts.name or c.symbol}（{_fmt_cap(c.facts.market_cap)}）",
        f"分數 {b.total:.1f} ｜ 操縱風險：{RISK_EMOJI[c.risk_label]} {c.risk_label}",
        (f"▸ 拆解：velocity z={b.velocity_z:.1f} · novelty={b.novelty:.0f} · "
         f"{b.cross_source} 個 leading 源 · 作者質素 {b.author_quality:.2f}"),
    ]
    if c.facts.is_otc or (c.facts.price is not None and c.facts.price < 1.0):
        lines.append("⚠️ Penny/OTC — 操縱風險基礎分已計入，注意流動性")
    if c.story:
        s = c.story
        lines += [
            f"▸ 論點：{s.get('thesis', '')}",
            f"▸ 催化劑：{s.get('catalyst', '')}",
            f"▸ 反方：{s.get('bear_case', '')}",
            f"▸ 風險：{s.get('risks', '')}",
            f"▸ 邊個喺度講：{s.get('who_is_talking', '')}",
        ]
        if s.get("manipulation_notes"):
            lines.append(f"▸ 操縱觀察：{s['manipulation_notes']}")
    links = [p.url for p in c.top_posts[:3] if p.url]
    if links:
        lines.append("▸ 原文：" + " ".join(f"<{u}|link{i + 1}>" for i, u in enumerate(links)))
    return lines


def header_text(day: date, slot: str, n_candidates: int, stats: dict) -> str:
    slot_label = {"premarket": "盤前", "postclose": "收市後"}.get(slot, slot)
    scanned = f"掃描：{stats.get('subreddits', 0)} subreddits · {stats.get('posts', 0)} posts"
    found = f"發現 {n_candidates} 個候選" if n_candidates else "今日無發現"
    return f"📡 Stock Scout Daily — {day.isoformat()} {slot_label}\n{scanned} ｜ {found}"


def candidate_slack_blocks(rank: int, c: Candidate) -> list[dict]:
    text = "\n".join(_candidate_lines(rank, c))
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": "👍 值得研究 / 👎 冇用 —— react 呢個 message"}]},
    ]


def render_markdown(day: date, slot: str, candidates: list[Candidate], stats: dict) -> str:
    parts = [header_text(day, slot, len(candidates), stats), ""]
    for i, c in enumerate(candidates, 1):
        parts.append("─" * 30)
        parts.extend(_candidate_lines(i, c))
        parts.append("")
    parts.append(DISCLAIMER)
    return "\n".join(parts)
