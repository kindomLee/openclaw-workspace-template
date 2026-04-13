#!/bin/bash
# runner.sh — Oracle Cron 通用 wrapper
# 用法：runner.sh <job-name>
# 範例：runner.sh social-summary-v2ex
#
# 流程：載入 config → 讀取 prompt → claude -p 執行 → 記錄日誌
set -euo pipefail

JOB="${1:?Usage: $0 <job-name>}"
SCRIPT_DIR="$(cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROMPT_FILE="$SCRIPT_DIR/prompts/${JOB}.md"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/${JOB}-$(date +%Y%m%d-%H%M%S).log"
CONFIG_FILE="$SCRIPT_DIR/config.env"

# 檢查 prompt 檔
if [ ! -f "$PROMPT_FILE" ]; then
  echo "ERROR: prompt file not found: $PROMPT_FILE" >&2
  exit 1
fi

# 載入環境變數
if [ -f "$CONFIG_FILE" ]; then
  set -a
  source "$CONFIG_FILE"
  set +a
fi

mkdir -p "$LOG_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting cron job: $JOB" | tee "$LOG_FILE"

# 等待網路就緒（睡眠喚醒後網路可能需要幾秒）
MAX_WAIT=60
WAITED=0
while ! curl -sf --max-time 3 https://api.anthropic.com > /dev/null 2>&1; do
  if [ "$WAITED" -ge "$MAX_WAIT" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Network not ready after ${MAX_WAIT}s, aborting" | tee -a "$LOG_FILE"
    osascript -e "display notification \"$JOB: network timeout\" with title \"Oracle Cron\" sound name \"Basso\"" 2>/dev/null || true
    exit 1
  fi
  sleep 5
  WAITED=$((WAITED + 5))
done
if [ "$WAITED" -gt 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Network ready after ${WAITED}s" | tee -a "$LOG_FILE"
fi

# macOS 通知：開始
osascript -e "display notification \"$JOB 開始執行\" with title \"Oracle Cron\"" 2>/dev/null || true

# 讀取 per-job allowedTools
# 格式：prompt 檔第一行若為 "<!-- allowed_tools: Bash,Read,Grep -->" 則使用該清單
# 否則 fallback 到安全預設
# 靈感來自 OpenClaw 2026.4.1 "Per-job tool allowlists for cron tasks"
DEFAULT_TOOLS="Bash,Read,Write,Edit,Grep,Glob,WebFetch"
FIRST_LINE=$(head -1 "$PROMPT_FILE")
if [[ "$FIRST_LINE" =~ allowed_tools:[[:space:]]*([A-Za-z,]+) ]]; then
  ALLOWED_TOOLS="${BASH_REMATCH[1]}"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Per-job allowed_tools: $ALLOWED_TOOLS" | tee -a "$LOG_FILE"
else
  ALLOWED_TOOLS="$DEFAULT_TOOLS"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] No per-job allowed_tools, using default: $ALLOWED_TOOLS" | tee -a "$LOG_FILE"
fi

# 執行 Claude Code
PROMPT=$(cat "$PROMPT_FILE")
START_TS=$(date +%s)
claude -p "$PROMPT" \
  --allowedTools "$ALLOWED_TOOLS" \
  -d "$PROJECT_DIR" \
  >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
ELAPSED=$(( $(date +%s) - START_TS ))

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Job $JOB finished with exit code $EXIT_CODE (${ELAPSED}s)" | tee -a "$LOG_FILE"

# macOS 通知：結束
if [ "$EXIT_CODE" -eq 0 ]; then
  osascript -e "display notification \"$JOB 完成 (${ELAPSED}s)\" with title \"Oracle Cron\" sound name \"Glass\"" 2>/dev/null || true
else
  osascript -e "display notification \"$JOB 失敗 (exit $EXIT_CODE)\" with title \"Oracle Cron\" sound name \"Basso\"" 2>/dev/null || true
fi

# 清理 30 天以上的舊日誌
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true

exit "$EXIT_CODE"
