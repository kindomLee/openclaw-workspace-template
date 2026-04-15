# Multi-workspace Guide (Claude Code mode)

*For the OpenClaw multi-instance / gateway-port / profile architecture,
see the legacy section at the bottom of this file. The Claude Code model
is fundamentally different — no daemon, no gateway, no port conflicts —
so the Claude Code track below is the primary guide.*

## Why multiple workspaces?

Different jobs want different minds:

- **Work agent** — focused, technical, reads project code
- **Personal agent** — casual, tracks habits / food / coffee / health
- **Research agent** — long-horizon investigation, heavy note-taking
- **Experiment agent** — try risky configs without polluting production

In Claude Code the unit of separation is a **workspace directory** —
one directory with its own `AGENTS.md`, `SOUL.md`, `USER.md`,
`MEMORY.md`, `memory/`, `.learnings/`, `.claude/`, and `cron/`. Claude
Code is one-shot per invocation (each `claude` call reads the workspace
and exits when the session ends), so there are no long-running daemons
to collide.

## What's isolated vs shared

| Thing | Per workspace | Global | Notes |
|---|---|---|---|
| `SOUL.md` / `IDENTITY.md` / `USER.md` | ✅ | — | The persona is the workspace |
| `AGENTS.md` / `BOOTSTRAP.md` / `HEARTBEAT.md` | ✅ | — | Operating manual is per-persona |
| `MEMORY.md` + `memory/` journal | ✅ | — | Never cross-link memories between workspaces |
| `.learnings/` | ✅ | — | Each persona learns from its own mistakes |
| `notes/` | ✅ | — | Topic knowledge stays with the persona that collected it |
| `.claude/settings.json` (workspace) | ✅ | — | Per-workspace hook config |
| `.claude/settings.local.json` | ✅ | — | Developer's local tweaks, gitignored |
| `~/.claude/CLAUDE.md` | — | ✅ | Personal cross-workspace prefs (loaded by Claude Code on every session) |
| `~/.claude/settings.json` | — | ✅ | Global allow-list, global hooks |
| `<workspace>/.claude/skills/` | ✅ | — | Template's default skills ship here (auto-loaded per workspace) |
| `~/.claude/skills/` | — | ✅ | Skills *promoted* to global are visible in every workspace |
| `~/.claude/agents/*.md` | — | ✅ | Sub-agent definitions are global too |
| `scripts/lib/*.sh`, `cron/runner.sh` | ✅ (copied) | — | Each workspace has its own copy from bootstrap |

### Workspace-local vs global skills

Claude Code loads `SKILL.md` from two places on every session:

1. **`<workspace>/.claude/skills/<name>/SKILL.md`** — workspace-local.
   The template ships its default skills (`curate-memory`,
   `telegram-html-reply`, `write-tmp`) to this path via `bootstrap.sh`,
   so a fresh workspace has them working immediately.
2. **`~/.claude/skills/<name>/SKILL.md`** — global. Loaded in every
   session regardless of cwd.

**Rule of thumb**: ship skills workspace-local (what the template
does). When one proves useful across several of your workspaces,
*promote* it to the global path:

```bash
# Promote a workspace-local skill to global
mv my-workspace/.claude/skills/coffee-log ~/.claude/skills/

# Or keep the source in the workspace but expose it globally
ln -s /abs/path/to/my-workspace/.claude/skills/coffee-log \
      ~/.claude/skills/coffee-log
```

Shared skills at `~/.claude/skills/` stay in sync for every persona;
workspace-local skills are isolated, which is what you want for
personas that should behave differently (e.g. the "work" persona has
no access to the "personal" journal-writing skill).

## Cron label collision (the main multi-workspace footgun)

This is the gotcha to watch out for.

`cron/install-mac.sh` copies every `cron/launchd/org.oracle.*.plist`
into `~/Library/LaunchAgents/org.oracle.*.plist`. If you run it twice
— once for workspace A, once for workspace B — **the second run
overwrites the first**, because both workspaces ship plists with the
same label (`org.oracle.memory-janitor`, `org.oracle.curate-memory`,
…). You end up with one set of cron jobs pointing at whichever
workspace was installed last.

**Fix**: give each workspace a unique launchd label prefix.

```bash
# In workspace A, rename every plist Label:
cd workspace-a/cron/launchd
for f in org.oracle.*.plist; do
  mv "$f" "${f/org.oracle./org.work.}"
done
# And inside each file, update the <string>org.oracle.X</string> →
# <string>org.work.X</string>. A quick sed will do it:
sed -i.bak 's|org\.oracle\.|org.work.|g' org.work.*.plist && rm *.bak

# Then re-install
bash cron/install-mac.sh
```

Now workspace A's jobs are `org.work.memory-janitor` etc. and
workspace B's stay `org.oracle.memory-janitor`. Verify with
`launchctl list | grep -E 'org\.(oracle|work)\.'`.

The same applies to `org.personal.*`, `org.research.*`, etc. Pick a
prefix that makes sense for the persona.

