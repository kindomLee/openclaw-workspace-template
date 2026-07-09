#!/usr/bin/env bash
# SessionStart hook: detect unfinished plan files under .claude/plans/ (top-level
# unchecked stages) and inject a reminder so the next session decides whether to
# resume or archive them. See guides/plan-file-policy.md.
[ "$CLAUDE_CODE_ENTRYPOINT" = "sdk-cli" ] && exit 0

D="${CLAUDE_PROJECT_DIR:-.}/.claude/plans"
[ -d "$D" ] || exit 0

shopt -s nullglob
unfinished=()
for f in "$D"/*.md; do
  grep -q '^- \[ \]' "$f" && unfinished+=("$f")
done
[ ${#unfinished[@]} -eq 0 ] && exit 0

ctx=""
for f in "${unfinished[@]}"; do
  title=$(grep -m1 '^# Plan:' "$f" | sed 's/^# Plan: *//')
  todo=$(grep -c '^- \[ \]' "$f")
  done_n=$(grep -c '^- \[x\]' "$f")
  ctx+="== $(basename "$f") =="$'\n'
  ctx+="title: ${title:-(none)}"$'\n'
  ctx+="progress: done ${done_n} / open ${todo}"$'\n\n'
done

msg="Unfinished plan file(s) detected. Tell the user and decide (resume or archive) per guides/plan-file-policy.md:\n\n${ctx}Read the full plan file before resuming. When all stages are done AND verified, delete the file to close it out."

if command -v jq >/dev/null 2>&1; then
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$m}}'
else
  python3 - "$msg" <<'PY'
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
fi
