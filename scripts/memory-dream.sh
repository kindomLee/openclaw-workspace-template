#!/bin/bash
# memory-dream.sh — 冷記憶聯想（「做夢」機制）
# 從不同領域的記憶中隨機抽取，讓 LLM 找交叉洞察
# 靈感來源：Karry's Orb AI assistant (2026-03-17)
set -euo pipefail

MEMORY_DIR="/root/clawd/memory"
MEMORY_MD="/root/clawd/MEMORY.md"
REFERENCE_DIR="/root/clawd/reference"
OUTPUT="/root/clawd/memory/dreams.md"
NOTIFY=${1:-true}  # pass 'false' to skip telegram notification

# Collect all memory snippets (recent 30 days, skip archives)
SNIPPETS=$(find "$MEMORY_DIR" -name "2026-*.md" -mtime -30 ! -path "*/archive*" ! -name "dreams.md" | sort -R | head -8)

# Also grab some MEMORY.md sections randomly
MEMORY_SECTIONS=$(grep -n "^## \|^### \|^- \*\*" "$MEMORY_MD" | shuf | head -5 | cut -d: -f2-)

# Build the prompt
PROMPT="你是一個「做夢」引擎。以下是來自不同時間、不同領域的記憶碎片。
你的任務是找出這些看似不相關的記憶之間的**意外共通點**或**跨領域洞察**。

規則：
- 不要只做摘要，要找到**非顯而易見的連結**
- 每個洞察用 1-2 句話描述
- 只輸出有價值的（如果真的沒有就說「本次無有效聯想」）
- 繁體中文
- 最多 3 個洞察

=== 記憶碎片 ===
"

# Append file snippets (first 20 lines of each)
for f in $SNIPPETS; do
  basename=$(basename "$f")
  content=$(head -20 "$f" 2>/dev/null || true)
  PROMPT="$PROMPT
--- $basename ---
$content
"
done

# Append MEMORY.md sections
PROMPT="$PROMPT
--- MEMORY.md 摘錄 ---
$MEMORY_SECTIONS
"

# Run through MiniMax API (cheapest, good enough for creative association)
MM_API_KEY="${MINIMAX_API_KEY:-$(cat ~/.config/minimax/api_key 2>/dev/null || echo '')}"

if [ -z "$MM_API_KEY" ]; then
  echo "❌ No MiniMax API key"
  exit 1
fi

RESULT=$(curl -s -X POST "https://api.minimax.io/anthropic/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $MM_API_KEY" \
  -d "$(jq -n --arg prompt "$PROMPT" '{
    model: "MiniMax-M2.5",
    max_tokens: 1024,
    messages: [{role: "user", content: $prompt}]
  }')" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for block in data.get('content', []):
    if block.get('type') == 'text':
        print(block['text']); break
" 2>&1)

if [ -z "$RESULT" ] || echo "$RESULT" | grep -q "Error"; then
  echo "❌ Dream failed: $RESULT"
  exit 1
fi

# Append to dreams.md
DATE=$(date +%Y-%m-%d)
{
  echo ""
  echo "### $DATE"
  echo "$RESULT"
} >> "$OUTPUT"

echo "✅ Dream recorded to $OUTPUT"

# Notify if requested
if [ "$NOTIFY" = "true" ]; then
  openclaw message send -c telegram -t YOUR_CHAT_ID "🌙 冷記憶聯想（做夢機制）

$RESULT

_Source: memory-dream.sh_" 2>/dev/null || true
fi
