#!/bin/bash
# install-linux.sh — Generate user crontab entries from launchd plists
# Usage: bash cron/install-linux.sh [--dry-run] [--uninstall]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_DIR="$SCRIPT_DIR/launchd"
RUNNER="$SCRIPT_DIR/runner.sh"
MARKER_BEGIN="# >>> Oracle Cron BEGIN >>>"
MARKER_END="# <<< Oracle Cron END <<<"

DRY_RUN=false
UNINSTALL=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --uninstall) UNINSTALL=true ;;
  esac
done

# Parse plist files and generate crontab lines.
# Supports two plist styles:
#   1. runner.sh dispatch:    ProgramArguments = [<...>/cron/runner.sh, <job>]
#                             → emits  `<sched>  <runner> <job>`
#   2. direct shell wrapper:  ProgramArguments = [/bin/bash, -lc, "<cmd>"]
#                             → emits  `<sched>  <cmd-with-placeholders-resolved>`
# Placeholder substitution (`__PROJECT_DIR__`, `__HOME__`) mirrors what
# install-mac.sh does for plist contents at install time.
generate_crontab_entries() {
  # Vixie cron runs jobs with PATH=/usr/bin:/bin and does NOT expand
  # variables in env lines, so we detect claude's real location here and
  # bake a fully-expanded PATH line into the generated block.
  local claude_dir
  claude_dir="$(dirname "$(command -v claude 2>/dev/null)" 2>/dev/null || true)"
  python3 - "$PLIST_DIR" "$RUNNER" "$PROJECT_DIR" "$HOME" "$claude_dir" <<'PYEOF'
import plistlib, sys, os

plist_dir   = sys.argv[1]
runner      = sys.argv[2]
project_dir = sys.argv[3]
home_dir    = sys.argv[4]
claude_dir  = sys.argv[5] if len(sys.argv) > 5 else ''

# PATH for all generated entries (mirrors the launchd plists' PATH, fully
# expanded because cron env lines do not expand variables).
path_dirs = [os.path.join(home_dir, '.local/bin'), '/usr/local/bin', '/usr/bin', '/bin']
if claude_dir and claude_dir not in path_dirs:
    path_dirs.insert(0, claude_dir)
print('PATH=' + ':'.join(path_dirs))


def resolve(s: str) -> str:
    return s.replace('__PROJECT_DIR__', project_dir).replace('__HOME__', home_dir)


for fname in sorted(os.listdir(plist_dir)):
    if not fname.endswith('.plist'):
        continue
    fpath = os.path.join(plist_dir, fname)
    try:
        with open(fpath, 'rb') as fp:
            d = plistlib.load(fp)
    except (plistlib.InvalidFileException, ValueError, OSError) as e:
        # Log to stderr so the bash caller can see the warning without
        # tripping the generator. We skip the malformed plist rather than
        # aborting the whole install — losing one job is better than
        # losing the entire schedule.
        print(f"# WARNING: failed to parse {fname}: {e} (skipped)", file=sys.stderr)
        continue

    prog = d.get('ProgramArguments') or []
    if not prog:
        print(f"# WARNING: {fname} missing ProgramArguments (skipped)", file=sys.stderr)
        continue

    cal = d.get('StartCalendarInterval', {})
    if not cal:
        print(f"# WARNING: {fname} has no StartCalendarInterval (skipped)", file=sys.stderr)
        continue

    # Decide which plist style we have, build the command tail.
    first = prog[0] if prog else ''
    if first.endswith('runner.sh') and len(prog) >= 2:
        stem = prog[-1]
        cmd_tail = f"{runner} {prog[-1]}"
    elif first in ('/bin/bash', '/bin/sh') and len(prog) >= 3 and prog[1] in ('-lc', '-c'):
        stem = fname[:-len('.plist')].rsplit('.', 1)[-1]
        cmd_tail = resolve(prog[-1])
    else:
        print(f"# WARNING: {fname} unsupported ProgramArguments shape (skipped)", file=sys.stderr)
        continue

    # cron has no launchd StandardOutPath equivalent — without a redirect,
    # stdout becomes local mail. Append per-job log redirection unless the
    # command already manages its own.
    if '>>' not in cmd_tail and '2>&1' not in cmd_tail:
        log_path = os.path.join(project_dir, 'cron/logs', f'cron-{stem}.log')
        cmd_tail = f"{cmd_tail} >> {log_path} 2>&1"

    entries = cal if isinstance(cal, list) else [cal]
    # Deduplicate: group by (minute, hour, day) and merge weekdays
    seen = {}
    for c in entries:
        # launchd ANDs Day with Weekday; POSIX cron ORs them — silently
        # different semantics, so refuse to translate that shape.
        if 'Day' in c and 'Weekday' in c:
            print(f"# WARNING: {fname} sets both Day and Weekday "
                  "(launchd=AND, cron=OR — semantics differ); entry skipped",
                  file=sys.stderr)
            continue
        m = str(c.get('Minute', '*'))
        h = str(c.get('Hour', '*'))
        dom = str(c.get('Day', '*'))
        dow = str(c.get('Weekday', '*'))
        key = (m, h, dom)
        if key not in seen:
            seen[key] = set()
        if dow != '*':
            seen[key].add(dow)

    for (m, h, dom), dows in seen.items():
        dow_str = ','.join(sorted(dows)) if dows else '*'
        print(f"{m} {h} {dom} * {dow_str}  {cmd_tail}")
PYEOF
}

if $UNINSTALL; then
  echo "Removing Oracle Cron entries from user crontab..."
  CURRENT=$(crontab -l 2>/dev/null || true)
  if echo "$CURRENT" | grep -q "$MARKER_BEGIN"; then
    NEW=$(echo "$CURRENT" | sed "/$MARKER_BEGIN/,/$MARKER_END/d")
    if $DRY_RUN; then
      echo "[dry-run] Would update crontab to:"
      echo "$NEW"
    else
      echo "$NEW" | crontab -
      echo "Done. Oracle Cron entries removed."
    fi
  else
    echo "No Oracle Cron entries found in crontab."
  fi
  exit 0
fi

# Generate crontab block
ENTRIES=$(generate_crontab_entries)
BLOCK=$(cat <<EOF
$MARKER_BEGIN
# Auto-generated from cron/launchd/*.plist — do not edit manually
# Re-run: bash cron/install-linux.sh
$ENTRIES
$MARKER_END
EOF
)

echo "Generated crontab entries:"
echo "$ENTRIES" | wc -l | xargs -I{} echo "  {} jobs"
echo ""

if $DRY_RUN; then
  echo "[dry-run] Would add to crontab:"
  echo "$BLOCK"
  exit 0
fi

# Generated entries redirect into cron/logs — make sure it exists.
mkdir -p "$PROJECT_DIR/cron/logs"

# Get current crontab, remove old Oracle block, add new one
CURRENT=$(crontab -l 2>/dev/null || true)
if echo "$CURRENT" | grep -q "$MARKER_BEGIN"; then
  CLEANED=$(echo "$CURRENT" | sed "/$MARKER_BEGIN/,/$MARKER_END/d")
  NEW="${CLEANED}
${BLOCK}"
else
  NEW="${CURRENT}
${BLOCK}"
fi

echo "$NEW" | crontab -
echo "Done. Oracle Cron installed to user crontab."
echo "Verify with: crontab -l | grep runner"
