# OpenClaw Workspace Template

**Language**: English | [繁體中文](README.zh-TW.md)

Production-tested workspace template for Claude Code (and OpenClaw) AI agents, extracted from a real agent running 4+ months in production.

A fresh OpenClaw agent is stateless — it wakes up, helps you, and forgets everything. This template turns it into something that **persists, learns, and improves** over time.

## What You Get

After installing:

- 🧠 **Your agent remembers** — Daily logs (`memory/YYYY-MM-DD.md`) + curated long-term memory (`MEMORY.md`) with priority levels (P0/P1/P2) and auto-expiry. It reads yesterday's and today's logs every session.

- 🔧 **Your agent learns from mistakes** — A three-tier self-improvement system (repair / optimize / innovate) tracks errors, corrections, and knowledge gaps. Problems that recur 3+ times auto-promote to long-term memory.

- 🤖 **Your agent delegates** — Battle-tested sub-agent patterns with result verification and delivery confirmation. Main agent stays focused while sub-agents handle heavy lifting.

- 🌙 **Your agent dreams** — Weekly "cold memory association" finds cross-domain insights by randomly pairing unrelated memories. Weekly "rumination" (Wed 21:03) detects contradictions between recent and long-term memory. Monthly auto-archival keeps memory fresh.

- 📋 **Your agent maintains itself** — Routine checks framework (Type A: fixed logic / Type B: needs LLM) so your agent doesn't waste tokens on things a shell script can do.

- 🛡️ **Your agent verifies everything** — Four defense lines: create → execute → deliver → alert. "I did it" is never enough — it checks that the user actually received the result.

- 👤 **Your agent has personality** — `SOUL.md` defines who it is, `IDENTITY.md` gives it a name and emoji, `USER.md` helps it understand you.

- 🧬 **Your agent evolves its soul** — Behavioral corrections accumulate as proposals; after 3+ similar corrections, the agent proposes a `SOUL.md` update (with your approval).

- 📚 **Your agent builds a knowledge base** — Topic-organized notes (`notes/areas/`, `notes/resources/`) complement daily logs (`memory/`). The knowledge layer merges related entries instead of creating fragments. Add `notes/` to `memorySearch.extraPaths` for full-text retrieval. See [Context Tree guide](guides/context-tree.md).

- 🔍 **Your agent finds things faster** — Hybrid memory search (`scripts/memory-search-hybrid.py`) scores `memory/` and `notes/` by keyword overlap × temporal recency × hall-type boost. A MemPalace-inspired hall taxonomy (`hall_facts`, `hall_events`, `hall_discoveries`, `hall_preferences`, `hall_advice`) tags journal entries for better retrieval, and a UserPromptSubmit hook forces a memory search whenever hard-trigger keywords appear — so "should I search memory?" is no longer a judgment call.

- 🚩 **Your agent has a pending-work inbox** — A **cron → flag → SessionStart hook** pipeline turns deterministic background checks (broken wikilinks, TODO backlog, stale caches) into flag files under `.claude/flags/`. Cron does the detection; the next Claude session picks them up via a SessionStart hook and acts on them. Cron never wakes the LLM directly — "hard trigger, soft action". See [flag-system guide](guides/flag-system.md).

## Features at a Glance

| Capability | Where | What it does |
|------------|-------|-------------|
| **Memory journal** | `memory/YYYY-MM-DD.md` | Daily logs with `[hall_*]` taxonomy tags for retrieval |
| **Long-term memory** | `MEMORY.md` | Curated facts, infrastructure, patterns (P0/P1/P2 priority) |
| **AAAK compact** | `MEMORY_COMPACT.md` | Lossless ~200-token snapshot loaded on every session |
| **Knowledge base** | `notes/areas/`, `notes/resources/` | Topic-organized notes that complement journal entries |
| **Hybrid search** | `scripts/memory-search-hybrid.py` | keyword × temporal recency × hall-type boost |
| **Hall-type tags** | `[hall_facts]` `[hall_events]` `[hall_discoveries]` `[hall_preferences]` `[hall_advice]` | Categorize journal entries for boosted retrieval |
| **Self-improvement** | `.learnings/`, `LEARNINGS.md` | Track corrections / errors / gaps; auto-promote when recurring ≥ 3 |
| **Memory dreaming** | `cron/prompts/memory-dream.md` | Weekly cross-domain association of unrelated memories |
| **Memory rumination** | `cron/prompts/memory-reflect.md` | Weekly contradiction detection with action-tracking + stale-check |
| **Memory expiry** | `cron/prompts/memory-expire.md` | Monthly auto-archive of memories older than 30 days |
| **Memory janitor** | `cron/prompts/memory-janitor.md` | Hall-tag backfill + duplicate detection + notes quality check |
| **Cron → flag → hook** | `.claude/flags/`, `.claude/hooks/session-start-flags.sh` | Background checks drop flags; next session picks them up |
| **Personality** | `SOUL.md`, `IDENTITY.md`, `USER.md` | Decision priors, name/emoji, user profile |
| **Sub-agent patterns** | `guides/sub-agent-patterns.md` | Battle-tested delegation with delivery verification |
| **Four defense lines** | `AGENTS.md` | create → execute → deliver → alert verification chain |
| **Hard-trigger memory search** | `.claude/hooks/memory-search-trigger.py` | UserPromptSubmit hook forces search on keyword match |
| **Cron system (Mac)** | `cron/install-mac.sh` | launchd plists with placeholder substitution |
| **Cron system (Linux)** | `cron/install-linux.sh` | Auto-converts plists → user crontab |
| **Network-wait wrapper** | `cron/runner.sh` | Waits for network readiness on wake-from-sleep before `claude -p` |

