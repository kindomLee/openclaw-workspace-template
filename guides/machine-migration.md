# Machine Migration Guide

Moving an existing agent workspace to a new machine is not the same as
a fresh install. A fresh install fails loudly — missing files, broken
paths, nothing works. A migration fails *quietly*: the workspace looks
complete, `health-check.sh` passes, and then over the next week your
cron jobs die one by one, each in silence.

This guide comes from a real migration where **eight** missing
dependencies surfaced over five days — every one of them invisible on
day one. The lesson is not "make a better list" (the eighth miss was
discovered while writing up the first seven). The lesson is a
different verification model.

## The four blind-spot layers

Dotfiles + package manifest + workspace rsync covers less than you
think. Misses cluster in four layers, and each needs its own check.

### Layer 1 — packages and binaries

Your bootstrap installs the workspace's minimal dependency set. It
does **not** cover:

- Self-built binaries (not in brew/apt/pip — they live only on the
  old machine's disk)
- Project-specific pip packages for repos *outside* the workspace
- Runtimes needed by a single plugin (e.g. `bun` for a messaging
  plugin's poller — nothing else uses it, so nothing else misses it)

**The PATH-ghost trap**: migrated shell/launchd config often carries
PATH entries like `~/.bun/bin` from the old machine. The PATH entry
migrated; the binary did not. Config referencing a dependency creates
the *illusion* that the dependency exists. Never verify by grepping
config — verify by executing.

```bash
# For every interpreter/binary a job uses, test in the job's own PATH:
env -i HOME="$HOME" PATH="<the plist/crontab PATH>" command -v bun python3 jq
# For every python import, test with the interpreter the job resolves to:
env -i HOME="$HOME" PATH="<job PATH>" python3 -c "import dateutil, jieba"
```

### Layer 2 — secrets and state files (the hand-carry list)

Some files are *deliberately* excluded from every sync channel —
dotfiles, rsync, git, cloud backup. That exclusion is correct; the
mistake is not keeping an explicit **hand-carry list** of them:

- Credentials and wallets (`~/.config/<project>/…`)
- Encryption passphrases for backup pipelines
- **Plugin runtime state** — e.g. a messaging plugin's
  pairing/allowlist JSON. Not secret, but not in any sync path
  either. Lose it and the bot treats its owner as a stranger.
- CLI auth tokens (`~/.codex/auth.json`, OAuth caches)

Maintain `HANDCARRY.md` next to your bootstrap script: one line per
file, where it lives, where the recovery copy is (password manager,
old-machine Time Machine, nowhere).

### Layer 3 — machine behavior settings

Not files. Behaviors:

- `git config --global user.name/email` — commit identity silently
  becomes the machine default
- `pmset -c sleep 0` (macOS) — a cron host that sleeps kills
  long-running jobs mid-flight; a machine that *happens* to stay
  awake (some app holding an audio assertion) is the most dangerous
  state, because it looks like correct config
- Network auto-join / VPN default-route behavior

Diff these against the old machine explicitly; no sync tool carries
them.

### Layer 4 — verification itself

The first three layers are what you miss; this one is why you don't
notice for days. Three structures make failures silent:

1. **`set -e` + `2>/dev/null` + command substitution** — the inner
   failure kills the wrapper before any logging line runs. Zero
   output, zero alert.
2. **Alerting wired after the failure point** — if the "prompt file
   missing" check exits before the alert config loads, that failure
   path bypasses your alerting by construction. Audit the order.
3. **Long-running calls killed by sleep/shutdown** — the log ends at
   "calling API…" with no error; exit status resets on reboot and
   reads as success.

And the umbrella illusion: **exit code 0 ≠ produced output**. Health
checks that only look at exit codes see none of the above.

## The verification model that works

1. **Audit all jobs at once, proactively.** Passively waiting costs
   3–5 days of latency per miss. One full sweep (for every scheduled
   job: script exists → interpreter resolves → imports/binaries
   execute → *recent output artifact exists*) surfaced 6 broken jobs
   in an afternoon, 4 of them fully silent.
2. **Fail-informative, not just fail-loud.** An alert that says
   "job failed" without *why* leaves you unable to reconstruct the
   cause after the window closes. Cheap fix:

   ```bash
   if ! OUT=$(some_command 2>/tmp/jobname.err); then
       tail -1 /tmp/jobname.err >> "$LOG"           # real cause into log
       notify "job failed: $(tail -1 /tmp/jobname.err)"
       exit 1
   fi
   ```

3. **Verify behavior, not config presence.** "The plist is loaded"
   is not acceptance. "The job fired once in the real launchd/cron
   environment and produced its expected artifact" is. Interactive
   shell runs don't count: launchd PATH is a different world, and
   `bash -lc` runs `path_helper`, which reorders `/usr/bin` ahead of
   your package manager — the same script can resolve a different
   python under cron than in your terminal.

## Acceptance checklist

For every scheduled job on the new machine:

- [ ] Dependencies verified **in the job's own PATH**, by execution
- [ ] Hand-carry files restored from the explicit list (and one
      encrypted-backup round-trip actually decrypted)
- [ ] Machine behavior settings diffed against the old host
      (sleep, git identity, network)
- [ ] First real scheduled run observed producing its artifact
- [ ] Failure path exercised once: does the alert fire, and does it
      carry the cause?

And accept that the list is never complete — the goal is not a
complete list, it is a system where the *next* missing dependency
announces itself instead of hiding for five days.

## Debug tip: headless TUI sessions

If a bridge/daemon runs an interactive TUI under `script(1)` via
launchd, you can't attach to it. Reproduce it under tmux instead:

```bash
tmux new-session -d -s probe "<same command line>"
tmux send-keys -t probe "/mcp" Enter
tmux capture-pane -t probe -p   # read panels, error states, statuses
```

This is how a "poller never spawned" root cause was actually seen —
the status panel showed the component `✘ failed` with the real error,
which never reached any log file.

## See also

- [Post-install Checklist](post-install-checklist.md) — fresh-install
  verification (`health-check.sh`)
- [Routine Checks](routine-checks.md) — ongoing Type A/B monitoring
  after the migration settles
