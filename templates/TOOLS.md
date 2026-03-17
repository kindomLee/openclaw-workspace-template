# TOOLS.md - Quick Reference

> Add your frequently-used tools, connections, and commands here.
> Keep it operational — "how to connect/use", not just state.

## Example Entries

```bash
# Home Assistant
# HA: 192.168.x.x:8123 (token in reference/services.md)

# SSH to server
# ssh -p 22 user@server -i ~/.ssh/key

# Cron reminders (always use CLI, don't calculate timestamps)
openclaw cron add --name "name" --at "30m" --system-event "content" --session main --wake now --delete-after-run
```

## Coding Agent
Prefer `sessions_spawn` over direct exec for coding tasks.

## OpenClaw Version Management
```bash
openclaw --version          # current version
npm view openclaw version   # latest version
curl -fsSL https://openclaw.ai/install.sh | bash  # upgrade
```
⚠️ Check CHANGELOG before upgrading for breaking changes.
