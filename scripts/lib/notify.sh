#!/bin/bash
# notify.sh — pluggable notification dispatch for cron/flag scripts.
#
# Usage:
#     source "$(dirname "${BASH_SOURCE[0]}")/lib/notify.sh"
#     notify "<message>"
#
# Configuration (environment variables, typically loaded from cron/config.env):
#
#   Canonical names (recommended — consistent with cron/prompts/*.md):
#     TG_BOT_TOKEN   — Telegram bot token
#     TG_CHAT_ID     — Telegram chat id
#
#   Also supported for backwards compatibility:
#     TELEGRAM_BOT_TOKEN, NOTIFY_TARGET  (older scripts)
#     SLACK_WEBHOOK_URL                  (for Slack)
#     NOTIFY_CHANNEL                     (explicit channel override)
#
# Channel resolution order:
#   1. $NOTIFY_CHANNEL if set explicitly (telegram | slack | stdout | none)
#   2. Telegram if TG_BOT_TOKEN + TG_CHAT_ID set
#   3. Telegram if TELEGRAM_BOT_TOKEN + NOTIFY_TARGET set (legacy)
#   4. Slack if SLACK_WEBHOOK_URL set
#   5. none (silent no-op)
#
# notify is best-effort: curl failures are swallowed so cron jobs never
# abort on transient network errors.

_resolve_notify_channel() {
    if [ -n "${NOTIFY_CHANNEL:-}" ]; then
        echo "$NOTIFY_CHANNEL"
        return
    fi
    if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
        echo "telegram"
        return
    fi
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${NOTIFY_TARGET:-}" ]; then
        echo "telegram"
        return
    fi
    if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
        echo "slack"
        return
    fi
    echo "none"
}

notify() {
    local msg="$1"
    [ -z "$msg" ] && return 0
    local channel
    channel=$(_resolve_notify_channel)

    case "$channel" in
        telegram)
            # Prefer canonical TG_* naming; fall back to legacy names.
            local token="${TG_BOT_TOKEN:-${TELEGRAM_BOT_TOKEN:-}}"
            local target="${TG_CHAT_ID:-${NOTIFY_TARGET:-}}"
            if [ -z "$token" ] || [ -z "$target" ]; then
                return 0
            fi
            curl -fsS -X POST \
                "https://api.telegram.org/bot${token}/sendMessage" \
                -d "chat_id=${target}" \
                --data-urlencode "text=${msg}" \
                >/dev/null 2>&1 || true
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
            echo "[notify] unknown NOTIFY_CHANNEL='${channel}' — dropping message" >&2
            ;;
    esac
}
