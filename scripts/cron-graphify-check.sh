#!/bin/bash
# cron-graphify-check.sh — detect whether memory/ changed enough to need a
# graphify knowledge-graph rebuild. Writes a flag; the rebuild itself happens
# in the next Claude Code session (/graphify memory --update).
#
# Usage:
#   bash scripts/cron-graphify-check.sh weekly    # flag only when memory/ changed
#   bash scripts/cron-graphify-check.sh monthly   # always flag a full refresh
#
# Optional: does nothing (no flag) until graphify is installed. The graph is
# what `memory-search-hybrid.py --graph-expand` reads (graphify-out/graph.json).
#
# Config:
#   GRAPHIFY_PYTHON — python that has the `graphify` package
#                     (default: graphify-out/.graphify_python, else python3)
set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/workspace.sh
source "$SELF_DIR/lib/workspace.sh"
# shellcheck source=lib/flag.sh
source "$SELF_DIR/lib/flag.sh"

WS=$(openclaw_workspace)
cd "$WS"
FLAG_NAME="graphify"
MODE="${1:-weekly}"
PYTHON="${GRAPHIFY_PYTHON:-$(cat graphify-out/.graphify_python 2>/dev/null || true)}"
if [ -z "$PYTHON" ] && command -v graphify >/dev/null 2>&1; then
    # `uv tool install graphifyy` keeps graphify in its own venv, and
    # .graphify_python only appears after the first /graphify run.
    PYTHON="$(sed -n '1s/^#![[:space:]]*//p' "$(command -v graphify)")"
fi
PYTHON="${PYTHON:-python3}"

if ! "$PYTHON" -c "import graphify" 2>/dev/null; then
    echo "[graphify-check] graphify not installed for $PYTHON — skipping (optional feature)"
    exit 0
fi

if [ ! -f "graphify-out/graph.json" ]; then
    write_flag "$WS" "$FLAG_NAME" \
        "graphify: first build not done yet" \
        "Run /graphify memory in a Claude Code session to build the initial graph." \
        "When done: rm .claude/flags/${FLAG_NAME}.flag"
    echo "[graphify-check] first-run flag written"
    exit 0
fi

CHANGES=$("$PYTHON" - "$WS/memory" <<'PY' 2>/dev/null
import sys
from pathlib import Path
try:
    from graphify.detect import detect_incremental
    r = detect_incremental(Path(sys.argv[1]))
    print(f"{r.get('new_total', 0)}|{len(r.get('deleted_files', []))}")
except Exception as e:
    print(f"detect failed: {e}", file=sys.stderr)
    print("ERR")  # sentinel: a failed detect must never read as "0 changes"
PY
) || CHANGES="ERR"

# Detection failed → keep whatever flag exists; never auto-clear on a failure.
if ! printf '%s' "$CHANGES" | grep -Eq '^[0-9]+\|[0-9]+$'; then
    echo "[graphify-check] detect failed ($CHANGES) — keeping existing flag"
    exit 0
fi

NEW="${CHANGES%%|*}"
DEL="${CHANGES##*|}"

if [ "$MODE" = "monthly" ]; then
    write_flag "$WS" "$FLAG_NAME" \
        "graphify: monthly full refresh (new=$NEW, del=$DEL)" \
        "Optional: bash scripts/graphify-warm-cache.sh to pre-fill the extraction cache via claude -p." \
        "Then run /graphify memory --update in a Claude Code session and report node count + top god-nodes vs last month." \
        "When done: rm .claude/flags/${FLAG_NAME}.flag"
    echo "[graphify-check] monthly flag written"
    exit 0
fi

if [ "$NEW" -gt 0 ] || [ "$DEL" -gt 0 ]; then
    write_flag "$WS" "$FLAG_NAME" \
        "graphify: memory/ changed (new=$NEW, del=$DEL)" \
        "Run /graphify memory --update (it refreshes the graph manifest, so the next check reads 0)." \
        "When done: rm .claude/flags/${FLAG_NAME}.flag"
    echo "[graphify-check] flag written: new=$NEW del=$DEL"
else
    # Detection succeeded with no changes → producer-side auto-clear.
    clear_flag "$WS" "$FLAG_NAME"
    echo "[graphify-check] no changes"
fi
