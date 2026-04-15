# The flag system: cron → flag → SessionStart hook

A recurring problem with LLM agents: you want some background monitor to
notice when things need attention (broken links, TODO backlog, stale cache,
new logs) but you don't want the monitor itself to wake up an LLM every time.
Cron is cheap; LLM calls are not.

The workspace solves this with a three-step pipeline:

```
┌─────────────┐   ┌───────────────────┐   ┌──────────────────┐
│ cron        │──▶│ .claude/flags/    │──▶│ SessionStart     │
│ (fixed logic)│   │   <name>.flag     │   │ hook → Claude    │
└─────────────┘   └───────────────────┘   └──────────────────┘
  deterministic        plain text           LLM reads, acts,
  detection             signal               deletes the flag
```

**The rule**: cron only detects and writes flags. Cron never calls an LLM.
The reaction happens the next time you open a Claude Code session, which
may be in an hour, a day, or a week — whenever you're already paying the
wake-up cost for something else. This is the "hard trigger, soft action"
pattern.

## Anatomy of a flag

A flag is a tiny text file in `.claude/flags/`:

```
notes/ has 47 broken wikilinks (threshold 5)
Read .claude/flags/broken-links-report.txt for the list. Triage by fixing
or removing stale references.
When done: rm .claude/flags/broken-links.flag
```

Two things matter:
1. **Line 1 is the title** — what the SessionStart hook shows Claude.
2. **The last line tells how to clear the flag** — `rm <path>` so Claude
   knows when its job is done.

The companion report file (`<name>-report.txt`) holds the long-form
listing so the flag itself stays scannable.

## Anatomy of a cron script

```bash
#!/bin/bash
set -euo pipefail
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SELF_DIR/lib/workspace.sh"
source "$SELF_DIR/lib/notify.sh"
source "$SELF_DIR/lib/flag.sh"

WS=$(openclaw_workspace)
THRESHOLD="${MY_THRESHOLD:-10}"

# 1. Do the fixed detection (Python, grep, whatever — no LLM)
count=$(...)

# 2. Below threshold → clear any previous flag, exit clean
if [ "$count" -lt "$THRESHOLD" ]; then
    clear_flag "$WS" "my-check"
    exit 0
fi

# 3. Over threshold → write a flag + fire notification
write_flag "$WS" "my-check" \
    "short title with count and threshold" \
    "instructions including 'rm .claude/flags/my-check.flag' to clear"
notify "my-check crossed threshold: $count"
```

`scripts/cron-broken-links-check.sh` and `scripts/cron-notes-todo-check.sh`
are the two checks shipped by default. Copy them as a starting point.

## Anatomy of the SessionStart hook

`.claude/hooks/session-start-flags.sh` runs whenever a Claude Code session
starts. It reads every `*.flag` file under `.claude/flags/` and emits a
SessionStart `additionalContext` payload listing them. Claude sees the
flags as a system reminder and decides what to do.

No changes needed when you add new flag types — the hook picks up any
`*.flag` file automatically.

## Installing the cron jobs

```bash
bash scripts/install-cron.sh             # prints the snippet
bash scripts/install-cron.sh --install   # appends with confirmation
```

The snippet is derived from `templates/crontab.example`. Edit that file if
you want to add new checks or change the schedule.

## Notifications

Flag writes are silent by default. To get pinged when a flag fires, set
environment variables — canonical home is `cron/config.env` (loaded by
`cron/runner.sh`; source it manually in non-runner cron scripts too):

```
TG_BOT_TOKEN=...
TG_CHAT_ID=-1001234567890
```

`scripts/lib/notify.sh` also accepts the legacy `TELEGRAM_BOT_TOKEN` +
`NOTIFY_TARGET` pair for backwards compatibility. Supported channels:
`telegram`, `slack`, `stdout`, `none` — set `NOTIFY_CHANNEL` explicitly
if you want to override the auto-detection (which picks `telegram`
whenever `TG_BOT_TOKEN` + `TG_CHAT_ID` are both set).

## Why not just call the LLM from cron?

- Cost. Fixed detection is nearly free; LLM calls are not.
- Context. The LLM responds best when you're already in a session with
  loaded state — batching the reaction into your next intentional session
  keeps context coherent.
- Reliability. Cron → file is deterministic. Cron → LLM introduces a
  second failure mode (API errors, rate limits, quota exhaustion) on top
  of the actual detection logic.
- Debuggability. You can `ls .claude/flags/` to see the current agenda
  without reading logs or querying an LLM.
