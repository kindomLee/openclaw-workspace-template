#!/usr/bin/env python3
"""weekly-review-digest — merge the self-improvement queues into one weekly
review checklist (zero LLM, never edits memory files).

Sources:
  1. cron/state/observations.jsonl  correction candidates (status=candidate,
                                    written by classify-corrections.py)
  2. memory/reflections.md          "## YYYY-MM-DD 反思" sections not yet marked
                                    "✅ 已覆審" (written by memory-reflect)
  3. LEARNINGS.md                   promotion candidates + stale low-signal
                                    entries (learnings-promotion-check --json)

Writes cron/state/weekly-review-<YYYY-Www>.md and, when anything is pending,
.claude/flags/weekly-review.flag. Run by cron/bin/weekly-review.sh.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "cron" / "state"
OBS = STATE / "observations.jsonl"
REFLECTIONS = REPO / "memory" / "reflections.md"
LEARNINGS = REPO / "LEARNINGS.md"
FLAG = REPO / ".claude" / "flags" / "weekly-review.flag"
REVIEWED = "✅ 已覆審"


def corrections() -> list[str]:
    if not OBS.exists():
        return []
    out = []
    for line in OBS.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("status") == "candidate":
            msg = d.get("user_msg", "").replace("\n", " ")[:100]
            out.append(f"`{d.get('id')}`: {msg}")
    return out


def reflections() -> list[str]:
    if not REFLECTIONS.exists():
        return []
    heads = re.findall(r"^## (\d{4}-\d{2}-\d{2}) (反思.*)$", REFLECTIONS.read_text(encoding="utf-8"), re.M)
    return [f"{d} {t}" for d, t in heads if REVIEWED not in t]


def learnings() -> tuple[list[str], list[str]]:
    if not LEARNINGS.exists():
        return [], []
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "learnings-promotion-check.py"), "--json"],
                         capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    promote = [f"`{e['id']}` {e['title'][:70]}" for e in d["candidates"]]
    stale = subprocess.run([sys.executable, str(REPO / "scripts" / "learnings-archive.py"), "--ids", "stale"],
                           capture_output=True, text=True, check=True).stdout.splitlines()
    return promote, [s for s in stale if s and not s.startswith(("共 ", "（"))]


def section(title: str, items: list[str], action: str, cap: int = 15) -> str:
    if not items:
        return f"## {title} (0)\n\nNone.\n"
    body = "\n".join(f"- {x}" for x in items[:cap])
    more = f"\n- … {len(items) - cap} more" if len(items) > cap else ""
    return f"## {title} ({len(items)})\n\n{body}{more}\n\nAction: {action}\n"


def main() -> int:
    corr, refl = corrections(), reflections()
    promote, stale = learnings()
    total = len(corr) + len(refl) + len(promote) + len(stale)

    week = date.today().strftime("%G-W%V")
    STATE.mkdir(parents=True, exist_ok=True)
    report = STATE / f"weekly-review-{week}.md"
    report.write_text("\n".join([
        f"# Weekly review {week}",
        "",
        f"> Generated {datetime.now():%Y-%m-%d %H:%M}. {total} item(s) pending.",
        "",
        section("Correction candidates", corr,
                "curate the ones worth keeping into feedback memory or LEARNINGS.md; "
                "set `status: rejected` in cron/state/observations.jsonl for the rest"),
        section("Reflections not yet reviewed", refl,
                f"read the matching section in memory/reflections.md, apply what you accept, "
                f"then append \"{REVIEWED} YYYY-MM-DD\" to that section's heading "
                f"(otherwise it is listed again every week)"),
        section("LEARNINGS promotion candidates", promote,
                "promote to MEMORY.md and mark the entry resolved"),
        section("LEARNINGS archivable (rc=1, little evidence, >90 days)", stale,
                "to archive the whole batch: `python3 scripts/learnings-archive.py --ids stale --apply`; "
                "add evidence or bump rc for any you want to keep"),
    ]), encoding="utf-8")

    if total:
        FLAG.parent.mkdir(parents=True, exist_ok=True)
        FLAG.write_text("\n".join([
            f"Weekly review {week}: corrections {len(corr)}, reflections {len(refl)}, "
            f"LEARNINGS promote {len(promote)}, archivable {len(stale)}",
            f"Read {report.relative_to(REPO)} and work through each section.",
            "When done: rm .claude/flags/weekly-review.flag",
        ]) + "\n", encoding="utf-8")
    else:
        FLAG.unlink(missing_ok=True)
    print(f"{report.relative_to(REPO)}: {total} item(s) (corrections {len(corr)}, reflections {len(refl)}, "
          f"promote {len(promote)}, archivable {len(stale)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
