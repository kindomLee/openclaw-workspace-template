#!/bin/bash
# workspace.sh — resolve the active workspace root.
#
# Source this from any script in scripts/ or scripts/lib/:
#     source "$(dirname "${BASH_SOURCE[0]}")/lib/workspace.sh"
#     WS=$(openclaw_workspace)
#
# Resolution order:
#   1. $OPENCLAW_WORKSPACE (explicit override — kept for OpenClaw-mode compat)
#   2. $CLAUDE_PROJECT_DIR (set by Claude Code when hooks or tools run)
#   3. script-relative: parent of the directory containing this file,
#      but only if it looks like a workspace (has MEMORY.md or memory/).
#
# The previous `$HOME/.openclaw` fallback was removed — it masked configuration
# errors by silently pointing at a directory that most users don't have.
# Callers now get a non-empty path only when it can be verified, and otherwise
# see an error on stderr and an empty result. Scripts should treat "empty" as
# a fatal "no workspace configured" condition.

openclaw_workspace() {
    if [ -n "${OPENCLAW_WORKSPACE:-}" ]; then
        echo "$OPENCLAW_WORKSPACE"
        return
    fi
    if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
        echo "$CLAUDE_PROJECT_DIR"
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
    echo "error: could not resolve workspace root — set OPENCLAW_WORKSPACE or run inside Claude Code" >&2
    return 1
}
