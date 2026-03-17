#!/bin/bash
# memory-reflect.sh — Memory rumination (reflection)
# Reviews recent memories against long-term memory for contradictions
# Inspired by Karry's Orb "rumination" layer
set -euo pipefail

WORKSPACE="${OPENCLAW_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
MEMORY_DIR="$WORKSPACE/memory"
MEMORY_MD="$WORKSPACE/MEMORY.md"
NOTIFY=${1:-true}

TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d)

# Gather recent memory (today + yesterday)
RECENT=""
for f in "$MEMORY_DIR/$TODAY.md" "$MEMORY_DIR/$YESTERDAY.md"; do
  [ -f "$f" ] && RECENT="$RECENT
--- $(basename "$f") ---
$(cat "$f")
"
done

if [ -z "$RECENT" ]; then
  echo "No recent memory to reflect on"
  exit 0
fi

# Gather MEMORY.md key sections (not full file to keep prompt small)
MEMORY_CONTEXT=""
if [ -f "$MEMORY_MD" ]; then
  MEMORY_CONTEXT=$(grep -A 2 "^## \|^### \|^- \*\*" "$MEMORY_MD" | head -60)
fi

PROMPT="You are a memory rumination engine. Review recent memories against long-term memory.

Tasks:
1. **Contradiction detection** — Any conflicts between recent and long-term memory?
2. **Integration suggestions** — What from recent memory should be promoted to MEMORY.md?
3. **Decay markers** — What in MEMORY.md might be outdated?

Rules:
- Only list suggestions with concrete action value
- For each: file, section, suggested action
- If nothing needs attention, say 'Memory consistent, no adjustment needed'

=== Recent Memory ===
$RECENT

=== Long-term Memory (MEMORY.md key sections) ===
$MEMORY_CONTEXT"

ANNOUNCE_FLAG=""
if [ "$NOTIFY" = "true" ]; then
  ANNOUNCE_FLAG="--announce"
fi

# Trigger via OpenClaw isolated session (model-agnostic)
openclaw cron add \
  --name "reflect-${TODAY}" \
  --at "5s" \
  --session isolated \
  --message "$PROMPT" \
  $ANNOUNCE_FLAG \
  --delete-after-run 2>/dev/null

echo "✅ Reflection triggered via OpenClaw cron"