## Quick Start

1. Install your runtime of choice:
```bash
# Claude Code (default) — see https://docs.claude.com/claude-code for installer
# OpenClaw (alternative)
curl -fsSL https://openclaw.ai/install.sh | bash
```

2. Clone this template:
```bash
git clone https://github.com/kindomLee/openclaw-workspace-template.git
cd openclaw-workspace-template
```

3. Run the bootstrap script (installs into the current directory by default):
```bash
./bootstrap.sh
# or: ./bootstrap.sh --path ~/my-workspace --yes
```

4. Run the health check:
```bash
cd <your-workspace>
bash scripts/health-check.sh
```

5. Edit the template files to personalize:
   - `IDENTITY.md` — Name, emoji, personality
   - `USER.md` — Your info so the agent knows you
   - `SOUL.md` — Agent personality and decision priors
   - `TOOLS.md` — Your frequently-used tools and connections
   - `cron/config.env` — Copy from `cron/config.env.example` and fill `TG_BOT_TOKEN` / `TG_CHAT_ID` for Telegram alerts

6. Set up cron jobs:

```bash
# Claude Code mode (default) — macOS
bash cron/install-mac.sh

# Claude Code mode (default) — Linux
bash cron/install-linux.sh

# OpenClaw mode (alternative)
bash scripts/install-cron.sh --install
```

See [cron/README.md](cron/README.md) for details and [Post-Install Checklist](guides/post-install-checklist.md) for verification.

## Architecture

```
workspace/
├── AGENTS.md          # Operating manual (read every session)
├── SOUL.md            # Personality & decision priors
├── IDENTITY.md        # Name & emoji
├── USER.md            # About the human
├── TOOLS.md           # Quick reference for tools & connections
├── MEMORY.md          # Curated long-term memory (P0/P1/P2)
├── HEARTBEAT.md       # Scheduled tasks architecture
├── BOOTSTRAP.md       # Pre-generation task classification
├── memory/            # Daily journal (YYYY-MM-DD.md)
│   ├── dreams.md      # Weekly cross-domain insights
│   ├── reflections.md # Weekly memory rumination (Wed 9pm)
│   └── archive-*/     # Auto-archived old memories
├── notes/             # Knowledge base — optional, merge-first (see guides/context-tree.md)
│   ├── areas/         # Topics by domain
│   └── resources/     # Tools, services, references
├── .learnings/        # Self-improvement tracking
│   ├── ERRORS.md
│   ├── LEARNINGS.md
│   └── FEATURE_REQUESTS.md
├── cron/                  # Claude Code scheduled jobs (claude -p)
│   ├── runner.sh          # Universal job wrapper
│   ├── install-mac.sh     # macOS launchd installer
│   ├── install-linux.sh   # Linux crontab installer
│   ├── prompts/           # Job prompts (Markdown)
│   └── launchd/           # Schedule definitions (plist)
├── .claude/
│   ├── flags/            # Pending-work flags (cron drops them here)
│   ├── hooks/            # SessionStart + UserPromptSubmit hooks
│   └── skills/           # Workspace-local skills (auto-loaded by Claude Code)
│       ├── curate-memory/
│       ├── telegram-html-reply/
│       └── write-tmp/
├── scripts/
│   ├── lib/              # Shared helpers (workspace / notify / flag)
│   ├── cron-broken-links-check.sh  # Flag when broken wikilinks > N
│   ├── cron-notes-todo-check.sh    # Flag when TODO backlog > N
│   ├── memory-dream.sh    # Weekly "dreaming" — cold memory association
│   ├── memory-reflect.sh  # Weekly rumination — contradiction detection
│   ├── memory-expire.sh   # Monthly archive of old daily files
│   ├── memory-compress.py # Long-term memory compression (MEMORY.md + archive)
│   ├── memory-search-hybrid.py   # Hybrid keyword × temporal × hall scoring
│   ├── hall-tagger.sh             # Backfill hall_* tags on journal bullets
│   ├── compact-update.py          # Generate MEMORY_COMPACT.md from markers
│   ├── check-broken-wikilinks.py  # Standalone broken-link scanner
│   ├── check-schedule-drift.py    # Verify doc schedule tables match plists
│   ├── install-cron.sh            # Print / install the crontab snippet
│   └── health-check.sh            # Post-install verification
└── guides/            # Reference documentation
    ├── self-improvement.md
    ├── sub-agent-patterns.md
    ├── routine-checks.md
    └── multi-instance.md
```

