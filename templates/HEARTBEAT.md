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
| `:02` hourly | curate-memory | Closed-day journals not yet curated → `curate-memory.flag` for `/curate-memory` (zero LLM) |
| 09:05 daily | memory-archive-rotate | Journal >5 days → `archive-YYYY-MM/` (pure shell, no LLM) |
| 20:07 daily | memory-janitor | Hall tag backfill + dup detection + notes QA |
| 21:07 daily | smart-wikilinks | Wikilink/Related suggestions (zero-LLM bare script) |
| 21:03 Wed (weekly) | memory-reflect | Contradiction detection |
| 21:30 Sat (weekly) | self-improvement | LEARNINGS promote |
| 03:03 Sun (weekly) | memory-dream | Cross-domain association |
| 09:10 1st (monthly) | memory-archive-timeline | MEMORY.md timeline rollup (pure shell, no LLM) |
| 10:00 1st (monthly) | monthly-review | Monthly highlights + stale-content review + old-archive cleanup suggestions |
| 09:30 Sun (weekly) | weekly-review | Weekly review checklist: corrections, unreviewed reflections, LEARNINGS promote/archive → `weekly-review.flag` |
| 21:30 Sun (weekly) | graphify-check-weekly | Flag a graph rebuild when `memory/` changed (no-op without graphify) |
| 21:32 Sun (weekly) | graphify-version-check | Flag when a newer `graphifyy` is on PyPI; self-clears (no-op without graphify) |
| 09:20 1st (monthly) | memory-retire-candidates | Retirement-candidate report for feedback memories (zero LLM) → `retire-review.flag` |
| 22:00 1st (monthly) | graphify-check-monthly | Monthly full graph refresh reminder (no-op without graphify) |
| 11:30 Mon (weekly) | broken-links-check | Broken `[[wikilinks]]` in notes/ ≥ threshold → `broken-links.flag` (zero LLM) |
| 11:32 Mon (weekly) | notes-todo-check | TODO backlog in notes/ ≥ threshold → `notes-todo.flag` (zero LLM) |
| 11:34 Mon (weekly) | external-links-check | External links returning 404/410 ≥ 5 → `broken-external-links.flag` (zero LLM, network) |

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
2. Create `cron/launchd/org.mklee.<job>.plist`
3. Re-install: `bash cron/install-mac.sh` or `bash cron/install-linux.sh`

### OpenClaw mode
- No LLM needed → bash script + `openclaw message send`
- Needs LLM → script collects data, then `openclaw cron add --at 10s`
