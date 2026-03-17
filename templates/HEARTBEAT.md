# HEARTBEAT.md

## Architecture

Heartbeats can be handled via OpenClaw cron or system crontab.

### Design Principles
1. **Scriptable → script it** — Don't waste LLM tokens on grep/find/compare
2. **Collect then decide** — Scripts gather data, LLM only when understanding needed
3. **Type A/B split** — Type A: fixed logic monitoring / Type B: needs LLM analysis
4. **Quiet hours** — 23:00-08:00 no disturbance unless urgent

### Example Crontab Layout
```
# Fixed scripts (no LLM needed)
05 * * * *   routine-checks          # hourly monitoring
05 8 * * *   version-check.sh        # daily version check

# Collect-then-decide (needs LLM)
02 * * * *   memory-sync.sh          # extract conversations → LLM writes memory if needed
02 20 * * *  daily-briefing.sh       # collect data → LLM summarizes
```

## Adding New Schedules

- No LLM needed → write a bash script, notify with `openclaw message send`
- Needs LLM → script collects data first, then `openclaw cron add --at 10s` triggers isolated LLM session
