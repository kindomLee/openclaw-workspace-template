#!/usr/bin/env python3
"""End-to-end smoke test for the template.

Bootstraps a fresh workspace (into a path with a space on purpose), seeds it
with journals / notes / LEARNINGS, then runs every scheduled job, hook and
installer the way launchd, cron and Claude Code would. `claude`, `launchctl`,
`crontab` and `osascript` are recording shims, so nothing is installed on the
machine running the test and no model is called.

    python3 tests/smoke_test.py          # exit 1 on any failure
    python3 tests/smoke_test.py --keep   # keep the temp dir for inspection

Stdlib only. Runs on macOS (incl. /bin/bash 3.2) and Linux.
"""
import datetime as dt
import json
import os
import pathlib
import plistlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix="owt-smoke-")).resolve()  # macOS /var → /private/var
WS = TMP / "my ws"            # the space is deliberate
HOME = TMP / "home"
SHIM = TMP / "shim"
CALLS = TMP / "calls.log"     # one line per shim call: name|cwd|args
TODAY = dt.date.today()
failures = []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        failures.append(what)


def run(cmd, cwd=WS, env=None, stdin=""):
    e = {"HOME": str(HOME), "PATH": f"{SHIM}:{os.environ['PATH']}",
         "LLM_PROBE_URL": "file:///dev/null", "LANG": "en_US.UTF-8"}
    e.update(env or {})
    return subprocess.run(cmd, cwd=cwd, env=e, input=stdin, capture_output=True,
                          text=True, timeout=300)


def calls(name):
    if not CALLS.exists():
        return []
    return [l.split("|", 2) for l in CALLS.read_text().splitlines() if l.startswith(name + "|")]


def make_shims():
    SHIM.mkdir(parents=True)
    HOME.mkdir()
    for name, tail in {"claude": "cat >/dev/null", "launchctl": "", "osascript": "",
                       "crontab": '[ "$1" = "-l" ] && exit 1; cat >/dev/null'}.items():
        p = SHIM / name
        p.write_text(f'#!/bin/bash\necho "{name}|$(pwd)|$*" >> "{CALLS}"\n{tail}\nexit 0\n')
        p.chmod(0o755)


def seed():
    mem = WS / "memory"
    for ago in (0, 1, 2, 3, 9, 15, 40, 120):
        d = TODAY - dt.timedelta(days=ago)
        p = mem / f"{d}.md"
        p.write_text(f"# {d}\n\n## Auth migration  [hall_events]\n\n"
                     f"- [hall_events] moved auth to the new cluster (day {ago})\n"
                     "- [hall_facts] decided on Postgres 16\n", encoding="utf-8")
        ts = dt.datetime.combine(d, dt.time(21)).timestamp()
        os.utime(p, (ts, ts))
    links = " ".join(f"[[missing-{i}]]" for i in range(6))
    todos = "".join(f"- [ ] task {i}\n" for i in range(22))
    (WS / "notes/01-Projects/Active/auth.md").write_text(
        f"---\ntitle: Auth\ndate: {TODAY}\ntags: [auth]\nstatus: active\n---\n\n# Auth\n\n{links}\n\n{todos}",
        encoding="utf-8")
    ev = "".join(f"  - {TODAY - dt.timedelta(days=a)}: scripts/x.py:{a}\n" for a in (40, 20, 2))
    with open(WS / "LEARNINGS.md", "a", encoding="utf-8") as f:
        f.write(f"\n## [CORRECTION-{TODAY:%Y%m%d}-001] Hard-coded paths\n\n"
                "- **claim**: scripts keep hard-coding home paths\n- **type**: correction\n"
                "- **recurring_count**: 3\n- **status**: active\n- **evidence**:\n" + ev +
                "- **suggested_action**: grep for /home/ before pushing\n- **blast_radius**: one repo\n")
    # Alerts go to stdout (= the job's log) so we can see them arrive.
    (WS / "cron/config.env").write_text("NOTIFY_CHANNEL=stdout\n")
    # Pretend the user last curated 12 days ago: the 9-day-old journal gets
    # rotated into memory/archive-YYYY-MM/ but must stay in the backlog.
    (WS / "cron/state").mkdir(parents=True, exist_ok=True)
    (WS / "cron/state/curate-memory.json").write_text(
        json.dumps({"last_curated_date": str(TODAY - dt.timedelta(days=12))}))


