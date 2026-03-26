# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-03-26

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

[2.2.0]: https://github.com/kindomLee/openclaw-workspace-template/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/kindomLee/openclaw-workspace-template/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/kindomLee/openclaw-workspace-template/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/kindomLee/openclaw-workspace-template/tree/v1.0.0
