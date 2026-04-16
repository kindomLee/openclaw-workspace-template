# Upgrading your workspace

When the template repo releases a new version, here's how to bring your
existing workspace up to date.

## TL;DR

```bash
# 1. Update template repo
cd /path/to/openclaw-workspace-template
git pull

# 2. Add new files (existing files are preserved)
bash bootstrap.sh --path /your/workspace --yes

# 3. See what changed in template vs your workspace
bash scripts/template-diff.sh /your/workspace

# 4. Manually merge the diffs you want to keep
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
# Option A: Accept the template version entirely
cp templates/CLAUDE.md /your/workspace/CLAUDE.md

# Option B: Manual merge (recommended for files you've customized)
# Open both files side-by-side and pick the sections you want
```

### 5. Regenerate settings.json (if using capability TOML)

If your workspace uses the capability-grouped permission system:

```bash
# Update the TOML source from template
cp templates/.claude/settings.capabilities.toml /your/workspace/.claude/settings.capabilities.toml

# Regenerate settings.json (preserves your hooks)
python3 tools/build-settings.py
```

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
incremental upgrade needed.