## Memory System

### Three-Layer Architecture

```
Daily Notes (memory/YYYY-MM-DD.md)
    ↓ extraction + curation
Long-term Memory (MEMORY.md)
    ↓ promoted patterns
Knowledge Base (notes/)     # Optional — topics organized by theme
Reference (reference/*.md)
```

> **Optional:** Add `notes/` to `memorySearch.extraPaths` for full-text search across the knowledge base. See [Context Tree guide](guides/context-tree.md) for setup details.

### Sleep-Inspired Memory Lifecycle

Inspired by research on [how biological sleep consolidates memory](https://x.com/karry_viber/status/2033671561421721821):

| Mechanism | Script | Schedule | What It Does |
|-----------|--------|----------|-------------|
| **Curate** | `cron/prompts/curate-memory.md` | Hourly (:02) | Early-return wrapper; when new journal entries exist, promote to MEMORY.md / notes/ / LEARNINGS.md |
| **Dreaming** | `memory-dream.sh` | Weekly (Sun 3am) | Random cross-domain memory association for unexpected insights |
| **Rumination** | `memory-reflect.sh` | Weekly (Wed 9pm) | Compare recent vs long-term memory, detect contradictions |
| **Forgetting** | `memory-expire.sh` | Monthly (1st) | Archive daily files older than 30 days |
| **Janitor** | `cron/prompts/memory-janitor.md` | Daily (20:07) | LLM-driven hall-tag backfill + duplicate detection + notes quality check |
| **Compress** | `scripts/memory-compress.py` | Manual or monthly | Compression-based long-term memory maintenance (fold old timeline, compress P2, archive daily logs >30d into `memory/archive/YYYY-MM/` with `MANIFEST.jsonl`; supports `--list-archive` / `--restore YYYY-MM-DD` for audit + rollback) |

### Priority System

- **P0** — Personal preferences, infrastructure, core patterns (permanent)
- **P1** — Technical solutions, dated (review periodically)
- **P2** — Experiments, temporary (auto-expire after 30 days)

## Key Concepts

### Decision Priors (SOUL.md)

Your agent develops decision-making preferences over time. These are captured in `SOUL.md` and override generic best practices:
- Action bias: "do then report" over "ask then do"
- Risk calibration: bold internally, careful externally
- Communication style: concise, structured, conclusion-first

### Four Defense Lines (AGENTS.md)

Every action goes through verification:
1. **Create** — Did the setup actually work?
2. **Execute** — Is the output correct?
3. **Deliver** — Did the user receive it?
4. **Alert** — If anything failed, notify immediately

### Task Classification (BOOTSTRAP.md)

Before responding, the agent classifies each message:
- ⚡ Instant (chat, status) → reply directly
- 🔧 Execute (clear instruction) → do it
- 🔍 Research (needs analysis) → delegate
- ⚠️ Confirm (external action) → ask first
- 🧩 Compound (multiple tasks) → split & handle

## Guides

- [Self-Improvement System](guides/self-improvement.md) — Three-tier learning from mistakes
- [Sub-agent Patterns](guides/sub-agent-patterns.md) — Delegation, verification, delivery
- [Routine Checks](guides/routine-checks.md) — Type A/B monitoring framework
- [Multi-instance Setup](guides/multi-instance.md) — Running multiple specialized agents
- [Post-Install Checklist](guides/post-install-checklist.md) — Verify everything actually works after setup
- [Flag System](guides/flag-system.md) — `cron → flag → SessionStart hook` for background work triage
- [Smart Wikilinks (optional)](guides/smart-wikilinks.md) — Recipe for embedding-based related-note suggestions
- [Upgrading](guides/upgrading.md) — How to update an existing workspace when the template releases a new version

## Upgrading

When a new template version is released:

```bash
cd /path/to/openclaw-workspace-template && git pull
bash bootstrap.sh --path /your/workspace --yes    # adds new files only
bash scripts/template-diff.sh /your/workspace      # shows what changed
```

`bootstrap.sh` uses **skip-if-exists** — it never overwrites your customized files. For updated template files (`CLAUDE.md`, hooks, scripts), review the diff and manually merge. See [guides/upgrading.md](guides/upgrading.md) for the full process.

## Customization

This template is a starting point. After running for a week, your agent will naturally evolve:
- `SOUL.md` accumulates decision priors from corrections
- `MEMORY.md` fills with your infrastructure and preferences
- `.learnings/` captures patterns specific to your workflow
- New skills can be added to `skills/` as needed

## License

MIT
