# Upgrading your workspace

When the template repo releases a new version, here's how to bring your
existing workspace up to date.

## TL;DR

```bash
# 1. Update template repo
cd /path/to/openclaw-workspace-template
git pull

# 2. Read the **Upgrading** notes in CHANGELOG.md for every entry since
#    your last upgrade — some changes need manual steps

# 3. Add new files (existing files are preserved)
bash bootstrap.sh --path /your/workspace --yes

# 4. See what changed in template vs your workspace
bash scripts/template-diff.sh /your/workspace

# 5. Manually merge the diffs you want to keep
```

## Why re-running bootstrap isn't enough

`bootstrap.sh` uses **skip-if-exists**: it copies new files but never
overwrites existing ones. This is the safe default — your customized
`USER.md`, `SOUL.md`, `IDENTITY.md` are never clobbered.

But it also means **updated template files** (like `CLAUDE.md`,
`AGENTS.md`, hook scripts, cron prompts) don't get refreshed either.
You need to manually review and merge those changes.

## File categories

| Category | Examples | bootstrap behavior | Upgrade action |
|---|---|---|---|
| **User-owned** | `USER.md`, `SOUL.md`, `IDENTITY.md`, `TOOLS.md`, `MEMORY.md` | skip-if-exists | Don't overwrite — these are yours |
| **Template-maintained** | `CLAUDE.md`, `AGENTS.md`, `BOOTSTRAP.md`, `HEARTBEAT.md` | skip-if-exists | **Review diff, manually merge** |
| **Hooks & settings** | `.claude/settings.json`, `.claude/hooks/*` | skip-if-exists | **Review diff, manually merge** |
| **Scripts** | `scripts/*.sh`, `scripts/*.py` | skip-if-exists | **Review diff, manually merge** |
| **Cron prompts** | `cron/prompts/*.md` | skip-if-exists | **Review diff, manually merge** |
| **New files** | anything that doesn't exist yet | copied automatically | Nothing to do |

## Step-by-step

### 1. Update the template repo

```bash
cd /path/to/openclaw-workspace-template
git pull
git log --oneline HEAD@{1}..HEAD  # see what changed
```

Then read the **Upgrading** notes in `CHANGELOG.md` for every entry since
your last upgrade. Breaking changes — e.g. the launchd label rename
`org.oracle.*` → `org.mklee.*`, or `LEARNINGS.md` moving from `.learnings/`
to the workspace root — need manual steps that neither bootstrap nor
`template-diff.sh` will do for you.

### 2. Re-run bootstrap

```bash
bash bootstrap.sh --path /your/workspace --yes
```

This adds any **new** files (new scripts, new guides, new cron prompts).
Existing files print `skip (exists)`.

### 3. Review diffs

```bash
bash scripts/template-diff.sh /your/workspace
```

This compares every template file against your workspace copy and shows
which files have diffs. For each differing file, it prints a one-line
summary. Pass `--full` to see the actual diff content.

It only walks files the template currently ships (under `templates/`,
`scripts/` and `cron/`), so it can't report files the template has since
removed or renamed — e.g. old `cron/launchd/org.oracle.*.plist`,
`cron/prompts/curate-memory.md`, `.learnings/LEARNINGS.md`. Those stay in
your workspace; delete them as the CHANGELOG notes say.

Alternatively, manually diff specific files:

```bash
diff templates/CLAUDE.md /your/workspace/CLAUDE.md
diff templates/AGENTS.md /your/workspace/AGENTS.md
diff templates/.claude/settings.json /your/workspace/.claude/settings.json
diff templates/.claude/hooks/session-start-flags.sh /your/workspace/.claude/hooks/session-start-flags.sh
```

### 4. Merge what you want

For each file with changes you want:

```bash
# Option A: Accept the template version entirely — the normal path for
# scripts/, cron/ and .claude/hooks/ files you haven't customized
# (they're template-owned)
cp templates/CLAUDE.md /your/workspace/CLAUDE.md
cp scripts/health-check.sh /your/workspace/scripts/health-check.sh

# Option B: Manual merge (recommended for files you've customized)
# Open both files side-by-side and pick the sections you want
```

### 5. Merge settings.json

The template ships `templates/.claude/settings.json` already generated from
`settings.capabilities.toml`; nothing in your workspace reads the TOML.
Merge new `permissions` / `hooks` entries from the template's JSON into
yours, keeping your own additions:

```bash
diff templates/.claude/settings.json /your/workspace/.claude/settings.json
```

`tools/build-settings.py` only regenerates the template's own
`templates/.claude/settings.json` (and `tools/` is not copied into
workspaces) — run it in the template clone only if you edit the TOML there.

## Common upgrade scenarios

### "I haven't touched CLAUDE.md at all"

Safe to overwrite:
```bash
cp templates/CLAUDE.md /your/workspace/CLAUDE.md
```

### "I customized CLAUDE.md with my own sections"

Review the diff and manually merge new template sections into your file.
The template's `CLAUDE.md` has clear `##` section headers, so you can
copy individual sections.

### "A new hook was added"

Re-running bootstrap copies the new hook file. But you also need to check
if `.claude/settings.json` needs a new entry in the `hooks` block. The
`template-diff.sh` output will flag this.

### "I'm multiple versions behind"

Same process — `git pull` gets you to latest, `bootstrap.sh` adds all
missing files, `template-diff.sh` shows all accumulated diffs. No
incremental upgrade needed — but do read the CHANGELOG **Upgrading** notes
for every entry you skipped.
