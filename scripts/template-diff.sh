#!/usr/bin/env bash
# template-diff.sh — Compare template files against an existing workspace.
#
# Usage:
#   bash scripts/template-diff.sh /path/to/workspace          # summary only
#   bash scripts/template-diff.sh /path/to/workspace --full    # show diffs
#
# Compares every file under templates/ with the corresponding file in
# the target workspace. Reports: identical / differs / missing in workspace.
# Skips user-owned files (USER.md, SOUL.md, IDENTITY.md, TOOLS.md, MEMORY.md)
# since those are intentionally different.
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(cd "$SCRIPT_DIR/../templates" && pwd)"

WORKSPACE="${1:-}"
FULL_DIFF=0
[ "${2:-}" = "--full" ] && FULL_DIFF=1

if [ -z "$WORKSPACE" ]; then
  echo "Usage: $0 <workspace-path> [--full]"
  exit 1
fi

if [ ! -d "$WORKSPACE" ]; then
  echo -e "${RED}Error: workspace not found: $WORKSPACE${NC}" >&2
  exit 1
fi

# Files that are user-owned and should NOT be compared.
SKIP_FILES=(
  "USER.md"
  "SOUL.md"
  "IDENTITY.md"
  "TOOLS.md"
  "MEMORY.md"
  "MEMORY_COMPACT.md"
  "workspace.spec"
)

is_skipped() {
  local rel="$1"
  for skip in "${SKIP_FILES[@]}"; do
    if [ "$rel" = "$skip" ]; then
      return 0
    fi
  done
  return 1
}

identical=0
differs=0
missing=0
skipped=0

echo -e "${BLUE}Comparing template → workspace${NC}"
echo -e "${BLUE}Template:  $TEMPLATE_DIR${NC}"
echo -e "${BLUE}Workspace: $WORKSPACE${NC}"
echo

(
  cd "$TEMPLATE_DIR"
  find . -type f ! -name "workspace.spec" | sort | while read -r file; do
    rel="${file#./}"
    target="$WORKSPACE/$rel"

    if is_skipped "$rel"; then
      skipped=$((skipped + 1))
      echo -e "  ${YELLOW}skip${NC} $rel (user-owned)"
      continue
    fi

    if [ ! -f "$target" ]; then
      missing=$((missing + 1))
      echo -e "  ${RED}missing${NC} $rel"
      continue
    fi

    if diff -q "$TEMPLATE_DIR/$rel" "$target" >/dev/null 2>&1; then
      identical=$((identical + 1))
      # silent for identical files
    else
      differs=$((differs + 1))
      echo -e "  ${YELLOW}differs${NC} $rel"
      if [ "$FULL_DIFF" -eq 1 ]; then
        diff --color=auto -u "$TEMPLATE_DIR/$rel" "$target" 2>/dev/null || true
        echo
      fi
    fi
  done
)

# Also check scripts/ and cron/ which are copied with dst_subdir
for extra_dir in scripts cron; do
  src_dir="$SCRIPT_DIR/../$extra_dir"
  [ -d "$src_dir" ] || continue
  (
    cd "$src_dir"
    find . -type f ! -name "config.env" ! -path "*/logs/*" | sort | while read -r file; do
      rel="${file#./}"
      target="$WORKSPACE/$extra_dir/$rel"

      if [ ! -f "$target" ]; then
        echo -e "  ${RED}missing${NC} $extra_dir/$rel"
        continue
      fi

      if ! diff -q "$src_dir/$rel" "$target" >/dev/null 2>&1; then
        echo -e "  ${YELLOW}differs${NC} $extra_dir/$rel"
        if [ "$FULL_DIFF" -eq 1 ]; then
          diff --color=auto -u "$src_dir/$rel" "$target" 2>/dev/null || true
          echo
        fi
      fi
    done
  )
done

echo
echo -e "${GREEN}Done.${NC} Review ${YELLOW}differs${NC} and ${RED}missing${NC} files above."
echo -e "Run with ${BLUE}--full${NC} to see actual diffs."
