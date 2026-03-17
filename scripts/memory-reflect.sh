#!/bin/bash
# memory-reflect.sh — 記憶反刍（Reflection）
# 回顧最近的記憶，找出矛盾、更新、和需要整合的內容
# 靈感來源：Karry's Orb "反刍" 層
set -euo pipefail

MEMORY_DIR="/root/clawd/memory"
MEMORY_MD="/root/clawd/MEMORY.md"
OUTPUT="/root/clawd/memory/reflections.md"
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

# Gather MEMORY.md key sections only (not full file)
MEMORY_CONTEXT=$(grep -A 2 "^## \|^### \|^- \*\*" "$MEMORY_MD" | head -60)

PROMPT="你是記憶反刍引擎。回顧最近的記憶，對照長期記憶，找出需要處理的問題。

任務：
1. **矛盾檢測** — 最近的記憶有沒有跟長期記憶矛盾？（例：舊方案已被新方案取代但 MEMORY.md 沒更新）
2. **整合建議** — 最近的記憶中，有哪些應該提升到 MEMORY.md？（反覆出現的 pattern、新的 P0 級資訊）
3. **衰減標記** — MEMORY.md 中有哪些條目可能已經過時？

規則：
- 繁體中文
- 只列出有具體行動價值的建議（不要廢話）
- 每個建議標明：檔案、段落、建議動作
- 沒有需要處理的就說「✅ 記憶一致，無需調整」

=== 最近記憶 ===
$RECENT

=== 長期記憶 (MEMORY.md) ===
$MEMORY_CONTEXT"

# Use MiniMax API
MM_API_KEY="${MINIMAX_API_KEY:-$(cat ~/.config/minimax/api_key 2>/dev/null || echo '')}"

RESULT=$(curl -s -X POST "https://api.minimax.io/anthropic/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $MM_API_KEY" \
  -d "$(jq -n --arg prompt "$PROMPT" '{
    model: "MiniMax-M2.5",
    max_tokens: 2048,
    messages: [{role: "user", content: $prompt}]
  }')" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for block in data.get('content', []):
    if block.get('type') == 'text':
        print(block['text']); break
" 2>&1)

if [ -z "$RESULT" ] || echo "$RESULT" | grep -q "Error"; then
  echo "❌ Reflection failed: $RESULT"
  exit 1
fi

# Append to reflections.md
{
  echo ""
  echo "### $TODAY"
  echo "$RESULT"
} >> "$OUTPUT"

echo "✅ Reflection recorded to $OUTPUT"

# Notify if requested
if [ "$NOTIFY" = "true" ]; then
  openclaw message send -c telegram -t YOUR_CHAT_ID "🔄 記憶反刍

$RESULT

_Source: memory-reflect.sh_" 2>/dev/null || true
fi
