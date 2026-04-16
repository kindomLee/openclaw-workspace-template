# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.0] - 2026-04-16

Major release: **Claude Code-first pivot**, declarative workspace spec,
capability-grouped permissions, and guided first-run onboarding.

Themes: the template shifts from "OpenClaw-only" to "Claude Code default,
OpenClaw optional", bootstrap moves from imperative bash to a declarative
spec, and the first-run experience goes from "read the README and edit
files yourself" to "type `hi` and the agent walks you through it".

### Added

- **First-run profile setup flag** (`welcome-profile-setup.flag`):
  `bootstrap.sh` writes a flag that the SessionStart hook surfaces on
  the first `claude` session. Claude uses `AskUserQuestion` to walk the
  user through personalizing `USER.md` / `IDENTITY.md` / `SOUL.md` /
  `TOOLS.md` one field at a time, in 繁體中文 by default. Skippable
  fields become `<!-- TODO: fill in -->` markers. (#6)
- **Declarative workspace spec** (`templates/workspace.spec`): 44-line
  DSL file (`dir`, `copy_tree` verbs) that replaces the imperative
  `mkdir`/`copy_tree` block in `bootstrap.sh`. Single source of truth
  for the workspace shape, diffable, parseable by pure bash. Unknown
  verbs fail loudly with `workspace.spec:<line>:` error messages. (#7)
- **Capability-grouped permissions** (`settings.capabilities.toml` +
  `tools/build-settings.py`): `settings.json`'s flat allow list is now
  generated from a TOML spec grouped into 6 capability buckets
  (`run_scripts`, `inspect_git`, `inspect_shell`, `read_files`,
  `write_memory`, `write_notes`). Build script uses stdlib `tomllib`,
  preserves hooks verbatim, idempotent. Permission set unchanged
  (25 entries). (#7)
- **`templates/.claude/SETTINGS_GUIDE.md`**: documents capability
  buckets, add/remove workflow, and why we generate instead of hand-edit.
- **Claude Code-first README** + **繁體中文 README** (`README.zh-TW.md`):
  rewrote Quick Start to default to `claude` CLI, with OpenClaw as an
  alternative. Added Features at a Glance table.
- **`templates/CLAUDE.md`**: new priming file with wake-up protocol,
  core truths (condensed from SOUL.md), hall classification cheat sheet,
  correction routing matrix, pending flags priority instruction, and
  reply principles. This is the first file Claude reads on session start.
- **Dual-mode guides** (`guides/multi-instance.md`, `guides/post-install-checklist.md`,
  `guides/routine-checks.md`): rewrites covering both Claude Code and
  OpenClaw usage.

### Changed

- **`bootstrap.sh`**: refactored to read `workspace.spec` via
  `process_workspace_spec()`. CLI parsing, DRY_RUN, confirmation,
  welcome flag, permissions, and next-steps banner stay in bash. "Next
  steps" now says "type `hi`" instead of "edit files manually". (#6, #7, #8)
- **`templates/.claude/settings.json`**: now a generated artifact from
  `settings.capabilities.toml`. Same 25 permission entries, reordered
  by capability group. Hooks preserved verbatim.
- **`templates/CLAUDE.md` § Pending flags**: rewritten from passive
  "need triage" to **"PRIORITY — act before anything else"**, ensuring
  flags (especially the welcome flag) are addressed immediately on the
  user's first message. (#8)
- **Scripts**: removed hardcoded paths, unified naming, dual-mode health
  check (`scripts/health-check.sh`).
- **Cron system**: job timeout, 9-job schedule, per-job `allowed_tools`,
  macOS + Linux installer hardening.
- **`.claude/hooks`**: hardened and promoted to workspace-local.

### Backported (from cc-memory-project production)

- **`cron/runner.sh`**: active vs wall elapsed metric (avoids false-hang
  reports from host sleep), network readiness gate raised to 120s with
  soft skip, prompt delivery via stdin, error-handling fix.
- **`memory-search-trigger.py`**: upgraded from reminder-only to
  auto-search + rerank with 3 layers (query classification, domain
  routing, category dedup) + 60s TTL cache.
- **`skills/memory/` → `skills/curate-memory/`**: renamed to avoid
  global-skill name collision with `save-memory`.

### Technical details (cron runner + memory-search hook)

- **`cron/bin/mono_seconds.py`**: prints `CLOCK_UPTIME_RAW` seconds via
  `ctypes`. On macOS this clock does NOT advance while the host is
  asleep (the opposite of Darwin's `CLOCK_MONOTONIC`, which does). Linux
  falls back to `CLOCK_MONOTONIC`. The runner uses this to measure
  actual execution time rather than wall-clock time that gets inflated
  by host sleep.
- **Per-job `allowed_tools` parsing in `cron/runner.sh`**: prompt files
  may declare their tool scope in a first-line HTML comment
  (`<!-- allowed_tools: Bash,Read -->`). Jobs without a declaration fall
  back to the safe default. Shrinks the blast radius of a misbehaving
  prompt without adding config surface. Inspired by OpenClaw's per-job
  tool allowlists.

### Changed

- **`cron/runner.sh` elapsed metric**: was reporting `date +%s` delta as
  `elapsed`, which on a laptop that slept mid-job inflated the number
  by the sleep duration. Jobs that ran in 40 seconds were logged as
  taking 39 hours because they happened to flush their "finished" line
  after a weekend of host sleep. The runner now prints `active: Xs`
  from `mono_seconds.py` by default, and only shows `(active: Xs, wall:
  Ys (host sleep included))` when wall noticeably exceeds active.
  No more false-positive hang investigations.
- **`cron/runner.sh` network readiness gate**: raised the timeout from
  60s to 120s, and changed the timeout behavior from `exit 1 + Basso
  failure sound` to a soft **skip** (`exit 0`) logged as
  `Skipped: network not ready after 120s (offline/sleeping)`. A laptop
  being offline or waking from sleep is expected operating state, not
  an incident, and a weekly `memory-sync` run shouldn't light up 24
  false-alarm notifications over a single weekend.
- **`cron/runner.sh` prompt delivery**: the prompt is now piped into
  `claude -p` via `<<<"$PROMPT"` instead of passed as a positional
  argument. On Linux, `claude-cli` 2.1.85+ treats `-p` as a pure
  `--print` flag and silently ignores positional prompt args, so the
  previous form sent an empty prompt and the job died with
  `no stdin data received`. Stdin works on both macOS and Linux.
- **`cron/runner.sh` error handling**: the `claude -p` call is now
  wrapped in an `if/else` so a non-zero exit is captured into
  `EXIT_CODE` before the "finished" log line runs. Previously `set -e`
  killed the script on a failed claude invocation before the elapsed
  log line could be written.
- **`templates/.claude/hooks/memory-search-trigger.py`** — upgraded from a
  reminder-only hook (89 lines) to an auto-search hook (~520 lines). The
  hook still detects the same set of hard-trigger keywords, but now also
  shells out to `scripts/memory-search-hybrid.py` itself and injects the
  top-N reranked results directly into `additionalContext`. Claude opens
  the next turn with the search output in front of it instead of having
  to remember to run the script.

  Three reranking layers on top of the raw hybrid score:
    1. **Query classification** — temporal hints in the prompt
       (`HISTORICAL_HINTS` / `RECENT_HINTS`, English + Chinese) pick a
       different `MODE_PARAMS` row (historical = 365d/top 8, recent =
       7d/top 5, default = 90d/top 5).
    2. **Domain routing** — `DOMAIN_MAP` maps each fired keyword to one
       or more expected file-path prefixes. Results matching a prefix get
       a small score bonus, results missing all of them get a small
       penalty. Empty by default — the hook still injects results, just
       without the path-aware scoring.
    3. **Category dedup** — `category_of()` classifies each result file
       into a coarse bucket (memory-index, memory-system, journal,
       journal-archive, or top-level dir) and keeps only the highest-
       scoring entry per bucket. Stops one chatty file (e.g. a long
       `reflections.md`) from crowding out other hits.

  60-second TTL cache (`/tmp/mem-search-<hash>.json`) so repeated prompts
  don't re-spawn the search subprocess. Self-test built into the file —
  run `python3 templates/.claude/hooks/memory-search-trigger.py --self-test`
  to validate the framework's pure functions without making a real
  search call.

  All customization points (KEYWORDS, WORD_BOUNDARY_KEYWORDS,
  HISTORICAL_HINTS, RECENT_HINTS, DOMAIN_MAP, MODE_PARAMS, scoring
  knobs) live under a clearly-marked `# CUSTOMIZE THIS SECTION FOR YOUR
  WORKSPACE` block at the top. The framework code below is generic and
  doesn't need editing for typical workspaces. KEYWORDS ships with
  bilingual (English + Chinese) example phrases, DOMAIN_MAP ships
  empty.

### Renamed

- **`skills/memory/` → `skills/curate-memory/`**: the skill's
  frontmatter `name:` collided with the global `save-memory` skill
  that ships with Claude Code. When both are present in a session,
  the global one shadows the workspace one and the workspace curator
  stops getting invoked. The rename frees the `name:` slot. The new
  description makes the distinction explicit: `save-memory` is a
  fast single-line append, `curate-memory` is the full classify-and-
  merge workflow. Existing workspaces that already copied the skill
  keep their local copy — bootstrap's skip-if-exists behavior means
  no in-place migration is needed.

### Docs

- **`cron/README.md`**: new "Runtime Details" section documenting the
  `active` vs `wall` elapsed metric, the network readiness gate, the
  stdin prompt delivery, and the per-job `allowed_tools` parser.
  Directory tree updated to show `cron/bin/mono_seconds.py`.

## [2.4.0] - 2026-04-10

Backported from 2+ weeks of production use on a Claude Code workspace
(`cc-memory-project`). The theme is **determinism around the LLM**: push
as much detection and scoring as possible into deterministic scripts, and
only wake the LLM when something actually needs judgment.

### Added

- **Hybrid memory search** (`scripts/memory-search-hybrid.py`): scores
  `memory/` and `notes/` files by keyword overlap × temporal recency ×
  hall-type boost. Designed to replace plain grep as the default memory
  lookup. Portable — derives the workspace root from its own location.
- **Hall tagger** (`scripts/hall-tagger.sh`): backfills `[hall_facts]` /
  `[hall_events]` / `[hall_discoveries]` / `[hall_preferences]` /
  `[hall_advice]` prefixes on journal bullets, driven by keyword rules.
  Idempotent, safe to run repeatedly. Inspired by MemPalace's hall
  taxonomy. Hybrid search uses the prefixes as a scoring signal.
- **Compact memory updater** (`scripts/compact-update.py`): generates
  `MEMORY_COMPACT.md` from a `<!-- compact:start --> ... <!-- compact:end -->`
  block inside `MEMORY.md`. Optionally mirrors the block into `CLAUDE.md`
  if the same markers are present. No hard-coded section names — each
  workspace decides its own compact format.
- **Flag system** (`guides/flag-system.md`) — the **cron → flag →
  SessionStart hook** pattern:
  - `scripts/lib/workspace.sh`, `scripts/lib/notify.sh`, `scripts/lib/flag.sh`
    — three tiny helper libs shared by every cron script. `notify.sh`
    supports telegram / slack / stdout / none out of the box.
  - `scripts/cron-broken-links-check.sh` — scan `notes/` for unresolved
    `[[wikilinks]]`, write a flag when count exceeds
    `BROKEN_LINKS_THRESHOLD`.
  - `scripts/cron-notes-todo-check.sh` — count unresolved TODOs in
    active notes (configurable via `NOTES_TODO_GLOBS`), flag when over
    `NOTES_TODO_THRESHOLD`.
  - `templates/.claude/hooks/session-start-flags.sh` — reads every
    `.claude/flags/*.flag` and injects them as SessionStart
    `additionalContext`. No code changes needed to add new flag types.
  - `templates/.claude/hooks/memory-search-trigger.py` — UserPromptSubmit
    hook that forces a memory search when hard-trigger keywords hit
    (tracked proper nouns, cross-host intents, temporal references,
    credential questions). Keyword lists are documented and editable.
  - `templates/.claude/settings.json` — wires both hooks into the
    permission model.
  - `templates/.claude/flags/README.md` — file-format and
    add-a-new-flag-type documentation.
  - `templates/crontab.example` — environment-variable driven schedule,
    no hard-coded paths.
  - `scripts/install-cron.sh` — prints the crontab snippet with the
    detected `OPENCLAW_WORKSPACE` substituted in. Confirms before
    writing anything with `--install`.
- **Broken wikilink detector** (`scripts/check-broken-wikilinks.py`):
  standalone pure-regex scanner for manual triage. Works on a single
  file or the whole `notes/` tree, supports `--json` for tool chaining.
- **Smart-wikilinks guide** (`guides/smart-wikilinks.md`): recipe for
  optional embedding-based "related notes" suggestions. Documents the
  shape of an implementation without shipping one — embedding providers
  and auth differ too much across workspaces to ship a useful default.

### Changed

- `templates/AGENTS.md`: added **Hall Classification**, **Hybrid search**,
  **Memory-search hard triggers**, and **Pending Flags** sections. The
  hard-trigger list is the behavior change that matters most — it takes
  "should I search memory?" off the LLM's plate.

### Notes

- The flag system embodies **"hard trigger, soft action"**: cron detects
  deterministically on a schedule, the LLM reacts when the user is
  already in a session. Cron never wakes the LLM directly.
- Hybrid search replaces grep as the default memory lookup in all new
  guidance. It's ~2× more accurate for noun-queries and handles Chinese
  tokenization without extra config.

---

## [2.3.0] - 2026-03-28

### Added
- **Context Tree Guide** (`guides/context-tree.md`): Comprehensive documentation on the two-layer memory architecture — journal (memory/) for temporal events vs knowledge (notes/) for semantic topic organization. Includes cleanup strategy, merge-first principle, memorySearch.extraPaths configuration, and background references to ByteRover Context Tree and NLAH paper (arXiv:2603.25723)
- **Knowledge Base** (`templates/notes/`): New optional directory structure for topic-organized knowledge (areas/, resources/) with .gitkeep files for git tracking
- **Memory Skill Update** (`skills/memory/SKILL.md`): Added two-layer classification tree — journal (memory/YYYY-MM-DD.md) vs knowledge (notes/). Classification logic: "what happened" → journal, "what was learned" → merge into notes/ first

### Changed
- **AGENTS.md** (templates/): Rewrote Memory Extraction section with two-layer architecture — Layer 1: Journal (5-day rolling, then archive), Layer 2: Knowledge (merge-first, optional notes/). Added classification decision tree
- **README.md**: Added "Knowledge Base" to What You Get section. Updated Architecture diagram with notes/ directory. Added knowledge layer to Three-Layer Architecture section with memorySearch.extraPaths setup

### Notes
- Fully backward compatible — journal-only mode still works, knowledge layer is optional enhancement
- Two-layer approach inspired by Harness Engineering's Entropy Management concept
- Lightweight file-based implementation — no external dependencies (ByteRover/NLAH are references, not requirements)

### Added
- **Post-Install Checklist** (`guides/post-install-checklist.md`): Step-by-step verification guide to ensure memory system is actually working after bootstrap. Includes real-world case study from CramClaw where scripts existed but none of the automated parts functioned (wrong CLI flags, missing cron entries, root ownership, hardcoded paths, missing notification targets)
- **Health Check Script** (`scripts/health-check.sh`): Automated workspace health verification — checks directory structure, core files, script permissions, cron entries, memory status, file ownership, and skill symlinks. Run after bootstrap or anytime to catch "installed but not activated" problems
- **Memory Sync Script** (`scripts/cron-memory-sync.sh`): Self-contained hourly conversation extraction that reads session JSONL directly (no external dependencies). Supports multi-instance via `OPENCLAW_PROFILE`, `OPENCLAW_STATE_DIR`, and configurable notification delivery via `NOTIFY_CHANNEL`/`NOTIFY_TARGET`
- Quick Start now includes health check step and cron setup reminder

### Fixed
- Post-install checklist now warns about hardcoded `~/.openclaw/` paths in helper scripts — the #1 cause of "memory-sync runs but never finds conversations" in multi-instance setups
- Notification delivery section added — `--announce` without `--channel`/`--to` may go nowhere

### Notes
- Case study: CramClaw had `memory-janitor` failing silently for weeks due to non-existent `--workspace` CLI flag; `memory-sync` called an external script with hardcoded paths that always read the wrong instance; reflect/dream had `--announce` but no target channel. All looked "installed" but none worked for 2+ weeks.

## [2.1.0] - 2026-03-24

### Added
- **Source-First Principle** (SOUL.md + BOOTSTRAP.md): Factual claims must be verified via search/read before answering. Model memory only for reasoning, never for facts. "Unverified" label required when sources unavailable
- **Source-First Checkpoint** (BOOTSTRAP.md): Decision gate between task classification and reply generation — blocks unverified factual claims
- **Context Curator Pattern** (AGENTS.md): Main session injects precise context excerpts into sub-agent task prompts (preferences → SOUL.md, infrastructure → MEMORY.md, history → memory/)
- **Unverified Facts row** in Friction Check table (AGENTS.md): Catches replies containing names/numbers/features without sources
- **Information Density prior** (SOUL.md): Dense output (tables, bullets) preferred; conclusion-first structure
- **Interaction Rhythm prior** (SOUL.md): Progress report restraint (5+ tool calls) and mandatory sub-agent review

### Changed
- **BOOTSTRAP.md**: Added model hint column to classification matrix; added Evaluate (🧪) and Writing (📝) categories; Source-First checkpoint as mandatory gate; expanded decision tree with factual claim branch
- **AGENTS.md**: Added Context Curator section under Sub-agent Delegation; expanded config change protocol (prefer `openclaw config set`); memory query tips with concrete examples; compaction guide adds proactive trimming advice
- **SOUL.md**: Expanded Decision Priors with Information Density, Source-First Principle, and Interaction Rhythm sections

### Notes
- All changes extracted from 5+ months of production usage patterns
- Source-First principle alone prevented ~15 hallucination incidents in testing
- Context Curator pattern reduced sub-agent fact errors by providing relevant workspace context

---

## [2.0.0] - 2026-03-17

### Added
- **Memory Dream Script** (`memory-dream.sh`): Weekly cold memory association ("dreaming") that randomly pairs unrelated memories for cross-domain insights
- **Memory Reflect Script** (`memory-reflect.sh`): Daily rumination with contradiction detection between recent and long-term memory
- **Memory Expire Script** (`memory-expire.sh`): Monthly auto-archive of >30 day old daily files
- **Bootstrap Script**: Now copies scripts/ directory during setup
- **4 Starter Skills**: Pre-configured skills for immediate productivity
- **'What You Get' Section**: Documentation of included components

### Changed
- **AGENTS.md**: Streamlined from 181→107 lines. Added SOUL evolution mechanism, friction check matrix, config change protocol. Removed verbose self-improvement (moved to guides/). Added compaction survival guide
- **SOUL.md**: Added Decision Priors section (action bias, risk tolerance)
- **BOOTSTRAP.md**: Added IF-THEN decision tree for task classification
- **HEARTBEAT.md**: Rewritten with design principles and crontab examples
- **MEMORY.md**: Cleaner template with P0/P1/P2 priority system
- **TOOLS.md**: Stripped to generic template with examples
- **IDENTITY.md**: Now a fill-in-the-blank template
- **Bootstrap Behavior**: Now preserves existing files (skip-if-exists)

### Fixed
- Memory scripts now model-agnostic
- Removed non-existent openclaw cron run-now command references

### Removed
- **obsidian-markdown skill**: Too personal/specific for general use

### Dependencies
- **Kept**: memory, telegram-html-reply, write-tmp (universal applicability)

---

## [1.0.0] - 2026-03-02

### Added
- **Three-layer Memory Storage**: Session / Daily / Long-term hierarchy
- **P0/P1/P2 Priority System**: Task and memory classification
- **Progressive Retrieval Strategy**: Context-aware memory access
- **Automated Maintenance**: Janitor script for memory management
- **Project Templates**:
  - AGENTS.md: Agent workspace configuration
  - MEMORY.md: Long-term memory store
  - SOUL.md: Agent identity and behavior guide
  - USER.md: User profile and preferences
  - daily-log.md: Daily activity logging
- **Documentation**:
  - Architecture.md: System design and principles
  - Comparisons.md: Analysis vs memU, Claude Code, mem0, Letta
- **License**: MIT License

### Technical
- Initial project structure generated via multi-model debate (MM + Gemini + Opus)

---

[2.4.0]: https://github.com/kindomLee/openclaw-workspace-template/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/kindomLee/openclaw-workspace-template/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/kindomLee/openclaw-workspace-template/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/kindomLee/openclaw-workspace-template/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/kindomLee/openclaw-workspace-template/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/kindomLee/openclaw-workspace-template/tree/v1.0.0
