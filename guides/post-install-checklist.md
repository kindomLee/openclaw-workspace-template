# Post-install Checklist

After bootstrap — or after deploying an existing workspace to a new
machine — you want to verify everything actually **works**, not just
that the files exist. Files that exist but silently fail to run are
the most expensive class of bug in a memory system: you don't notice
for weeks and by then the journal is full of holes.

## Step 1 — run the health check

```bash
bash scripts/health-check.sh
```

The script auto-detects whether you're in Claude Code mode
(`.claude/settings.json` present) or OpenClaw mode (`openclaw` CLI in
PATH), and runs the matching set of checks:

| Section | What it verifies |
|---|---|
| Directory structure | `memory/` + `scripts/` exist (hard); `tmp/` / `.learnings/` / `skills/` optional |
| Core files | `AGENTS.md` / `SOUL.md` / `USER.md` / `MEMORY.md` / `BOOTSTRAP.md` / `HEARTBEAT.md` |
| Claude Code integration | `claude` CLI in PATH; `.claude/settings.json` is valid JSON; hooks exist |
| OpenClaw integration | `openclaw` CLI available (only in `--mode openclaw`) |
| Memory scripts | `memory-search-hybrid.py` / `hall-tagger.sh` / `compact-update.py` / `memory-compress.py` |
| Cron jobs | macOS: `launchctl list \| grep org.oracle` — count ≥ 1. Linux: matching crontab entries |
| Memory journal | today's + yesterday's journal exist + their size |
| File ownership | no root-owned files in the top two levels |
| Skill symlinks | dangerous (root-owned) symlinks flagged |

**Exit code**: `0` on pass, `0` on warnings-only (`.learnings` missing
etc.), `1` on errors (missing core file, broken settings.json, no
cron jobs loaded).

Override the mode manually if auto-detection picks wrong:

```bash
bash scripts/health-check.sh --mode claude
bash scripts/health-check.sh --mode openclaw
```

## Step 2 — fire a cron job manually

Don't trust "the plist is loaded." Pick one job and fire it by hand:

```bash
bash cron/runner.sh memory-janitor
# ...follow the log that gets printed...
tail -f cron/logs/memory-janitor-*.log
```

