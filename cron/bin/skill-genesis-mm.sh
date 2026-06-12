#!/bin/bash
# skill-genesis-mm.sh — 從 LEARNINGS 萃取「新 skill 候選」（生成軸，與 evolve 互補）
#
# 全程走輕量 LLM endpoint（LLM_API_URL/LLM_MODEL，預設 MiniMax），不佔用互動式 agent 額度。
# 流程：skill_genesis_mine.py 掃 LEARNINGS manual_repeat/best_practice(rc≥2, 有步驟)
#   → M3 強制三分類 SKILL/PRINCIPLE/ONE_OFF + 三問 → 對既有 skill 去重
#   → **絕不自動建檔**：worth 的寫 cron/state/skill-genesis/<slug>/SKILL.draft.md + flag。
# 人工覆審 flag → 採納則 skill-creator scaffold → 進 evolve 精煉。
#
# 建議排程：每週一次，接在 weekly memory-reflect 之後（LEARNINGS 更新慢，不需高頻）。
# 預設只產草稿 + flag，不動 .claude/skills/。
#
# Usage: skill-genesis-mm.sh [--min-rc N] [--gate F]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_DIR/cron/logs"
CONFIG_FILE="$PROJECT_DIR/cron/config.env"

mkdir -p "$LOG_DIR" "$PROJECT_DIR/cron/state/skill-genesis"
LOG_FILE="$LOG_DIR/skill-genesis-mm-$(date +%Y%m%d-%H%M%S).log"

if [ -f "$CONFIG_FILE" ]; then
  set -a; source "$CONFIG_FILE"; set +a
else
  echo "ERROR: $CONFIG_FILE not found" >&2; exit 1
fi
: "${LLM_API_KEY:=${MINIMAX_API_KEY:-}}"
[ -n "$LLM_API_KEY" ] || { echo "ERROR: LLM_API_KEY (or legacy MINIMAX_API_KEY) not set in cron/config.env" >&2; exit 1; }
export LLM_API_KEY

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# Interpreter：預設 PATH 上的 python3（需 httpx）；可用 PY_BIN 覆寫
PY="${PY_BIN:-$(command -v python3)}"

# 預設參數，可被 CLI 覆寫
MIN_RC="2"; GATE="0.7"
while [ $# -gt 0 ]; do
  case "$1" in
    --min-rc) MIN_RC="$2"; shift 2;;
    --gate) GATE="$2"; shift 2;;
    *) shift;;
  esac
done

cd "$PROJECT_DIR"
log "[genesis] 掃 LEARNINGS（min-rc=$MIN_RC, gate=$GATE）"
"$PY" "$PROJECT_DIR/scripts/skill_genesis_mine.py" --min-rc "$MIN_RC" --gate "$GATE" 2>&1 | tee -a "$LOG_FILE"

# TG 通知摘要（best-effort）
if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  SUMMARY="$("$PY" "$PROJECT_DIR/scripts/skill_genesis_mine.py" --report 2>/dev/null || echo "report 失敗")"
  DRAFTS="$(ls "$PROJECT_DIR"/.claude/flags/skill-genesis-*.flag 2>/dev/null | wc -l | tr -d ' ')"
  curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT_ID}" \
    --data-urlencode "text=🌱 skill-genesis 完成（${DRAFTS} 個草稿待覆審）
${SUMMARY}" >/dev/null 2>&1 || log "⚠️ TG 通知失敗"
fi

log "Done"
