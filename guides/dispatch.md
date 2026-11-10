# Dispatch: running work in another repo

The workspace can act as a coordinator: it starts a `claude -p` session
*inside* another repo, gets back a session_id and a result, and verifies the
work itself. The `dispatch` skill (`.claude/skills/dispatch/`) wraps this in
`dispatch.sh`.

```
workspace session ──dispatch.sh──▶ claude -p (cwd = target repo)
   (coordinator)                     loads the target's CLAUDE.md, skills, hooks
        ▲                            works under narrow, explicit permissions
        └──── session_id + result ───┘
   verifies with git / tests itself, --resume for follow-ups
```

## Why run it in the target repo

A repo with its own `CLAUDE.md`, `.claude/skills/`, hooks and settings is a
working context of its own. Editing it from the workspace would apply the
workspace's persona and permissions to that code, and none of the target's
rules would load. Dispatching keeps each repo's rules with its code; the
workspace only gets summaries and pointers.

Layering mostly buys context isolation. It doesn't buy security by itself: a
coordinator that can dispatch anything effectively holds every target's
permissions. Safety comes from not storing credentials in the workspace and
from requiring a human for irreversible actions at the target.

## When to use it

| Good fit | Poor fit |
|---|---|
| Clear spec, checkable result: run tests and report, summarize recent commits or an issue, a small change from an existing spec, a report | Exploratory development, step-by-step debugging, deciding direction from a diff |
| You're away from the computer and ask from a phone | Anything needing several rounds of discussion — each round goes through the coordinator |

Expect roughly 1.5–2× the cost of working in the repo directly (two
sessions each hold context). A cheap, high-value recurring use is a sweep:
ask each repo for its open "to verify" items and unpushed commits.

## Permissions under `-p`

Nobody can answer a permission prompt in `-p` mode. `dispatch.sh` runs with
`--permission-mode dontAsk`, so anything not allowed is refused at once and
recorded in the JSON's `permission_denials`. In our runs on 2.1.322,
`default` and `acceptEdits` waited about 115 seconds per such call before
refusing. `dispatch.sh` builds the lists:

| Mode | Allowed | Denied |
|---|---|---|
| default (read-only) | Read, Grep, Glob, `git log/show/diff/status` | Edit, Write, NotebookEdit |
| `--write` | the above + Edit, Write | `git commit`, `git push` (unless `--allow`ed), `git reset --hard`, `rm -rf` |
| scoped writes | `--allow 'Edit(dir/**)' --allow 'Write(dir/**)'` without `--write` | Edit/Write elsewhere aren't allowed |
| `--auto` (add to either) | the lists above, plus whatever the auto-mode classifier approves | the lists above, plus Edit/Write on the target's `.claude/settings*.json` and `.claude/hooks/**` |

To let the target commit, allow staging too — `git add` is not on the list,
so `--allow 'Bash(git commit:*)'` alone still fails at `git add`:
`--allow 'Bash(git add:*)' --allow 'Bash(git commit:*)'`.

`--auto` runs `--permission-mode auto`. Deny rules are checked before the
classifier, so the lists above still hold. Two things to know before using
it:

- The classifier approves what the task text asks for. In testing, a task
  that spelled out `git push --force`, `rm -rf` on a sibling directory and a
  keychain read had all three approved. Keep irreversible steps on the deny
  list (`--deny`).
- Entering auto mode drops broad allow rules such as `Bash(*)`, wildcarded
  interpreters and `Agent`, so those calls go to the classifier too.

Use it for jobs that have to write the target's `.claude/` (specs, notes),
which `dontAsk` always refuses. Tested with `--auto --write`: an edit under
`.claude/specs/` went through, edits to `.claude/settings.json` and
`.claude/hooks/` were refused, so was a shell redirect into
`.claude/settings.local.json`, and `git commit` stayed denied.

Things worth knowing:

- **Settings scope.** `dispatch.sh` passes `--setting-sources project` by
  default. Allow rules merge across scopes, and a project's settings can't
  narrow a broad user-level allow such as `Bash(python3:*)`, so leaving user
  settings out is what keeps the lists above the real boundary. It also
  skips your user-level hooks and plugins, and the target's own
  `.claude/settings.local.json`. Use `--user-settings` when the target needs
  them. Your user-level `CLAUDE.md` still loads either way
  (observed: an English task answered in the language a user-level
  `CLAUDE.md` asks for).
- **Folder trust.** Until a folder has been opened interactively once and
  trusted, `-p` ignores that project's own `permissions.allow`.
  `dispatch.sh` warns; fix with `cd <repo> && claude`, accept, exit.
- **Absolute-path rules** need a leading `//`: `Edit(//abs/path/**)`.
  `--src` does this for you.
- **The target's `.claude/` can't be written** without `--auto`, even when
  Edit is allowed. Either add `--auto`, or have the session write a patch
  somewhere else and apply it from the coordinator.
- **`~/.claude/` is a sensitive path** for the child session: writes there are
  refused even with `--add-dir`. Point output directories outside the repo
  *and* outside `~/.claude`.
- **Deny rules are prefixes.** Denying `Bash(glab issue:*)` also blocked
  `glab issue view`, so the child couldn't read the issue. To block writes
  only, deny each write subcommand (`glab issue note:*`, `glab issue create:*`,
  `glab issue update:*`, `glab issue close:*`) and leave reads allowed.
- **No waiting loops.** A foreground `sleep` loop in the child is refused. To
  wait for CI, use the forge's auto-merge or poll from the coordinator.

## Stop points

When the task needs a decision, ask the target to stop instead of guessing:
"if X is ambiguous, stop and list the options with file paths". The
coordinator relays the options to the user and continues with
`--resume <session_id>`. Without `--resume`, a new session starts with no
memory of the earlier work. Several stages (change → review → merge) can
run as successive `--resume` calls on one session, with the coordinator
checking the repo between stages. Write "do this stage, then stop and report"
in each brief, and use deny rules as the backstop for actions that belong to
a later stage.

## Following up in the target's own memory

If the target has its own memory workflow (for example a `/curate-memory`
skill), resume the session and let it file what it learned, with writes scoped
to its memory directory:

```bash
dispatch.sh --repo <dir> --resume <id> \
  --allow 'Edit(.agents/memory/**)' --allow 'Write(.agents/memory/**)' "/curate-memory"
```

Check the target for uncommitted memory changes first so they don't mix. When
you pass a hint, label your own inferences as unverified; the target files
whatever it's given.

## Verify at the coordinator

The child's report is a claim. Check `git log`, `git status`, `git diff` in
the target, re-run one of the checks it says passed, and read the denied
commands. Every run keeps its event stream (`<log>.stream`, one JSON event per
line, so you can `tail -f` a long run) and the result JSON under
`$DISPATCH_LOG_DIR` (default `~/.cache/dispatch`).

`total_cost_usd` in the JSON is an API-price estimate. With a Claude
subscription login (no `ANTHROPIC_API_KEY` set), runs count against the
subscription instead.
