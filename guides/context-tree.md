# Context Tree: Two-Layer Memory Architecture

A lightweight, file-based approach to persistent agent memory — inspired by Context Tree concepts from ByteRover and the NLAH paper (arXiv:2603.25723), but implemented without external dependencies.

## Why Context Tree?

### The Journal Noise Problem

A single-layer memory system (only `memory/YYYY-MM-DD.md`) accumulates everything:
- Casual conversations
- Status checks
- Debug sessions
- Intermediate attempts

Over time, this creates noise that drowns signal. The agent spends tokens reading through days of chitchat to find the one important decision.

### The Knowledge Fragmentation Problem

Without a dedicated knowledge layer, learned information gets scattered:
- Coffee preferences in one day's journal
- VPN setup in another
- User's project deadline in a third

Cross-referencing becomes impossible. The agent can't answer "what do I know about X" — it can only answer "what happened on day Y."

## The Solution: Two-Layer Architecture

| Layer | Purpose | File Pattern | Retention |
|-------|---------|--------------|-----------|
| **Journal** | Temporal log — what happened | `memory/YYYY-MM-DD.md` | 5-day rolling, then archive |
| **Knowledge** | Semantic store — what was learned | `notes/` (by topic) | Permanent until merged |

```
workspace/
├── memory/                    # Layer 1: Journal
│   ├── YYYY-MM-DD.md          # Daily journal (events, decisions, status)
│   └── archive-YYYY-MM/       # Auto-archived old journals
├── notes/                     # Layer 2: Knowledge (PARA-lite)
│   ├── 00-Inbox/              # Fresh drafts, triage here first
│   ├── 01-Projects/Active/    # In-flight projects with a deadline
│   ├── 01-Projects/Archive/   # Completed projects
│   ├── 02-Areas/              # Ongoing responsibilities / topics
│   ├── 03-Resources/          # Reference material, tools, services
│   └── 04-Archive/            # Cold storage
├── MEMORY.md                  # Long-term index (P0/P1/P2)
└── reference/                 # Deep references (optional)
```

## Layer 1: Journal (memory/)

**What goes here:**
- Events that occurred
- Decisions made
- Status changes (service up/down, config changed)
- Anything with a timestamp that matters

**What doesn't go here:**
- Topic-specific knowledge (that's for notes/)
- Detailed solutions (merge into notes/)
- Fragments <500 words (let cron sync organize later)

**Retention:** 5 days rolling. After 5 days, auto-archive to `archive-YYYY-MM/`.

## Layer 2: Knowledge (notes/)

**Suggested structure (PARA-lite):**
```
notes/
├── 00-Inbox/                # Drafts, triage candidates — nothing permanent
├── 01-Projects/Active/      # In-flight work with a deadline
│   └── <project-slug>/*.md
├── 01-Projects/Archive/     # Shipped / cancelled projects
├── 02-Areas/                # Ongoing responsibilities, no end date
│   └── <area>/*.md          #   e.g. coffee/, tech/openclaw/, infrastructure/
├── 03-Resources/            # Reference material, tools, services
│   └── <topic>/*.md
└── 04-Archive/              # Cold storage — moved out of daily use
```

The cron prompts (`curate-memory`, `weekly-memory-hygiene`,
`monthly-review`, `smart-wikilinks`) all assume this layout — if you
rename or flatten it, adjust those prompts too.

> **Naming convention:** Use kebab-case directory and file names (e.g., `home-automation/`, `wireguard-setup.md`). Organize by topic, not by date.

**Key principle: Merge First**
- Before creating a new note, search for existing related notes
- If found, append/merge instead of creating duplicate
- This prevents fragment explosion

**Making notes/ searchable:**

- **Claude Code mode (default)** — no config needed.
  `scripts/memory-search-hybrid.py` already walks `memory/` **and**
  `notes/` in one pass, so the hybrid-search hook (`.claude/hooks/
  memory-search-trigger.py`) automatically picks up anything you put
  under `notes/`. Add more directories by editing the `for base_dir
  in [memory_dir, notes_dir]` loop in `memory-search-hybrid.py`.

- **OpenClaw mode** — set `memorySearch.extraPaths` in your OpenClaw
  config:
  ```json
  {
    "memorySearch": {
      "extraPaths": ["notes/"]
    }
  }
  ```
  Path is workspace-relative. You can also add `reference/` if you keep
  deep reference docs there.

## Cleanup Strategy

### Journal (memory/)
- **5-day rolling window** — keeps recent context accessible
- **Monthly archive** — old journals moved to `archive-YYYY-MM/`
- **Cron job:** `memory-expire.sh` (monthly)

### Knowledge (notes/)
- **Merge, don't create** — always search first
- **Consolidate periodically** — weekly cron can merge related fragments
- **Archive when outdated** — old project notes → `notes/04-Archive/`

## Background Concepts

### Harness Engineering: Entropy Management

This approach borrows from the concept of "Entropy Management" in Harness Engineering (one of three pillars: Context Engineering, Constraints, Entropy Management). The idea is:

- **Context Engineering:** What information to retain
- **Constraints:** What boundaries to enforce
- **Entropy Management:** How to prevent information chaos

The two-layer system manages entropy by:
1. Limiting journal to recent 5 days (hard constraint)
2. Forcing knowledge to merge rather than fragment (entropy control)
3. Providing clear classification paths (structure)

### ByteRover Context Tree

ByteRover's Context Tree concept organizes memory hierarchically. Our file-based approach is lighter — no external tools needed, just directories and naming conventions. The principle is the same: distinguish between temporal events and semantic knowledge.

### NLAH Paper (arXiv:2603.25723)

The "Not Like A Human" paper discusses long-horizon agent memory. Our approach aligns with its findings:
- Separate working memory (journal) from long-term memory (knowledge)
- Periodic consolidation (cron jobs)
- Retrieval-aware storage (notes/ organized by topic)

## Quick Setup

1. `bootstrap.sh` already creates the full PARA tree. If you're
   adding it by hand:
```bash
mkdir -p notes/{00-Inbox,01-Projects/Active,01-Projects/Archive,02-Areas,03-Resources,04-Archive}
```

2. (Claude Code) No further setup — `memory-search-hybrid.py` already
   scans `notes/`. For OpenClaw, add `memorySearch.extraPaths` as
   shown above.

3. The cron jobs already handle journal cleanup. For knowledge
   consolidation, `cron/prompts/weekly-memory-hygiene.md` runs every
   Mon 21:00 and covers most of it.

## Backward Compatibility

This system is **optional**. New users can:
- Use only journal (memory/) — works exactly as before
- Add knowledge layer (notes/) — gains semantic retrieval
- Ignore the entire guide — template still functions

The journal-only mode remains fully supported. The knowledge layer is an enhancement, not a replacement.