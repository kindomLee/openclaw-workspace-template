#!/bin/bash
# cron-notes-todo-check.sh — count unresolved TODOs in active notes.
# Raises a flag when the backlog crosses the threshold.
#
# Config:
#   OPENCLAW_WORKSPACE       — workspace root (auto-detected if unset)
#   NOTES_TODO_THRESHOLD     — flag threshold (default: 20)
#   NOTES_TODO_GLOBS         — ':'-separated globs relative to notes/
#                              (default: '01-Projects/Active/**/*.md:00-Inbox/**/*.md')
#   NOTIFY_CHANNEL / TARGET  — see scripts/lib/notify.sh
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
FLAG_NAME="notes-todo"
THRESHOLD="${NOTES_TODO_THRESHOLD:-20}"
GLOBS="${NOTES_TODO_GLOBS:-01-Projects/Active/**/*.md:00-Inbox/**/*.md}"

if [ ! -d "$NOTES_DIR" ]; then
    echo "[notes-todo] no notes/ directory at $NOTES_DIR, skipping"
    exit 0
fi

REPORT=$(flag_report_path "$WS" "$FLAG_NAME")
mkdir -p "$(dirname "$REPORT")"

COUNT=$(python3 - "$NOTES_DIR" "$REPORT" "$GLOBS" <<'PY'
import re, sys
from pathlib import Path

notes_root = Path(sys.argv[1])
report_path = sys.argv[2]
globs = sys.argv[3].split(':')

targets = []
for g in globs:
    targets.extend(notes_root.glob(g))

TODO_RE = re.compile(r'^\s*[-*]\s*\[ \]\s+(.+)$', re.M)
TODO_TAG_RE = re.compile(r'\bTODO[:：]\s*(.+)', re.I)
PENDING_RE = re.compile(r'^status:\s*pending\s*$', re.M | re.I)

items = []
for md in targets:
    try:
        text = md.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue
    rel = str(md.relative_to(notes_root))
    for m in TODO_RE.finditer(text):
        items.append((rel, 'checkbox', m.group(1).strip()[:80]))
    for m in TODO_TAG_RE.finditer(text):
        items.append((rel, 'TODO', m.group(1).strip()[:80]))
    if PENDING_RE.search(text):
        items.append((rel, 'pending', 'frontmatter status:pending'))

with open(report_path, 'w', encoding='utf-8') as f:
    f.write(f'Unresolved items: {len(items)}\n')
    for src, kind, txt in items[:60]:
        f.write(f'  [{kind}] {src}: {txt}\n')

print(len(items))
PY
)

if [ "${COUNT:-0}" -lt "$THRESHOLD" ]; then
    echo "[notes-todo] $COUNT < $THRESHOLD, clearing flag"
    clear_flag "$WS" "$FLAG_NAME"
    exit 0
fi

write_flag "$WS" "$FLAG_NAME" \
    "notes/ has $COUNT unresolved items (threshold $THRESHOLD)" \
    "Read $REPORT for the list. Triage: complete, archive, or split into sub-tasks." \
    "When done: rm .claude/flags/${FLAG_NAME}.flag"

notify "notes-todo backlog: $COUNT items (threshold $THRESHOLD)"
echo "[notes-todo] flag written: $COUNT items"
