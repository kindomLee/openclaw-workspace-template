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

| Time | Job | Purpose |
|------|-----|---------|
| 20:07 daily | memory-janitor | Hall tag backfill |
| 21:03 daily | memory-reflect | Contradiction detection |
| 21:30 Sat | self-improvement | LEARNINGS promote |
| 03:03 Sun | memory-dream | Cross-domain association |
| 03:33 1st | memory-expire | Archive old memories |

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
