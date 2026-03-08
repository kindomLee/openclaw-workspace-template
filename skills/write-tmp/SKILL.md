---
name: write-tmp
description: Writing temporary files in this workspace. Use when you need to save files to a temporary location — the workspace root /tmp is blocked; use /root/clawd/tmp/ instead.
---

# Write Tmp Files

## Rule

`/tmp` is outside the workspace root and will fail with "Path escapes workspace root".

**Always use `/root/clawd/tmp/` for temporary files.**

```bash
# ❌ Wrong
/tmp/output.md

# ✅ Correct
/root/clawd/tmp/output.md
```

## Setup

The directory may not exist yet:

```bash
mkdir -p /root/clawd/tmp
```

## Cleanup

Files here are not auto-cleaned. Remove when done:

```bash
rm /root/clawd/tmp/<file>
```
