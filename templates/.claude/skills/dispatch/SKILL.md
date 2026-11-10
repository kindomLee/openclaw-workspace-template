---
name: dispatch
description: Hand a task to another repo with `claude -p` so it runs under that repo's own CLAUDE.md, skills and hooks, while this workspace coordinates and verifies. Use for well-specified, checkable work in a different project — run its tests and report, summarize recent commits or an issue, apply a small change from an existing spec, have that repo curate its own memory — or when the user is away and asks for something in another repo. Triggers on "go do X in <repo>", "dispatch this to <repo>", "ask <repo> to …", "/dispatch". Not for exploratory debugging or back-and-forth design work.
---

# dispatch

This workspace is the coordinator; the target repo is where the work happens.
Running the task with cwd inside the target means its `CLAUDE.md`, project
skills and hooks apply — editing another repo from here would apply this
workspace's rules to that code instead. Full background and limits:
`guides/dispatch.md`.

## 1. Dispatch or not

| Dispatch | Don't |
|---|---|
| Clear spec, checkable result: run tests and report, summarize commits / an issue, a small change from an existing spec, a report | Exploratory development, debugging that needs judgement at each step, deciding direction from a diff |
| The user is away and asked for it | Work that needs several rounds of discussion — every round goes through you, which is slow and loses detail |

For day-to-day work in that repo the user should just open it:
`cd <repo> && claude`.

## 2. Run it

```bash
D="$CLAUDE_PROJECT_DIR/.claude/skills/dispatch/dispatch.sh"
$D --repo <dir> "<task>"                                   # read-only (default)
$D --repo <dir> --write "<task>"                           # may edit; no commit/push
$D --repo <dir> --write --allow 'Bash(pytest:*)' "<task>"  # extra tools, one rule each
$D --repo <dir> --write --auto "<task>"                    # classifier approves the rest; can write .claude/specs (guides/dispatch.md first)
$D --repo <dir> --src <other dir> "<task>"                 # extra readable, not writable, dir
$D --repo <dir> --resume <session_id> "<follow-up>"        # same session, keeps its context
```

Write the task like a ticket: what to do, what "done" means, what to report
back (a table, file paths, the commands it ran and their output). End with
"stop when done and report" for anything multi-step. Put any facts the target
needs from this workspace's memory into the task — it can't see it.

Long jobs: run with `run_in_background`, tell the user it's dispatched and
the session_id. To check progress, read the last lines of the `stream:` file
the script prints (one JSON event per line: tool calls, results, denials).

## 3. Follow up in the same session

`--resume <session_id>` continues with the target's full context — for a
second stage, or to answer a question it stopped on. Without it a new session
starts and knows nothing. A common follow-up is letting the repo file what it
learned in its *own* memory, scoping writes to that directory:

```bash
$D --repo <dir> --resume <id> --allow 'Edit(.agents/memory/**)' --allow 'Write(.agents/memory/**)' "/curate-memory"
```

Mark anything in a hint that is your inference rather than a verified fact —
the target will otherwise file it as fact.

## 4. Verify here

Don't relay the target's report as-is:

- Check the repo state yourself: `git -C <dir> log --oneline -3`, `git -C <dir> status --short`, `git -C <dir> diff`.
- Re-run at least one check it reported as passing.
- `permission_denials` not empty → list the denied commands for the user to
  decide. Don't run them here on the target's behalf, and don't widen the
  rules just to get past them.

## 5. Report

Session_id, what it changed (paths), what you verified and how, what is
unverified, and anything left for the user (denied commands, uncommitted
changes in the target).
