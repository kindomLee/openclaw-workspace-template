#!/usr/bin/env python3
"""UserPromptSubmit hook: capture *negative signals* for a feedback corpus.

Stage 1 of a "learn from corrections" pipeline. This hook is PURE REGEX — no
LLM, no network, no blocking. It only asks "does this user message look like it
might be correcting my last action?" via a keyword gate. On a hit it snapshots
a small bundle (the user message + a summary of the previous assistant action,
pulled from the transcript tail) into a pending queue:

    cron/state/pending-corrections.jsonl

The expensive part — deciding whether it's REALLY a correction vs a
clarification / new request — is deferred to scripts/classify-corrections.py
(runs out-of-band). That keeps zero latency on the user's turn. We prefer to
MISS a correction than to inject noise, so the classifier (not this gate) is
the precision layer; this gate is loose recall.

Silent on stdout (no context injection). Skips sdk-cli. Exits 0 always.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Correction keyword gate (bilingual). HIGH = strong correction phrasing;
# MID = softer contrastive / "you missed X". Loose by design — the classifier
# is the precision layer. English uses word-boundary regex; CJK uses substring.
HIGH_SIGNAL_CJK = [
    "不對", "錯了", "不是這樣", "你搞錯", "搞錯了", "你誤解", "誤會",
    "我不是要", "我不是說", "不是叫你", "應該是", "其實是", "不應該",
    "別這樣", "不要這樣", "重來", "弄錯", "不是這個意思",
]
MID_SIGNAL_CJK = [
    "我剛剛說", "照我說的", "你漏了", "漏掉", "沒有做到", "不是說過",
    "為什麼會", "怎麼會", "明明", "我說的是",
]
HIGH_SIGNAL_EN = [
    r"that'?s (not|wrong)", r"\bnot what i (asked|wanted|meant|said)\b",
    r"\byou (misunderstood|got it wrong|misread)\b", r"\bi (didn'?t|did not) (say|ask|mean)\b",
    r"\b(no,|nope|wrong)\b", r"\bit should (be|have been)\b", r"\bactually it'?s\b",
    r"\bdon'?t do (that|this)\b", r"\bredo\b", r"\bstop doing\b", r"\byou broke\b",
]
MID_SIGNAL_EN = [
    r"\byou (missed|forgot|skipped|left out)\b", r"\bi (already )?told you\b",
    r"\blike i said\b", r"\bwhy (did|would) (you|it)\b", r"\bi meant\b",
]

PENDING_REL = "cron/state/pending-corrections.jsonl"
TAIL_BYTES = 64 * 1024


def _gate(prompt: str):
    """Return (tier, matched) or (None, None)."""
    for kw in HIGH_SIGNAL_CJK:
        if kw in prompt:
            return "high", kw
    low = prompt.lower()
    for pat in HIGH_SIGNAL_EN:
        if re.search(pat, low):
            return "high", pat
    for kw in MID_SIGNAL_CJK:
        if kw in prompt:
            return "mid", kw
    for pat in MID_SIGNAL_EN:
        if re.search(pat, low):
            return "mid", pat
    return None, None


def _prev_action_summary(transcript_path: str) -> str:
    """Summarise the last assistant turn (text + tool_use names) from the
    transcript tail. Best-effort: returns '' on any error."""
    if not transcript_path:
        return ""
    p = Path(transcript_path)
    if not p.is_file():
        return ""
    try:
        size = p.stat().st_size
        with p.open("rb") as fh:
            if size > TAIL_BYTES:
                fh.seek(-TAIL_BYTES, os.SEEK_END)
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""

    last_text, last_tools = "", []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue  # partial first line from tail seek
        if d.get("type") != "assistant":
            continue
        msg = d.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        texts, tools = [], []
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and c.get("text"):
                texts.append(c["text"])
            elif c.get("type") == "tool_use" and c.get("name"):
                ti = c.get("input", {})
                hint = str(ti.get("command") or ti.get("file_path") or "")[:60] if isinstance(ti, dict) else ""
                tools.append(f"{c['name']}({hint})" if hint else c["name"])
        if texts or tools:
            last_text = " ".join(texts)[-400:]
            last_tools = tools[-5:]
    parts = []
    if last_text:
        parts.append(f"text: {last_text}")
    if last_tools:
        parts.append(f"tools: {', '.join(last_tools)}")
    return " | ".join(parts)


def main() -> int:
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "sdk-cli":
        return 0

    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        return 0

    prompt = payload.get("prompt") or ""
    if not prompt.strip():
        return 0

    tier, matched = _gate(prompt)
    if tier is None:
        return 0  # not correction-looking → silent, instant

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
    prev_action = _prev_action_summary(payload.get("transcript_path", ""))

    entry = {
        "schema_version": 1,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": payload.get("session_id", ""),
        "cwd": str(root),
        "user_msg": prompt[:1000],
        "gate_tier": tier,
        "gate_match": matched,
        "prev_action": prev_action,
        "status": "pending",
    }

    out_path = root / PENDING_REL
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
