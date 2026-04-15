# Routine Checks Guide — 例行檢查指南

> Mixed-mode maintenance loop: let shell scripts do the deterministic part, let the LLM do the judgment part, and glue them together with Claude Code hooks + flag files.

## Core Principle — "Scriptable → script it"

Routine checks evolved through three phases:

1. **All-LLM** — easy to write, but every check burns tokens
2. **All-shell** — cheap, but can't handle semantic work
3. **Hybrid (current)** — fixed logic for the deterministic part, LLM only where understanding is required

The rule of thumb: **if it can be expressed as a threshold comparison or a pattern match, don't call the LLM.**

## Type A vs Type B

### Type A — Monitoring

Clear normal/abnormal boundary, can be decided by a shell/python script.

**Examples:**
- Service health check (HTTP status code)
- Disk usage threshold
- Memory file size (prevent runaway growth)
- API quota remaining
- Broken wikilinks count
- Stale TODO backlog count

**Implementation:** pure shell/python + threshold → drop a flag file, fire a `osascript` notification, or send Telegram.

### Type B — Analytical

Requires content understanding or cross-context judgment.

**Examples:**
- Summarizing news / emails and deciding which matter
- Pattern analysis across error logs
- User intent classification
- Memory contradiction detection (rumination)
- Weekly "dreaming" — random cross-domain memory association

**Implementation:** shell collects raw data → LLM analyzes it → LLM decides or writes the result back.

## Three-Layer Decision Tree

```text
Task classification
 ├── 1. Pure numeric / state check
 │    └── → fixed script + threshold → flag file / notification
 │
 ├── 2. Collect-then-decide
 │    └── → shell collects, then invokes LLM once for the decision
 │
 └── 3. Deep context understanding
      └── → LLM-driven from the start
```

---

## Claude Code Mode (default)

The template ships with a **cron → flag → SessionStart hook** pipeline that implements the three layers cleanly. It separates *detection* (deterministic, cheap, runs on cron) from *action* (expensive, requires LLM, runs only in the next Claude Code session).

### Layer 1 — Pure script (no LLM at all)

Use `launchd` (Mac) or user `crontab` (Linux) to run a shell/python script. The script either:

- fires a Telegram notification directly when a threshold is crossed, or
- drops a flag file into `.claude/flags/<name>.flag` (+ a sibling `<name>-report.txt` with the details) and exits

**Example — broken wikilinks check:**

```bash
# scripts/cron-broken-links-check.sh  (runs every Mon 11:30)
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

REPORT="broken-links-report.txt"
python3 scripts/check-broken-wikilinks.py > "$REPORT"
COUNT=$(wc -l < "$REPORT" | tr -d ' ')

if [ "$COUNT" -ge 5 ]; then
  cat > .claude/flags/broken-links.flag <<EOF
Broken wikilinks ≥ 5 (found $COUNT).
Run: read $REPORT, triage with scripts/add-wikilink-single.py, then rm .claude/flags/broken-links.flag
EOF
fi
```

The `session-start-flags.sh` hook (in `.claude/hooks/`) reads every `*.flag` on SessionStart and injects them as a system reminder, so the next time you open Claude Code you immediately see:

> ⚠️ Pending flags: broken-links.flag — Broken wikilinks ≥ 5 (found 12). …

You (or Claude) triage it, then `rm` the flag.

**Why this beats cron-calling-LLM-directly:**
- Cron runs deterministically, in the background, on schedule — no LLM needed to detect "there are 12 broken links"
- The expensive LLM session happens *only when you open Claude Code anyway*, so you pay zero extra token cost
- If you're offline or asleep, flags queue up silently — no failed runs, no noisy retries

### Layer 2 — Collect then decide (LLM called once)

Use `cron/runner.sh <job-name>` which:

1. waits for network readiness (skips cleanly if offline —筆電場景不算 failure)
2. loads `cron/config.env` (Telegram tokens, API keys)
3. reads `cron/prompts/<job>.md` (the prompt body, with optional `<!-- allowed_tools: … -->` per-job allowlist on line 1)
4. pipes the prompt into `claude -p` with the per-job tool allowlist
5. logs to `cron/logs/<job>-YYYYMMDD-HHMMSS.log`
6. fires macOS notifications on start/finish
7. measures both wall-clock and `CLOCK_UPTIME_RAW` so Mac sleep doesn't look like a hang

**Example — memory-janitor (daily):**

```xml
<!-- cron/launchd/org.oracle.memory-janitor.plist -->
<dict>
  <key>Label</key><string>org.oracle.memory-janitor</string>
  <key>ProgramArguments</key>
  <array>
    <string>__PROJECT_DIR__/cron/runner.sh</string>
    <string>memory-janitor</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>20</integer>
    <key>Minute</key><integer>7</integer>
  </dict>
</dict>
```

The matching `cron/prompts/memory-janitor.md` tells the LLM exactly what to do (backfill hall tags, detect duplicates, verify notes frontmatter) and — importantly — to **send a Telegram report at the end, even if nothing changed** (four-defense-line rule 4: never fail silently).

