# LEARNINGS

> Self-improvement tracker. Entries that reach `recurring_count >= 3` get
> promoted to MEMORY.md (see AGENTS.md § Correction Routing).
> `scripts/learnings-promotion-check.py`, `scripts/learnings-archive.py`, the
> weekly review and the self-improvement job all parse this file, so keep the
> field names exactly as below. Errors and feature requests go to
> `.learnings/ERRORS.md` and `.learnings/FEATURE_REQUESTS.md`.

## Format

| Field | Required | Meaning |
|---|---|---|
| **claim** | yes | One-sentence statement of the pattern |
| **type** | yes | correction / knowledge_gap / best_practice / manual_repeat / error / regression |
| **recurring_count** | yes | 1 the first time; +1 each time it is seen again |
| **status** | yes | active / resolved / superseded / wontfix (the last three get archived) |
| **evidence** | yes | One dated line per occurrence: file path + line, commit, or session date |
| **suggested_action** | yes | The concrete fix or way to avoid it, not "be careful" |
| **blast_radius** | no | One script / whole system / across projects |
| **promoted_to** | after promotion | The MEMORY.md section it went to |
| **sunset_date** | no | YYYY-MM-DD; promotion-check marks the entry stale after it |

Headings are `## [TYPE-YYYYMMDD-NNN] Title` with TYPE in upper case and real
digits, e.g. `CORRECTION-20261109-001`. The template below keeps the letters
so the scripts don't read it as an entry.

```markdown
## [TYPE-YYYYMMDD-NNN] Title

- **claim**: one-sentence statement
- **type**: manual_repeat
- **recurring_count**: 2
- **status**: active
- **evidence**:
  - 2026-04-08: scripts/foo.py:42 hard-codes `/root/clawd/` (commit a1b2c3d)
  - 2026-04-10: .claude/skills/bar/SKILL.md:15, same kind
- **suggested_action**: after a migration, run `grep -r '/root/clawd' .`
- **blast_radius**: across projects
```

---
