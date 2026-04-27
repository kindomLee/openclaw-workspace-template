#!/usr/bin/env bash
# cron-state.sh — 顯式記錄 cron job 執行紀錄、偵測 missed run（Mac sleep 盲點）
#
# 仿 OpenClaw 2026.4.25 cron interrupted-job pattern：
# - record interrupted as failed at original timestamp
# - skip unsafe startup replay
# - disable interrupted one-shot jobs to surface visible failure
#
# 解的問題（polymarket-bot.md 已知坑）：
#   "Mac 深度睡眠時 launchd StartCalendarInterval 不觸發，醒來只補跑 1 次
#    → 盲點，目前無 safety net"
#
# 用法（在每個 cron-wrapper.sh 開頭）：
#     source "$PROJECT_DIR/scripts/lib/cron-state.sh"
#     cron_state_record "polymarket-cron" 1800   # job_id, expected_interval_seconds
#     ... 你的 cron 邏輯 ...
#
# 環境變數：
#   CRON_STATE_DIR  覆寫 state 目錄（預設 .claude/state/cron/）
#   CRON_STATE_TG_BOT_TOKEN, CRON_STATE_TG_CHAT_ID  缺一就不發 TG（best-effort）

set -euo pipefail

_cron_state_dir() {
    # 解析順序：CRON_STATE_DIR override → CLAUDE_PROJECT_DIR → PROJECT_DIR → git toplevel → cwd
    if [[ -n "${CRON_STATE_DIR:-}" ]]; then
        echo "$CRON_STATE_DIR"
        return
    fi
    local root="${CLAUDE_PROJECT_DIR:-${PROJECT_DIR:-}}"
    if [[ -z "$root" ]]; then
        root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    fi
    echo "$root/.claude/state/cron"
}

# Internal: epoch seconds (BSD/GNU date 都吃)
_cron_state_now() {
    date -u +%s
}

# Internal: 嘗試發 TG（best-effort，失敗不中斷）
_cron_state_notify() {
    local msg="$1"
    if [[ -n "${CRON_STATE_TG_BOT_TOKEN:-}" && -n "${CRON_STATE_TG_CHAT_ID:-}" ]]; then
        curl -sS --max-time 5 -X POST \
            "https://api.telegram.org/bot${CRON_STATE_TG_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${CRON_STATE_TG_CHAT_ID}" \
            --data-urlencode "text=${msg}" >/dev/null 2>&1 || true
    fi
}

# cron_state_record <job_id> <expected_interval_seconds> [missed_threshold_multiplier]
#
# 寫入 last_run，若上次紀錄與現在差距 > expected_interval × multiplier
# → 視為 missed run，寫 "interrupted" 紀錄到 jsonl + TG 告警一次。
#
# multiplier 預設 2.5（30min cron → 75min 才算 missed，避開正常抖動）。
cron_state_record() {
    local job_id="$1"
    local expected_interval="${2:-1800}"   # 預設 30min
    local multiplier="${3:-2.5}"
    local state_dir
    state_dir="$(_cron_state_dir)"
    mkdir -p "$state_dir"

    local state_file="$state_dir/${job_id}.json"
    local log_file="$state_dir/${job_id}.runs.jsonl"
    local now
    now="$(_cron_state_now)"
    local last_run="0"

    if [[ -f "$state_file" ]]; then
        last_run="$(grep -oE '"last_run":[0-9]+' "$state_file" | head -1 | cut -d: -f2)"
        last_run="${last_run:-0}"
    fi

    # 計算 missed
    if [[ "$last_run" -gt 0 ]]; then
        local gap=$(( now - last_run ))
        local threshold
        threshold=$(awk -v i="$expected_interval" -v m="$multiplier" 'BEGIN{print int(i*m)}')
        if [[ "$gap" -gt "$threshold" ]]; then
            local missed_count
            missed_count=$(awk -v g="$gap" -v i="$expected_interval" 'BEGIN{print int(g/i) - 1}')
            local human_gap
            human_gap=$(awk -v g="$gap" 'BEGIN{
                if (g >= 3600) printf "%.1fh", g/3600
                else if (g >= 60) printf "%.0fmin", g/60
                else printf "%ds", g
            }')
            # 寫一筆 interrupted 紀錄
            printf '{"ts":%s,"event":"interrupted","job":"%s","gap_seconds":%s,"missed_count":%s,"last_run":%s}\n' \
                "$now" "$job_id" "$gap" "$missed_count" "$last_run" >> "$log_file"
            _cron_state_notify "🛑 cron-state: ${job_id} missed ${missed_count} runs (last ${human_gap} ago)"
            # stderr 給 cron log 也記一份
            echo "[cron-state] ${job_id}: missed=${missed_count} gap=${human_gap}" >&2
        fi
    fi

    # 寫一筆 normal run + 更新 last_run
    printf '{"ts":%s,"event":"run","job":"%s"}\n' "$now" "$job_id" >> "$log_file"
    cat > "$state_file" <<EOF
{"job":"$job_id","last_run":$now,"expected_interval":$expected_interval}
EOF
}

# cron_state_disable_oneshot <job_id> [reason]
#
# 標記一次性 job 為 "disabled"，下次 cron_state_check_oneshot_blocked
# 看到就直接退出 0（避免 missed 後重跑造成副作用，例如重複下單）。
cron_state_disable_oneshot() {
    local job_id="$1"
    local reason="${2:-interrupted}"
    local state_dir
    state_dir="$(_cron_state_dir)"
    mkdir -p "$state_dir"
    cat > "$state_dir/${job_id}.disabled" <<EOF
{"job":"$job_id","disabled_at":$(_cron_state_now),"reason":"$reason"}
EOF
}

# cron_state_check_oneshot_blocked <job_id>  → returns 0 if disabled (caller should exit)
cron_state_check_oneshot_blocked() {
    local job_id="$1"
    local state_dir
    state_dir="$(_cron_state_dir)"
    [[ -f "$state_dir/${job_id}.disabled" ]]
}

# cron_state_summary <job_id> [--json]  → 印最近 N 筆 run / interrupted 紀錄
cron_state_summary() {
    local job_id="$1"
    local fmt="${2:-text}"
    local state_dir
    state_dir="$(_cron_state_dir)"
    local log_file="$state_dir/${job_id}.runs.jsonl"
    if [[ ! -f "$log_file" ]]; then
        echo "no runs yet for $job_id"
        return 0
    fi
    if [[ "$fmt" == "--json" ]]; then
        tail -50 "$log_file"
    else
        echo "=== $job_id (last 20 events) ==="
        tail -20 "$log_file"
    fi
}
