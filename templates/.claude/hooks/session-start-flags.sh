#!/usr/bin/env bash
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
#         "timeout": 10
#       }]
#     }]
#   }
#
# $CLAUDE_PROJECT_DIR is injected by Claude Code and always points to the
# workspace root, regardless of the current working directory. Using it
# avoids a foot-gun where any cwd drift earlier in the session would make
# `.claude/flags` resolve to the wrong place.
#
# JSON encoding: prefers `jq` (fast, proper escaping); falls back to
# `python3` (ubiquitous on both macOS and Linux) if jq is missing. Silently
# skipping on a missing encoder would mean the user never sees pending
# flags, so we'd rather pay the python import cost.
set -euo pipefail

# Flag body size cap (chars). A single oversized report should not be
# allowed to flood SessionStart context; the flag file is supposed to be
# a summary, with details in a sibling *.txt the agent reads on demand.
MAX_FLAG_BYTES=4096

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

# Stable order: sort by filename so a burst of flags always renders the
# same way and the user can rely on positional references.
IFS=$'\n' FLAGS=($(printf '%s\n' "${FLAGS[@]}" | sort))
unset IFS

# Build a concatenated report block from every flag file. We truncate each
# body to MAX_FLAG_BYTES and append the trailing blank line *outside* the
# command substitution because `$( ... )` strips trailing newlines, which
# would otherwise run two flags together in the rendered output.
report=""
for f in "${FLAGS[@]}"; do
    name=$(basename "$f" .flag)
    body=$(head -c "$MAX_FLAG_BYTES" "$f")
    # If head truncated, signal that clearly so the agent knows to look
    # at the sibling report file instead of the flag.
    full_size=$(wc -c < "$f" | tr -d ' ')
    if [ "$full_size" -gt "$MAX_FLAG_BYTES" ]; then
        body+=$'\n… (truncated at '"$MAX_FLAG_BYTES"$' bytes; full content in .claude/flags/'"$name"$'.flag)'
    fi
    report+="=== ${name} ===
${body}

"
done

reminder_prefix="Pending workspace flags detected. Surface these to the user and act on the instructions. After resolving, delete the corresponding .claude/flags/<name>.flag file.

"

# Emit the hook payload. Prefer jq, fall back to python3 if unavailable.
if command -v jq >/dev/null 2>&1; then
    jq -n --arg c "$report" --arg p "$reminder_prefix" '{
        hookSpecificOutput: {
            hookEventName: "SessionStart",
            additionalContext: ($p + $c)
        }
    }'
elif command -v python3 >/dev/null 2>&1; then
    python3 - "$reminder_prefix" "$report" <<'PY'
import json, sys
prefix, report = sys.argv[1], sys.argv[2]
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": prefix + report,
    }
}))
PY
else
    echo "[session-start-flags] neither jq nor python3 available; skipping flag injection" >&2
    exit 0
fi
