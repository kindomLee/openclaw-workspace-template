#!/usr/bin/env bash
# bootstrap.sh — Claude Code / OpenClaw Workspace Template Bootstrap
#
# Usage:
#   ./bootstrap.sh                          # Interactive install into .
#   ./bootstrap.sh --path ~/my-workspace    # Non-interactive path
#   ./bootstrap.sh --path . --yes           # Fully non-interactive
#   ./bootstrap.sh --dry-run                # Preview only, no writes
#   ./bootstrap.sh --help                   # Show help
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Defaults
DEFAULT_WORKSPACE="."
WORKSPACE_PATH=""
ASSUME_YES=0
DRY_RUN=0

usage() {
  cat <<EOF
Claude Code / OpenClaw Workspace Template Bootstrap

Usage: bootstrap.sh [OPTIONS]

Options:
  --path DIR     Target workspace directory (default: prompt, then ".")
  --yes, -y      Skip confirmation prompts (for CI / automation)
  --dry-run      Show what would happen without writing any files
  --help, -h     Show this help and exit

Examples:
  ./bootstrap.sh
  ./bootstrap.sh --path ~/my-workspace
  ./bootstrap.sh --path . --yes
  ./bootstrap.sh --dry-run --path /tmp/preview --yes
EOF
}

# Parse args
while [ $# -gt 0 ]; do
  case "$1" in
    --path)
      [ $# -ge 2 ] || { echo "--path requires an argument" >&2; exit 2; }
      WORKSPACE_PATH="$2"; shift 2 ;;
    --yes|-y)     ASSUME_YES=1; shift ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --help|-h)    usage; exit 0 ;;
    *)            echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

echo -e "${BLUE}Claude Code / OpenClaw Workspace Template Bootstrap${NC}"
echo -e "${BLUE}====================================================${NC}"
echo

# ---- Dependency check --------------------------------------------------
# Required: hard fail if missing. Recommended: warn but continue.
MISSING=()
RECOMMENDED_MISSING=()
for cmd in python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || MISSING+=("$cmd")
done
if ! command -v claude >/dev/null 2>&1; then
  MISSING+=("claude (Claude Code CLI — see https://docs.claude.com/claude-code)")
fi
if ! command -v timeout >/dev/null 2>&1 && ! command -v gtimeout >/dev/null 2>&1; then
  MISSING+=("timeout (macOS: brew install coreutils)")
fi
# jq is used by the SessionStart flag hook. If missing, the hook silently
# falls back to python3, so treat jq as recommended rather than required.
if ! command -v jq >/dev/null 2>&1; then
  RECOMMENDED_MISSING+=("jq (macOS: brew install jq — hook falls back to python3 if absent)")
