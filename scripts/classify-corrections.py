#!/usr/bin/env python3
"""Stage 2 of the correction-capture pipeline: classify pending signals.

Reads cron/state/pending-corrections.jsonl (produced by the regex gate in
.claude/hooks/correction-capture.py), asks an LLM to label each entry, and
promotes only high-confidence `correction` labels into
cron/state/observations.jsonl as candidates for human review. Writes
.claude/flags/correction-candidates.flag when new candidates appear.

This is the "cheap LLM triages -> flag -> you review" pattern: the LLM filters
noise; nothing auto-applies to memory. We bias toward DISCARDING (a
clarification / new request / preference is not a correction).

OPT-IN: requires an LLM. If no API key is set — LLM_API_KEY (or legacy
MINIMAX_API_KEY), via env or cron/config.env — the script skips cleanly
(exit 0) and the regex gate keeps queueing signals for a later run. Endpoint
and model follow LLM_API_URL / LLM_MODEL (same convention as evolve_skill.py),
so any Anthropic-compatible backend works.

Usage: python3 scripts/classify-corrections.py [--dry-run] [--limit N]
Requires: httpx.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx not installed; skipping (pip install httpx to enable).")
    raise SystemExit(0)

REPO = Path(__file__).resolve().parent.parent
PENDING = REPO / "cron" / "state" / "pending-corrections.jsonl"
OBSERVATIONS = REPO / "cron" / "state" / "observations.jsonl"
FLAG = REPO / ".claude" / "flags" / "correction-candidates.flag"
CONFIG_ENV = REPO / "cron" / "config.env"

# Anthropic-compatible endpoint, overridable via env (same convention as
# scripts/evolve_skill.py). Defaults to MiniMax; legacy MINIMAX_API_KEY honored.
API_URL = os.environ.get("LLM_API_URL", "https://api.minimax.io/anthropic/v1/messages")
MODEL = os.environ.get("LLM_MODEL", "MiniMax-M3")
CONF_THRESHOLD = 0.7
PENDING_RETENTION = 500
MAX_RETRIES = 2
RETRY_DELAY = 5
LABELS = {"correction", "clarification", "new_request", "preference", "unclear"}


def _api_key() -> str | None:
    key = os.environ.get("LLM_API_KEY") or os.environ.get("MINIMAX_API_KEY")
    if key:
        return key
    if CONFIG_ENV.is_file():
        for line in CONFIG_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            for var in ("LLM_API_KEY=", "MINIMAX_API_KEY="):
                if line.startswith(var):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    return None


def call_llm(prompt: str, api_key: str, max_tokens: int = 500, timeout: int = 60) -> str:
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = httpx.post(
                API_URL,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": MODEL,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            for c in resp.json().get("content") or []:
                if c.get("type") == "text":
                    return c["text"]
            return ""
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError):
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                time.sleep(int(e.response.headers.get("retry-after", RETRY_DELAY * (attempt + 1))))
            else:
                raise
    return ""


def classify(entry: dict, api_key: str) -> dict:
    prompt = f"""You analyse a conversation. Decide whether the user's message is
CORRECTING the assistant's previous action/output.

Assistant's previous action (summary):
{entry.get('prev_action') or '(none recorded)'}

User's message:
{entry.get('user_msg', '')}

Classify as exactly one of:
- correction: explicitly says the assistant got it wrong / misunderstood / went
  the wrong way, and wants it fixed
- clarification: adds detail or clarifies the request, but is not saying the
  assistant was wrong
- new_request: a new/different task, unrelated to whether the last action was right
- preference: a style/preference statement, not an error correction
- unclear: not enough information to decide

