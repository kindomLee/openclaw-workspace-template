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

# Wait for network readiness (laptops may need a few seconds after wake from
# sleep). On timeout we treat this as a soft skip (exit 0) rather than a
# loud failure — a laptop being offline or asleep is expected operating
# state, not an error worth alerting on.
MAX_WAIT=120
WAITED=0
# We don't use `curl -f`: api.anthropic.com returns 404 for unauthenticated
# GETs, and -f would treat that as failure. Any HTTP response proves the
# TCP/TLS path is up, which is all this readiness probe needs.
while ! curl -s --max-time 3 -o /dev/null https://api.anthropic.com; do
  if [ "$WAITED" -ge "$MAX_WAIT" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Skipped: network not ready after ${MAX_WAIT}s (offline/sleeping)" | tee -a "$LOG_FILE"
    exit 0
  fi
  sleep 5
  WAITED=$((WAITED + 5))
done
if [ "$WAITED" -gt 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Network ready after ${WAITED}s" | tee -a "$LOG_FILE"
fi

# Desktop notification (macOS only, silently skip on Linux)
osascript -e "display notification \"$JOB started\" with title \"Oracle Cron\"" 2>/dev/null || true

# Per-job allowed_tools:
# Prompt files may declare their tool scope on the first line, e.g.:
#   <!-- allowed_tools: Bash,Read,Grep -->
# Jobs without a declaration fall back to the safe default below.
# Inspired by the OpenClaw "per-job tool allowlists for cron tasks" pattern.
DEFAULT_TOOLS="Bash,Read,Write,Edit,Grep,Glob,WebFetch"
FIRST_LINE=$(head -1 "$PROMPT_FILE")
if [[ "$FIRST_LINE" =~ allowed_tools:[[:space:]]*([A-Za-z,]+) ]]; then
  ALLOWED_TOOLS="${BASH_REMATCH[1]}"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Per-job allowed_tools: $ALLOWED_TOOLS" | tee -a "$LOG_FILE"
else
  ALLOWED_TOOLS="$DEFAULT_TOOLS"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] No per-job allowed_tools, using default: $ALLOWED_TOOLS" | tee -a "$LOG_FILE"
fi

# Time measurement:
# - ACTIVE: CLOCK_UPTIME_RAW seconds, system-wide monotonic clock that does
#   NOT advance while the host is asleep. This is the real execution time.
# - WALL:   date +%s delta. If the host sleeps during the job, the wall
#   number gets inflated by the sleep duration; it is only a fallback.
# We print ACTIVE by default; if WALL is noticeably larger than ACTIVE we
# print both and tag it as "host sleep included" so the log is not
# misinterpreted as a runaway job.
mono_now() { /usr/bin/python3 "$SCRIPT_DIR/bin/mono_seconds.py" 2>/dev/null || date +%s; }

# Execute Claude Code
PROMPT=$(cat "$PROMPT_FILE")
START_WALL=$(date +%s)
START_MONO=$(mono_now)
# Use if/else to keep EXIT_CODE; otherwise `set -e` would abort the script
# on a non-zero claude exit before the "finished" log line could be written.
# The prompt is piped via stdin (<<<): on Linux, claude-cli 2.1.85+ treats
# `-p` as a pure --print flag and IGNORES positional prompt arguments, so
# passing the prompt as an arg would silently send an empty prompt. Stdin
# works on both macOS and Linux, keeping the wrapper cross-platform.
if claude -p \
  --allowedTools "$ALLOWED_TOOLS" \
  -d "$PROJECT_DIR" \
  <<<"$PROMPT" \
  >> "$LOG_FILE" 2>&1; then
  EXIT_CODE=0
else
  EXIT_CODE=$?
fi
ACTIVE=$(( $(mono_now) - START_MONO ))
WALL=$(( $(date +%s) - START_WALL ))

if [ "$WALL" -gt $(( ACTIVE + 60 )) ]; then
  # Wall-clock significantly exceeds active time → host slept mid-job.
  ELAPSED_MSG="active: ${ACTIVE}s, wall: ${WALL}s (host sleep included)"
else
  ELAPSED_MSG="${ACTIVE}s"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Job $JOB finished with exit code $EXIT_CODE ($ELAPSED_MSG)" | tee -a "$LOG_FILE"

# Desktop notification (macOS only)
if [ "$EXIT_CODE" -eq 0 ]; then
  osascript -e "display notification \"$JOB done (${ACTIVE}s)\" with title \"Oracle Cron\" sound name \"Glass\"" 2>/dev/null || true
else
  osascript -e "display notification \"$JOB failed (exit $EXIT_CODE)\" with title \"Oracle Cron\" sound name \"Basso\"" 2>/dev/null || true
fi

# Clean up logs older than 30 days
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true

exit "$EXIT_CODE"
