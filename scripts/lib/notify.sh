#!/bin/bash
# notify.sh — pluggable notification dispatch for cron/flag scripts.
#
# Source this and call:
#     notify "<message>"
#
# Configured via environment variables (set in crontab or ~/.openclaw/env):
#     NOTIFY_CHANNEL  — telegram | slack | stdout | none    (default: none)
#     NOTIFY_TARGET   — chat_id / webhook / channel name
#     TELEGRAM_BOT_TOKEN  — required if NOTIFY_CHANNEL=telegram
#     SLACK_WEBHOOK_URL   — required if NOTIFY_CHANNEL=slack (overrides NOTIFY_TARGET)
#
# Notify is best-effort: failures are swallowed so cron jobs never abort on them.

notify() {
    local msg="$1"
    [ -z "$msg" ] && return 0
    case "${NOTIFY_CHANNEL:-none}" in
        telegram)
            if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${NOTIFY_TARGET:-}" ]; then
                curl -fsS -X POST \
                    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
                    -d "chat_id=${NOTIFY_TARGET}" \
                    --data-urlencode "text=${msg}" \
                    >/dev/null 2>&1 || true
            fi
            ;;
        slack)
            local url="${SLACK_WEBHOOK_URL:-${NOTIFY_TARGET:-}}"
            if [ -n "$url" ]; then
                curl -fsS -X POST -H 'Content-Type: application/json' \
                    -d "{\"text\":$(printf '%s' "$msg" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}" \
                    "$url" >/dev/null 2>&1 || true
            fi
            ;;
        stdout)
            echo "[notify] $msg"
            ;;
        none|"")
            :
            ;;
        *)
            echo "[notify] unknown NOTIFY_CHANNEL='${NOTIFY_CHANNEL}' — dropping message" >&2
            ;;
    esac
}
