#!/bin/bash
# flag.sh — write/clear pending flags that the SessionStart hook surfaces.
#
# A "flag" is a two-line file under $WORKSPACE/.claude/flags/<name>.flag:
#     line 1: short title (shown in Claude session)
#     line 2+: human-readable instructions including how to clear it
#
# Use `write_flag` to create one, `clear_flag` to remove it.
#
# Philosophy: cron jobs only detect + write flags. They do not call Claude.
# The next Claude Code session picks the flag up via a SessionStart hook
# and decides what to do. This is the "hard trigger, soft action" pattern —
# deterministic detection, LLM-driven response.

_flag_dir() {
    local ws="$1"
    echo "${ws}/.claude/flags"
}

write_flag() {
    # write_flag <workspace> <name> <title> <instructions...>
    local ws="$1" name="$2" title="$3"
    shift 3
    local dir
    dir=$(_flag_dir "$ws")
    mkdir -p "$dir"
    {
        echo "$title"
        printf '%s\n' "$@"
    } > "${dir}/${name}.flag"
}

clear_flag() {
    # clear_flag <workspace> <name>
    local ws="$1" name="$2"
    rm -f "$(_flag_dir "$ws")/${name}.flag"
}

flag_report_path() {
    # flag_report_path <workspace> <name>
    local ws="$1" name="$2"
    echo "$(_flag_dir "$ws")/${name}-report.txt"
}
