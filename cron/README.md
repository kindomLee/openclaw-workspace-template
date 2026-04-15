# Cron System (Claude Code mode)

Scheduled jobs driven by `claude -p`. Each job is a Markdown prompt
(`prompts/<job>.md`) executed by `runner.sh` under launchd (macOS) or
user crontab (Linux).

> **If you're running the OpenClaw agent instead of Claude Code**, use
> the alternative pipeline under `scripts/memory-*.sh` + `scripts/
> install-cron.sh` (OpenClaw-mode, crontab-driven, calls
> `openclaw cron add`). See the comparison table at the bottom of this
> file.

Supports **macOS** (launchd) and **Linux** (crontab).

## Architecture

```
Scheduler (launchd / crontab)
  → runner.sh <job-name>
    → source config.env (load API keys)
    → claude -p "$(cat prompts/<job>.md)" (start Claude Code session)
    → logs written to logs/
```

Schedule definitions are stored as macOS `launchd/*.plist` files (source of truth).
The Linux installer auto-converts them to crontab entries.

## Default Jobs

> **Source of truth**: the master schedule lives in `templates/HEARTBEAT.md`.
> This table is a convenience copy — if you update either, update both
> or they will drift.

| Schedule | Job | Purpose |
|----------|-----|---------|
| `:02` hourly | curate-memory | Early-return curation (journal → MEMORY.md / notes/ / LEARNINGS.md) |
| 20:07 daily | memory-janitor | Hall-tag backfill + duplicate detection |
| 21:07 daily | smart-wikilinks | Conservative wikilink / Related-section suggestions for today's notes |
| 21:00 Mon (weekly) | weekly-memory-hygiene | Bulk hygiene: hall tags, wikilinks, dedupe, broken-link triage |
| 21:03 Wed (weekly) | memory-reflect | Recent-vs-long-term memory contradiction detection |
| 21:30 Sat (weekly) | self-improvement | Promote `.learnings/*` entries with `recurring_count ≥ 3` |
| 03:03 Sun (weekly) | memory-dream | Cross-domain cold-memory association |
| 10:00 1st (monthly) | monthly-review | Monthly highlights + stale-content review |
| 03:33 1st (monthly) | memory-expire | Archive `memory/*.md` older than 30 days |

## Installation

### Prerequisites

- `claude` CLI installed and in PATH (`claude -p` must work)
- `config.env` configured (see below)

### macOS (launchd)

```bash
# Install all jobs
bash cron/install-mac.sh

# Uninstall
bash cron/install-mac.sh --uninstall

# Verify
launchctl list | grep oracle
```

### Linux (crontab)

```bash
# Preview (dry run)
bash cron/install-linux.sh --dry-run

# Install to user crontab
bash cron/install-linux.sh

# Uninstall
bash cron/install-linux.sh --uninstall

# Verify
crontab -l | grep runner
```

## Configuration

```bash
cp cron/config.env.example cron/config.env
# Edit config.env with your values
```

`runner.sh` sources `cron/config.env` if it exists. Missing file is not
an error — jobs will run, they just won't send Telegram reports and
won't override the default job timeout.

### Recommended (for full functionality)

| Variable | Purpose |
|----------|---------|
| `TG_BOT_TOKEN` | Telegram bot token — required for any job that posts status reports |
| `TG_CHAT_ID` | Telegram chat id receiving reports |
| `JOB_TIMEOUT` | Per-job timeout in seconds. Default `1800` (30 min). Prevents `claude -p` hanging for hours; set higher for jobs that genuinely need it. |

### Optional

| Variable | Purpose |
|----------|---------|
| `MINIMAX_API_KEY` | MiniMax LLM API, used by some prompts if available |
| `NOTIFY_CHANNEL` / `SLACK_WEBHOOK_URL` | Alternative non-Telegram notification routing — see `scripts/lib/notify.sh` |

Jobs themselves can override `JOB_TIMEOUT` by exporting a different
value in `config.env`. The timeout is enforced via coreutils `timeout`
(or `gtimeout`); install with `brew install coreutils` on macOS if
neither is in `PATH`.

## Runtime Details

### Per-job `allowed_tools`

`runner.sh` parses the first line of a prompt file for an HTML comment of
the form:

```
<!-- allowed_tools: Bash,Read,Grep -->
```

