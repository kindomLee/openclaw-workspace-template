#!/bin/bash
# skill-evolve-mm.sh — skill 自動進化 + keep/revert 決策（RSI 閉環）
#
# 全程走輕量 LLM endpoint（LLM_API_URL/LLM_MODEL，預設 MiniMax），不佔用互動式 agent 額度。
# Phase 1: evolve_skill.py 用 M3 產 evolved 候選 + eval 分數
# Phase 2: skill_evolve_apply.py 決策 AUTO_APPLY / FLAG / REVERT
#   - content-loss guard（硬擋）+ delta 門檻 + M3 信度
#   - M3 信度不足 → 寫 .claude/flags/skill-evolve-review.flag 等互動式覆審
#
# 預設 dry-run（不寫 skill 檔，只決策 + telemetry + flag）。
# 真要自動套用：傳 --auto-apply（謹慎，建議先累積 telemetry 觀察採納率）。
#
# Usage:
#   skill-evolve-mm.sh <skill-name> [--auto-apply]
#   skill-evolve-mm.sh --all          # 輪掃所有 skill（dry-run）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILLS_DIR="$PROJECT_DIR/.claude/skills"
EVOLVE_OUT="$PROJECT_DIR/cron/state/evolve"
LOG_DIR="$PROJECT_DIR/cron/logs"
CONFIG_FILE="$PROJECT_DIR/cron/config.env"

mkdir -p "$LOG_DIR" "$EVOLVE_OUT"
LOG_FILE="$LOG_DIR/skill-evolve-mm-$(date +%Y%m%d-%H%M%S).log"

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

AUTO_APPLY=""
[[ " $* " == *" --auto-apply "* ]] && AUTO_APPLY="--auto-apply"

evolve_one() {
  local name="$1"
  local skill="$SKILLS_DIR/$name/SKILL.md"
  if [ ! -f "$skill" ]; then
    log "❌ skill 不存在：$skill"; return 1
  fi
  local out="$EVOLVE_OUT/$name"
  mkdir -p "$out"
  log "[evolve] $name (M3, --reuse-cases --n-runs 3)"
  # --reuse-cases：固定 eval set 防分數漂移（首次無 eval_cases.json 會 fail，需先 seed）
  if [ ! -f "$out/eval_cases.json" ]; then
    log "[evolve] 首次：自動生成 eval_cases.json（之後 --reuse-cases 固定）"
    "$PY" "$PROJECT_DIR/scripts/evolve_skill.py" \
      --skill "$skill" --output "$out" --iterations 2 --n-runs 3 2>&1 | tee -a "$LOG_FILE"
  else
    "$PY" "$PROJECT_DIR/scripts/evolve_skill.py" \
      --skill "$skill" --output "$out" --iterations 2 --n-runs 3 --reuse-cases 2>&1 | tee -a "$LOG_FILE"
  fi
  log "[apply] $name 決策"
  "$PY" "$PROJECT_DIR/scripts/skill_evolve_apply.py" \
    --skill "$skill" --output "$out" $AUTO_APPLY 2>&1 | tee -a "$LOG_FILE"
}

cd "$PROJECT_DIR"

if [ "${1:-}" == "--all" ]; then
  for d in "$SKILLS_DIR"/*/; do
    n="$(basename "$d")"
    evolve_one "$n" || log "⚠️ $n 失敗，續下一個"
  done
elif [ -n "${1:-}" ] && [[ "${1:-}" != --* ]]; then
  evolve_one "$1"
else
  echo "Usage: $0 <skill-name> [--auto-apply] | --all" >&2; exit 2
fi

# TG 通知採納率摘要（best-effort）
if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  SUMMARY="$("$PY" "$PROJECT_DIR/scripts/skill_evolve_apply.py" --report 2>/dev/null || echo "report 失敗")"
  curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT_ID}" \
    --data-urlencode "text=🧬 skill-evolve 完成${AUTO_APPLY:+ (auto-apply)}
${SUMMARY}" >/dev/null 2>&1 || log "⚠️ TG 通知失敗"
fi

log "Done"
