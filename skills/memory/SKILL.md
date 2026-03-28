---
name: memory
description: >
  Save important information from conversations to the memory system. Triggers when user says
  "remember this" "save this" "don't forget" "record this" or /memory command. Also proactively
  triggers on new decisions, config changes, problem solutions, and preference updates.
  Stores to memory/, MEMORY.md, notes/, reference/, .learnings/.
user-invocable: true
---

# Memory Skill

## Trigger Scenarios

**Explicit:** "remember this" "save this" "don't forget" "record this" "/memory"

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
# Check journal + long-term index
grep -i "keyword" MEMORY.md memory/*.md

# Check knowledge base (notes/ included in memory_search)
memory_search "keyword"
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

# Search memory
grep -rn "keyword" MEMORY.md memory/*.md

# Search knowledge base (if extraPaths configured)
memory_search "keyword"

# Check MEMORY.md Events Timeline
grep "^- \*\*" MEMORY.md | tail -10
```

## Memory Search Configuration (Optional)

To enable full-text search across notes/, add to OpenClaw config:

```json
{
  "memorySearch": {
    "extraPaths": ["notes/"]
  }
}
```

This integrates the knowledge layer with the memory search system for semantic retrieval.