Jobs that declare their tool scope get exactly those tools passed to
`claude --allowedTools`. Jobs without a declaration fall back to the safe
default `Bash,Read,Write,Edit,Grep,Glob,WebFetch`. Use the narrowest set
that still lets the job finish — it reduces the blast radius of a
misbehaving prompt.

### Elapsed time: `active` vs `wall`

`runner.sh` prints the job's wall-clock end timestamp plus one of two
elapsed forms:

```
Job memory-reflect finished with exit code 0 (42s)
Job memory-reflect finished with exit code 0 (active: 42s, wall: 11820s (host sleep included))
```

- **active**: real execution time, measured via `CLOCK_UPTIME_RAW` (see
  `cron/bin/mono_seconds.py`). On macOS, this clock does NOT advance
  while the host is asleep, so it reflects the time the job actually
  spent running.
- **wall**: `date +%s` delta. If the host slept partway through a job,
  wall gets inflated by the sleep duration — it is only a fallback.

> **Why two numbers?** Before this instrumentation, a job that finished
> in seconds but happened to log its "finished" line after a multi-hour
> sleep would show up as "42,000s". That made successful jobs look like
> runaway hangs and led to real misdiagnosis. The runner now prints
> `active` by default and only shows `wall` when it is noticeably larger.

### Network readiness gate

`runner.sh` probes `api.anthropic.com` on startup until TCP/TLS is up,
waiting up to 120 seconds. On timeout the run is treated as a **skipped**
job (exit 0, no failure notification sound), because a laptop being
offline or waking from sleep is expected operating state, not an
incident. Skipped runs are logged with:

```
Skipped: network not ready after 120s (offline/sleeping)
```

### Prompt delivery via stdin

The prompt is piped into `claude -p` via `<<<`, not passed as a
positional argument. On Linux, claude-cli 2.1.85+ treats `-p` as a pure
`--print` flag and ignores any positional prompt argument, so passing
the prompt as `claude -p "$PROMPT"` silently sends an empty prompt and
the job dies with `no stdin data received`. Stdin delivery works on
both macOS and Linux.

## Manual Execution

```bash
# Run a specific job
bash cron/runner.sh memory-reflect

# Check logs
ls -lt cron/logs/ | head
cat cron/logs/memory-reflect-*.log
```

## Adding a New Job

1. Create `prompts/<job-name>.md` — the prompt Claude will execute
2. Create `launchd/org.oracle.<job-name>.plist` — schedule definition
3. Re-install:
   - macOS: `bash cron/install-mac.sh`
   - Linux: `bash cron/install-linux.sh`

## Directory Structure

```
cron/
├── runner.sh              ← Universal job wrapper (network gate, timeout, logging)
├── install-mac.sh         ← macOS launchd installer (supports --dry-run / --uninstall)
├── install-linux.sh       ← Linux crontab installer (reads plists via plistlib)
├── config.env             ← Secrets — gitignored
├── config.env.example     ← Config template
├── prompts/               ← Per-job Markdown prompts (9 shipped)
│   ├── curate-memory.md             ← hourly :02
│   ├── memory-janitor.md            ← daily 20:07
│   ├── smart-wikilinks.md           ← daily 21:07
│   ├── memory-reflect.md            ← Wed 21:03
│   ├── weekly-memory-hygiene.md     ← Mon 21:00
│   ├── self-improvement.md          ← Sat 21:30
│   ├── memory-dream.md              ← Sun 03:03
│   ├── monthly-review.md            ← 1st 10:00
│   └── memory-expire.md             ← 1st 03:33
├── launchd/               ← macOS plist schedule definitions (one per prompt)
│   └── org.oracle.<job-name>.plist
├── logs/                  ← Per-job execution logs (auto-cleaned after 30 days)
└── bin/
    └── mono_seconds.py    ← CLOCK_UPTIME_RAW reader for active-time measurement
```

## OpenClaw vs Claude Code

The existing `scripts/memory-*.sh` use `openclaw cron add` for LLM invocation.
This `cron/` system uses `claude -p` instead. Both approaches work — choose based on your runtime:

| | OpenClaw (`scripts/`) | Claude Code (`cron/`) |
|---|---|---|
| LLM invocation | `openclaw cron add --session isolated` | `claude -p` |
| Scheduler | system crontab | launchd (Mac) or crontab (Linux) |
| Model | Configured in OpenClaw | Claude (the LLM itself) |
| Best for | OpenClaw-managed agents | Claude Code / standalone setups |
