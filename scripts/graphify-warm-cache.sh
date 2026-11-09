#!/bin/bash
# graphify-warm-cache.sh — pre-fill graphify's semantic extraction cache for
# memory/ using graphify's own `extract --backend claude-cli`.
#
# Runs through the local `claude -p` (your Claude subscription, not an API
# key). The cache is the same one `/graphify memory --update` reads, so after
# this the interactive rebuild only handles cache misses (usually none).
#
# Usage:
#   bash scripts/graphify-warm-cache.sh
#   then in a Claude Code session: /graphify memory --update
#
# Config:
#   GRAPHIFY_BIN              — graphify CLI (default: `graphify` on PATH)
#   GRAPHIFY_CLAUDE_CLI_MODEL — model for extraction (default: sonnet)
set -euo pipefail
cd "$(dirname "$0")/.."

GRAPHIFY="${GRAPHIFY_BIN:-$(command -v graphify || true)}"
if [ -z "$GRAPHIFY" ]; then
    echo "graphify CLI not found — install with: uv tool install graphifyy" >&2
    exit 1
fi
export GRAPHIFY_CLAUDE_CLI_MODEL="${GRAPHIFY_CLAUDE_CLI_MODEL:-sonnet}"

"$GRAPHIFY" extract memory --backend claude-cli --no-cluster
echo ""
echo "Cache warmed. Next: run /graphify memory --update in a Claude Code session."
