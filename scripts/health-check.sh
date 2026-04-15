#!/usr/bin/env bash
# health-check.sh — workspace health check (Claude Code + OpenClaw dual-mode)
#
# Usage:
#   bash scripts/health-check.sh                 # auto-detect mode
#   bash scripts/health-check.sh --mode claude   # force Claude Code mode
#   bash scripts/health-check.sh --mode openclaw # force OpenClaw mode
#   bash scripts/health-check.sh --help
#
# Mode auto-detection (first match wins):
#   1. .claude/settings.json exists        → claude
#   2. `openclaw` CLI in PATH              → openclaw
#   3. $OPENCLAW_WORKSPACE env set         → openclaw
#   4. Fall back to claude (less invasive)
set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${OPENCLAW_WORKSPACE:-$(cd "$SELF_DIR/.." && pwd)}"
MODE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --mode)
            [ $# -ge 2 ] || { echo "--mode requires an argument" >&2; exit 2; }
            MODE="$2"; shift 2 ;;
        --help|-h)
            sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *)
            echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

detect_mode() {
    if [ -f "$WORKSPACE/.claude/settings.json" ]; then
        echo "claude"; return
    fi
    if command -v openclaw >/dev/null 2>&1; then
        echo "openclaw"; return
    fi
    if [ -n "${OPENCLAW_WORKSPACE:-}" ]; then
        echo "openclaw"; return
    fi
    echo "claude"
}

if [ -z "$MODE" ]; then
    MODE=$(detect_mode)
fi

case "$MODE" in
    claude|openclaw) ;;
    *) echo "invalid --mode: $MODE (want: claude | openclaw)" >&2; exit 2 ;;
esac

ERRORS=0
WARNINGS=0

pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; WARNINGS=$((WARNINGS+1)); }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; ERRORS=$((ERRORS+1)); }

echo "=== Workspace health check ==="
echo "Workspace: $WORKSPACE"
echo "Mode:      $MODE"
echo

# ---- 1. Directory structure -------------------------------------------
# memory/ and scripts/ are hard requirements; everything else is optional.
# tmp/, .learnings/, and skills/ are template conventions — downstream
# workspaces can run fine without them, so we warn rather than fail.
echo "--- Directory structure ---"
for dir in memory scripts; do
    if [ -d "$WORKSPACE/$dir" ]; then
        pass "$dir/"
    else
        fail "$dir/ missing"
    fi
done
for dir in tmp .learnings; do
    if [ -d "$WORKSPACE/$dir" ]; then
        pass "$dir/"
    else
        warn "$dir/ missing (optional template convention)"
    fi
done
# Skills can live at either the top-level (template layout) or under
# .claude/skills/ (Claude Code native). Accept either.
if [ -d "$WORKSPACE/skills" ] || [ -d "$WORKSPACE/.claude/skills" ]; then
    if [ -d "$WORKSPACE/.claude/skills" ] && [ ! -d "$WORKSPACE/skills" ]; then
        pass ".claude/skills/"
    else
        pass "skills/"
    fi
else
    warn "skills/ and .claude/skills/ both missing"
fi

# ---- 2. Core files ----------------------------------------------------
echo
echo "--- Core files ---"
for f in AGENTS.md SOUL.md USER.md MEMORY.md BOOTSTRAP.md HEARTBEAT.md; do
    if [ -f "$WORKSPACE/$f" ]; then
        pass "$f"
    else
        warn "$f missing"
    fi
done

# ---- 3. Claude Code integration ---------------------------------------
if [ "$MODE" = "claude" ]; then
    echo
    echo "--- Claude Code integration ---"
    if command -v claude >/dev/null 2>&1; then
        pass "claude CLI"
    else
        fail "claude CLI not in PATH (install: https://docs.claude.com/claude-code)"
    fi
    if [ -f "$WORKSPACE/.claude/settings.json" ]; then
        if python3 -c "import json; json.load(open('$WORKSPACE/.claude/settings.json'))" 2>/dev/null; then
            pass ".claude/settings.json valid JSON"
        else
            fail ".claude/settings.json is not valid JSON"
        fi
    else
        warn ".claude/settings.json missing (hooks won't run)"
    fi
    for hook in memory-search-trigger.py session-start-flags.sh; do
        if [ -f "$WORKSPACE/.claude/hooks/$hook" ]; then
            pass ".claude/hooks/$hook"
        else
            warn ".claude/hooks/$hook missing"
        fi
    done
fi

# ---- 4. OpenClaw integration ------------------------------------------
if [ "$MODE" = "openclaw" ]; then
    echo
    echo "--- OpenClaw integration ---"
    if command -v openclaw >/dev/null 2>&1; then
        pass "openclaw CLI: $(openclaw --version 2>&1 | head -1)"
    else
        fail "openclaw not found (install: https://openclaw.ai/install.sh)"
    fi
fi

# ---- 5. Memory scripts ------------------------------------------------
echo
echo "--- Memory scripts ---"
for script in memory-search-hybrid.py hall-tagger.sh compact-update.py memory-compress.py; do
    path="$WORKSPACE/scripts/$script"
    if [ -f "$path" ]; then
        pass "$script"
    else
        warn "$script missing"
    fi
