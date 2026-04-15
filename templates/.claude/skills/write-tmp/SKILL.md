---
name: write-tmp
description: Writing temporary files in this workspace. Use when you need to save files to a temporary location — the system /tmp is outside the workspace root and gets blocked; use the workspace-local tmp/ instead.
---

# Write Tmp Files

## Rule

System `/tmp` is outside the workspace root and will fail with "Path escapes workspace root".

**Always use the workspace-local `tmp/` directory** — resolve it relative to `$CLAUDE_PROJECT_DIR` (or `$OPENCLAW_WORKSPACE` if you're in OpenClaw mode).

```bash
# ❌ Wrong — system /tmp is outside the workspace
/tmp/output.md

# ✅ Correct — workspace-local
"$CLAUDE_PROJECT_DIR/tmp/output.md"
# or (OpenClaw)
"$OPENCLAW_WORKSPACE/tmp/output.md"
```

## Setup

The directory is created by `bootstrap.sh`, but if it's missing:

```bash
mkdir -p "$CLAUDE_PROJECT_DIR/tmp"
```

## Cleanup

Files here are not auto-cleaned. Remove when done:

```bash
rm "$CLAUDE_PROJECT_DIR/tmp/<file>"
```
