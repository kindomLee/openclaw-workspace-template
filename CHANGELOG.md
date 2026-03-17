# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[2.0.0]: https://github.com/kindomLee/openclaw-workspace-template/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/kindomLee/openclaw-workspace-template/tree/v1.0.0
