#!/bin/bash
# workspace.sh — derive the OpenClaw workspace root.
#
# Source this from any script in scripts/ or scripts/lib/:
#     source "$(dirname "${BASH_SOURCE[0]}")/lib/workspace.sh"
#     WS=$(openclaw_workspace)
#
# Resolution order:
#   1. $OPENCLAW_WORKSPACE (explicit override)
#   2. script-relative: parent of the directory containing this file
#   3. $HOME/.openclaw (last-resort default)

openclaw_workspace() {
    if [ -n "${OPENCLAW_WORKSPACE:-}" ]; then
        echo "$OPENCLAW_WORKSPACE"
        return
    fi
    # scripts/lib/workspace.sh → workspace root is two levels up
    local self_dir
    self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local candidate
    candidate="$(dirname "$(dirname "$self_dir")")"
    if [ -f "$candidate/MEMORY.md" ] || [ -d "$candidate/memory" ]; then
        echo "$candidate"
        return
    fi
    echo "${HOME}/.openclaw"
}
