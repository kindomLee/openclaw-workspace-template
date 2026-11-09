#!/bin/bash
# curate-memory.sh — hourly closed-day backlog check (pure bash, no LLM).
#
# Raises .claude/flags/curate-memory.flag when a journal from yesterday or
# earlier hasn't been curated yet; the next Claude Code session runs the
# /curate-memory skill on it. Starting `claude -p` every hour just to find
# nothing new costs more than everything else in cron/ combined, so the
# detection lives here and the LLM only runs when there is real work.
#
#   - Today's journal is never counted: a live file keeps changing, so a
#     flag based on it could never settle.
#   - State is the date in cron/state/curate-memory.json (last_curated_date),
#     not file mtimes. The skill's wrap-up step advances it.
#   - The flag carries an identity (the pending dates): the same backlog is
#     not rewritten or re-notified. No backlog → the flag is removed.
#
# Config: TG_BOT_TOKEN / TG_CHAT_ID (or SLACK_WEBHOOK_URL) — scripts/lib/notify.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_DIR/cron/logs"
LOG_FILE="$LOG_DIR/curate-memory-$(date +%Y%m%d-%H%M%S).log"
STATE_DIR="$PROJECT_DIR/cron/state"
STATE_FILE="$STATE_DIR/curate-memory.json"
FLAG_DIR="$PROJECT_DIR/.claude/flags"
FLAG_FILE="$FLAG_DIR/curate-memory.flag"
CONFIG_FILE="$PROJECT_DIR/cron/config.env"

mkdir -p "$LOG_DIR" "$FLAG_DIR" "$STATE_DIR"

if [ -f "$CONFIG_FILE" ]; then
  set -a
  source "$CONFIG_FILE"
  set +a
fi
# shellcheck source=../../scripts/lib/notify.sh
source "$PROJECT_DIR/scripts/lib/notify.sh"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# state_set <key> <value|null> — update one field of the state file
state_set() {
  python3 - "$STATE_FILE" "$1" "$2" <<'PY'
import json, sys
path, key, val = sys.argv[1:4]
try:
    d = json.load(open(path))
except Exception:
    d = {}
d[key] = None if val == "null" else val
json.dump(d, open(path, "w"), ensure_ascii=False, indent=2)
PY
}
state_get() {
  python3 -c "import json, sys; print(json.load(open(sys.argv[1])).get(sys.argv[2]) or '')" "$STATE_FILE" "$1" 2>/dev/null || true
}

cd "$PROJECT_DIR"
log "curate-memory check (closed-day backlog, no LLM)"

TODAY="$(date +%Y-%m-%d)"
YESTERDAY="$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d yesterday +%Y-%m-%d)"

# Missing state → start from yesterday, so the first run doesn't flag the
# whole history.
LAST_CURATED="$(state_get last_curated_date)"
if [ -z "$LAST_CURATED" ]; then
  LAST_CURATED="$YESTERDAY"
  state_set last_curated_date "$LAST_CURATED"
  log "no state → last_curated_date=$LAST_CURATED"
fi

# Backlog: journal dates after last_curated_date and before today
# (YYYY-MM-DD compares correctly as a string).
PENDING=""
for f in memory/20??-??-??.md; do
  [ -e "$f" ] || continue
  base="$(basename "$f" .md)"
  if [[ "$base" > "$LAST_CURATED" && "$base" < "$TODAY" ]]; then
    PENDING="$PENDING$f"$'\n'
  fi
done
PENDING="$(printf '%s' "$PENDING" | sed '/^$/d' | sort)"
state_set last_check_at "$(date '+%Y-%m-%dT%H:%M:%S%z')"

if [ -z "$PENDING" ]; then
  log "no backlog (last_curated_date=$LAST_CURATED)"
  if [ -f "$FLAG_FILE" ]; then
    rm -f "$FLAG_FILE"
    log "removed flag"
  fi
  exit 0
fi

COUNT="$(printf '%s\n' "$PENDING" | wc -l | tr -d ' ')"
DATES="$(printf '%s\n' "$PENDING" | sed 's|memory/||;s|\.md||' | paste -sd, -)"
IDENTITY="curate:$DATES"
log "backlog: $COUNT file(s), identity=$IDENTITY"

if [ -f "$FLAG_FILE" ] && [ "$(sed -n 's/^identity: //p' "$FLAG_FILE" | head -1)" = "$IDENTITY" ]; then
  log "flag unchanged → no rewrite, no notify"
  exit 0
fi

TMP="$(mktemp)"
{
  echo "curate-memory: $COUNT closed-day journal(s) not curated yet (last_curated_date=$LAST_CURATED)"
  echo "Run the /curate-memory skill on these files, then do its Wrap-up step: advance last_curated_date in cron/state/curate-memory.json first, then rm .claude/flags/curate-memory.flag (removing only the flag makes the next hourly check raise it again)."
  echo "identity: $IDENTITY"
  echo ""
  printf '%s\n' "$PENDING" | sed 's|^|  - |'
} > "$TMP"
mv -f "$TMP" "$FLAG_FILE"
log "wrote flag"

if [ "$(state_get notified_identity)" != "$IDENTITY" ]; then
  notify "curate-memory: $COUNT closed-day journal(s) to curate ($DATES)" || true
  state_set notified_identity "$IDENTITY"
  log "notified"
fi

find "$LOG_DIR" -name "curate-memory-*.log" -mtime +30 -delete 2>/dev/null || true
exit 0