Reply with JSON only: {{"label": "<one of the above>", "confidence": <0..1>, "reason": "<short>"}}
No other text."""
    raw = call_llm(prompt, api_key)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {"label": "unclear", "confidence": 0.0, "reason": "parse_fail"}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"label": "unclear", "confidence": 0.0, "reason": "json_fail"}
    label = obj.get("label", "unclear")
    if label not in LABELS:
        label = "unclear"
    try:
        conf = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return {"label": label, "confidence": max(0.0, min(1.0, conf)), "reason": str(obj.get("reason", ""))[:40]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="classify but don't write observations/flag")
    ap.add_argument("--limit", type=int, default=0, help="max pending entries to process (0=all)")
    args = ap.parse_args()

    if not PENDING.is_file():
        print("no pending-corrections.jsonl, nothing to do")
        return 0

    entries = []
    for l in PENDING.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        try:
            entries.append(json.loads(l))
        except json.JSONDecodeError:
            entries.append(None)

    pending_idx = [i for i, e in enumerate(entries) if e and e.get("status") == "pending"]
    if args.limit:
        pending_idx = pending_idx[: args.limit]
    if not pending_idx:
        print("no pending entries")
        return 0

    api_key = _api_key()
    if not api_key:
        print(f"LLM_API_KEY (or MINIMAX_API_KEY) not set; skipping classification "
              f"({len(pending_idx)} pending entries queued for a later run).")
        return 0

    new_candidates = []
    counts = {l: 0 for l in LABELS}

    for i in pending_idx:
        e = entries[i]
        cls = classify(e, api_key)
        counts[cls["label"]] += 1
        e["classification"] = cls
        is_candidate = cls["label"] == "correction" and cls["confidence"] >= CONF_THRESHOLD
        e["status"] = "candidate" if is_candidate else "discarded"
        print(f"  [{cls['label']:12} {cls['confidence']:.2f}] {e.get('user_msg','')[:50]}"
              + ("  -> CANDIDATE" if is_candidate else ""))
        if is_candidate:
            uid = e.get("ts", "") + e.get("session_id", "")
            new_candidates.append({
                "schema_version": 1,
                "id": "corr_" + re.sub(r"[^0-9A-Za-z]", "", uid)[:16],
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "type": "correction_candidate",
                "session_id": e.get("session_id", ""),
                "cwd": e.get("cwd", ""),
                "user_msg": e.get("user_msg", ""),
                "prev_action": e.get("prev_action", ""),
                "classification": cls,
                "status": "candidate",
                "source": "correction-capture",
            })

    print(f"\nresult: {counts}; {len(new_candidates)} new candidate(s)")

    if args.dry_run:
        print("(--dry-run: nothing written)")
        return 0

    # Durability order: write candidates to observations FIRST, then flip pending
    # statuses. Worst case on a crash is a re-classified candidate, never a lost one.
    if new_candidates:
        OBSERVATIONS.parent.mkdir(parents=True, exist_ok=True)
        with OBSERVATIONS.open("a", encoding="utf-8") as fh:
            for c in new_candidates:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    kept = [e for e in entries if e]
    if len(kept) > PENDING_RETENTION:
        still_pending = [e for e in kept if e.get("status") == "pending"]
        processed = [e for e in kept if e.get("status") != "pending"]
        kept = still_pending + processed[-PENDING_RETENTION:]
    PENDING.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in kept) + "\n", encoding="utf-8")

    if new_candidates:
        _write_flag(len(new_candidates))

    return 0


def _write_flag(n: int) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    body = [
        "flag: correction-candidates",
        "producer: scripts/classify-corrections.py",
        f"identity: corr:{today}",
        "verify: review each candidate in observations.jsonl; promote the ones "
        "worth remembering into your feedback notes, mark the rest rejected, then rm this flag.",
        "",
        f"The classifier surfaced {n} high-confidence correction candidate(s) ({today}) for review.",
        "",
        f"Candidates: {OBSERVATIONS}",
        "(status=candidate; clarification/new_request/preference were filtered out)",
        "",
        "Action: read the candidates, decide which are real feedback worth keeping, curate, then rm this flag.",
    ]
    try:
        FLAG.parent.mkdir(parents=True, exist_ok=True)
        FLAG.write_text("\n".join(body) + "\n", encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