done

# ---- 6. Cron wiring ---------------------------------------------------
echo
echo "--- Cron jobs ---"
if [ "$MODE" = "claude" ]; then
    # Claude Code: prefer launchd on macOS, crontab on Linux.
    if [ "$(uname -s)" = "Darwin" ]; then
        ORACLE_JOBS=$(launchctl list 2>/dev/null | awk '$3 ~ /^org\.oracle\./ {print $3}')
        if [ -z "$ORACLE_JOBS" ]; then
            warn "no org.oracle.* launchd jobs loaded (run: bash cron/install-mac.sh)"
        else
            JOB_COUNT=$(printf '%s\n' "$ORACLE_JOBS" | wc -l | tr -d ' ')
            pass "$JOB_COUNT org.oracle.* launchd jobs loaded"
        fi
    else
        ORACLE_JOBS=$(crontab -l 2>/dev/null | grep -c 'cron/runner.sh' || true)
        if [ "$ORACLE_JOBS" -eq 0 ]; then
            warn "no cron/runner.sh entries in crontab (run: bash cron/install-linux.sh)"
        else
            pass "$ORACLE_JOBS cron/runner.sh crontab entries"
        fi
    fi
else
    # OpenClaw: scripts/install-cron.sh writes crontab entries referencing $WORKSPACE.
    CRON_ENTRIES=$(crontab -l 2>/dev/null | grep -c "$WORKSPACE" || true)
    if [ "$CRON_ENTRIES" -eq 0 ]; then
        warn "no crontab entries referencing $WORKSPACE (run: bash scripts/install-cron.sh --install)"
    else
        pass "$CRON_ENTRIES crontab entries referencing workspace"
    fi
fi

# ---- 7. Today / yesterday journal -------------------------------------
echo
echo "--- Memory journal ---"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d 2>/dev/null || echo "")
if [ -f "$WORKSPACE/memory/$TODAY.md" ]; then
    size=$(wc -c < "$WORKSPACE/memory/$TODAY.md" | tr -d ' ')
    pass "today ($TODAY): $size bytes"
else
    warn "no journal for today ($TODAY) — is memory-sync / curate-memory running?"
fi
if [ -n "$YESTERDAY" ] && [ -f "$WORKSPACE/memory/$YESTERDAY.md" ]; then
    size=$(wc -c < "$WORKSPACE/memory/$YESTERDAY.md" | tr -d ' ')
    pass "yesterday ($YESTERDAY): $size bytes"
elif [ -n "$YESTERDAY" ]; then
    warn "no journal for yesterday ($YESTERDAY)"
fi
TOTAL_MEMORIES=$(find "$WORKSPACE/memory" -maxdepth 1 -name "20??-??-??.md" 2>/dev/null | wc -l | tr -d ' ')
echo "  · total daily files: $TOTAL_MEMORIES"

# ---- 8. File ownership ------------------------------------------------
echo
echo "--- File ownership ---"
ROOT_FILES=$(find "$WORKSPACE" -maxdepth 2 -user root 2>/dev/null | wc -l | tr -d ' ')
if [ "$ROOT_FILES" -eq 0 ]; then
    pass "no root-owned files"
else
    warn "$ROOT_FILES root-owned file(s) in top 2 levels (may cause permission issues)"
fi

# ---- 9. Skill symlinks ------------------------------------------------
# Check both possible skill directories. The existence check is already
# done in section 1; here we just look for dangerous symlinks.
echo
echo "--- Skill symlinks ---"
SKILL_DIRS=()
[ -d "$WORKSPACE/skills" ] && SKILL_DIRS+=("$WORKSPACE/skills")
[ -d "$WORKSPACE/.claude/skills" ] && SKILL_DIRS+=("$WORKSPACE/.claude/skills")
if [ ${#SKILL_DIRS[@]} -eq 0 ]; then
    echo "  · no skills directory to check"
else
    SKILL_OK=0
    for skill_root in "${SKILL_DIRS[@]}"; do
        for skill in "$skill_root"/*/; do
            [ -d "$skill" ] || continue
            name=$(basename "$skill")
            if [ -L "${skill%/}" ]; then
                warn "$name is a symlink (may be root-owned)"
            else
                SKILL_OK=$((SKILL_OK+1))
            fi
        done
    done
    [ "$SKILL_OK" -gt 0 ] && pass "$SKILL_OK skill(s) without dangerous symlinks"
fi

# ---- Summary ----------------------------------------------------------
echo
echo "=== Summary ==="
if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    printf '\033[32m✓ All checks passed — workspace is healthy.\033[0m\n'
    exit 0
elif [ "$ERRORS" -eq 0 ]; then
    printf '\033[33m! %d warning(s) — non-critical.\033[0m\n' "$WARNINGS"
    exit 0
else
    printf '\033[31m✗ %d error(s), %d warning(s) — needs attention.\033[0m\n' "$ERRORS" "$WARNINGS"
    exit 1
fi
