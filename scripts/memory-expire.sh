#!/bin/bash
# memory-expire.sh — Auto-archive old daily memory files
# Moves daily memory files older than 30 days to archive-YYYY-MM/
#
# DEPRECATED: the daily memory-archive rotate job (scripts/memory-archive.py
# via cron-memory-archive.sh, 5-day window) supersedes this monthly 30-day
# scan — with both installed this script never finds anything. Kept for
# workspaces that opted out of the daily rotate. Not in crontab.example.
set -euo pipefail
echo "NOTE: memory-expire.sh is deprecated — prefer the daily memory-archive rotate job (see templates/HEARTBEAT.md)" >&2

WORKSPACE="${OPENCLAW_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
MEMORY_DIR="$WORKSPACE/memory"
CUTOFF_DATE=$(date -d "-30 days" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d)
DRY_RUN=${1:-false}

echo "=== Memory Expiry Check ==="
echo "Cutoff: $CUTOFF_DATE"
echo ""

EXPIRED_COUNT=0

# Find daily memory files older than cutoff
while IFS= read -r file; do
  basename=$(basename "$file" .md)
  file_date=$(echo "$basename" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' || true)
  
  if [ -n "$file_date" ] && [[ "$file_date" < "$CUTOFF_DATE" ]]; then
    EXPIRED_COUNT=$((EXPIRED_COUNT + 1))
    if [ "$DRY_RUN" = "true" ]; then
      echo "  [DRY RUN] Would archive: $file ($file_date)"
    else
      archive_month=$(echo "$file_date" | cut -d- -f1,2)
      archive_dir="$MEMORY_DIR/archive-${archive_month}"
      mkdir -p "$archive_dir"
      if [ ! -f "$archive_dir/$basename.md" ]; then
        mv "$file" "$archive_dir/"
        echo "  ✅ Archived: $basename → archive-${archive_month}/"
      fi
    fi
  fi
done < <(find "$MEMORY_DIR" -maxdepth 1 -name "2*.md" \
  ! -name "dreams.md" ! -name "reflections.md" \
  ! -name "soul-proposals.md" ! -name "compaction-buffer.md")

echo ""
echo "Total expired: $EXPIRED_COUNT"
if [ "$DRY_RUN" = "true" ]; then
  echo "(Dry run — no files moved)"
fi