### Layer 3 — Full LLM (rare)

Used when a job genuinely needs multi-step reasoning over context — e.g. `memory-reflect` (weekly rumination) or `memory-dream` (weekly cross-domain association). Same wiring as Layer 2, the difference is just that the script upstream barely collects anything — the prompt tells the LLM to go read files itself.

### Default schedule (shipped in `cron/launchd/`)

| Time | Job | Layer | Purpose |
|------|-----|-------|---------|
| `:02` hourly | curate-memory | 2 | Early-return wrapper; when new journal entries exist, promote to MEMORY.md / notes/ / LEARNINGS.md |
| 20:07 daily | memory-janitor | 2 | Hall-tag backfill + duplicate detection |
| 21:07 daily | smart-wikilinks | 2 | Conservative wikilink/Related section suggestions for today's notes |
| 21:03 Wed (weekly) | memory-reflect | 3 | Contradiction detection across recent vs long-term memory |
| 21:00 Mon (weekly) | weekly-memory-hygiene | 2 | Weekly bulk hygiene: hall tags, wikilinks, dedup, broken-link triage |
| 03:03 Sun | memory-dream | 3 | Cross-domain cold-memory association |
| 10:00 1st of month | monthly-review | 3 | Monthly highlights + stale-content review |
| 03:33 1st of month | memory-expire | 1 | Archive memory/*.md older than 30 days |
| 21:30 Sat | self-improvement | 2 | Promote `.learnings/*` entries with `recurring_count ≥ 3` |
| Mon 11:30 | cron-broken-links-check | 1 | Flag when broken wikilinks ≥ 5 |
| Mon 11:32 | cron-notes-todo-check | 1 | Flag when TODO backlog ≥ 20 |

Install: `bash cron/install-mac.sh` (macOS) or `bash cron/install-linux.sh` (Linux). See `cron/README.md` for details.

### Writing a new routine check (Claude Code mode)

1. **Detection is deterministic** → write a shell script in `scripts/cron-*.sh` that drops a flag file. No prompt needed.
2. **Detection needs LLM** → write `cron/prompts/<job>.md` + `cron/launchd/org.oracle.<job>.plist`, then re-run `cron/install-mac.sh`.
3. Every new prompt should have a `<!-- allowed_tools: Bash,Read,Grep,... -->` first line — keeps the blast radius small.
4. Every prompt must **always** report back (Telegram / flag / log), even on "nothing to do" — silent success violates the fourth defense line.

---

## OpenClaw Mode (alternative)

If you're running this template inside an OpenClaw agent instead of Claude Code, the mapping is:

| Claude Code concept | OpenClaw equivalent |
|---|---|
| `cron/runner.sh` + `claude -p` | system crontab + `openclaw cron add --session isolated` |
| `.claude/flags/*.flag` + SessionStart hook | `openclaw message send` to main session |
| `cron/prompts/<job>.md` | inline prompt in `--system-event` or `sessions_spawn` payload |
| `cron/config.env` | OpenClaw workspace config |

**Example — Type A check (OpenClaw mode):**

```bash
#!/bin/bash
# health-check.sh — runs from system crontab
set -e
WORKSPACE="/path/to/workspace"
ALERT_THRESHOLD=90

DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt "$ALERT_THRESHOLD" ]; then
  openclaw cron add --name "disk-alert" --at "now" \
    --system-event "⚠️ Disk usage: ${DISK_USAGE}%" --session main
fi

if ! pgrep -f "openclaw gateway" > /dev/null; then
  openclaw cron add --name "gateway-down" --at "now" \
    --system-event "🔴 OpenClaw gateway is down" --session main
fi
```

**Example — Type B check (OpenClaw mode):**

```bash
# system crontab
0 22 * * * openclaw cron add --name "daily-sync" --at "now" \
  --system-event "trigger daily sync" --session main
```

The tradeoff: OpenClaw mode gives you direct access to the main agent's memory and context, at the cost of depending on the OpenClaw gateway running. Claude Code mode is decoupled (cron doesn't care if Claude Code is open), at the cost of a flag-file round trip.

## Language Choice

| Language | Use when |
|---|---|
| **Bash** | File checks, API probes, simple state comparisons |
| **Python** | JSON/YAML parsing, multi-step logic, anything calling the Anthropic SDK |
| **Rust/Go** | Performance-critical log analysis, anything running more than once a minute |

## Implementation Tips

1. **Start with Type A** — get the boring scriptable checks in place first, then layer Type B on top
2. **Incremental migration** — if you have an all-LLM routine, split the deterministic part out into a shell pre-step
3. **Uniform output** — all scripts should produce `flag + report.txt` so the SessionStart hook can treat them uniformly
4. **Log and watch the watchers** — a routine check that silently stops firing is worse than no check. Keep `cron/logs/` around and `tail` them once a week.

Remember: **get it running, then refine.** A crude shell check beats a beautiful LLM check that never gets deployed.
