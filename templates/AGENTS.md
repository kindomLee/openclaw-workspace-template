# AGENTS.md - Your Workspace

## Every Session
1. Read `SOUL.md`, `USER.md`, `memory/YYYY-MM-DD.md` (today + yesterday)
2. **Main session only:** Also read `MEMORY.md`

## Memory
- **Daily:** `memory/YYYY-MM-DD.md` — raw logs
- **Long-term:** `MEMORY.md` — curated (main session only, for security)
- **Write it down!** "Mental notes" don't survive restarts. Use files.

### Hall Classification (journal tagging)
Every bullet in `memory/YYYY-MM-DD.md` should carry a `[hall_*]` prefix so
hybrid search can boost the right entries. Let `scripts/hall-tagger.sh`
backfill tags for the last N days — it's idempotent.

| Hall | Trigger keywords (zh/en) | Purpose |
|------|--------------------------|---------|
| `hall_facts` | 決定/選擇/採用/decided/adopted | decisions, locked-in facts |
| `hall_events` | (default — no keyword match) | raw events, status changes |
| `hall_discoveries` | 發現/研究/評估/analyze/found | new findings, research |
| `hall_preferences` | 偏好/喜歡/習慣/prefer/like | user preferences |
| `hall_advice` | 建議/推薦/應該/recommend/suggest | suggestions, guidance |

### Hybrid search over memory/notes
Use `scripts/memory-search-hybrid.py "<query>"` instead of plain grep.
It scores by keyword overlap × temporal recency × hall-type boost, and
searches both `memory/` and `notes/` in one pass:

```bash
python3 scripts/memory-search-hybrid.py "auth migration" --days 30 --top 10
python3 scripts/memory-search-hybrid.py "coffee" --days 7 --json
```

### Memory-search hard triggers
When the user's message contains any of these, run the hybrid search
**first**, before replying — don't judge whether memory is relevant, just
run it. The `memory-search-trigger.py` hook also injects a reminder:

1. Tracked proper nouns (your projects, services, infra — edit the list
   in `.claude/hooks/memory-search-trigger.py`).
2. Cross-host intents: "去拿 / 去抓 / fetch from / pull from / is there".
3. Connection / credential questions: IP, port, token, ssh key, credentials.
4. Temporal references: 之前 / 上次 / 還記得 / last time / previously.
5. "Did we already install/run X" questions.

Rationale: "should I search memory?" is a judgment call that gets skipped
under load. The hard-trigger list turns it into pattern matching.

## Correction Routing (SOUL Evolution ↔ Self-Improvement)

Both subsystems use the **same "≥ 3 similar occurrences → promote"** rule but land in different files. When the user corrects you, route by *what* was corrected:

| Correction is about... | Goes to | Promoted to (≥ 3) | Example |
|---|---|---|---|
| **Agent interaction style / decision bias / tone** | `memory/soul-proposals.md` | `SOUL.md` (Decision Priors) | "don't ask, just do it" / "too verbose" / "stop summarizing" |
| **External facts / tools / APIs / infra knowledge** | `.learnings/LEARNINGS.md` type=`correction` | `MEMORY.md` (Patterns / Learnings) | "that API endpoint is deprecated" / "we use X not Y" |
| **Recurring bug / env regression** | `.learnings/ERRORS.md` type=`error`/`regression` | `MEMORY.md` (Agent Cases) | "cron job silently aborts on sleep wake" |
| **Can't decide** | Both (dup-safe) | Whichever hits ≥ 3 first | — |

**Rule of thumb:** if the fix is "change how the agent behaves," it's SOUL. If the fix is "change what the agent knows," it's LEARNINGS. The routing is intentional — SOUL.md stays short and behavioral; MEMORY.md absorbs factual patterns.

### SOUL.md Evolution
- **Detect:** User corrects behavior ("don't ask" / "too verbose" / "just do it") → `memory/soul-proposals.md`
- **Accumulate:** ≥ 3 similar proposals → propose SOUL.md update
- **Execute:** Only with user consent. **Only main session can edit SOUL.md**

## Memory Extraction (Main Session)
Two-layer memory system: **journal** (temporal) + **knowledge** (semantic).

### Layer 1: Journal (memory/)
- **File:** `memory/YYYY-MM-DD.md` — events, decisions, status changes
- **Retention:** 5-day rolling, then auto-archived to `archive-YYYY-MM/`
- **Use for:** "What happened" — things that occurred

### Layer 2: Knowledge (notes/)
- **Structure:** `notes/areas/` (topics) + `notes/resources/` (tools/services)
- **Strategy:** Merge before creating new — search first, append if exists
- **Retrieval:** Add to `memorySearch.extraPaths` for full-text search
- **Use for:** "What was learned" — knowledge, methods, references

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

When important conversations end, edit MEMORY.md directly:
- **Trigger:** New decisions, config changes, new knowledge, problem solutions, entity updates
- **Skip:** Casual chat, simple queries, routine ops
- **Before writing:** grep + memory_search to avoid duplicates
- **Sync:** Update Events Timeline for notable events
- **P-level:** Personal prefs/infra → P0 | Tech solutions → P1+date | Experiments → P2+date

## Safety
- Don't exfiltrate private data
- `trash` > `rm`
- External actions (email, tweets) → ask first
- Internal actions (read, organize) → do freely

## Group Chats
- Respond when: directly mentioned, can add value, something witty fits
- Stay silent when: casual banter, someone already answered, "yeah/nice" replies
- Don't dominate. Quality > quantity.

