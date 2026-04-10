# `.claude/flags/`

Pending-action flags dropped here by cron jobs or manual scripts. Each flag
is a small text file whose presence means "a Claude Code session should look
at this the next time it wakes up".

## How it works

1. A cron script (see `scripts/cron-*-check.sh`) does fixed detection work —
   counting broken wikilinks, scanning TODOs, checking whether the knowledge
   graph needs a rebuild. No LLM involved.
2. If a threshold is crossed, the script calls `write_flag` (see
   `scripts/lib/flag.sh`) and creates `<name>.flag` here.
3. On the next Claude Code session, `SessionStart` runs
   `.claude/hooks/session-start-flags.sh`, which reads every `*.flag` file
   and injects their contents as `additionalContext`. Claude sees the flags
   as a system reminder and decides how to act on them.
4. After resolving, Claude (or you) deletes the flag file:
   `rm .claude/flags/<name>.flag`.

This is the **hard trigger, soft action** pattern: detection is deterministic
and scheduled, the reaction is LLM-driven and happens on demand. Cron never
wakes the LLM by itself.

## Flag file format

Plain text, human-readable. By convention:

```
<line 1: short title, surfaced in the SessionStart reminder>
<line 2+: instructions including how to clear the flag>
```

See `scripts/lib/flag.sh` for the helper that writes these consistently.

## Adding a new flag type

1. Write a `scripts/cron-<thing>-check.sh` that sources the three lib files
   (`workspace.sh`, `notify.sh`, `flag.sh`) and calls `write_flag` when the
   threshold is crossed.
2. Add an entry to `templates/crontab.example`.
3. That's it — the SessionStart hook already picks up any `*.flag` file, so
   no changes to `settings.json` are required.
