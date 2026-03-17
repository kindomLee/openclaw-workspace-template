#!/bin/bash
# memory-dream.sh — Cold memory association ("dreaming")
# Randomly pairs unrelated memories for cross-domain insights
# Inspired by Karry's Orb AI assistant (2026-03)
set -euo pipefail

WORKSPACE="${OPENCLAW_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
MEMORY_DIR="$WORKSPACE/memory"
MEMORY_MD="$WORKSPACE/MEMORY.md"
NOTIFY=${1:-true}

# Collect recent memory snippets (last 30 days, skip archives)
SNIPPETS=$(find "$MEMORY_DIR" -maxdepth 1 -name "2*.md" -mtime -30 \
  ! -name "dreams.md" ! -name "reflections.md" ! -name "soul-proposals.md" \
  ! -name "compaction-buffer.md" 2>/dev/null | sort -R | head -8)

if [ -z "$SNIPPETS" ]; then
  echo "No memory files found to dream about"
  exit 0
fi

# Also grab some MEMORY.md sections randomly
MEMORY_SECTIONS=""
if [ -f "$MEMORY_MD" ]; then
  MEMORY_SECTIONS=$(grep -n "^## \|^### \|^- \*\*" "$MEMORY_MD" | shuf | head -5 | cut -d: -f2-)
fi

# Build the prompt
PROMPT="You are a 'dreaming' engine. Below are memory fragments from different times and domains.
Your task: find **unexpected connections** between these seemingly unrelated memories.

Rules:
- Don't just summarize — find **non-obvious links**
- Each insight in 1-2 sentences
- Only output valuable ones (if none, say 'No meaningful associations this time')
- Max 3 insights

=== Memory Fragments ===
"

for f in $SNIPPETS; do
  fname=$(basename "$f")
  content=$(head -20 "$f" 2>/dev/null || true)
  PROMPT="$PROMPT
--- $fname ---
$content
"
done

if [ -n "$MEMORY_SECTIONS" ]; then
  PROMPT="$PROMPT
--- MEMORY.md excerpts ---
$MEMORY_SECTIONS
"
fi

DATE=$(date +%Y-%m-%d)
ANNOUNCE_FLAG=""
if [ "$NOTIFY" = "true" ]; then
  ANNOUNCE_FLAG="--announce"
fi

# Trigger via OpenClaw isolated session (model-agnostic)
# Uses whatever default model is configured
openclaw cron add \
  --name "dream-${DATE}" \
  --at "5s" \
  --session isolated \
  --message "$PROMPT" \
  $ANNOUNCE_FLAG \
  --delete-after-run 2>/dev/null

echo "✅ Dream triggered via OpenClaw cron"
