#!/bin/bash
# Quick workspace health check
# Run after bootstrap or anytime to verify memory system is working
set -euo pipefail

WORKSPACE="${OPENCLAW_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
ERRORS=0
WARNINGS=0

echo "=== Workspace Health Check ==="
echo "Workspace: $WORKSPACE"
echo ""

# 1. Directory structure
echo "--- Structure ---"
for dir in memory .learnings scripts skills tmp; do
  if [ -d "$WORKSPACE/$dir" ]; then
    echo "  ✅ $dir/"
  else
    echo "  ❌ $dir/ missing"
    ERRORS=$((ERRORS+1))
  fi
done

# 2. Core files
echo ""
echo "--- Core Files ---"
for f in AGENTS.md SOUL.md USER.md MEMORY.md BOOTSTRAP.md HEARTBEAT.md; do
  if [ -f "$WORKSPACE/$f" ]; then
    echo "  ✅ $f"
  else
    echo "  ⚠️  $f missing"
    WARNINGS=$((WARNINGS+1))
  fi
done

# 3. Memory scripts
echo ""
echo "--- Memory Scripts ---"
for script in memory-reflect.sh memory-dream.sh memory-expire.sh; do
  path="$WORKSPACE/scripts/$script"
  if [ -f "$path" ]; then
    if [ -x "$path" ]; then
      echo "  ✅ $script (executable)"
    else
      echo "  ⚠️  $script (not executable — run: chmod +x $path)"
      WARNINGS=$((WARNINGS+1))
    fi
  else
    echo "  ❌ $script missing"
    ERRORS=$((ERRORS+1))
  fi
done

# 4. Cron scripts
echo ""
echo "--- Cron Scripts ---"
for script in cron-memory-sync.sh cron-memory-janitor.sh; do
  path="$WORKSPACE/scripts/$script"
  if [ -f "$path" ]; then
    # Check for common flag errors
    if grep -q "\-\-workspace" "$path" 2>/dev/null; then
      echo "  ⚠️  $script uses --workspace flag (use OPENCLAW_WORKSPACE env var instead)"
      WARNINGS=$((WARNINGS+1))
    elif grep -q "\-\-state-dir" "$path" 2>/dev/null; then
      echo "  ⚠️  $script uses --state-dir flag (use --profile instead)"
      WARNINGS=$((WARNINGS+1))
    else
      echo "  ✅ $script"
    fi
  else
    echo "  ⚠️  $script not found (optional but recommended)"
    WARNINGS=$((WARNINGS+1))
  fi
done

# 5. External tools
echo ""
echo "--- External Tools ---"
if command -v memory-tools &>/dev/null; then
  echo "  ✅ memory-tools ($(memory-tools --help 2>&1 | head -1))"
else
  echo "  ⚠️  memory-tools not in PATH (optional but recommended for janitor)"
  WARNINGS=$((WARNINGS+1))
fi

if command -v openclaw &>/dev/null; then
  echo "  ✅ openclaw ($(openclaw --version 2>&1 | head -1))"
else
  echo "  ❌ openclaw not found"
  ERRORS=$((ERRORS+1))
fi

# 6. Cron entries
echo ""
echo "--- Cron Entries ---"
CRON_ENTRIES=$(crontab -l 2>/dev/null | grep -c "$WORKSPACE" || true)
echo "  Found: $CRON_ENTRIES entries referencing this workspace"

EXPECTED_JOBS=("memory-sync" "memory-janitor" "memory-reflect" "memory-dream" "memory-expire")
for job in "${EXPECTED_JOBS[@]}"; do
  if crontab -l 2>/dev/null | grep -q "$job"; then
    echo "  ✅ $job scheduled"
  else
    echo "  ❌ $job not in crontab"
    ERRORS=$((ERRORS+1))
  fi
done

# 7. Today's memory
echo ""
echo "--- Memory Status ---"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d 2>/dev/null || echo "unknown")

if [ -f "$WORKSPACE/memory/$TODAY.md" ]; then
  SIZE=$(wc -c < "$WORKSPACE/memory/$TODAY.md")
  echo "  ✅ Today ($TODAY): ${SIZE} bytes"
else
  echo "  ⚠️  No memory for today ($TODAY)"
fi

if [ "$YESTERDAY" != "unknown" ] && [ -f "$WORKSPACE/memory/$YESTERDAY.md" ]; then
  SIZE=$(wc -c < "$WORKSPACE/memory/$YESTERDAY.md")
  echo "  ✅ Yesterday ($YESTERDAY): ${SIZE} bytes"
else
  echo "  ⚠️  No memory for yesterday"
fi

TOTAL_MEMORIES=$(find "$WORKSPACE/memory" -maxdepth 1 -name "20*.md" 2>/dev/null | wc -l)
echo "  📊 Total daily memory files: $TOTAL_MEMORIES"

# 8. File ownership (multi-instance check)
echo ""
echo "--- File Ownership ---"
ROOT_FILES=$(find "$WORKSPACE" -maxdepth 2 -user root 2>/dev/null | wc -l)
if [ "$ROOT_FILES" -eq 0 ]; then
  echo "  ✅ No root-owned files"
else
  echo "  ⚠️  $ROOT_FILES root-owned files found (may cause permission issues)"
  find "$WORKSPACE" -maxdepth 2 -user root 2>/dev/null | head -5 | while read -r f; do
    echo "    → $f"
  done
  WARNINGS=$((WARNINGS+1))
fi

# 9. Skill symlinks check
echo ""
echo "--- Skills ---"
SYMLINK_COUNT=0
for skill in "$WORKSPACE/skills"/*/; do
  [ -d "$skill" ] || continue
  name=$(basename "$skill")
  if [ -L "${skill%/}" ]; then
    echo "  ⚠️  $name is a symlink (may be root-owned, consider copying)"
    SYMLINK_COUNT=$((SYMLINK_COUNT+1))
  else
    echo "  ✅ $name"
  fi
done
[ "$SYMLINK_COUNT" -gt 0 ] && WARNINGS=$((WARNINGS+1))

# Summary
echo ""
echo "=== Summary ==="
if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
  echo "✨ All checks passed — workspace is healthy!"
elif [ "$ERRORS" -eq 0 ]; then
  echo "⚠️  $WARNINGS warnings (non-critical)"
else
  echo "❌ $ERRORS errors, $WARNINGS warnings — needs attention"
fi
