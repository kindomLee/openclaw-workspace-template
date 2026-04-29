#!/bin/bash
# cron-memory-archive.sh — Mac/Linux 通用，呼叫 memory-archive.py 的 thin wrapper
# 用法：
#   bash cron-memory-archive.sh rotate          # 每日：搬超齡 journal
#   bash cron-memory-archive.sh timeline        # 每月 1 日：搬上月 events
#   bash cron-memory-archive.sh both            # 兩者都跑
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ACCESS_LOG="${MEM_ACCESS_LOG:-$HOME/.claude/state/mem-access.jsonl}"

MODE="${1:-rotate}"
case "$MODE" in
  rotate)   ARGS="--mode rotate-journal" ;;
  timeline) ARGS="--mode archive-timeline" ;;
  both)     ARGS="--mode both" ;;
  *)
    echo "usage: $0 {rotate|timeline|both}" >&2
    exit 2
    ;;
esac

cd "$PROJECT_DIR"
exec python3 scripts/memory-archive.py $ARGS \
  --respect-access-log "$ACCESS_LOG"
