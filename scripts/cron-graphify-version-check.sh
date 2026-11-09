#!/bin/bash
# cron-graphify-version-check.sh — flag when a newer graphifyy is on PyPI.
# Upgrades can change the graph schema, so the flag asks for a full rebuild.
# The flag clears itself on the next run once current == latest.
#
# Optional: does nothing until graphifyy is installed.
#
# Config:
#   GRAPHIFY_PYTHON — python that has graphifyy installed
#                     (default: graphify-out/.graphify_python, else python3)
set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/workspace.sh
source "$SELF_DIR/lib/workspace.sh"
# shellcheck source=lib/flag.sh
source "$SELF_DIR/lib/flag.sh"

WS=$(openclaw_workspace)
cd "$WS"
FLAG_NAME="graphify-upgrade"
PYTHON="${GRAPHIFY_PYTHON:-$(cat graphify-out/.graphify_python 2>/dev/null || echo python3)}"

# Read the installed version from package metadata (uv tool venvs have no pip).
CURRENT=$("$PYTHON" -c "import importlib.metadata as m; print(m.version('graphifyy'))" 2>/dev/null || true)
if [ -z "$CURRENT" ]; then
    echo "[graphify-version] graphifyy not installed for $PYTHON — skipping (optional feature)"
    exit 0
fi

LATEST=$(curl -s --max-time 15 https://pypi.org/pypi/graphifyy/json \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])" 2>/dev/null || true)
if [ -z "$LATEST" ]; then
    echo "[graphify-version] PyPI query failed (current=$CURRENT) — keeping existing flag"
    exit 0
fi

if [ "$CURRENT" = "$LATEST" ]; then
    echo "[graphify-version] up to date ($CURRENT)"
    clear_flag "$WS" "$FLAG_NAME"
    exit 0
fi

write_flag "$WS" "$FLAG_NAME" \
    "graphifyy update available: $CURRENT → $LATEST" \
    "1) uv tool upgrade graphifyy (or pip install -U graphifyy)" \
    "2) /graphify memory --mode deep — a new version may change the schema, so rebuild fully" \
    "3) Re-run bash scripts/cron-graphify-version-check.sh; this flag clears itself when current == latest"
echo "[graphify-version] flag written: $CURRENT → $LATEST"
