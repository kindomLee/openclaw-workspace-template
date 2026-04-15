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

# Parse plist files and generate crontab lines
generate_crontab_entries() {
  python3 - "$PLIST_DIR" "$RUNNER" <<'PYEOF'
import plistlib, sys, os

plist_dir = sys.argv[1]
runner = sys.argv[2]

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

    try:
        job_name = d['ProgramArguments'][-1]
    except (KeyError, IndexError) as e:
        print(f"# WARNING: {fname} missing ProgramArguments: {e} (skipped)", file=sys.stderr)
        continue

    cal = d.get('StartCalendarInterval', {})
    if not cal:
        print(f"# WARNING: {fname} has no StartCalendarInterval (skipped)", file=sys.stderr)
        continue

    entries = cal if isinstance(cal, list) else [cal]
    # Deduplicate: group by (minute, hour, day) and merge weekdays
    seen = {}
    for c in entries:
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
        if dows:
            dow_str = ','.join(sorted(dows))
        else:
            dow_str = '*'
        print(f"{m} {h} {dom} * {dow_str}  {runner} {job_name}")
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
