# TOOLS.md - Quick Reference

> Your frequently-used tools, connections, and commands.
> Keep it **operational** — "how to reach / use", not marketing copy or
> state. If a value is sensitive (token, password), put the value in
> `reference/services.md` and just point to it from here.

## Personal Entries

```bash
# Home Assistant
# HA: 192.168.x.x:8123 (token in reference/services.md)

# SSH to server
# ssh -p 22 user@server -i ~/.ssh/key
```

## Cron Management

### Claude Code mode (default)
```bash
# Install all jobs (macOS launchd / Linux crontab)
bash cron/install-mac.sh         # macOS
bash cron/install-linux.sh       # Linux

# Uninstall
bash cron/install-mac.sh --uninstall

# Inspect loaded jobs
launchctl list | grep org.oracle    # macOS
crontab -l                           # Linux

# Run a job on demand (for debugging)
bash cron/runner.sh memory-janitor
bash cron/runner.sh curate-memory

# Tail the latest log for a job
tail -f cron/logs/memory-janitor-*.log
```

### OpenClaw mode
```bash
# Print the crontab snippet (copy into `crontab -e`)
bash scripts/install-cron.sh

# Append to current crontab (asks first)
bash scripts/install-cron.sh --install

# One-off reminder
openclaw cron add --name "name" --at "30m" --system-event "content" \
  --session main --wake now --delete-after-run
```

## Version Management

### Claude Code
```bash
claude --version
# Upgrade depends on how you installed: `npm i -g @anthropic-ai/claude-code`,
# `brew upgrade claude-code`, or re-run the installer you originally used.
```

### OpenClaw
```bash
openclaw --version
npm view openclaw version
curl -fsSL https://openclaw.ai/install.sh | bash
```
⚠️ Check CHANGELOG before upgrading for breaking changes.

## Sub-agent Preference
Prefer sub-agent delegation for heavy research / long-running tasks;
main session stays focused on decisions and interaction. See
`guides/sub-agent-patterns.md`.
