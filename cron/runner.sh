#!/bin/bash
# runner.sh — Universal cron job wrapper
# Usage: runner.sh <job-name>
# Example: runner.sh memory-reflect
#
# Flow: load config → read prompt → claude -p → log output
set -euo pipefail

JOB="${1:?Usage: $0 <job-name>}"
SCRIPT_DIR="$(cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROMPT_FILE="$SCRIPT_DIR/prompts/${JOB}.md"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/${JOB}-$(date +%Y%m%d-%H%M%S).log"
CONFIG_FILE="$SCRIPT_DIR/config.env"

# Check prompt file exists
if [ ! -f "$PROMPT_FILE" ]; then
  echo "ERROR: prompt file not found: $PROMPT_FILE" >&2
  exit 1
fi

# Load environment variables
if [ -f "$CONFIG_FILE" ]; then
  set -a
  source "$CONFIG_FILE"
  set +a
fi

mkdir -p "$LOG_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting cron job: $JOB" | tee "$LOG_FILE"

# Wait for network (may need a few seconds after wake from sleep)
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

# Desktop notification (macOS only, silently skip on Linux)
osascript -e "display notification \"$JOB started\" with title \"Oracle Cron\"" 2>/dev/null || true

# Execute Claude Code
PROMPT=$(cat "$PROMPT_FILE")
START_TS=$(date +%s)
claude -p "$PROMPT" \
  --allowedTools "Bash,Read,Write,Edit,Grep,Glob,WebFetch" \
  -d "$PROJECT_DIR" \
  >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
ELAPSED=$(( $(date +%s) - START_TS ))

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Job $JOB finished with exit code $EXIT_CODE (${ELAPSED}s)" | tee -a "$LOG_FILE"

# Desktop notification (macOS only)
if [ "$EXIT_CODE" -eq 0 ]; then
  osascript -e "display notification \"$JOB done (${ELAPSED}s)\" with title \"Oracle Cron\" sound name \"Glass\"" 2>/dev/null || true
else
  osascript -e "display notification \"$JOB failed (exit $EXIT_CODE)\" with title \"Oracle Cron\" sound name \"Basso\"" 2>/dev/null || true
fi

# Clean up logs older than 30 days
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true

exit "$EXIT_CODE"