def hook(name, event):
    cmd = ["python3" if name.endswith(".py") else "bash", str(WS / ".claude/hooks" / name)]
    payload = {"session_id": "smoke", "cwd": str(WS), "transcript_path": "", **event}
    return run(cmd, env={"CLAUDE_PROJECT_DIR": str(WS)}, stdin=json.dumps(payload))


def plist_jobs():
    for p in sorted((WS / "cron/launchd").glob("*.plist")):
        d = plistlib.loads(p.read_bytes())
        sub = lambda s: s.replace("__PROJECT_DIR__", str(WS)).replace("__HOME__", str(HOME))
        env = {k: sub(v) for k, v in d.get("EnvironmentVariables", {}).items()}
        env["PATH"] = f"{SHIM}:{env.get('PATH', '/usr/bin:/bin')}"
        yield p.stem, [sub(a) for a in d["ProgramArguments"]], env, sub(d.get("WorkingDirectory") or "/")


def main():
    make_shims()
    print(f"workspace: {WS}")

    print("bootstrap")
    r = run(["bash", str(REPO / "bootstrap.sh"), "--path", str(WS), "--yes"], cwd=TMP)
    check(r.returncode == 0, "bootstrap exits 0")
    if r.returncode:
        print(r.stdout[-1500:], r.stderr[-1500:], sep="\n")
        return 1
    check((WS / ".claude/flags/welcome-profile-setup.flag").exists(), "fresh workspace gets the welcome flag")
    check((WS / "MEMORY_COMPACT.md").exists(), "MEMORY_COMPACT.md generated (CLAUDE.md wake-up reads it)")
    seed()

    print("hooks (UserPromptSubmit / PostToolUse)")
    r = hook("memory-search-trigger.py", {"hook_event_name": "UserPromptSubmit",
                                          "prompt": "what did we decide about the auth migration last week?"})
    check(r.returncode == 0 and "additionalContext" in r.stdout, "memory-search-trigger injects recall")
    r = hook("correction-capture.py", {"hook_event_name": "UserPromptSubmit",
                                       "prompt": "no, that's wrong, I told you Postgres 16"})
    check(r.returncode == 0 and (WS / "cron/state/pending-corrections.jsonl").exists(),
          "correction-capture queues the correction")
    r = hook("runtime-friction-monitor.py", {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                             "tool_input": {"command": "ls"}, "tool_response": {"stdout": ""}})
    check(r.returncode == 0, "runtime-friction-monitor exits 0")

    print("scheduled jobs, as launchd runs them")
    names = []
    for name, args, env, cwd in plist_jobs():
        names.append(name)
        r = run(args, cwd=cwd, env=env)
        check(r.returncode == 0, f"{name} exits 0 {r.stdout.strip()[-160:] if r.returncode else ''}")
    check(len(names) == 17, f"17 plists shipped (found {len(names)})")
    llm = calls("claude")
    check(len(llm) == 5, f"5 prompt jobs reached claude -p (got {len(llm)})")
    check(all(c[1] == str(WS) for c in llm), "claude -p runs inside the workspace")

    print("runner.sh as POSIX cron runs it (cwd=$HOME, bare PATH, no coreutils on macOS)")
    CALLS.unlink(missing_ok=True)
    r = run([str(WS / "cron/runner.sh"), "memory-janitor"], cwd=HOME, env={"PATH": f"{SHIM}:/usr/bin:/bin"})
    llm = calls("claude")
    check(r.returncode == 0 and len(llm) == 1 and llm[0][1] == str(WS),
          f"runner reaches claude from $HOME and cds into the workspace ({r.stderr.strip()[-160:]})")

    print("flags and reports")
    flags = WS / ".claude/flags"
    for f in ("broken-links", "notes-todo", "curate-memory", "weekly-review"):
        check((flags / f"{f}.flag").exists(), f"{f}.flag written")
    log = WS / "cron/logs/broken-links-check-launchd.log"
    check(log.exists() and "[notify] broken wikilinks" in log.read_text(),
          "a job started straight from its plist picks up cron/config.env for alerts")
    run(["bash", "cron/bin/curate-memory.sh"])
    flag = flags / "curate-memory.flag"
    nine = str(TODAY - dt.timedelta(days=9))
    check(flag.exists() and nine in flag.read_text(), "curate backlog keeps a journal already rotated to archive")
    report = next((p.read_text() for p in (WS / "cron/state").glob("weekly-review-*.md")), "")
    check("Captured corrections not classified (1)" in report, "weekly review lists the unclassified correction")
    r = run(["python3", "scripts/learnings-promotion-check.py", "--json", "--gate", "0"])
    found = json.loads(r.stdout)["candidates"] if r.returncode == 0 else []
    check(len(found) == 1 and found[0]["evidence_count"] == 3, "promotion-check counts 3 evidence lines, not 5")
    r = hook("session-start-flags.sh", {"hook_event_name": "SessionStart", "source": "startup"})
    check(r.returncode == 0 and "curate-memory" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"],
          "SessionStart hook injects pending flags")
    for h in ("budget-flag-guard.py", "plan-resume-check.sh"):
        check(hook(h, {"hook_event_name": "SessionStart", "source": "startup"}).returncode == 0, f"{h} exits 0")

    print("installers (shimmed)")
    CALLS.unlink(missing_ok=True)
    r = run(["bash", "cron/install-linux.sh", "--help"])
    check(r.returncode == 0 and not calls("crontab"), "install-linux --help installs nothing")
    r = run(["bash", "cron/install-linux.sh", "--bogus"])
    check(r.returncode != 0 and not calls("crontab"), "install-linux rejects unknown options")
    r = run(["bash", "cron/install-linux.sh", "--dry-run"])
    check(r.returncode == 0 and "17 jobs" in r.stdout and f"'{WS}/cron/runner.sh'" in r.stdout,
          f"install-linux --dry-run: 17 jobs, workspace path quoted (rc={r.returncode} {r.stderr.strip()[-200:]})")
    r = run(["bash", "cron/install-mac.sh"])
    agents = list((HOME / "Library/LaunchAgents").glob("org.mklee.*.plist"))
    check(r.returncode == 0 and len(agents) == 17, f"install-mac installs 17 agents ({len(agents)})")
    check(not any("__PROJECT_DIR__" in a.read_text() for a in agents), "installed plists have no placeholders")
    r = run(["bash", "cron/install-mac.sh", "--uninstall"])
    check(r.returncode == 0 and not list((HOME / "Library/LaunchAgents").glob("org.mklee.*")), "install-mac --uninstall removes them")

    r = run(["bash", "scripts/health-check.sh"])
    check(r.returncode == 0, f"health-check reports no errors ({r.stdout.strip()[-300:] if r.returncode else ''})")

    print("upgrade re-run")
    (flags / "welcome-profile-setup.flag").unlink()
    r = run(["bash", str(REPO / "bootstrap.sh"), "--path", str(WS), "--yes"], cwd=TMP)
    check(r.returncode == 0 and not (flags / "welcome-profile-setup.flag").exists(),
          "re-running bootstrap does not bring back a resolved welcome flag")

    print(f"\n{len(failures)} failure(s)")
    if "--keep" in sys.argv:
        print(f"kept: {TMP}")
    else:
        shutil.rmtree(TMP, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
