#!/bin/bash
# memory-expire.sh — P2 記憶過期自動歸檔
# P2 條目在 MEMORY.md 中超過 30 天未被引用就移到 reference/expired-memory.md
set -euo pipefail

MEMORY_MD="/root/clawd/MEMORY.md"
EXPIRED_FILE="/root/clawd/reference/expired-memory.md"
ARCHIVE_DIR="/root/clawd/memory"
CUTOFF_DATE=$(date -d "-30 days" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d)
DRY_RUN=${1:-false}

echo "=== Memory Expiry Check ==="
echo "Cutoff: $CUTOFF_DATE"
echo ""

# Find P2 entries with dates in MEMORY.md
# P2 entries typically have a date suffix like (03-09) or dates in text
EXPIRED_COUNT=0

# Check daily memory files older than 30 days that aren't archived
while IFS= read -r file; do
  basename=$(basename "$file" .md)
  # Extract date from filename
  file_date=$(echo "$basename" | grep -oP '^\d{4}-\d{2}-\d{2}' || true)
  
  if [ -n "$file_date" ] && [[ "$file_date" < "$CUTOFF_DATE" ]]; then
    EXPIRED_COUNT=$((EXPIRED_COUNT + 1))
    if [ "$DRY_RUN" = "true" ]; then
      echo "  [DRY RUN] Would archive: $file ($file_date)"
    else
      # Move to archive
      archive_month=$(echo "$file_date" | cut -d- -f1,2)
      archive_dir="$ARCHIVE_DIR/archive-${archive_month}"
      mkdir -p "$archive_dir"
      if [ ! -f "$archive_dir/$basename.md" ]; then
        mv "$file" "$archive_dir/"
        echo "  ✅ Archived: $basename → archive-${archive_month}/"
      fi
    fi
  fi
done < <(find "$ARCHIVE_DIR" -maxdepth 1 -name "2026-*.md" ! -name "dreams.md" ! -name "soul-proposals.md" ! -name "compaction-buffer.md")

echo ""
echo "Total expired: $EXPIRED_COUNT"
if [ "$DRY_RUN" = "true" ]; then
  echo "(Dry run — no files moved)"
fi
