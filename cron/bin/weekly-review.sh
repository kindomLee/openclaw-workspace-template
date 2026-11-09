#!/bin/bash
# weekly-review.sh — weekly review checklist: classify the correction queue →
# archive resolved LEARNINGS entries → write the digest + flag + notification.
# Only classify-corrections.py calls an LLM (needs LLM_API_KEY or MINIMAX_API_KEY;
# without one it queues the entries and the digest still runs). The rest is pure scripting.
#
# Config (cron/config.env):
#   TG_BOT_TOKEN / TG_CHAT_ID (or SLACK_WEBHOOK_URL) — see scripts/lib/notify.sh
#   WEEKLY_REVIEW_NO_NOTIFY=1 — skip the notification (testing)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_DIR/cron/logs"
LOG_FILE="$LOG_DIR/weekly-review-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

if [ -f cron/config.env ]; then
  set -a; source cron/config.env; set +a
fi
# shellcheck source=../../scripts/lib/notify.sh
source "$PROJECT_DIR/scripts/lib/notify.sh"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# Keep going on failure: if classification breaks, the digest still lists
# the existing candidates.
python3 scripts/classify-corrections.py >>"$LOG_FILE" 2>&1 || log "classify-corrections failed (exit $?)"
# The digest already covers correction candidates — one flag, not two.
rm -f .claude/flags/correction-candidates.flag
python3 scripts/learnings-archive.py --apply >>"$LOG_FILE" 2>&1 || log "learnings-archive failed (exit $?)"

SUMMARY="$(python3 scripts/weekly-review-digest.py 2>>"$LOG_FILE")" || { log "digest failed"; exit 1; }
log "$SUMMARY"

if [ -z "${WEEKLY_REVIEW_NO_NOTIFY:-}" ]; then
  notify "Weekly review: $SUMMARY"
fi

find "$LOG_DIR" -name "weekly-review-*.log" -mtime +60 -delete 2>/dev/null || true
