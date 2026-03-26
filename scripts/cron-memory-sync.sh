#!/bin/bash
# Memory Sync — extract recent conversations → trigger LLM to write daily memory
# Schedule: 02 * * * * (every hour at :02)
#
# Required env:
#   OPENCLAW_WORKSPACE — workspace path (e.g., /home/user/clawd)
#   OPENCLAW_PROFILE   — openclaw profile name (e.g., "cramclaw"; omit for default)
#
# Optional env:
#   OPENCLAW_STATE_DIR  — state directory (default: ~/.openclaw or ~/.openclaw-$PROFILE)
#   NOTIFY_CHANNEL      — discord/telegram channel for announce (e.g., "discord")
#   NOTIFY_TARGET       — target for announce (e.g., "channel:1234567890")
#
# Note: This script extracts conversations directly from session JSONL files.
#       It does NOT depend on external scripts like extract-recent-conversation.py.
#       This avoids the common pitfall of hardcoded paths pointing to the wrong instance.
set -euo pipefail

WORKSPACE="${OPENCLAW_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
PROFILE="${OPENCLAW_PROFILE:-}"
STATE_DIR="${OPENCLAW_STATE_DIR:-}"
TODAY=$(date +%Y-%m-%d)

# Resolve state dir
if [ -z "$STATE_DIR" ]; then
  if [ -n "$PROFILE" ]; then
    STATE_DIR="$HOME/.openclaw-${PROFILE}"
  else
    STATE_DIR="$HOME/.openclaw"
  fi
fi

SESSIONS_DIR="$STATE_DIR/agents/main/sessions"

# Extract recent conversations directly from session JSONL
CONV=$(python3 -c "
import json, os, glob
from datetime import datetime, timezone, timedelta

cutoff = datetime.now(timezone.utc) - timedelta(minutes=65)
sessions_dir = '$SESSIONS_DIR'
sessions_json = os.path.join(sessions_dir, 'sessions.json')

try:
    with open(sessions_json) as f:
        sdata = json.load(f)
    sessions = sdata.get('sessions', sdata)
    main_entry = sessions.get('agent:main:main', {})
    main_sid = main_entry.get('sessionId', '')
    if not main_sid:
        print('無對話')
        exit(0)
except Exception:
    print('無對話')
    exit(0)

# Find the session JSONL file
candidates = [os.path.join(sessions_dir, f'{main_sid}.jsonl')]
candidates += sorted(glob.glob(os.path.join(sessions_dir, f'*{main_sid}*.jsonl')), reverse=True)

lines = []
for path in candidates:
    if os.path.exists(path):
        with open(path) as f:
            lines = f.readlines()
        break

if not lines:
    print('無對話')
    exit(0)

# Extract user/assistant text after cutoff
result = []
for line in lines:
    try:
        d = json.loads(line)
        ts_str = d.get('timestamp', '')
        if not ts_str:
            continue
        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        if ts < cutoff:
            continue
        msg = d.get('message', {})
        role = msg.get('role', '')
        if role not in ('user', 'assistant'):
            continue
        content = msg.get('content', '')
        text = ''
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'text':
                    text += c.get('text', '')
        # Strip metadata noise
        if 'UNTRUSTED' in text:
            parts = text.split('UNTRUSTED Discord message body')
            if len(parts) > 1:
                text = parts[-1].split('<<<END')[0].strip()
        if text and len(text) > 5:
            prefix = '👤' if role == 'user' else '🤖'
            result.append(f'{prefix} {text[:300]}')
    except Exception:
        continue

if not result:
    print('無對話')
else:
    print('\n'.join(result[-20:]))
" 2>/dev/null)

if [ -z "$CONV" ] || echo "$CONV" | grep -q "^無對話$"; then
  exit 0
fi

# Build openclaw command
OPENCLAW_CMD="openclaw"
if [ -n "$PROFILE" ]; then
  OPENCLAW_CMD="openclaw --profile $PROFILE"
fi

ANNOUNCE_FLAGS=""
if [ -n "${NOTIFY_CHANNEL:-}" ] && [ -n "${NOTIFY_TARGET:-}" ]; then
  ANNOUNCE_FLAGS="--announce --channel $NOTIFY_CHANNEL --to $NOTIFY_TARGET"
elif [ -n "${NOTIFY_CHANNEL:-}" ]; then
  ANNOUNCE_FLAGS="--announce --channel $NOTIFY_CHANNEL"
fi

$OPENCLAW_CMD cron add \
  --name "memory-sync-write" \
  --at "5s" \
  --session isolated \
  --message "以下是最近一小時的對話摘要，請更新 memory/${TODAY}.md：

$CONV" \
  $ANNOUNCE_FLAGS \
  --delete-after-run 2>/dev/null || true

echo "[$(date)] memory-sync triggered for ${TODAY}"