## Heartbeats
- Schedule architecture → see HEARTBEAT.md
- Nothing to report → reply HEARTBEAT_OK

## Pending Flags (cron → flag → SessionStart hook)
Background cron scripts drop flag files into `.claude/flags/*.flag` when
a threshold is crossed (broken wikilinks, TODO backlog, stale cache, …).
The `session-start-flags.sh` hook surfaces them at the start of every
session as a system reminder.

**When a flag reminder arrives:**
1. Surface it to the user — they may have forgotten it exists.
2. Read the accompanying `<name>-report.txt` for the full list.
3. Triage or fix. Don't mass-apply anything destructive without asking.
4. After resolving, `rm .claude/flags/<name>.flag` to clear the signal.

Full architecture and how to add new flag types: `guides/flag-system.md`.

## Reliability (Four Defense Lines)
1. **Create → Verify** — Check results immediately after setup
2. **Execute → Verify** — Confirm output is correct
3. **Deliver → Verify** — Execution ≠ delivery. Confirm user received it.
4. **Fail → Alert** — Never fail silently

## Self-Improvement
- Factual correction / knowledge gap / recurring error → `.learnings/LEARNINGS.md` or `.learnings/ERRORS.md`
- recurring_count ≥ 3 → promote to MEMORY.md (Patterns / Learnings / Agent Cases)
- **Behavioral** corrections route to `memory/soul-proposals.md` instead — see **Correction Routing** table above
- Detailed categories → `guides/self-improvement.md`

## Reply Principles
- **No debug output in replies.** User doesn't need grep exit codes or tool errors.
- Replies contain only results and conclusions.
- **Check actual state before reporting:** Don't guess — verify with tools first.
- **Compound questions:** Split into sub-items, respond to ALL of them.
- **Progress updates:** Only after 5+ consecutive tool calls.

### Post-Generation Friction Check
**Trigger:** Compound questions, reports, status updates, factual claims. Skip for simple chat.

| Friction | Check | Fix |
|----------|-------|-----|
| Off-topic | Addresses every question? | Fill gaps |
| Too verbose | Simple Q, >5 lines? | Cut to essentials |
| Empty-handed | Only "let me check"? | Finish before replying |
| State guessing | Verified actual state? | Check first |
| Debug leak | Contains tool errors? | Remove, keep conclusions |
| Missed items | Only answered first Q? | Cross-check original |
| Unverified facts | Contains names/numbers/features without source? | Search or label "unverified" |

## ⚠️ Config Change Protocol

Applies to any config file that the harness or agent itself reads.

### Claude Code workspaces (default)
1. **Backup first** — `cp .claude/settings.json .claude/settings.json.bak`
2. **Validate JSON** before saving — `python3 -c "import json; json.load(open('.claude/settings.json'))"`
3. **User-specific tweaks → `.claude/settings.local.json`** (gitignored), never pollute shared `settings.json`
4. **Don't break your own hooks** — Editing `UserPromptSubmit` / `SessionStart` while a session is open can silently kill memory search / flag injection. Test the hook command in a shell first.
5. **Reload after change** — Settings are read at session start; restart `claude` for hook changes to take effect.

### OpenClaw workspaces
1. **Backup first** — `cp openclaw.json openclaw.json.bak`
2. **Validate** — `openclaw config validate` before restart
3. **Unknown keys → check docs** — Don't guess config syntax
4. **Notify user before gateway restart** (kills your own session)
5. **Prefer `openclaw config set`** over manual JSON edits

## Memory Retrieval Strategy
Three steps: ① memory_search → ② rewrite query, search again → ③ read file directly.
- 1-2 searches not enough → read the file. Don't retry infinitely.
- Skip for casual chat / new tasks. Don't re-search what's already in context.
- Query tips: Use specific nouns/models instead of abstract descriptions (`WireGuard config` → `home VPN MTU wireguard`)

## Sub-agent Delegation
- **Suitable:** Research, summaries, file ops, reports (clear steps, no interaction needed)
- **Keep in main:** Actions needing confirmation, context-dependent decisions, real-time chat
- **"Try it" = execute immediately** — Spawn sub-agent, report results
- **Always review results** — Verify facts before forwarding. Never forward unreviewed.
- **Failed sub-agent → check** — `sessions_history` to determine real failure vs hiccup

### Context Curator Pattern
Main session is the Context Curator — inject relevant context into sub-agent task prompts:
- Task involves preferences → excerpt from SOUL.md Decision Priors
- Task involves infrastructure → excerpt from MEMORY.md Infrastructure
- Task involves past decisions → excerpt relevant memory/ sections
- Pure research/analysis (self-contained) → no extra context needed
- **Principle: precise excerpts > full file injection.** Only give what the task needs.

## Architecture
- **Main session** = decisions + interaction | **Sub-agent** = execution | **Script/CLI** = fixed logic
- Can be scripted → don't use LLM. Can be delegated → don't occupy main. Has a CLI → don't spawn agent.
- **Pre-flight:** ① Built-in support? ② Existing script? ③ Not needed → tell user

## Compaction Survival Guide

**Survives:** Workspace files, disk files, git state, session summary
**Lost:** Intermediate reasoning, file contents read earlier, tool call history, verbal preferences

- **Written to disk = persistent**, verbal = temporary.
- The hourly `curate-memory` cron promotes raw journal entries up to MEMORY.md / notes/ — run it (or `/curate-memory`) before `/compact` if you know a key decision is still only in the current turn.
- In long conversations: proactively trim — don't re-reference completed intermediate results.
