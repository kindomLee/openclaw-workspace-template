---
name: curate-memory
description: >
  Full curator workflow for memory archival: scan the conversation, dedup against
  existing records, classify via the Context Tree, then decide whether each entry
  belongs in memory/ journal, MEMORY.md long-term index, notes/, reference/, or
  .learnings/. Merges fragments into existing notes when possible.
  Triggers on "curate memory", "organize memory", "archive this", "where should
  this go", "/curate-memory", and proactively after non-trivial technical
  decisions, infrastructure changes, or problem solutions.
  Complements the global save-memory skill: save-memory is a fast append-one-line
  shortcut for the journal, curate-memory is the full classify-and-merge workflow.
user-invocable: true
---

# Curate Memory Skill

> **Relationship to `save-memory`** (the global skill with a similar trigger surface):
> - `save-memory` — fast path. Appends a single line to `memory/YYYY-MM-DD.md` and exits.
>   Use when the user says "remember X" and X is already a well-formed journal entry.
> - `curate-memory` (this skill) — full curator flow. Reviews the conversation,
>   dedups against MEMORY.md and notes/, classifies via the Context Tree, and
>   writes to the right layer (journal vs long-term index vs topic notes vs
>   learnings). Higher latency, makes real classification decisions.
>
> This skill lives under `.claude/skills/curate-memory/`. The directory name must
> differ from the global `save-memory` skill to avoid a frontmatter `name:`
> collision. When a conversation produces a single one-liner, prefer `save-memory`.
> When it produces a chunk of new knowledge that needs to land in the right place,
> prefer this skill.

## Trigger Scenarios

**Explicit:** "curate memory" "organize memory" "archive this" "where should this go" "/curate-memory"

**Implicit (proactive):**
- Technical decisions or config changes
- Problem solutions
- Infrastructure changes (new services, config modifications)
- User preference/requirement changes
- **Compaction test:** Would this info be lost on compaction? Yes → record it

## Workflow

### 1. Scan Conversation
Review all conversation from last memory write to now. Identify new decisions/settings/preferences.

### 2. Duplicate Check (mandatory before writing)

```bash
# Fast grep on journal + long-term index
grep -ri "keyword" MEMORY.md memory/*.md

# Hybrid scored search across memory/ + notes/ in one pass
# (keyword overlap × temporal recency × hall-type boost)
python3 scripts/memory-search-hybrid.py "keyword" --days 90 --top 5
```

- Exact duplicate → skip
- Partially related → merge into existing entry (notes/ or memory/)
- Conflict → keep newer, note replacement date

### 3. Classify and Store (Two-Layer System)

The memory system has two layers: **journal** (temporal) and **knowledge** (semantic).

```
═══ Layer 1: Journal (memory/) — Temporal ═══
memory/YYYY-MM-DD.md              ← What happened (events, decisions, status changes)
                                    Retention: 5 days, then auto-archive to archive-YYYY-MM/

═══ Layer 2: Knowledge (notes/) — Semantic ═══
MEMORY.md                        ← Long-term index (P0 prefs/infra, P1 tech, P2 experiments)
notes/areas/{topic}/              ← Topic knowledge (merge-first, don't create fragments)
notes/resources/{topic}/          ← Tools/services references
reference/                        ← Deep references
.learnings/                       ← Errors and learnings
```

### Classification Tree

```
Is this "what happened" or "what was learned"?
├─ "What happened" (event/decision/status) → memory/YYYY-MM-DD.md
│   └─ Important enough for long-term index? → Also update MEMORY.md Events Timeline
├─ "What was learned" (knowledge/method/principle)
│   ├─ Related notes/ already exist? → Merge into existing (don't create new)
│   ├─ New topic + >500 words? → notes/areas/ or resources/ (create new)
│   └─ Fragment <500 words? → memory/YYYY-MM-DD.md, let cron sync organize
├─ Preference/infrastructure/core Pattern? → MEMORY.md (P0)
├─ Error/learning? → .learnings/LEARNINGS.md
└─ Uncertain? → memory/YYYY-MM-DD.md (safe default)
```

**Key Principles:**
- **Merge First:** Always search notes/ for related content before creating new
- **Don't put topics in memory/:** memory/ is for date-based journal only; topic knowledge goes to notes/
- **Keep memory/ clean:** Only recent 5 days + system files

### 4. Report
List: what was recorded (summary), where it was stored, what priority level.
Nothing to record → `✅ No unrecorded important information`

## Condensation Principles

- Long conversations → condense to 3-5 sentences (keep: decisions, actions, conclusions)
- Keep specific numbers (IPs, ports, prices, parameters)
- Omit chitchat and intermediate attempts (unless failure experience is valuable)

## Quick Reference

```bash
# Check today's memory
cat memory/$(date +%Y-%m-%d).md

# Fast grep
grep -rn "keyword" MEMORY.md memory/*.md

# Hybrid search (memory/ + notes/, scored)
python3 scripts/memory-search-hybrid.py "keyword" --top 10

# Check MEMORY.md Events Timeline (last 10 bullets)
grep "^- \*\*" MEMORY.md | tail -10
```

## Memory Search Notes

`scripts/memory-search-hybrid.py` already walks both `memory/` and
`notes/` in one pass, so no extra config is needed. If you're on
OpenClaw mode instead, see `guides/context-tree.md § Making notes/
searchable` for `memorySearch.extraPaths` setup.