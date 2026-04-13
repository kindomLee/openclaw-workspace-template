#!/bin/bash
# install-mac.sh — Install/update all Oracle Cron launchd jobs
# Usage: bash cron/install-mac.sh [--uninstall]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_DIR="$SCRIPT_DIR/launchd"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$LAUNCH_AGENTS_DIR"

if [ "${1:-}" = "--uninstall" ]; then
  echo "Uninstalling Oracle Cron jobs..."
  for plist in "$PLIST_DIR"/*.plist; do
    [ -f "$plist" ] || continue
    LABEL=$(basename "$plist" .plist)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$LAUNCH_AGENTS_DIR/$LABEL.plist"
    echo "  - Removed $LABEL"
  done
  echo "Done."
  exit 0
fi

echo "Installing Oracle Cron jobs..."
echo "  Project: $PROJECT_DIR"
echo "  Home:    $HOME"

for plist in "$PLIST_DIR"/*.plist; do
  [ -f "$plist" ] || continue
  LABEL=$(basename "$plist" .plist)
  # Stop existing job
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  # Copy to LaunchAgents with path substitution
  sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
      -e "s|__HOME__|$HOME|g" \
      "$plist" > "$LAUNCH_AGENTS_DIR/$LABEL.plist"
  # Load
  launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENTS_DIR/$LABEL.plist"
  echo "  + Installed $LABEL"
done
echo "Done. Verify with: launchctl list | grep oracle"
