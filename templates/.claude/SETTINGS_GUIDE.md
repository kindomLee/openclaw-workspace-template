# .claude/settings.json Guide

`settings.json` is **generated** from `settings.capabilities.toml`. Do not
hand-edit the `permissions.allow` list in the JSON file — your change will
be clobbered the next time someone regenerates it. Edit the TOML instead.

## Why generate?

Inspired by the OpenAI Agents SDK's "Capabilities" concept: a flat
`allow` array of opaque `Bash(...)` strings is hard to review. Grouping
entries into capability buckets lets any reviewer answer "what is this
agent actually allowed to do?" in a glance.

## Capability buckets

| Bucket | Purpose |
|---|---|
| `run_scripts` | Execute project-owned scripts under `scripts/` (python3 / bash). |
| `inspect_git` | Read-only git plumbing: `status`, `diff`, `log`, `show`, `branch`. |
| `inspect_shell` | Read-only shell inspection: `cat`, `ls`, `head`, `tail`, `wc`, `date`, `find`. |
| `read_files` | Structured reads via the harness tools: `Read`, `Grep`, `Glob`. |
| `write_memory` | Append/edit memory palace artifacts (`memory/*`, `MEMORY.md`, `MEMORY_COMPACT.md`). |
| `write_notes` | Edit PARA knowledge base under `notes/*`. |

Hooks (`UserPromptSubmit`, `SessionStart`, ...) live directly in
`settings.json` and are preserved verbatim by the build script.

## Adding a permission

1. Decide which bucket it belongs to (or add a new bucket if none fit).
2. Edit `templates/.claude/settings.capabilities.toml`, appending the
   new entry to the matching `[capabilities.<name>].allow` array.
3. From the template repo root, regenerate:
   ```bash
   python3 tools/build-settings.py
   ```
4. Commit **both** files together — the TOML source and the regenerated
   `settings.json`. CI and reviewers assume they are in sync.

## Removing / moving a permission

Same workflow: edit the TOML, rerun the build script, commit both
files. Running the script twice in a row must produce byte-identical
output — if it doesn't, that's a bug in `tools/build-settings.py`.

## Troubleshooting

* **JSON didn't change** — you probably edited a copy inside a
  bootstrapped workspace; the authoritative path is
  `templates/.claude/settings.capabilities.toml` in the template repo.
* **Hooks disappeared** — the build script preserves `hooks` by reading
  the existing `settings.json`. If you deleted the JSON first, restore
  hooks by hand, then rerun the script.
