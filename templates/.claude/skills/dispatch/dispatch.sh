#!/bin/bash
# dispatch.sh — run a task inside another repo with `claude -p`, so that repo's
# own CLAUDE.md, skills and hooks apply. This workspace stays the coordinator:
# it gets back a session_id + result and verifies the work itself.
#
#   dispatch.sh --repo <dir> [options] "<task>"
#
#   --repo <dir>      target repo; the session runs with cwd = <dir>      (required)
#   --resume <id>     continue that session (follow-ups, answering a stop point,
#                     running the repo's own /curate-memory on what it just did)
#   --write           allow Edit/Write inside the target (default: read-only)
#   --src <dir>       extra readable dir; Edit/Write on it stays denied (repeatable)
#   --allow <rule>    extra allow rule, e.g. 'Bash(pytest:*)' (repeatable)
#   --deny <rule>     extra deny rule (repeatable)
#   --user-settings   also load your user-level settings (default: project only)
#
# Defaults are deliberately narrow:
#   - read-only: Read/Grep/Glob + read-only git; Edit/Write/NotebookEdit denied
#   - --write adds Edit/Write with acceptEdits; reset --hard and rm -rf stay
#     denied, git commit / push too unless you --allow them explicitly
#     (committing also needs --allow 'Bash(git add:*)')
#   - scoped writes without --write: --allow 'Edit(path/**)' 'Write(path/**)'
#   - --setting-sources project: allow rules merge across scopes and a project
#     can't narrow a broad user-level allow (e.g. Bash(python3:*)), so user
#     settings are left out unless --user-settings
#   - a tool not on the list is refused (nobody can answer a prompt under -p) and
#     shows up in permission_denials
#
# Every run writes its raw JSON to $DISPATCH_LOG_DIR (default ~/.cache/dispatch).
# Exit 1 when claude fails, reports is_error, or returns no session_id.
# Needs: claude, jq.
set -uo pipefail
LOG="${DISPATCH_LOG_DIR:-$HOME/.cache/dispatch}"
die() { echo "dispatch: $*" >&2; exit 2; }
command -v jq >/dev/null || die "needs jq (macOS: brew install jq)"
abs() { (cd "$1" 2>/dev/null && pwd) || die "no such dir: $1"; }

repo=""; resume=(); write=0; sources=project
allow=(Read Grep Glob "Bash(git log:*)" "Bash(git show:*)" "Bash(git diff:*)" "Bash(git status:*)")
deny=()
while [ $# -gt 1 ]; do
  case $1 in
    --repo) repo=$(abs "$2") || exit 2; shift 2 ;;
    --resume) resume=(--resume "$2"); shift 2 ;;
    --write) write=1; shift ;;
    --src) d=$(abs "$2") || exit 2
           # permission rules write absolute paths as //abs/path; $d already starts with /
           srcs+=(--add-dir "$d"); deny+=("Edit(/$d/**)" "Write(/$d/**)"); shift 2 ;;
    --allow) allow+=("$2"); shift 2 ;;
    --deny) deny+=("$2"); shift 2 ;;
    --user-settings) sources=user,project,local; shift ;;
    *) break ;;
  esac
done
task=${1:-}
[ -n "$repo" ] && [ -n "$task" ] || die 'usage: dispatch.sh --repo <dir> [--resume id] [--write] [--src dir]... [--allow rule]... [--deny rule]... "<task>"'

given=" ${allow[*]} "   # defaults + every --allow, for the checks below
if [ $write -eq 1 ]; then
  allow+=(Edit Write)
  deny+=("Bash(git reset --hard:*)" "Bash(rm -rf:*)")
  # commit / push stay denied unless explicitly --allow'ed
  case $given in *"Bash(git commit"*) ;; *) deny+=("Bash(git commit:*)") ;; esac
  case $given in *"Bash(git push"*) ;; *) deny+=("Bash(git push:*)") ;; esac
  mode=acceptEdits
  n=$(git -C "$repo" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  [ "$n" = 0 ] || echo "dispatch: warning — $repo has $n uncommitted change(s); the session's edits will mix with them" >&2
else
  # read-only, unless you scoped writes yourself (e.g. --allow 'Edit(docs/**)')
  case $given in *" Edit("*|*" Write("*) ;; *) deny+=(Edit Write NotebookEdit) ;; esac
  mode=default
fi
# Untrusted folders silently drop the project's own permissions.allow under -p.
jq -e --arg d "$repo" '.projects[$d].hasTrustDialogAccepted == true' "$HOME/.claude.json" >/dev/null 2>&1 \
  || echo "dispatch: warning — $repo not marked trusted; run 'cd $repo && claude' once and accept, or its project allow rules are ignored" >&2

mkdir -p "$LOG"
J="$LOG/$(date +%Y%m%d-%H%M%S)-$$.json"
cd "$repo" || exit 2
claude -p "$task" ${resume[@]+"${resume[@]}"} ${srcs[@]+"${srcs[@]}"} \
  --allowedTools "${allow[@]}" ${deny[@]+--disallowedTools "${deny[@]}"} \
  --permission-mode "$mode" --setting-sources "$sources" --output-format json > "$J"
rc=$?
echo "log: $J"
if [ $rc -ne 0 ] || ! jq -e '.is_error == false and ((.session_id // "") | length > 0)' "$J" >/dev/null 2>&1; then
  echo "dispatch FAILED (rc=$rc)"; head -c 2000 "$J"; echo; exit 1
fi
jq -r '"session_id: \(.session_id)\nturns: \(.num_turns)  cost_usd (API-price estimate): \(.total_cost_usd)\npermission_denials: \(.permission_denials | map(.tool_input.command // .tool_name) | tostring)\n---\n\(.result)"' "$J"