On Linux the analogous issue is the crontab's marker block:
`install-linux.sh` uses `# >>> Oracle Cron BEGIN >>>` as a delimiter,
so running it twice will **replace** the previous block, not append.
Either install from a single workspace, or patch the marker
(`MARKER_BEGIN`/`MARKER_END`) per workspace.

## Opening sessions across workspaces

From one terminal you typically run one workspace at a time:

```bash
cd ~/work/workspace-a
claude
# ... work on A ...
# ^D to exit
cd ~/personal/workspace-b
claude
```

If you want both open simultaneously, open them in separate terminals.
Each session reads its own workspace's `CLAUDE.md` / `AGENTS.md` /
`SOUL.md` independently — there's no cross-session state in Claude Code
itself, so the workspaces never leak into each other.

> Tip: add `cd "$(pwd)"` contexts to your shell prompt so you always
> know which workspace a terminal is pinned to.

## Memory search boundaries

`scripts/memory-search-hybrid.py` is workspace-scoped — it resolves
`memory/` and `notes/` relative to the script's parent directory. Two
workspaces searching for "Polymarket" will each return their own
history only. If you *want* cross-workspace search (e.g. "where did I
write about X?"), keep a thin shim in `~/.claude/skills/` that loops
over known workspace paths and calls each one's hybrid search.

## Cron configuration per workspace

Each workspace's `cron/config.env` lives under the workspace and is
loaded by *that workspace's* `cron/runner.sh`. If you use different
Telegram chat ids or MiniMax keys per persona, that's the place.

Global values that apply to all workspaces (e.g. a single Telegram
token) can stay in `~/.zshrc` / `~/.bash_profile` as exported env —
`runner.sh` inherits them before sourcing `config.env`, so per-workspace
`config.env` overrides global env where both are set.

## Naming conventions that save pain later

- **Directory**: `~/work/<persona>` or `~/.workspaces/<persona>` — a
  stable parent dir makes `health-check.sh` and cross-workspace tools
  easier.
- **Launchd prefix**: one prefix per workspace. Never reuse
  `org.oracle.*` across workspaces.
- **`IDENTITY.md` emoji**: one emoji per persona so you can tell which
  agent just messaged you on Telegram.
- **Telegram**: one bot per persona if possible. Same bot with
  different `reply_to` headers also works.

## Checklist when adding workspace N+1

1. `git clone / cp -r` or re-run `bootstrap.sh --path <new>` to lay
   down the template.
2. Rename `cron/launchd/*.plist` labels to a new prefix (see above).
3. Create `cron/config.env` from the example; fill TG credentials.
4. Edit `IDENTITY.md` / `USER.md` / `SOUL.md` to set the persona.
5. `bash cron/install-mac.sh` (or `install-linux.sh`) from the new
   workspace.
6. `bash scripts/health-check.sh` — should hit 0 errors.
7. `launchctl list | grep "$NEW_PREFIX"` — confirm the right number of
   jobs loaded.
8. Verify you didn't clobber an existing workspace's jobs:
   `launchctl list | grep -E 'org\.'` and count each prefix.

---

## Legacy: OpenClaw multi-instance

> **OpenClaw-specific — skip if you're on Claude Code.** The
> Claude Code model above is what most users want. This section exists
> only because the template still supports an OpenClaw-mode cron
> pipeline (see `scripts/memory-*.sh`, `templates/crontab.example`,
> `scripts/install-cron.sh`) and the OpenClaw deployment model is
> fundamentally different.

OpenClaw runs a long-lived gateway per instance, each instance binding
to a distinct TCP port (`8080`, `8081`, ...). Different instances also
want different `--profile` / state dir combinations. The points to
watch:

- **Gateway ports must not collide** — one port per instance; track
  them in each workspace's `TOOLS.md`.
- **State directory per profile** — `~/.openclaw-<profile>/` keeps
  state files isolated; never let two instances share a state dir.
- **`--profile` flag on every `openclaw` invocation** — cron entries
  must set `OPENCLAW_PROFILE` or pass `--profile <name>` explicitly;
  forgetting it is the classic silent-failure mode.
- **Shared skills via symlink** — OpenClaw skills under
  `/usr/lib/node_modules/openclaw/skills/` can be symlinked into the
  workspace's `skills/` dir, but the symlinks will be root-owned.
  Prefer `cp -r` over `ln -s` if the instance runs as a non-root user.
- **File ownership** — if the instance runs as a service user, make
  sure `chown -R` covers workspace + state dir + log dir.
- **Cron entries** — `scripts/install-cron.sh` wraps everything in
  `# >>> Oracle Cron BEGIN >>>` / `<<<` markers; running it from a
  second workspace replaces the first workspace's block. Use a
  per-instance prefix environment variable or install by hand for the
  second workspace.
- **Channel routing** — set `NOTIFY_CHANNEL` + `NOTIFY_TARGET` per
  instance; `--announce` alone falls through to the last active
  session and may deliver to the wrong channel entirely.

Everything else — `SOUL.md` isolation, per-persona `AGENTS.md`,
isolated `memory/` journals — is the same as the Claude Code story
above. The architectural difference is just: Claude Code has no daemon
to collide on, OpenClaw does.