It should:
1. Print `Starting cron job: memory-janitor` to the log
2. Wait for the network (`Network ready after Ns` or `Skipped: network
   not ready after 120s` if you're offline)
3. Run `claude -p` against the prompt
4. Print `Job memory-janitor finished with exit code 0 (Ns)`

If it sits on step 2 forever, see FAQ #2.
If step 3 prints `TIMEOUT: job exceeded 1800s`, see FAQ #4.
If step 4 exits non-zero, open the log — the claude -p stderr will be
inlined.

## Step 3 — wait one day, verify journal updates

```bash
ls -la memory/$(date +%Y-%m-%d).md memory/$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d yesterday +%Y-%m-%d).md
```

If today's file is zero bytes after 24 hours of Claude Code activity,
`curate-memory` isn't running. See FAQ #5.

---

## FAQ — common failures

### 1. `health-check.sh` reports `.learnings/ missing` / `tmp/ missing`

**Symptom**: warn-level, not error-level. Exit 0.

**What it means**: these directories are template conventions but not
required for the system to function. If you're fine without them,
ignore the warning.

**Fix** (if you want them): `mkdir -p .learnings tmp && touch
.learnings/.gitkeep tmp/.gitkeep`.

### 2. Job sits on "waiting for network" forever (or logs `Skipped: network not ready after 120s`)

**Symptom**: `cron/logs/<job>-launchd.log` shows `Starting` but no
`Network ready` line, or shows `Skipped: network not ready`.

**What it means**: `runner.sh` probes `api.anthropic.com` on startup.
If the TCP/TLS handshake doesn't complete within 120 seconds, the run
is treated as a **skipped** job (exit 0) on the assumption you're
offline or waking from sleep — this is by design on laptops.

**Check**:
```bash
curl -I --max-time 5 https://api.anthropic.com
```
A 404 response is fine — we want *any* HTTP reply, which means the
TCP/TLS path is up.

**Fix**:
- Laptop offline: ignore, it'll run on the next schedule
- Actual network problem: check DNS, VPN, firewall rules
- Probe endpoint changed: the probe is hardcoded in
  `cron/runner.sh` — point it at a different host if needed

### 3. No Telegram notifications arriving

**Symptom**: jobs run successfully but the TG reports never show up.

**Check**:
```bash
cat cron/config.env       # should have TG_BOT_TOKEN and TG_CHAT_ID
curl -s "https://api.telegram.org/bot${TG_BOT_TOKEN}/getMe"
```

**Fix**:
- `cron/config.env` missing: `cp cron/config.env.example cron/config.env`
  and fill `TG_BOT_TOKEN` + `TG_CHAT_ID`
- `runner.sh` silently skips missing config — the job still runs, it
  just can't send. This is intentional (see the "config.env missing
  is not an error" note in `cron/README.md`)
- `TG_BOT_TOKEN` set but wrong: `getMe` returns a JSON error
- `TG_CHAT_ID` wrong: `getMe` works but `sendMessage` fails silently.
  Check by sending a manual test:
  ```bash
  curl -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
       -d chat_id=${TG_CHAT_ID} -d text="test"
  ```

### 4. Job logs show `TIMEOUT: job exceeded 1800s`

**Symptom**: `runner.sh` SIGTERMs the job after 30 minutes and the log
shows `exit 124` or `exit 137`.

**What it means**: `claude -p` hung. Historically this has been the #1
cause of "the agent looks broken" — one long-running session could go
for 32+ hours before being noticed. The timeout exists to kill these.

**Fix**:
- Raise the ceiling for jobs that genuinely need longer: in
  `cron/config.env`, add `JOB_TIMEOUT=3600` (1 hour).
- Find out *why* the job is hanging: `grep -i timeout cron/logs/
  <job>-*.log`. Common causes are a `Read` / `WebFetch` that stalled,
  or an infinite loop in prompt logic.
- If the job doesn't need LLM for the bulk of its work, consider
  splitting it: shell does the deterministic part, `claude -p` only
  does the judgment part.

### 5. Journal files aren't updating day-to-day

**Symptom**: `memory/$(date +%F).md` doesn't exist or hasn't grown
since an old date.

**Check**:
1. `launchctl list | grep curate-memory` — is the hourly job loaded?
2. `ls -lt cron/logs/curate-memory-*.log | head` — recent runs?
3. `tail cron/logs/curate-memory-*.log` — any errors?

**Fix**:
- Job not loaded: `bash cron/install-mac.sh` to re-install
- Job loaded but silent exit every hour: that's normal if your
  journal is already up-to-date. `curate-memory` does aggressive
  early-return. It's only meant to push stragglers.
- `save-memory` skill never wrote anything: the journal is populated
  manually during interactive sessions via `/save-memory`; cron is a
  safety net, not the primary writer. Make sure you actually use
  `/save-memory` during important turns.

### 6. `prompt file not found: cron/prompts/<job>.md`

**Symptom**: `cron/logs/<job>-launchd.log` shows the error and the job
exits 1 immediately.

**What it means**: the plist is loaded but the matching prompt doesn't
exist in `cron/prompts/`. Usually caused by:
- Hand-copying plists between workspaces without copying the prompts
- Deleting a prompt without unloading the plist
- Renaming a prompt without updating the plist

**Fix**:
```bash
ls cron/launchd/org.oracle.*.plist cron/prompts/*.md | sort
```
The plist label (after `org.oracle.`) must match a prompt filename
(minus the `.md`). Either delete the orphan plist or restore the
missing prompt.

### 7. SessionStart hook not injecting flags

**Symptom**: `.claude/flags/*.flag` exists but Claude doesn't mention
them when you open a session.

**Check**:
1. `python3 -c "import json; json.load(open('.claude/settings.json'))"`
   — valid JSON?
2. `bash .claude/hooks/session-start-flags.sh` — does it emit a JSON
   blob? (Set `CLAUDE_PROJECT_DIR=$PWD` first.)
3. `command -v jq || command -v python3` — at least one present? The
   hook falls back to python3 if jq is missing, but both missing =
   silent skip.
4. `.claude/settings.json` hook command path matches the actual script
   location?

**Fix**: most common cause is stale settings.json from before the
hooks were wired up. Re-bootstrap or copy the hook block from
`templates/.claude/settings.json`.

### 8. `timeout: command not found` in job logs

**Symptom**: job logs print `WARN: neither timeout nor gtimeout
available` and the job runs without a timeout guard.

**Fix** (macOS): `brew install coreutils`. The `timeout` binary
ships as `gtimeout` by default but `coreutils` also installs `timeout`
on modern Homebrew.

**Fix** (Linux): GNU coreutils is usually pre-installed; if not,
`apt install coreutils` / `yum install coreutils`.

### 9. Multi-workspace: one workspace's cron overwrites another's

**Symptom**: you install workspace A, then workspace B, and
workspace A's jobs stop running (or now point at B's prompts).

