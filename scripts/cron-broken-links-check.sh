#!/bin/bash
# cron-broken-links-check.sh — scan notes/ for unresolved [[wikilinks]].
# Raises a flag when broken link count crosses the threshold.
#
# Config:
#   OPENCLAW_WORKSPACE       — workspace root (auto-detected if unset)
#   BROKEN_LINKS_THRESHOLD   — flag threshold (default: 5)
#   NOTIFY_CHANNEL / TARGET  — see scripts/lib/notify.sh
#
# This script is safe to skip: if the workspace has no notes/ directory it
# exits silently. Run from cron weekly (see templates/crontab.example).
set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/workspace.sh
source "$SELF_DIR/lib/workspace.sh"
# shellcheck source=lib/notify.sh
source "$SELF_DIR/lib/notify.sh"
# shellcheck source=lib/flag.sh
source "$SELF_DIR/lib/flag.sh"

WS=$(openclaw_workspace)
NOTES_DIR="$WS/notes"
FLAG_NAME="broken-links"
THRESHOLD="${BROKEN_LINKS_THRESHOLD:-5}"

if [ ! -d "$NOTES_DIR" ]; then
    echo "[broken-links] no notes/ directory at $NOTES_DIR, skipping"
    exit 0
fi

REPORT=$(flag_report_path "$WS" "$FLAG_NAME")
mkdir -p "$(dirname "$REPORT")"

COUNT=$(python3 - "$NOTES_DIR" "$REPORT" <<'PY'
import re, sys
from pathlib import Path

notes_root = Path(sys.argv[1])
report_path = sys.argv[2]

WIKI = re.compile(r'\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]')
all_md = list(notes_root.rglob('*.md'))
stems = {p.stem.lower() for p in all_md}
basenames = {p.name.lower() for p in all_md}

broken = []
for md in all_md:
    try:
        text = md.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue
    for m in WIKI.finditer(text):
        target = m.group(1).strip().split('/')[-1].lower()
        if not target:
            continue
        if target in stems or f'{target}.md' in basenames:
            continue
        broken.append((str(md.relative_to(notes_root)), m.group(1).strip()))

with open(report_path, 'w', encoding='utf-8') as f:
    f.write(f'Broken wikilinks: {len(broken)}\n')
    for src, tgt in broken[:50]:
        f.write(f'  {src} -> [[{tgt}]]\n')

print(len(broken))
PY
)

if [ "${COUNT:-0}" -lt "$THRESHOLD" ]; then
    echo "[broken-links] $COUNT < $THRESHOLD, clearing flag"
    clear_flag "$WS" "$FLAG_NAME"
    exit 0
fi

write_flag "$WS" "$FLAG_NAME" \
    "notes/ has $COUNT broken wikilinks (threshold $THRESHOLD)" \
    "Read $REPORT for the list. Triage by fixing the links or removing the stale references." \
    "When done: rm .claude/flags/${FLAG_NAME}.flag"

notify "broken wikilinks: $COUNT in notes/ (threshold $THRESHOLD)"
echo "[broken-links] flag written: $COUNT broken"
