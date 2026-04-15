#!/usr/bin/env python3
"""check-schedule-drift.py — verify doc schedule tables match `cron/launchd/*.plist`.

Ground truth: `cron/launchd/*.plist` (consumed directly by launchd on macOS
and by `cron/install-linux.sh` on Linux).

Checked documents:
  - `templates/HEARTBEAT.md`   (per README.md, this is the *designated*
    source of truth for humans; we still diff it against plists to catch
    the case where a plist is added but HEARTBEAT forgets)
  - `cron/README.md`           (convenience copy, high drift risk)
  - `guides/routine-checks.md` (convenience copy, even higher drift risk)

Usage:
  python3 scripts/check-schedule-drift.py             # check all
  python3 scripts/check-schedule-drift.py --quiet     # only print drift
  python3 scripts/check-schedule-drift.py --doc PATH  # check a single doc

Exit code:
  0 — all docs match plists (warnings allowed, e.g. doc lists a job that
      has no matching plist — usually an OpenClaw-mode entry)
  1 — at least one doc is missing a plist job or has a mismatched schedule
  2 — fatal error (plists directory missing, invalid args)
"""
from __future__ import annotations

import argparse
import os
import plistlib
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Schedule normalization
# ---------------------------------------------------------------------------

# Canonical tuple forms (first element is the "kind", rest are fields):
#   ("hourly", minute)
#   ("daily",  hour, minute)
#   ("weekly", weekday, hour, minute)     # weekday: 0=Sun .. 6=Sat
#   ("monthly", day, hour, minute)        # day: 1..31

WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

DAY_MAP = {
    "sun": 0, "sunday": 0,
    "mon": 1, "monday": 1,
    "tue": 2, "tues": 2, "tuesday": 2,
    "wed": 3, "wednesday": 3,
    "thu": 4, "thurs": 4, "thursday": 4,
    "fri": 5, "friday": 5,
    "sat": 6, "saturday": 6,
}


def format_schedule(s) -> str:
    if s is None:
        return "<unparseable>"
    kind = s[0]
    if kind == "hourly":
        return f"hourly :{s[1]:02d}"
    if kind == "daily":
        return f"daily {s[1]:02d}:{s[2]:02d}"
    if kind == "weekly":
        return f"weekly {WEEKDAY_NAMES[s[1]]} {s[2]:02d}:{s[3]:02d}"
    if kind == "monthly":
        return f"monthly day-{s[1]} {s[2]:02d}:{s[3]:02d}"
    return str(s)


def plist_to_schedule(plist_data: dict):
    """Translate a launchd plist's StartCalendarInterval to a canonical tuple."""
    cal = plist_data.get("StartCalendarInterval")
    if not cal:
        return None
    if isinstance(cal, list):
        if not cal:
            return None
        cal = cal[0]  # first entry only — multi-trigger plists aren't used in this template

    minute = cal.get("Minute")
    hour = cal.get("Hour")
    weekday = cal.get("Weekday")  # launchd: 0 or 7 = Sun
    day = cal.get("Day")

    if weekday == 7:
        weekday = 0

    # hourly: only Minute is set
    if minute is not None and hour is None and weekday is None and day is None:
        return ("hourly", minute)

    # monthly: Day+Hour+Minute
    if day is not None and hour is not None and minute is not None:
        return ("monthly", day, hour, minute)

    # weekly: Weekday+Hour+Minute
    if weekday is not None and hour is not None and minute is not None:
        return ("weekly", weekday, hour, minute)

    # daily: Hour+Minute (no Weekday, no Day)
    if hour is not None and minute is not None and weekday is None and day is None:
        return ("daily", hour, minute)

    return None


