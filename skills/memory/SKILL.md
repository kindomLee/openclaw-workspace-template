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
grep -i "keyword" MEMORY.md memory/*.md
```

- Exact duplicate → skip
- Partially related → merge into existing entry
- Conflict → keep newer, note replacement date

### 3. Classify and Store

```
Infrastructure/preferences/core patterns? → MEMORY.md (P0)
Technical solutions/problem fixes?        → MEMORY.md (P1 + date)
Experimental/temporary?                   → MEMORY.md (P2 + date)
Personal notes/projects?                  → notes/
Tool/API reference?                       → reference/
Errors/learnings?                         → .learnings/
None of the above?                        → memory/YYYY-MM-DD.md
```

> P-level definitions and format in AGENTS.md

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

# Check MEMORY.md Events Timeline
grep "^- \*\*" MEMORY.md | tail -10
```
