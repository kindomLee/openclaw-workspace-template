#!/bin/bash
# hall-tagger.sh — Retroactively tag all memory/*.md entries with Hall classification
# Usage: ./hall-tagger.sh [--dry-run] [--days N]
# Run manually or via cron. Safe to run multiple times (idempotent).
set -euo pipefail

# Portable: derive from script location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MEMORY_DIR="${PROJECT_DIR}/memory"
DRY_RUN=false
DAYS_BACK=7

for arg in "$@"; do
    case $arg in
        --dry-run) DRY_RUN=true; shift ;;
        --days) DAYS_BACK="$2"; shift 2 ;;
    esac
done

# ── Hall Classification Function ────────────────────────────
hall_tag() {
    local text="$1"
    # Portable lowercase (bash 3.2 on macOS has no ${var,,} expansion).
    local t
    t=$(printf '%s' "$text" | tr '[:upper:]' '[:lower:]')

    if echo "$t" | grep -qE '(決定|决策|選擇|選用|採用|decided|chose|selected|adopted|locked|settled)'; then
        echo "hall_facts"
    elif echo "$t" | grep -qE '(發現|研究|評估|分析|實驗|discover|found|research|analyze|evaluate|experiment|studied)'; then
        echo "hall_discoveries"
    elif echo "$t" | grep -qE '(偏好|喜歡|想要|習慣|prefer|like|want|habit|aversion|dislike)'; then
        echo "hall_preferences"
    elif echo "$t" | grep -qE '(建議|推薦|應該|最好|recommend|suggest|should|advice|tip|propose)'; then
        echo "hall_advice"
    else
        echo "hall_events"
    fi
}

# ── Process a single file ─────────────────────────────────
process_file() {
    local filepath="$1"
    local dry="$2"
    local changed=false
    local tmp_file
    tmp_file=$(mktemp)

    while IFS= read -r line; do
        if [ -z "$line" ] || [[ "$line" =~ ^# ]]; then
            echo "$line"
        elif [[ "$line" =~ ^\[hall_ ]]; then
            # Already tagged, preserve as-is
            echo "$line"
        elif [[ "$line" =~ ^([[:space:]]*)([-*])[[:space:]]+(.+)$ ]]; then
            # Capture the whole bullet body (including any [[wikilinks]]);
            # the earlier `[^[]+` pattern stopped at the first `[`, so any
            # entry containing an inline wikilink silently lost its hall tag.
            local content="${BASH_REMATCH[3]}"
            local tag
            tag=$(hall_tag "$content")
            local indent="${BASH_REMATCH[1]}"
            local bullet="${BASH_REMATCH[2]}"
            if [ "$dry" = "false" ]; then
                echo "${indent}[$tag] ${bullet} ${content}"
            else
                echo "${indent}[$tag] DRY: ${bullet} ${content}"
            fi
            changed=true
        else
            echo "$line"
        fi
    done < "$filepath" > "$tmp_file"

    if [ "$changed" = "true" ] && [ "$dry" = "false" ]; then
        mv "$tmp_file" "$filepath"
        echo "Tagged: $filepath"
    elif [ "$changed" = "true" ] && [ "$dry" = "true" ]; then
        echo "DRY RUN: $filepath"
        cat "$tmp_file"
        rm "$tmp_file"
    else
        rm "$tmp_file"
        echo "No changes: $filepath"
    fi
}

# ── Main ───────────────────────────────────────────────────
echo "[hall-tagger] Starting$([ "$DRY_RUN" = "true" ] && echo " (DRY RUN)") --days $DAYS_BACK"

find "$MEMORY_DIR" -name "*.md" -mtime "-${DAYS_BACK}" | sort | while read -r f; do
    process_file "$f" "$DRY_RUN"
done

echo "[hall-tagger] Done"
