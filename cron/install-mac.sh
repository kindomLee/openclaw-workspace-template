#!/usr/bin/env bash
# install-mac.sh — Install/update/remove Oracle Cron launchd jobs on macOS.
#
# Usage:
#   bash cron/install-mac.sh                # install or re-install
#   bash cron/install-mac.sh --dry-run      # preview without touching launchd
#   bash cron/install-mac.sh --uninstall    # bootout + remove
#   bash cron/install-mac.sh --help         # this help
#
# The source of truth is cron/launchd/*.plist. On install, each plist is
# copied into ~/Library/LaunchAgents/ with __PROJECT_DIR__ and __HOME__
# substituted, then booted via launchctl bootstrap.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_DIR="$SCRIPT_DIR/launchd"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

DRY_RUN=false
UNINSTALL=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)    DRY_RUN=true ;;
    --uninstall)  UNINSTALL=true ;;
    --help|-h)
      sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "unknown option: $arg" >&2
      echo "try: bash cron/install-mac.sh --help" >&2
      exit 2 ;;
  esac
done

if [ ! -d "$PLIST_DIR" ]; then
  echo "error: $PLIST_DIR does not exist — nothing to install" >&2
  exit 1
fi

if [ "$DRY_RUN" = "false" ]; then
  mkdir -p "$LAUNCH_AGENTS_DIR"
fi

# --- Uninstall path ----------------------------------------------------
if [ "$UNINSTALL" = "true" ]; then
  echo "Uninstalling Oracle Cron jobs..."
  for plist in "$PLIST_DIR"/*.plist; do
    [ -f "$plist" ] || continue
    LABEL=$(basename "$plist" .plist)
    if [ "$DRY_RUN" = "true" ]; then
      echo "  [dry-run] would bootout $LABEL and remove $LAUNCH_AGENTS_DIR/$LABEL.plist"
    else
      launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
      rm -f "$LAUNCH_AGENTS_DIR/$LABEL.plist"
      echo "  - Removed $LABEL"
    fi
  done
  echo "Done."
  exit 0
fi

# --- Install path ------------------------------------------------------
echo "Installing Oracle Cron jobs..."
echo "  Project: $PROJECT_DIR"
echo "  Home:    $HOME"
[ "$DRY_RUN" = "true" ] && echo "  [dry-run — no files will be written and launchctl will not be called]"

for plist in "$PLIST_DIR"/*.plist; do
  [ -f "$plist" ] || continue
  LABEL=$(basename "$plist" .plist)
  DEST="$LAUNCH_AGENTS_DIR/$LABEL.plist"

  if [ "$DRY_RUN" = "true" ]; then
    echo "  [dry-run] would install $LABEL → $DEST"
    continue
  fi

  # bootout first — safe to fail if the job isn't already loaded
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
      -e "s|__HOME__|$HOME|g" \
      "$plist" > "$DEST"
  launchctl bootstrap "gui/$(id -u)" "$DEST"
  echo "  + Installed $LABEL"
done

if [ "$DRY_RUN" = "true" ]; then
  echo "Dry run complete. Re-run without --dry-run to actually install."
else
  echo "Done. Verify with: launchctl list | grep oracle"
fi
