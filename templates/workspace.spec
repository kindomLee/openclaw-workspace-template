# workspace.spec — Declarative workspace layout
#
# Consumed by bootstrap.sh. This file is the single source of truth for the
# shape of a freshly bootstrapped workspace. Each line is one directive:
#
#   dir <relative-path>
#       Ensure <workspace>/<relative-path> exists (mkdir -p).
#
#   copy_tree <src-relative-to-SCRIPT_DIR> [<dst-subdir>]
#       Recursively copy files from the template repo into the workspace.
#       If <dst-subdir> is omitted, files land at the workspace root.
#       Existing files are preserved (skip-if-exists); cron runtime
#       artifacts (config.env, logs/) are never copied.
#
# Blank lines and lines starting with "#" are ignored.
# Unknown verbs cause bootstrap.sh to fail loudly — keep this file in sync.

# ---- Trees copied from the template repo ------------------------------
# templates/ holds .claude/, guides/, and all the profile scaffold files
# (IDENTITY.md, USER.md, SOUL.md, TOOLS.md, AGENTS.md, MEMORY.md, ...).
# Skills live under templates/.claude/skills/ and ride along here.
copy_tree templates
copy_tree scripts scripts
copy_tree cron cron

# ---- Directories created unconditionally ------------------------------
# These exist so downstream tooling (memory system, notes system, cron
# logs, hooks) can write without first checking for missing parents.
dir memory
dir notes/00-Inbox
dir notes/01-Projects/Active
dir notes/01-Projects/Archive
dir notes/02-Areas
dir notes/03-Resources
dir notes/04-Archive
dir .learnings
dir scripts
dir .claude/skills
dir cron/logs
dir reference
dir tmp
