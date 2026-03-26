# Post-Install Checklist

After bootstrapping a workspace (or deploying to a new instance), run through this checklist to verify everything is actually **working**, not just **installed**.

> **Case study:** CramClaw had all memory scripts copied and cron entries added, but:
> - `memory-janitor` used `--workspace` flag (doesn't exist) → silently failing for weeks
> - `memory-sync` used `--state-dir` flag (invalid) → never synced
> - `memory-reflect/dream/expire` scripts existed but had no cron entries → never ran
> - File ownership was `root` instead of the service user → couldn't write
>
> Result: The agent had a "memory system" that looked complete but **none of the automated parts actually worked**.

## The Checklist

### 1. File Ownership

If running as a non-root user (e.g., a separate instance):

```bash
# Check for root-owned files in workspace
find /path/to/workspace -not -user YOUR_USER 2>/dev/null

# Fix
chown -R YOUR_USER:YOUR_USER /path/to/workspace
chown -R YOUR_USER:YOUR_USER /path/to/state-dir
```

**Why it matters:** Scripts copied by root during setup will be root-owned. The service user can't write to them, and cron jobs running as root may create files the service user can't later modify.

### 2. Cron Jobs Are Registered

```bash
# List all cron entries for your workspace
crontab -l | grep your-workspace-path
```

Expected entries (adjust paths):

| Job | Schedule | Purpose |
|-----|----------|---------|
| `cron-memory-sync.sh` | `02 * * * *` | Extract conversations → write daily memory |
| `cron-memory-janitor.sh` | `02 20 * * *` | Compress old memory entries |
| `memory-reflect.sh` | `0 21 * * *` | Daily contradiction detection |
| `memory-dream.sh` | `0 3 * * 0` | Weekly cross-domain association |
| `memory-expire.sh` | `30 3 1 * *` | Monthly archive of old daily files |

If any are missing, add them:

```bash
crontab -e
# Add missing entries with full paths
```

### 3. Scripts Actually Run

Don't trust "the file exists." Run each one:

```bash
# Janitor (safe — dry run by default)
OPENCLAW_WORKSPACE=/path/to/workspace memory-tools janitor --dry-run

# Reflect (will trigger LLM — costs tokens)
bash /path/to/workspace/scripts/memory-reflect.sh false  # false = no notification

# Expire (safe — dry run)
bash /path/to/workspace/scripts/memory-expire.sh true  # true = dry run
```

**Common failures:**
- Wrong CLI flags (`--workspace` vs env var `OPENCLAW_WORKSPACE`)
- Missing binaries (`memory-tools` not in PATH)
- Wrong `openclaw` profile flag (`--state-dir` doesn't exist; use `--profile`)

### 4. Environment Variables

Scripts need to know the workspace path. Verify:

```bash
# For cron jobs, set env vars inline:
OPENCLAW_WORKSPACE=/path/to/workspace /path/to/script.sh

# Or in the crontab entry:
0 21 * * * OPENCLAW_WORKSPACE=/path/to/workspace /path/to/scripts/memory-reflect.sh true
```

### 5. Memory Files Are Being Written

After the system has been running for a day:

```bash
# Check if today's memory exists
ls -la /path/to/workspace/memory/$(date +%Y-%m-%d).md

# Check if sync log shows activity
tail -5 /path/to/workspace/tmp/memory-sync.log
```

If the daily file doesn't exist after 24h of conversations, `memory-sync` isn't working.

### 6. Multi-Instance Specifics

When running multiple OpenClaw instances on one host:

```bash
# Verify each instance uses the correct profile
openclaw --profile YOUR_PROFILE cron add --name test --at 10s --system-event "test" --session main --delete-after-run

# Check symlinks vs copies for shared skills
ls -la /path/to/workspace/skills/
# Symlinks to /usr/lib/node_modules/openclaw/skills/ → root-owned, read-only
# Better: copy to workspace for full ownership
```

### 7. Quick Health Check Script

Save this as `scripts/health-check.sh` in your workspace:

```bash
#!/bin/bash
# Quick workspace health check
WORKSPACE="${OPENCLAW_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
ERRORS=0

echo "=== Workspace Health Check ==="
echo "Workspace: $WORKSPACE"

# Check memory directory
[ -d "$WORKSPACE/memory" ] && echo "✅ memory/ exists" || { echo "❌ memory/ missing"; ERRORS=$((ERRORS+1)); }

# Check today's memory
TODAY=$(date +%Y-%m-%d)
[ -f "$WORKSPACE/memory/$TODAY.md" ] && echo "✅ Today's memory exists" || echo "⚠️  No memory for today yet"

# Check scripts are executable
for script in memory-reflect.sh memory-dream.sh memory-expire.sh; do
  [ -x "$WORKSPACE/scripts/$script" ] && echo "✅ $script executable" || { echo "❌ $script not executable"; ERRORS=$((ERRORS+1)); }
done

# Check memory-tools binary
command -v memory-tools &>/dev/null && echo "✅ memory-tools in PATH" || { echo "❌ memory-tools not found"; ERRORS=$((ERRORS+1)); }

# Check cron entries
CRON_COUNT=$(crontab -l 2>/dev/null | grep -c "$WORKSPACE" || true)
echo "📋 Cron entries found: $CRON_COUNT (expected: 5)"
[ "$CRON_COUNT" -ge 5 ] || { echo "⚠️  Missing cron entries"; ERRORS=$((ERRORS+1)); }

# Check file ownership
ROOT_FILES=$(find "$WORKSPACE" -maxdepth 2 -user root 2>/dev/null | wc -l)
[ "$ROOT_FILES" -eq 0 ] && echo "✅ No root-owned files" || echo "⚠️  $ROOT_FILES root-owned files found"

echo ""
[ "$ERRORS" -eq 0 ] && echo "✨ All checks passed" || echo "⚠️  $ERRORS issues found"
```

## Prevention

To avoid "installed but not activated" problems:

1. **Always run health check after bootstrap** — Add it to your setup workflow
2. **Test scripts manually before adding to cron** — Catches flag/path issues immediately
3. **Check cron logs the next day** — `tail /path/to/workspace/tmp/*.log`
4. **For multi-instance: copy, don't symlink** — Ensures the service user has full ownership
