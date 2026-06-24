#!/usr/bin/env python3
"""PostToolUse hook: observe-only runtime friction monitor.

Detects cheap, reliable "I might be stuck / spinning" signals from tool-call
patterns alone — no token-window introspection, no LLM, no semantic judgement
(a hook can't see remaining context tokens, so it doesn't pretend to). On a new
signal it writes `.claude/flags/runtime-friction.flag` for review next session.
It NEVER aborts a turn — purely advisory.

Signals (per session_id):
  - tool_loop   : same tool + normalized input repeated >= TOOL_LOOP times
  - file_thrash : same file edited >= FILE_THRASH times
  - tool_volume : session tool total >= TOOL_VOLUME (runaway)
  - bash_errors : best-effort consecutive Bash failures >= BASH_ERROR_STREAK

Tune the thresholds below. Skips sdk-cli (subagents/background). Per-session
state lives under ~/.claude/state/friction/ and is pruned after PRUNE_AGE_S.
Exits 0 always; silent on stdout.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

TOOL_LOOP = 5
FILE_THRASH = 6
TOOL_VOLUME = 80
BASH_ERROR_STREAK = 4

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
STATE_DIR = Path.home() / ".claude" / "state" / "friction"
PRUNE_AGE_S = 3 * 24 * 3600
FLAG_NAME = "runtime-friction.flag"
PRODUCER = ".claude/hooks/runtime-friction-monitor.py"


def _norm_key(tool: str, ti: dict) -> str:
    if tool == "Bash":
        cmd = re.sub(r"\s+", " ", str(ti.get("command", ""))).strip()[:200]
        return f"Bash|{cmd}"
    if tool in EDIT_TOOLS or tool == "Read":
        return f"{tool}|{ti.get('file_path', '')}"
    if tool in {"Grep", "Glob"}:
        return f"{tool}|{ti.get('pattern', ti.get('path', ''))}"
    try:
        return f"{tool}|{json.dumps(ti, ensure_ascii=False, sort_keys=True)[:200]}"
    except (TypeError, ValueError):
        return f"{tool}|?"


def _bash_failed(tr) -> bool:
    """Best-effort failure detection. Under-detects rather than over-detects."""
    return isinstance(tr, dict) and (tr.get("is_error") is True or tr.get("interrupted") is True)


def _prune() -> None:
    now = time.time()
    try:
        for f in STATE_DIR.glob("*.json"):
            try:
                if now - f.stat().st_mtime > PRUNE_AGE_S:
                    f.unlink()
            except OSError:
                pass
    except OSError:
        pass


def main() -> int:
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "sdk-cli":
        return 0

    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        return 0

    sid = payload.get("session_id") or "nosid"
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
    tool = payload.get("tool_name") or "?"
    ti = payload.get("tool_input") or {}
    tr = payload.get("tool_response")
    if not isinstance(ti, dict):
        ti = {}

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0  # can't track → fail open, never break a tool call
    state_path = STATE_DIR / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', sid)}.json"

    fresh = not state_path.exists()
    if fresh:
        _prune()
    try:
        st = json.loads(state_path.read_text(encoding="utf-8")) if not fresh else {}
    except (OSError, json.JSONDecodeError):
        st = {}

    st.setdefault("session_id", sid)
    st.setdefault("started", datetime.now().astimezone().isoformat(timespec="seconds"))
    st.setdefault("tool_total", 0)
    st.setdefault("loops", {})
    st.setdefault("file_edits", {})
    st.setdefault("bash_error_streak", 0)
    st.setdefault("flagged", [])
    st.setdefault("details", [])

    st["tool_total"] += 1
    key = _norm_key(tool, ti)
    st["loops"][key] = st["loops"].get(key, 0) + 1

    if tool in EDIT_TOOLS and ti.get("file_path"):
        fp = ti["file_path"]
        st["file_edits"][fp] = st["file_edits"].get(fp, 0) + 1

    if tool == "Bash":
        st["bash_error_streak"] = st["bash_error_streak"] + 1 if _bash_failed(tr) else 0

    # Bound per-session state: drop one-off keys once the maps get large (they
    # are below the loop threshold anyway), so we don't read+write a huge JSON.
    if len(st["loops"]) > 400:
        st["loops"] = {k: v for k, v in st["loops"].items() if v >= 2}
    if len(st["file_edits"]) > 400:
        st["file_edits"] = {k: v for k, v in st["file_edits"].items() if v >= 2}

    new_signals: list[str] = []

    if st["loops"][key] == TOOL_LOOP:
        sig = f"tool_loop:{key}"
        if sig not in st["flagged"]:
            st["flagged"].append(sig)
            new_signals.append(f"tool_loop — same operation repeated {TOOL_LOOP}x: {key[:120]}")

    if tool in EDIT_TOOLS and ti.get("file_path"):
        fp = ti["file_path"]
        if st["file_edits"][fp] == FILE_THRASH:
            sig = f"file_thrash:{fp}"
            if sig not in st["flagged"]:
                st["flagged"].append(sig)
                new_signals.append(f"file_thrash — same file edited {FILE_THRASH}x: {fp}")

    if st["tool_total"] == TOOL_VOLUME:
        if "tool_volume" not in st["flagged"]:
            st["flagged"].append("tool_volume")
            new_signals.append(f"tool_volume — {TOOL_VOLUME} tool calls this session (possible runaway)")

    if st["bash_error_streak"] == BASH_ERROR_STREAK:
        if "bash_errors_active" not in st["flagged"]:
            st["flagged"].append("bash_errors_active")
            new_signals.append(f"bash_errors — {BASH_ERROR_STREAK} consecutive Bash failures (possibly stuck)")
    elif tool == "Bash" and st["bash_error_streak"] == 0:
        if "bash_errors_active" in st["flagged"]:
            st["flagged"].remove("bash_errors_active")

    if new_signals:
        st["details"].extend(new_signals)

    st["updated"] = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        state_path.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass

    if new_signals:
        _write_flag(root, st)

    return 0


def _write_flag(root: Path, st: dict) -> None:
    flags_dir = root / ".claude" / "flags"
    flag_path = flags_dir / FLAG_NAME
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    details = st.get("details", [])
    lines = [
        "flag: runtime-friction",
        f"producer: {PRODUCER}",
        f"identity: friction:{st.get('session_id', '?')[:8]}",
        "verify: observe-only retrospective signal (nothing was aborted). Decide "
        "whether you were actually stuck / should change approach, then rm this flag.",
        "",
        f"Runtime friction ({ts}, session {st.get('session_id','?')[:8]}, "
        f"{st.get('tool_total','?')} tool calls, {len(details)} signal type(s)):",
        "",
    ]
    for s in details:
        lines.append(f"  ! {s}")
    lines += [
        "",
        "Action: if genuinely stuck, step back and list what you tried / the "
        "errors / alternative routes. If it was just heavy legitimate work, rm this flag.",
    ]
    try:
        flags_dir.mkdir(parents=True, exist_ok=True)
        flag_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
