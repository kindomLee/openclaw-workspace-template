# OpenClaw Workspace Template

Production-tested workspace template for OpenClaw AI agents, extracted from a real agent running 3+ months in production.

## What You Get

A fresh OpenClaw agent is stateless — it wakes up, helps you, and forgets everything. This template turns it into something that **persists, learns, and improves over time**.

After installing:

- 🧠 **Your agent remembers** — Daily logs (`memory/YYYY-MM-DD.md`) + curated long-term memory (`MEMORY.md`) with priority levels and auto-expiry. It reads yesterday's and today's logs every session.
- 🔧 **Your agent learns from mistakes** — A three-tier self-improvement system (`repair` / `optimize` / `innovate`) tracks errors, corrections, and knowledge gaps. Problems that recur 3+ times auto-promote to long-term memory so they never happen again.
- 🤖 **Your agent delegates** — Battle-tested sub-agent patterns with inject-rules, result verification, and delivery confirmation. Your main agent stays focused while sub-agents handle heavy lifting.
- 📋 **Your agent maintains itself** — Routine checks framework (Type A: fixed logic / Type B: needs LLM) so your agent doesn't waste tokens on things a shell script can do.
- 🛡️ **Your agent verifies everything** — Four defense lines: create → execute → deliver → alert. "I did it" is never enough — it checks that the user actually received the result.
- 👤 **Your agent has personality** — `SOUL.md` defines who it is, `IDENTITY.md` gives it a name and emoji, `USER.md` helps it understand you.

## Features

- **Memory System**: Daily logs + long-term curation with P0/P1/P2 priority and auto-archival
- **Self-Improvement**: Error tracking, correction learning, recurring pattern detection
- **Routine Checks**: Type A/B monitoring framework, crontab templates
- **Sub-agent Patterns**: inject-rules, REVIEW_THEN_DELIVER, STATUS_PENDING fallback
- **Starter Skills**: Memory management, Obsidian markdown, Telegram HTML replies, temp file handling
- **Multi-instance Support**: Run multiple specialized agents with isolated workspaces

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
4. Point OpenClaw to your new workspace:
   ```bash
   openclaw config set agents.defaults.workspace /path/to/your/workspace
   openclaw gateway restart
   ```
5. Fill in `USER.md` and `IDENTITY.md` with your specific information
6. Start chatting — your agent will use the workspace files automatically

## Directory Structure

```text
clawd/                          # Your workspace root
├── AGENTS.md                   # Core agent instructions and workflows
├── SOUL.md                     # Personality and interaction guidelines
├── IDENTITY.md                 # Agent identity configuration
├── USER.md                     # Information about the human user
├── TOOLS.md                    # Tool references and quick commands
├── MEMORY.md                   # Long-term curated memory
├── HEARTBEAT.md                # Heartbeat check instructions
├── memory/                     # Daily memory logs
│   └── YYYY-MM-DD.md           # Date-specific memory files
├── .learnings/                 # Self-improvement tracking
│   ├── ERRORS.md               # Error tracking and fixes
│   ├── LEARNINGS.md            # Knowledge gaps and improvements
│   └── FEATURE_REQUESTS.md     # New capability requests
├── guides/                     # Implementation guides
│   ├── self-improvement.md     # How to implement learning systems
│   ├── routine-checks.md       # Automated monitoring setup
│   ├── sub-agent-patterns.md   # Task delegation patterns
│   └── multi-instance.md       # Multiple agent instance setup
├── skills/                     # Starter agent skills
│   ├── memory/                 # Memory management skill
│   ├── write-tmp/              # Temp file writing workaround
│   ├── telegram-html-reply/    # Rich HTML replies for Telegram
│   └── obsidian-markdown/      # Obsidian-flavored markdown
├── scripts/                    # Utility scripts
├── reference/                  # Documentation and references
└── tmp/                        # Temporary files
```

## Guides Overview

### Self-Improvement Guide (`guides/self-improvement.md`)
Learn how to implement systematic self-improvement in your AI agent, including error tracking, learning from corrections, and building long-term capabilities.

### Routine Checks Guide (`guides/routine-checks.md`)
Set up automated monitoring and maintenance workflows, from simple health checks to complex analytical tasks.

### Sub-agent Patterns Guide (`guides/sub-agent-patterns.md`)
Master the patterns for delegating complex tasks to specialized sub-agents, including communication protocols and error handling.

### Multi-instance Guide (`guides/multi-instance.md`)
Run multiple specialized agent instances for different purposes, with proper isolation and resource management.

## Getting Started

After running `bootstrap.sh`, you'll have a complete workspace template. The key files to customize are:

1. **USER.md** - Information about yourself and your preferences
2. **IDENTITY.md** - Your agent's personality and identity
3. **TOOLS.md** - Add your specific tools and services
4. **AGENTS.md** - Customize workflows for your use case

## Requirements

- OpenClaw v1.x or higher
- Unix-like operating system (Linux, macOS, WSL)
- Basic shell environment

## License

MIT

---

*This template represents real-world patterns from a production OpenClaw deployment. Adapt and modify as needed for your specific use case.*