**What it means**: `cron/install-mac.sh` copies plists to
`~/Library/LaunchAgents/` by their label (`org.oracle.X.plist`). Two
workspaces shipping the same label → the second install overwrites
the first.

**Fix**: rename one workspace's plist labels to a unique prefix (e.g.
`org.work.X` vs `org.oracle.X`). See `guides/multi-instance.md §
Cron label collision` for the exact commands.

### 10. `compact-update.py` exits with "no compact:start block found"

**Symptom**: running `python3 scripts/compact-update.py` errors out.

**Fix**: add a `<!-- compact:start -->` ... `<!-- compact:end -->`
block to `MEMORY.md`. The template's default `MEMORY.md` ships with
this block in the stub form; if you rewrote MEMORY.md and forgot to
keep the markers, `compact-update.py` can't find anything to mirror.
See `templates/MEMORY.md` in the template repo for the expected
layout.

---

## Prevention — bake the check into your workflow

1. **Run `health-check.sh` right after bootstrap.** Five seconds, zero
   excuses.
2. **Tail a fresh log before assuming cron works.** `bash cron/
   runner.sh <job>` produces a timestamped file in `cron/logs/`; open
   it immediately and watch.
3. **After editing `.claude/settings.json`, restart the `claude` CLI.**
   Settings are read at session start; changes don't hot-reload.
4. **Weekly**: `tail cron/logs/*.log | grep -i "timeout\|error\|exit
   1"`. Catch drift before it becomes a 2-week silent failure.
5. **Keep `scripts/check-schedule-drift.py` in CI** so a doc edit
   can't desync from the plists.

---

## Historical case study

The template's original `post-install-checklist.md` was written after
a particularly bad deployment where **all five** of these happened at
once:

- `memory-janitor` used a `--workspace` flag that didn't exist → every
  run failed immediately with a stderr we weren't reading
- `memory-sync` called a helper script that hardcoded `~/.openclaw/`
  → always read the wrong instance's transcripts → "no conversations"
  every hour
- Three other scripts existed but had no matching cron entries → never
  ran at all
- Notification wiring assumed a default `--channel` that didn't match
  the actual Telegram setup → alerts went nowhere
- The workspace was owned by `root` because of an `sudo` during
  bootstrap → the service user couldn't write anyway

Result: a workspace that **looked complete**, passed every `file
exists` check, and wrote **zero** useful bytes for two weeks. The
fixes for each individual problem are in FAQ #2, #3, #5, #6, #8 above
— the lesson from the case is that **every one of these failures was
silent**. You only catch silent failures by:
(a) running the job by hand and watching the log, and
(b) running `health-check.sh` as a routine.
