#!/bin/bash
# install-cron.sh — print the crontab snippet for this workspace.
#
# Usage:
#   bash scripts/install-cron.sh              # print to stdout (copy into crontab -e)
#   bash scripts/install-cron.sh --install    # append to current crontab (confirms first)
#
# The snippet is derived from templates/crontab.example by substituting the
# detected OPENCLAW_WORKSPACE. This script never modifies crontab without an
# explicit --install flag and a confirmation prompt.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/workspace.sh
source "$SELF_DIR/lib/workspace.sh"

WS=$(openclaw_workspace)
TEMPLATE="$WS/templates/crontab.example"
if [ ! -f "$TEMPLATE" ]; then
    echo "error: $TEMPLATE not found" >&2
    exit 1
fi

snippet=$(sed "s|/path/to/your/workspace|$WS|g" "$TEMPLATE")

if [ "${1:-}" != "--install" ]; then
    echo "# --- generated crontab snippet for $WS ---"
    echo "# Paste into \`crontab -e\` (or rerun with --install to append)."
    echo
    echo "$snippet"
    exit 0
fi

echo "About to append the following to your crontab:"
echo "---"
echo "$snippet"
echo "---"
read -r -p "Proceed? [y/N] " ans
case "$ans" in
    y|Y|yes)
        (crontab -l 2>/dev/null; echo; echo "$snippet") | crontab -
        echo "installed."
        ;;
    *)
        echo "aborted."
        ;;
esac