def parse_schedule_cell(cell: str):
    """Normalize a markdown table schedule cell. Returns canonical tuple
    or None if the cell doesn't look like a schedule expression."""
    t = cell.strip().strip("`").strip()
    if not t:
        return None
    t_low = t.lower()

    # "hourly :02" or ":02 hourly" or "每小時 :02"
    if "hourly" in t_low or "每小時" in t_low or re.search(r"^\s*:\d{2}\b", t_low):
        m = re.search(r":(\d{2})", t_low)
        if m:
            return ("hourly", int(m.group(1)))

    # Extract HH:MM from the cell
    time_m = re.search(r"(\d{1,2}):(\d{2})", t_low)
    if not time_m:
        return None
    hh, mm = int(time_m.group(1)), int(time_m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None

    # Monthly: "1st", "1st of month", "(monthly)", or "day-N"
    mon_m = re.search(r"(\d+)(?:st|nd|rd|th)", t_low)
    if mon_m or "monthly" in t_low or "每月" in t_low:
        day = int(mon_m.group(1)) if mon_m else 1
        return ("monthly", day, hh, mm)

    # Weekly: a day-of-week word appears
    for dname, didx in DAY_MAP.items():
        if re.search(rf"\b{dname}\b", t_low):
            return ("weekly", didx, hh, mm)

    # Explicit "daily" or "每日"
    if "daily" in t_low or "每日" in t_low or "every day" in t_low:
        return ("daily", hh, mm)

    # No qualifier — default to daily
    return ("daily", hh, mm)


# ---------------------------------------------------------------------------
# Markdown table extraction
# ---------------------------------------------------------------------------

JOB_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
HEADER_KEYWORDS = {"schedule", "time", "when", "cron"}


def extract_schedule_rows(md_text: str):
    """Find all table rows where column-0 parses as a schedule and
    column-1 looks like a job slug. Returns list of tuples:
        (parsed_schedule, raw_schedule_text, job_name)
    Non-schedule tables are ignored automatically because their cells
    don't parse as schedules or their column-1 isn't a slug."""
    rows = []
    for line in md_text.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("|"):
            continue
        if re.match(r"^\s*\|[\s|:-]+\|\s*$", line):  # separator row
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue

        sched_text = cells[0]
        job_name = cells[1]

        # Strip inline formatting from job_name (e.g. `job` or **job**)
        job_name = re.sub(r"^[`*_]+|[`*_]+$", "", job_name).strip()

        if sched_text.lower().strip("`*_ ") in HEADER_KEYWORDS:
            continue  # header row
        if not JOB_NAME_RE.match(job_name):
            continue
        parsed = parse_schedule_cell(sched_text)
        if parsed is None:
            continue
        rows.append((parsed, sched_text, job_name))
    return rows


# ---------------------------------------------------------------------------
# Core diff
# ---------------------------------------------------------------------------

def load_plist_schedule(plist_dir: Path) -> dict:
    """Return {job_name: canonical_schedule} for every plist in plist_dir."""
    out = {}
    for fname in sorted(os.listdir(plist_dir)):
        if not fname.endswith(".plist"):
            continue
        fpath = plist_dir / fname
        try:
            with open(fpath, "rb") as fp:
                d = plistlib.load(fp)
        except Exception as e:
            print(f"WARNING: failed to parse {fname}: {e}", file=sys.stderr)
            continue
        try:
            job_name = d["ProgramArguments"][-1]
        except (KeyError, IndexError):
            continue
        sched = plist_to_schedule(d)
        if sched is None:
            print(f"WARNING: {fname} has no usable StartCalendarInterval", file=sys.stderr)
            continue
        out[job_name] = sched
    return out


def compare_doc(doc_label: str, doc_rows: list, plist_sched: dict):
    """Return (errors, warnings) lists for a single doc."""
    errors = []
    warnings = []

    doc_by_job = {}
    for parsed, raw, job in doc_rows:
        if job in doc_by_job:
            warnings.append(f"{doc_label}: duplicate row for '{job}'")
            continue
        doc_by_job[job] = (parsed, raw)

    for job, expected in plist_sched.items():
        if job not in doc_by_job:
            errors.append(
                f"{doc_label}: missing job '{job}' — "
                f"plist says {format_schedule(expected)}"
            )
            continue
        got, raw = doc_by_job[job]
        if got != expected:
            errors.append(
                f"{doc_label}: '{job}' schedule mismatch — "
                f"plist={format_schedule(expected)}, "
                f"doc cell {raw!r} → {format_schedule(got)}"
            )

    for job in doc_by_job:
        if job not in plist_sched:
            warnings.append(
                f"{doc_label}: '{job}' listed but no matching plist "
                f"(probably an OpenClaw-mode or crontab-only job — "
                f"confirm if that's intentional)"
            )

    return errors, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_DOCS = [
    ("templates/HEARTBEAT.md", "templates/HEARTBEAT.md"),
    ("cron/README.md", "cron/README.md"),
    ("guides/routine-checks.md", "guides/routine-checks.md"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--quiet", action="store_true", help="only print drift (no summary)")
    ap.add_argument(
        "--doc",
        action="append",
        default=None,
        help="check a single doc path (can be passed multiple times); "
             "default: HEARTBEAT.md, cron/README.md, guides/routine-checks.md",
    )
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    plist_dir = project_root / "cron" / "launchd"

    if not plist_dir.is_dir():
        print(f"ERROR: {plist_dir} does not exist — nothing to diff against", file=sys.stderr)
        return 2

    plist_sched = load_plist_schedule(plist_dir)
    if not plist_sched:
        print(f"ERROR: no valid plists in {plist_dir}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"Ground truth: {len(plist_sched)} plists in {plist_dir.relative_to(project_root)}")
        for job, sched in sorted(plist_sched.items()):
            print(f"  {job:25s}  {format_schedule(sched)}")
        print()

    docs: list[tuple[str, Path]] = []
    if args.doc:
        for rel in args.doc:
            docs.append((rel, project_root / rel))
    else:
        for label, rel in DEFAULT_DOCS:
            docs.append((label, project_root / rel))

    total_errors = 0
    total_warnings = 0

    for doc_label, doc_path in docs:
        if not doc_path.exists():
            print(f"SKIP {doc_label}: not found at {doc_path}")
            continue
        text = doc_path.read_text(encoding="utf-8")
        rows = extract_schedule_rows(text)
        errors, warnings = compare_doc(doc_label, rows, plist_sched)

        if not args.quiet or errors or warnings:
            print(f"--- {doc_label} ({len(rows)} schedule row(s)) ---")
            for e in errors:
                print(f"  ERROR: {e}")
            for w in warnings:
                print(f"  WARN:  {w}")
            if not errors and not warnings and not args.quiet:
                print("  OK")
            print()

        total_errors += len(errors)
        total_warnings += len(warnings)

    if total_errors == 0:
        if not args.quiet:
            print(f"✓ All docs match plists ({total_warnings} warning(s))")
        return 0
    else:
        print(f"✗ {total_errors} error(s), {total_warnings} warning(s)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
