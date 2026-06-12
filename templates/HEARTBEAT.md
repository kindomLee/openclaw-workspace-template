# HEARTBEAT.md

## Architecture

Two scheduling modes available:

| Mode | Scheduler | LLM Invocation | Best For |
|------|-----------|---------------|----------|
| **Claude Code** | launchd (Mac) / crontab (Linux) | `claude -p` | Standalone / Claude Code setups |
| **OpenClaw** | system crontab | `openclaw cron add` | OpenClaw-managed agents |

### Design Principles
1. **Scriptable → script it** — Don't waste LLM tokens on grep/find/compare
2. **Collect then decide** — Scripts gather data, LLM only when understanding needed
3. **Type A/B split** — Type A: fixed logic monitoring / Type B: needs LLM analysis
4. **Quiet hours** — 23:00-08:00 no disturbance unless urgent

### Claude Code Mode (cron/)

```
launchd / crontab
  → cron/runner.sh <job-name>
    → source config.env
    → claude -p "$(cat prompts/<job>.md)"
    → logs/
```

Default schedule:

> **This table is the single source of truth** for the shipped schedule.
> `cron/README.md` and `guides/routine-checks.md` link here; verify with
> `python3 scripts/check-schedule-drift.py`.

| Time | Job | Purpose |
|------|-----|---------|
| `:02` hourly | curate-memory | Early-return curate (journal → MEMORY.md/notes/LEARNINGS.md) |
| 09:05 daily | memory-archive-rotate | Journal >5 days → `archive-YYYY-MM/` (pure shell, no LLM) |
| 20:07 daily | memory-janitor | Hall tag backfill + dup detection + notes QA |
| 21:07 daily | smart-wikilinks | Wikilink/Related suggestions (zero-LLM bare script) |
| 21:03 Wed (weekly) | memory-reflect | Contradiction detection |
| 21:30 Sat (weekly) | self-improvement | LEARNINGS promote |
| 03:03 Sun (weekly) | memory-dream | Cross-domain association |
| 09:10 1st (monthly) | memory-archive-timeline | MEMORY.md timeline rollup (pure shell, no LLM) |
| 10:00 1st (monthly) | monthly-review | Monthly highlights + stale-content review + old-archive cleanup suggestions |

Retired jobs: `memory-expire` (daily rotate made its monthly 60-day scan a
permanent no-op; surviving duties moved into monthly-review) and
`weekly-memory-hygiene` (every duty was a superset copy of memory-janitor /
smart-wikilinks / the Monday broken-links flag check).

Install: `bash cron/install-mac.sh` or `bash cron/install-linux.sh`

### OpenClaw Mode (scripts/)

```
system crontab
  → scripts/memory-*.sh
    → openclaw cron add --session isolated
```

Install: `bash scripts/install-cron.sh --install`

## Adding New Schedules

### Claude Code mode
1. Create `cron/prompts/<job>.md`
2. Create `cron/launchd/org.oracle.<job>.plist`
3. Re-install: `bash cron/install-mac.sh` or `bash cron/install-linux.sh`

### OpenClaw mode
- No LLM needed → bash script + `openclaw message send`
- Needs LLM → script collects data, then `openclaw cron add --at 10s`
