# Using this template with OpenAI Codex CLI

> **Codex support is interactive / second-opinion only.**
> `cron/` and the `claude -p` runner are explicitly **Claude-only** —
> Codex headless OAuth + VDI/SSO behaviour does not survive unattended
> launchd / crontab execution. Do not wire Codex into the cron path.

## Position

This is a **personal AI assistant** template (not a dev-project template
— see `coding-agents-template` for that). The workspace contains:

- `SOUL.md` — agent personality and decision priors
- `USER.md` — about the human (preferences, context)
- `IDENTITY.md` — agent name, voice, emoji
- `MEMORY.md` — long-term curated memory (infrastructure, decisions, patterns)
- `memory/YYYY-MM-DD.md` — daily journal entries

**These files contain personal data**: real names, locations, credentials,
infrastructure, project history. Codex's sandbox model is coarser than
Claude Code's `allowedTools` — read access to `memory/` means Codex can
include any of it in a response, attachment, or upload. Treat `memory/`
as you would a private `~/.ssh/` directory.

## One-time setup

Register the workspace in Codex per-project config:

```bash
# Append to ~/.codex/config.toml
cat >> ~/.codex/config.toml <<EOF

[projects."$(pwd)"]
trust_level = "verified"  # use "trusted" only after a few sessions
EOF
```

Start with `verified` (Codex prompts on first entry) until you have a
sense of how Codex handles the workspace. Promote to `trusted` later if
nothing surprising happens.

## Recommended priming (default — privacy-bounded)

Codex auto-reads `AGENTS.md` per the [agentsmd.net](https://agentsmd.net)
spec. By default, point Codex at the **compact layer only**:

| File | Why | Personal data risk |
|---|---|---|
| `AGENTS.md` | Full operating manual | Low (rules, no facts) |
| `MEMORY_COMPACT.md` | ~200-token AAAK summary | Low (already curated for compactness) |

In your **first prompt** to Codex, say:

> Read `AGENTS.md` and `MEMORY_COMPACT.md`. Do not scan `memory/` or
> `MEMORY.md` unless I explicitly point you at a specific file.

This deliberately avoids the Claude Code wake-up protocol (which loads
`SOUL.md`, `USER.md`, full `MEMORY.md`, today + yesterday journal). For
Claude Code those files load via a SessionStart hook with full context
isolation; Codex has no such layer.

## Opt-in deep priming (when you need it)

For tasks that genuinely need history (debugging a recurring issue,
"what was the rationale for X"), point Codex at specific files in the
prompt:

```text
Read SOUL.md to understand my style preferences,
then read memory/2026-04-29.md and tell me why I switched X to Y.
```

Avoid `read everything in memory/` — that pulls every personal detail
into context.

## Manual session-start checklist

Codex has no SessionStart / UserPromptSubmit hook equivalent. On the
**first prompt** of a Codex session, do these manually (Claude Code
does them automatically):

1. `ls .claude/flags/` — surface any pending cron flags
2. `cat MEMORY_COMPACT.md` — load the AAAK summary
3. For history-flavored questions, run
   `python3 scripts/memory-search-hybrid.py "<keyword>" --top 5 --format context`
   and paste the output before asking your question

The `--format context` output renders memory snippets as markdown blocks
suitable for direct paste — see `scripts/memory-search-hybrid.py --help`.

## NOT supported with Codex

| Feature | Why |
|---|---|
| `cron/runner.sh` headless execution | hardcoded `claude -p`; Codex OAuth doesn't survive launchd |
| `cron/install-mac.sh` / `install-linux.sh` | installs Claude Code launchd / crontab jobs only |
| `.claude/hooks/memory-search-trigger.py` | UserPromptSubmit is Claude-only platform feature |
| `.claude/skills/` | Codex plugins are global (`~/.codex`), not per-repo |
| `SOUL.md` evolution proposals | Tied to Claude Code conversation model |

If you want any of those, use Claude Code as the **primary** runtime and
treat Codex as a second-opinion / code-review companion (e.g. via
`codex exec --sandbox read-only` for a quick critique).

## Limits vs Claude Code

| Feature | Claude Code | Codex |
|---|---|---|
| Main bootstrap | `CLAUDE.md` (compact priming) + `AGENTS.md` (full manual) | `AGENTS.md` only (auto) |
| Skills | `.claude/skills/` | Not supported per-repo |
| Hooks | Rich (`SessionStart`, `UserPromptSubmit`) | None |
| Per-project settings | `.claude/settings.json` | `~/.codex/config.toml` |
| Tool allowlist | per-prompt fine-grained | sandbox flags only |
| Cron / unattended | `runner.sh` + `claude -p` | **not supported** |

## Bootstrap with `--skip-claude-check`

`bootstrap.sh` normally requires the `claude` CLI. Codex-only users:

```bash
bash bootstrap.sh --skip-claude-check
```

This skips the Claude Code check and prints Codex-flavored next-steps
instead of `claude` invocation hints.

## Typical workflow

1. Daily writing / journaling / curation: Claude Code (full hook
   automation, memory-search auto-injection, skills)
2. Code review / second opinion / one-off Q&A: Codex (sandbox read-only,
   reasoning_effort high)
3. Memory stays identical (`memory/`, `MEMORY.md`) regardless of which
   tool wrote a particular entry — but only Claude Code is expected to
   consume the full layer in normal operation
