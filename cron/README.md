# Cron System

Scheduled jobs driven by `claude -p` (Claude Code) or `openclaw cron add` (OpenClaw).

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

| Time | Job | Purpose |
|------|-----|---------|
| 20:07 | memory-janitor | Hall tag backfill + quality cleanup |
| 21:03 | memory-reflect | Memory rumination / contradiction detection |
| 21:30 Sat | self-improvement | LEARNINGS analysis + promote to MEMORY.md |
| 03:03 Sun | memory-dream | Cold memory cross-domain association |
| 03:33 1st | memory-expire | Archive memories older than 30 days |

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

Required:
- `TG_BOT_TOKEN` / `TG_CHAT_ID` — Telegram notifications

Optional:
- `MINIMAX_API_KEY` — MiniMax LLM API
- Other service-specific keys

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
├── runner.sh              ← Universal job wrapper
├── install-mac.sh         ← macOS launchd installer
├── install-linux.sh       ← Linux crontab installer
├── config.env             ← API keys (.gitignore)
├── config.env.example     ← Config template
├── prompts/               ← Job prompts (Markdown)
│   ├── memory-reflect.md
│   ├── memory-dream.md
│   ├── memory-expire.md
│   ├── memory-janitor.md
│   └── self-improvement.md
├── launchd/               ← macOS plist schedule definitions
│   ├── org.oracle.memory-reflect.plist
│   └── ...
└── logs/                  ← Execution logs (auto-cleaned after 30 days)
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
