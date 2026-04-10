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
#         "command": "bash .claude/hooks/session-start-flags.sh",
#         "timeout": 5
#       }]
#     }]
#   }
set -euo pipefail

FLAG_DIR=".claude/flags"
shopt -s nullglob
FLAGS=("$FLAG_DIR"/*.flag)
[ ${#FLAGS[@]} -eq 0 ] && exit 0

# Build a concatenated report block from every flag file.
report=""
for f in "${FLAGS[@]}"; do
    name=$(basename "$f" .flag)
    report+="$(printf '=== %s ===\n%s\n\n' "$name" "$(cat "$f")")"
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
