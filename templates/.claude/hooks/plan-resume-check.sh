#!/usr/bin/env bash
# SessionStart hook: detect unfinished plan files under .claude/plans/ (top-level
# unchecked stages) and inject a reminder so the next session decides whether to
# resume or archive them. See guides/plan-file-policy.md.
[ "$CLAUDE_CODE_ENTRYPOINT" = "sdk-cli" ] && exit 0

D="${CLAUDE_PROJECT_DIR:-.}/.claude/plans"
[ -d "$D" ] || exit 0

# ponytail: a plan without `expires:` is considered stale after STALE_DAYS of no edits
STALE_DAYS=14
now=$(date +%s)
today=$(date +%F)
expired=

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
  ctx+="progress: done ${done_n} / open ${todo}"$'\n'
  exp=$(grep -m1 -E '^expires: *[0-9]{4}-[0-9]{2}-[0-9]{2}' "$f" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}')
  if [ -n "$exp" ]; then
    # ISO string compare: expired the day after `expires:` (BSD date -j would carry the current time and be off by one)
    [[ "$today" > "$exp" ]] && { ctx+="EXPIRED (expires ${exp})"$'\n'; expired=1; }
  else
    last=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f")  # GNU first: GNU `stat -f` prints fs info to stdout
    # tracked + unmodified plan: use last commit time, since checkout/pull resets mtime to now
    if git -C "$D" ls-files --error-unmatch "$f" >/dev/null 2>&1 && git -C "$D" diff --quiet HEAD -- "$f" 2>/dev/null; then
      last=$(git -C "$D" log -1 --format=%ct -- "$f")
    fi
    idle=$(( (now - last) / 86400 ))
    [ "$idle" -ge "$STALE_DAYS" ] && { ctx+="STALE (${idle} days without update, no expires)"$'\n'; expired=1; }
  fi
  ctx+=$'\n'
done
[ -n "$expired" ] && ctx+="For EXPIRED/STALE plans ask the user first: extend (write expires: YYYY-MM-DD) or close out (move to .claude/plans/archive/ and log one journal line on what was left undone)."$'\n\n'

msg="Unfinished plan file(s) detected. Tell the user and decide (resume or archive) per guides/plan-file-policy.md:"$'\n\n'"${ctx}Read the full plan file before resuming. When all stages are done AND verified, delete the file to close it out."

if command -v jq >/dev/null 2>&1; then
  jq -n --arg m "$msg" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$m}}'
else
  python3 - "$msg" <<'PY'
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
fi
