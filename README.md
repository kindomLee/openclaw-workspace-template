# OpenClaw Workspace Template

Production-tested workspace template for OpenClaw AI agents, extracted from a real agent running 4+ months in production.

A fresh OpenClaw agent is stateless — it wakes up, helps you, and forgets everything. This template turns it into something that **persists, learns, and improves** over time.

## What You Get

After installing:

- 🧠 **Your agent remembers** — Daily logs (`memory/YYYY-MM-DD.md`) + curated long-term memory (`MEMORY.md`) with priority levels (P0/P1/P2) and auto-expiry. It reads yesterday's and today's logs every session.

- 🔧 **Your agent learns from mistakes** — A three-tier self-improvement system (repair / optimize / innovate) tracks errors, corrections, and knowledge gaps. Problems that recur 3+ times auto-promote to long-term memory.

- 🤖 **Your agent delegates** — Battle-tested sub-agent patterns with result verification and delivery confirmation. Main agent stays focused while sub-agents handle heavy lifting.

- 🌙 **Your agent dreams** — Weekly "cold memory association" finds cross-domain insights by randomly pairing unrelated memories. Daily "rumination" detects contradictions between recent and long-term memory. Monthly auto-archival keeps memory fresh.

- 📋 **Your agent maintains itself** — Routine checks framework (Type A: fixed logic / Type B: needs LLM) so your agent doesn't waste tokens on things a shell script can do.

- 🛡️ **Your agent verifies everything** — Four defense lines: create → execute → deliver → alert. "I did it" is never enough — it checks that the user actually received the result.

- 👤 **Your agent has personality** — `SOUL.md` defines who it is, `IDENTITY.md` gives it a name and emoji, `USER.md` helps it understand you.

- 🧬 **Your agent evolves its soul** — Behavioral corrections accumulate as proposals; after 3+ similar corrections, the agent proposes a `SOUL.md` update (with your approval).

## Quick Start

1. Install [OpenClaw](https://openclaw.ai) if you haven't:
```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

2. Clone this template:
```bash
git clone https://github.com/kindomLee/openclaw-workspace-template.git
cd openclaw-workspace-template
```

3. Run the bootstrap script:
```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

4. Run the health check:
```bash
bash clawd/scripts/health-check.sh
```

5. Edit the template files to personalize:
   - `IDENTITY.md` — Name, emoji, personality
   - `USER.md` — Your info so the agent knows you
   - `SOUL.md` — Agent personality and decision priors
   - `TOOLS.md` — Your frequently-used tools and connections

6. Set up cron jobs (see [Post-Install Checklist](guides/post-install-checklist.md)):
```bash
crontab -e
# Add memory lifecycle jobs — see checklist for exact entries
```

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
├── memory/            # Daily logs (YYYY-MM-DD.md)
│   ├── dreams.md      # Weekly cross-domain insights
│   ├── reflections.md # Daily memory rumination
│   └── archive-*/     # Auto-archived old memories
├── .learnings/        # Self-improvement tracking
│   ├── ERRORS.md
│   ├── LEARNINGS.md
│   └── FEATURE_REQUESTS.md
├── scripts/
│   ├── memory-dream.sh    # Weekly "dreaming" — cold memory association
│   ├── memory-reflect.sh  # Daily rumination — contradiction detection
│   ├── memory-expire.sh   # Monthly archive of old daily files
│   ├── memory-janitor.py  # Memory cleanup utility
│   └── health-check.sh    # Post-install verification
├── skills/            # Agent skills
│   ├── memory/        # Memory management
│   ├── telegram-html-reply/  # Rich HTML replies for Telegram
│   └── write-tmp/     # Temp file handling
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
Reference (reference/*.md)
```

### Sleep-Inspired Memory Lifecycle

Inspired by research on [how biological sleep consolidates memory](https://x.com/karry_viber/status/2033671561421721821):

| Mechanism | Script | Schedule | What It Does |
|-----------|--------|----------|-------------|
| **Dreaming** | `memory-dream.sh` | Weekly (Sun 3am) | Random cross-domain memory association for unexpected insights |
| **Rumination** | `memory-reflect.sh` | Daily (9pm) | Compare recent vs long-term memory, detect contradictions |
| **Forgetting** | `memory-expire.sh` | Monthly (1st) | Archive daily files older than 30 days |
| **Janitor** | `memory-janitor.py` | Daily | Clean up and organize memory files |

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

## Customization

This template is a starting point. After running for a week, your agent will naturally evolve:
- `SOUL.md` accumulates decision priors from corrections
- `MEMORY.md` fills with your infrastructure and preferences
- `.learnings/` captures patterns specific to your workflow
- New skills can be added to `skills/` as needed

## License

MIT
