#!/usr/bin/env python3
"""SessionStart hook: persist spec-file context-budget breaches as a flag.

Your "always-on" spec files (SOUL.md / AGENTS.md / USER.md / MEMORY.md /
CLAUDE.md) are read into context every session. When they bloat, they quietly
eat the context window. This hook measures their estimated token size on
SessionStart and, when a file exceeds its role cap (or the total exceeds the
budget), writes a persistent `.claude/flags/sessionstart-budget.flag` so the
breach keeps surfacing every session until you actually slim the files down.
When everything is back under cap it AUTO-REMOVES the flag (self-resolving).

This is a budget *guard that nags*, not an enforcer: there is no single
injector to truncate (CLAUDE.md tells the model to Read the spec files itself),
so it cannot hard-cap context — it just makes the breach impossible to ignore.

Tuning: edit PER_FILE_CAPS / BUDGET_TOKENS below for your workspace. The
estimate is char_count // 3 (conservative). Skips sdk-cli (subagents). Exits 0
always; never blocks SessionStart.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Spec files measured (relative to the project root). Adjust to your workspace.
SPEC_FILES = ["CLAUDE.md", "SOUL.md", "AGENTS.md", "USER.md", "MEMORY.md"]

# Per-file role caps (estimated tokens). Each file plays a different context
# role; a per-file breach is alerted before the legacy total budget. Calibrate
# these against your own content — leave ~10% headroom over irreducible size.
PER_FILE_CAPS = {
    "CLAUDE.md": 1800,
    "SOUL.md": 900,
    "AGENTS.md": 1700,
    "USER.md": 600,
    "MEMORY.md": 4000,
    "~/.claude/CLAUDE.md": 800,
}
BUDGET_TOKENS = 12000  # legacy total alert line

FLAG_NAME = "sessionstart-budget.flag"
PRODUCER = ".claude/hooks/budget-flag-guard.py"


def estimate_tokens(text: str) -> int:
    return len(text) // 3


def main() -> int:
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "sdk-cli":
        return 0

    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}

    # Resolve the project root the same way session-start-flags.sh does, so the
    # flag lands where the SessionStart scanner will read it.
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
    flags_dir = root / ".claude" / "flags"
    flag_path = flags_dir / FLAG_NAME

    stats: dict[str, int] = {}
    total = 0
    for name in SPEC_FILES:
        path = root / name
        if not path.is_file():
            continue
        try:
            stats[name] = estimate_tokens(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        total += stats[name]

    user_claude = Path.home() / ".claude" / "CLAUDE.md"
    if user_claude.is_file():
        try:
            stats["~/.claude/CLAUDE.md"] = estimate_tokens(
                user_claude.read_text(encoding="utf-8")
            )
            total += stats["~/.claude/CLAUDE.md"]
        except (OSError, UnicodeDecodeError):
            pass

    over_caps = {
        n: stats[n] - PER_FILE_CAPS[n]
        for n in stats
        if n in PER_FILE_CAPS and stats[n] > PER_FILE_CAPS[n]
    }
    over_budget = total > BUDGET_TOKENS

    # Self-resolving: under budget → remove any stale flag and stay silent.
    if not over_caps and not over_budget:
        try:
            flag_path.unlink()
        except (FileNotFoundError, OSError):
            pass
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "flag: sessionstart-budget",
        f"producer: {PRODUCER}",
        f"identity: budget:{today}",
        "verify: trim the over-cap files below their cap; the next SessionStart "
        "auto-removes this flag (or rm it manually). Rewritten each session.",
        "",
        f"SessionStart context-budget breach ({today}): spec files are eating "
        "too much of the context window.",
        "",
    ]
    if over_caps:
        lines.append("Per-file over cap:")
        for n, over in sorted(over_caps.items(), key=lambda kv: kv[1], reverse=True):
            lines.append(f"  - {n} = {stats[n]} / cap {PER_FILE_CAPS[n]}  (+{over})")
    if over_budget:
        lines.append(f"Total = {total} tokens / budget {BUDGET_TOKENS}  (+{total - BUDGET_TOKENS})")
    lines += [
        "",
        "Action: trim the files above (or run your consolidation/archive tooling). "
        "Once back under cap the flag disappears on its own.",
    ]

    try:
        flags_dir.mkdir(parents=True, exist_ok=True)
        flag_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
