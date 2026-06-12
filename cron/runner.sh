#!/bin/bash
# runner.sh — Universal cron job wrapper
# Usage: runner.sh <job-name>
# Example: runner.sh memory-reflect
#
# Flow: load config → read prompt → claude -p → log output
set -euo pipefail

JOB="${1:?Usage: $0 <job-name>}"
# Resolve symlinks step by step: bare `readlink` returns a RELATIVE target
# for relative symlinks, and BSD readlink has no -f — loop until physical.
SRC="$0"
while [ -L "$SRC" ]; do
  SRC_DIR="$(cd "$(dirname "$SRC")" && pwd)"
  SRC="$(readlink "$SRC")"
  case "$SRC" in
    /*) ;;
    *) SRC="$SRC_DIR/$SRC" ;;
  esac
done
SCRIPT_DIR="$(cd "$(dirname "$SRC")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROMPT_FILE="$SCRIPT_DIR/prompts/${JOB}.md"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/${JOB}-$(date +%Y%m%d-%H%M%S).log"
CONFIG_FILE="$SCRIPT_DIR/config.env"

# Per-job reentrancy lock. mkdir is atomic on every POSIX filesystem and —
# unlike flock(1) — exists on stock macOS. Stale locks (holder died without
# cleanup) are reclaimed by checking the recorded pid.
LOCK_ROOT="$SCRIPT_DIR/state/locks"
LOCK_DIR="$LOCK_ROOT/${JOB}.lock"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  LOCK_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Job $JOB already running (pid $LOCK_PID) — skipping this run"
    exit 0
  fi
  rm -rf "$LOCK_DIR"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Job $JOB lost lock race — skipping this run"
    exit 0
  fi
fi
echo $$ > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

# Load environment variables (before the bare-script branch so cron-state
# alerting below covers bare jobs too).
if [ -f "$CONFIG_FILE" ]; then
  set -a
  source "$CONFIG_FILE"
  set +a
fi

# Shared libs: pluggable notifications + missed-run detection.
# shellcheck source=../scripts/lib/notify.sh
source "$PROJECT_DIR/scripts/lib/notify.sh"
# shellcheck source=../scripts/lib/cron-state.sh
source "$PROJECT_DIR/scripts/lib/cron-state.sh"

# Missed-run detection (Mac deep sleep: launchd does not replay skipped
# StartCalendarInterval fires). Prompts may declare their cadence via a
# header comment, e.g. `<!-- expected_interval: 3600 -->`; default daily.
EXPECTED_INTERVAL=""
if [ -f "$PROMPT_FILE" ]; then
  EXPECTED_INTERVAL=$(grep -m1 -oE 'expected_interval:[[:space:]]*[0-9]+' "$PROMPT_FILE" | grep -oE '[0-9]+' || true)
fi
CRON_STATE_TG_BOT_TOKEN="${TG_BOT_TOKEN:-}" CRON_STATE_TG_CHAT_ID="${TG_CHAT_ID:-}" \
  cron_state_record "$JOB" "${EXPECTED_INTERVAL:-86400}" || true

# Zero-LLM escape hatch: if a bin/<job>-bare.sh exists, run it instead of the
# `claude -p` prompt. This lets a job be converted from an LLM agent to a
# deterministic bash+python implementation (faster, no model cost, no API
# quota) WITHOUT changing its plist/crontab wiring — the bare script just
# needs to land in cron/bin/. The bare script is self-contained: it loads its
# own config.env, writes its own log, and needs no network readiness wait
# (deterministic jobs don't call the model). Jobs with no bare script fall
# through to the prompt-driven path below unchanged.
# (Invoked as a child process — NOT exec'd — so the lock's EXIT trap fires.)
BARE_SCRIPT="$SCRIPT_DIR/bin/${JOB}-bare.sh"
if [ -f "$BARE_SCRIPT" ]; then
  mkdir -p "$LOG_DIR"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running zero-LLM bare implementation: $BARE_SCRIPT" | tee "$LOG_FILE"
  if bash "$BARE_SCRIPT"; then exit 0; else exit $?; fi
fi

# Check prompt file exists
if [ ! -f "$PROMPT_FILE" ]; then
  echo "ERROR: prompt file not found: $PROMPT_FILE" >&2
  exit 1
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
PROBE_URL="${LLM_PROBE_URL:-https://api.anthropic.com}"
while ! curl -s --max-time 3 -o /dev/null "$PROBE_URL"; do
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
# PATH-resolved python3 (the hardcoded /usr/bin/python3 is a CLT shim on
# macOS without Xcode tools and absent on Nix/conda-only Linux).
mono_now() { python3 "$SCRIPT_DIR/bin/mono_seconds.py" 2>/dev/null || date +%s; }

# Execute Claude Code
PROMPT=$(cat "$PROMPT_FILE")
START_WALL=$(date +%s)
START_MONO=$(mono_now)

# Job-level timeout: prevents `claude -p` from hanging indefinitely
# (historical worst case: 32 hours on a stuck reflect job).
# Default 1800s (30 min). Override globally via JOB_TIMEOUT in config.env.
# Prefers coreutils `timeout`; falls back to `gtimeout` (Homebrew coreutils).
# If neither is installed, we warn and run without a timeout — install with
# `brew install coreutils` on macOS.
JOB_TIMEOUT="${JOB_TIMEOUT:-1800}"
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_CMD=(timeout --foreground --signal=TERM --kill-after=30 "$JOB_TIMEOUT")
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_CMD=(gtimeout --foreground --signal=TERM --kill-after=30 "$JOB_TIMEOUT")
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN: neither timeout nor gtimeout available, running without job-level timeout" | tee -a "$LOG_FILE"
  TIMEOUT_CMD=()
fi

# Use if/else to keep EXIT_CODE; otherwise `set -e` would abort the script
# on a non-zero claude exit before the "finished" log line could be written.
# The prompt is piped via stdin (<<<): on Linux, claude-cli 2.1.85+ treats
# `-p` as a pure --print flag and IGNORES positional prompt arguments, so
# passing the prompt as an arg would silently send an empty prompt. Stdin
# works on both macOS and Linux, keeping the wrapper cross-platform.
if "${TIMEOUT_CMD[@]}" claude -p \
  --allowedTools "$ALLOWED_TOOLS" \
  -d "$PROJECT_DIR" \
  <<<"$PROMPT" \
  >> "$LOG_FILE" 2>&1; then
  EXIT_CODE=0
else
  EXIT_CODE=$?
fi

# Timeout detection: 124 = SIGTERM fired, 137 = SIGKILL after --kill-after
TIMED_OUT=0
if [ "$EXIT_CODE" -eq 124 ] || [ "$EXIT_CODE" -eq 137 ]; then
  TIMED_OUT=1
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] TIMEOUT: job exceeded ${JOB_TIMEOUT}s and was killed (exit $EXIT_CODE)" | tee -a "$LOG_FILE"
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
elif [ "$TIMED_OUT" -eq 1 ]; then
  osascript -e "display notification \"$JOB TIMEOUT (${JOB_TIMEOUT}s)\" with title \"Oracle Cron\" sound name \"Basso\"" 2>/dev/null || true
else
  osascript -e "display notification \"$JOB failed (exit $EXIT_CODE)\" with title \"Oracle Cron\" sound name \"Basso\"" 2>/dev/null || true
fi

# Failure alerting via scripts/lib/notify.sh (never fail silently — the
# previous desktop notification is macOS-only and invisible on Linux).
# When killed by timeout, `claude -p` doesn't get to send its own report,
# so the runner sends the fallback alert itself.
if [ "$TIMED_OUT" -eq 1 ]; then
  notify "⏰ Cron timeout: ${JOB} exceeded ${JOB_TIMEOUT}s and was killed (log: $(basename "$LOG_FILE"))"
elif [ "$EXIT_CODE" -ne 0 ]; then
  notify "❌ Cron job ${JOB} failed with exit ${EXIT_CODE} (log: $(basename "$LOG_FILE"))"
fi

# Clean up logs older than 30 days
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true

# Persistent append-only logs (launchd StandardOutPath targets and cron
# redirect targets) always have a fresh mtime, so -mtime +30 never matches
# them — size-truncate instead, keeping the most recent ~1MB.
for f in "$LOG_DIR"/*-launchd.log "$LOG_DIR"/cron-*.log; do
  [ -f "$f" ] || continue
  if [ "$(wc -c < "$f")" -gt 5242880 ]; then
    tail -c 1048576 "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  fi
done

exit "$EXIT_CODE"