fi
if [ ${#MISSING[@]} -gt 0 ]; then
  echo -e "${RED}Missing required tools:${NC}"
  printf '  - %s\n' "${MISSING[@]}"
  echo
  echo -e "${YELLOW}Install the missing tools and re-run.${NC}"
  exit 1
fi
if [ ${#RECOMMENDED_MISSING[@]} -gt 0 ]; then
  echo -e "${YELLOW}Recommended tools missing (install for best experience):${NC}"
  printf '  - %s\n' "${RECOMMENDED_MISSING[@]}"
  echo
fi

# ---- Resolve workspace path -------------------------------------------
if [ -z "$WORKSPACE_PATH" ]; then
  if [ "$ASSUME_YES" -eq 1 ]; then
    WORKSPACE_PATH="$DEFAULT_WORKSPACE"
  else
    echo -e "${YELLOW}Workspace directory (default: ${DEFAULT_WORKSPACE}):${NC}"
    echo -e "  - For Claude Code:  \".\" (current dir) or a path like \"~/my-workspace\""
    echo -e "  - For OpenClaw:     \"./clawd\" (traditional)"
    read -r WORKSPACE_PATH
    WORKSPACE_PATH="${WORKSPACE_PATH:-$DEFAULT_WORKSPACE}"
  fi
fi

# Expand leading ~
WORKSPACE_PATH="${WORKSPACE_PATH/#\~/$HOME}"

# Resolve to absolute path (BSD/GNU-portable: cd + pwd works on existing dirs)
if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$WORKSPACE_PATH"
fi
if [ -d "$WORKSPACE_PATH" ]; then
  WORKSPACE_PATH=$(cd "$WORKSPACE_PATH" && pwd)
fi

echo -e "${BLUE}Target workspace: ${WORKSPACE_PATH}${NC}"
[ "$DRY_RUN" -eq 1 ] && echo -e "${YELLOW}[DRY RUN — no files will be written]${NC}"
echo

# ---- Non-empty directory confirmation ---------------------------------
if [ -d "$WORKSPACE_PATH" ] && [ "$(ls -A "$WORKSPACE_PATH" 2>/dev/null)" ]; then
  echo -e "${YELLOW}Warning: workspace directory is not empty.${NC}"
  echo -e "${YELLOW}Existing files will be preserved (skip-if-exists).${NC}"
  if [ "$ASSUME_YES" -eq 0 ]; then
    echo -e "${YELLOW}Continue? (y/N):${NC}"
    read -r CONTINUE
    if [[ ! "${CONTINUE:-}" =~ ^[Yy]$ ]]; then
      echo -e "${RED}Aborted.${NC}"
      exit 1
    fi
  fi
fi

# ---- Copy helpers ------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$SCRIPT_DIR/templates" ]; then
  echo -e "${RED}Error: templates/ not found in $SCRIPT_DIR${NC}" >&2
  exit 1
fi

# copy_tree SRC [DST_SUBDIR]
#   Walk SRC, copy each file into WORKSPACE_PATH (or WORKSPACE_PATH/DST_SUBDIR
#   when DST_SUBDIR is given). Skip files that already exist. Skip cron
#   runtime artifacts (config.env with secrets, logs/).
copy_tree() {
  local src="$1"
  local dst_subdir="${2:-}"
  [ -d "$src" ] || return 0
  local label
  label=$(basename "$src")
  echo -e "${YELLOW}Copying ${label}/...${NC}"
  (
    cd "$src"
    find . -type f ! -name "config.env" ! -path "*/logs/*" | while read -r file; do
      local rel="${file#./}"
      local target
      if [ -n "$dst_subdir" ]; then
        target="$WORKSPACE_PATH/$dst_subdir/$rel"
      else
        target="$WORKSPACE_PATH/$rel"
      fi
      if [ -f "$target" ]; then
        echo -e "  ${YELLOW}skip${NC} ${dst_subdir:+$dst_subdir/}$rel (exists)"
      else
        if [ "$DRY_RUN" -eq 0 ]; then
          mkdir -p "$(dirname "$target")"
          cp "$file" "$target"
        fi
        echo -e "  ${GREEN}copy${NC} ${dst_subdir:+$dst_subdir/}$rel"
      fi
    done
  )
}

copy_tree "$SCRIPT_DIR/templates"
# Skills now live under templates/.claude/skills/ and are copied as part
# of `templates/` above. Claude Code auto-loads SKILL.md files from
# <workspace>/.claude/skills/<name>/SKILL.md without any extra wiring.
copy_tree "$SCRIPT_DIR/scripts" "scripts"
copy_tree "$SCRIPT_DIR/cron"    "cron"

# ---- Additional directories -------------------------------------------
echo -e "${YELLOW}Creating directory structure...${NC}"
if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p \
    "$WORKSPACE_PATH/memory" \
    "$WORKSPACE_PATH/notes/00-Inbox" \
    "$WORKSPACE_PATH/notes/01-Projects/Active" \
    "$WORKSPACE_PATH/notes/01-Projects/Archive" \
    "$WORKSPACE_PATH/notes/02-Areas" \
    "$WORKSPACE_PATH/notes/03-Resources" \
    "$WORKSPACE_PATH/notes/04-Archive" \
    "$WORKSPACE_PATH/.learnings" \
    "$WORKSPACE_PATH/scripts" \
    "$WORKSPACE_PATH/.claude/skills" \
    "$WORKSPACE_PATH/cron/logs" \
    "$WORKSPACE_PATH/reference" \
    "$WORKSPACE_PATH/tmp"
fi

# ---- Permissions ------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  chmod 755 "$WORKSPACE_PATH"
  # shellcheck disable=SC2035
  find "$WORKSPACE_PATH" -maxdepth 1 -name "*.md" -exec chmod 644 {} \; 2>/dev/null || true
  find "$WORKSPACE_PATH/scripts" -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
  find "$WORKSPACE_PATH/cron" -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
fi

# ---- .claude/settings.json merge warning ------------------------------
#
# If the user's workspace already has a local .claude/settings.json (e.g.
# they're bootstrapping into an existing Claude Code project), skip-if-exists
# will keep the user's copy — which means the template's hooks are NOT
# wired up. Flag it loudly so the user knows to merge manually.
USER_SETTINGS="$WORKSPACE_PATH/.claude/settings.json"
TEMPLATE_SETTINGS="$SCRIPT_DIR/templates/.claude/settings.json"
if [ -f "$USER_SETTINGS" ] && [ -f "$TEMPLATE_SETTINGS" ]; then
  if ! diff -q "$USER_SETTINGS" "$TEMPLATE_SETTINGS" >/dev/null 2>&1; then
    echo
    echo -e "${YELLOW}⚠️  .claude/settings.json already exists and differs from the template.${NC}"
    echo -e "${YELLOW}    Template hooks are NOT wired up. Manually merge if you want them:${NC}"
    echo -e "    diff $TEMPLATE_SETTINGS $USER_SETTINGS"
  fi
fi

# ---- Finish -----------------------------------------------------------
echo
if [ "$DRY_RUN" -eq 1 ]; then
  echo -e "${YELLOW}Dry run complete. Re-run without --dry-run to actually install.${NC}"
  exit 0
fi

echo -e "${GREEN}Workspace setup complete.${NC}"
echo
echo -e "${BLUE}Next steps:${NC}"
echo
echo -e "${BLUE}[Claude Code — default]${NC}"
echo -e "  1. ${YELLOW}cd $WORKSPACE_PATH${NC}"
echo -e "  2. ${YELLOW}cp cron/config.env.example cron/config.env${NC} and fill TG_BOT_TOKEN / TG_CHAT_ID (optional, for Telegram alerts)"
echo -e "  3. Install cron: ${YELLOW}bash cron/install-mac.sh${NC}  (macOS)  or  ${YELLOW}bash cron/install-linux.sh${NC}  (Linux)"
echo -e "  4. Edit ${YELLOW}IDENTITY.md / USER.md / SOUL.md / TOOLS.md${NC} to personalize"
echo -e "  5. Run ${YELLOW}claude${NC} — the first session reads AGENTS.md and bootstraps"
echo
echo -e "${BLUE}[OpenClaw — alternative]${NC}"
echo -e "  1. ${YELLOW}openclaw workspace set $WORKSPACE_PATH${NC}"
echo -e "  2. Install cron: ${YELLOW}bash scripts/install-cron.sh --install${NC}"
echo -e "  3. Edit ${YELLOW}IDENTITY.md / USER.md / SOUL.md / TOOLS.md${NC}"
echo
echo -e "${BLUE}Health check:${NC} ${YELLOW}bash scripts/health-check.sh${NC}"
echo -e "${BLUE}Docs:${NC}         ${YELLOW}$WORKSPACE_PATH/guides/${NC}"
echo
echo -e "${GREEN}Happy agent building.${NC}"
