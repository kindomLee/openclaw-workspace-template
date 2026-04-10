#!/bin/bash
# session-start-flags.sh — SessionStart hook: surface pending flags to Claude.
#
# Reads every *.flag file under .claude/flags/ and emits a SessionStart
# additionalContext payload. The next Claude Code session will see the flags
# as a system reminder and decide how to handle them.
#
# Wire this up in .claude/settings.json:
#   "hooks": {
#     "SessionStart": [{
#       "hooks": [{
#         "type": "command",
#         "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/session-start-flags.sh\"",
#         "timeout": 5
#       }]
#     }]
#   }
#
# $CLAUDE_PROJECT_DIR is injected by Claude Code and always points to the
# workspace root, regardless of the current working directory. Using it
# avoids a foot-gun where any cwd drift earlier in the session would make
# `.claude/flags` resolve to the wrong place.
set -euo pipefail

# Resolve FLAG_DIR robustly: prefer the injected project dir, fall back to
# the script's own location (two levels up from .claude/hooks/).
if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
    FLAG_DIR="$CLAUDE_PROJECT_DIR/.claude/flags"
else
    SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    FLAG_DIR="$(dirname "$(dirname "$SELF_DIR")")/.claude/flags"
fi
shopt -s nullglob
FLAGS=("$FLAG_DIR"/*.flag)
[ ${#FLAGS[@]} -eq 0 ] && exit 0

# Build a concatenated report block from every flag file.
# Note: we append the trailing blank line *outside* the command substitution
# because `$( ... )` strips trailing newlines, which would otherwise run two
# flags together in the rendered output.
report=""
for f in "${FLAGS[@]}"; do
    name=$(basename "$f" .flag)
    body=$(cat "$f")
    report+="=== ${name} ===
${body}

"
done

# Emit the hook payload. Requires `jq` for safe JSON encoding.
if ! command -v jq >/dev/null 2>&1; then
    echo "[session-start-flags] jq not found; skipping flag injection" >&2
    exit 0
fi

jq -n --arg c "$report" '{
    hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext: ("Pending workspace flags detected. Surface these to the user and act on the instructions. After resolving, delete the corresponding .claude/flags/<name>.flag file.\n\n" + $c)
    }
}'
