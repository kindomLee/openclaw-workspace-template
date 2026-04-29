#!/usr/bin/env python3
"""memory-archive.py — Mac/Linux portable janitor for cc-memory-project.

替代 `memory-tools janitor`（VPS-only），純 Python 不依賴外部 binary。

Modes:
  --mode rotate-journal     搬超齡 memory/YYYY-MM-DD*.md → archive-YYYY-MM/
  --mode archive-timeline   把 MEMORY.md 中 < 本月的 ### YYYY-MM section
                            搬到 memory/timeline-archive.md
  --mode both               依序跑兩個

Pinning（受 hook 注入頻率保護）：
  --respect-access-log <path>     讀 hook 寫的 jsonl access log
  --access-window-days N          觀察視窗（預設 30）
  --access-threshold N            次數 >= 此值就 pin（預設 3）

其它：
  --dry-run                       只印不動
  --rotate-days N                 超過 N 天才 rotate（預設 5）
  --memory-dir / --memory-md / --timeline-archive  路徑覆寫

平台：Mac (BSD) / Linux (GNU) 皆可，所有 IO 走 Python 標準庫。
"""

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_ROTATE_DAYS = 5
DEFAULT_ACCESS_WINDOW_DAYS = 30
DEFAULT_ACCESS_THRESHOLD = 3

# 系統檔（即使檔名長得像日期也永不歸檔）
SYSTEM_FILES = frozenset({
    "MEMORY.md", "MEMORY_COMPACT.md", "AGENTS.md", "USER.md", "TOOLS.md",
    "CLAUDE.md", "SOUL.md", "BOOTSTRAP.md", "HEARTBEAT.md", "LEARNINGS.md",
    "reflections.md", "dreams.md", "timeline-archive.md", "reflect-done.md",
})

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def is_system_journal(name: str) -> bool:
    """memory/ 內的系統/月度檔（永不 rotate）。"""
    if name in SYSTEM_FILES:
        return True
    if name.startswith("monthly-") and name.endswith(".md"):
        return True
    return False


# ---------------------------------------------------------------------------
# Access log（受 use-aware pinning 用）
# ---------------------------------------------------------------------------

def load_access_counts(log_path: Path, window_days: int) -> Counter:
    """讀 jsonl，回傳 file → count（最近 window_days 內）。失敗回空 Counter。"""
    counts: Counter = Counter()
    if not log_path.exists():
        return counts
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    ts_str = rec.get("ts") or ""
                    file_path = rec.get("file") or ""
                    if not ts_str or not file_path:
                        continue
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff:
                        counts[file_path] += 1
                except Exception:
                    continue
    except Exception:
        pass
    return counts


def access_count_for_journal(journal_file: Path, counts: Counter) -> int:
    """
    Hook 寫的 access log 對 journal 命中可能有兩種 key 形態：
      - search hits：bare filename，例如 "2026-04-13.md"
      - graph hits：含 memory/ 前綴，例如 "memory/2026-04-13.md"
    這裡兩種都查並加總。
    """
    name_only = journal_file.name
    rel_with_dir = f"memory/{name_only}"
    return counts.get(name_only, 0) + counts.get(rel_with_dir, 0)


# ---------------------------------------------------------------------------
# Mode: rotate-journal
# ---------------------------------------------------------------------------

def rotate_journal(
    memory_dir: Path,
    rotate_days: int,
    counts: Counter,
    threshold: int,
    dry_run: bool,
) -> dict:
    today = datetime.now().date()
    cutoff = today - timedelta(days=rotate_days)
    actions: dict = {
        "moved": [],
        "pinned": [],
        "skipped_system": [],
        "errors": [],
    }

    if not memory_dir.exists():
        actions["errors"].append({"error": f"memory_dir not found: {memory_dir}"})
        return actions

    for f in sorted(memory_dir.glob("*.md")):
        if not f.is_file():
            continue
        if is_system_journal(f.name):
            actions["skipped_system"].append(f.name)
            continue
        m = DATE_RE.match(f.name)
        if not m:
            continue
        try:
            file_date = datetime.strptime(m.group(0), "%Y-%m-%d").date()
        except ValueError:
            continue

        if file_date >= cutoff:
            continue  # 仍在 rolling window 內，留著

        # Pinning check
        if threshold > 0 and counts:
            ac = access_count_for_journal(f, counts)
            if ac >= threshold:
                actions["pinned"].append({
                    "file": f.name,
                    "access_count": ac,
                    "age_days": (today - file_date).days,
                })
                continue

        # 搬到 archive-YYYY-MM/
        archive_dir = memory_dir / f"archive-{m.group(1)}-{m.group(2)}"
        target = archive_dir / f.name
        action = {
            "from": str(f.relative_to(memory_dir.parent)),
            "to": str(target.relative_to(memory_dir.parent)),
            "age_days": (today - file_date).days,
        }
        actions["moved"].append(action)
        if not dry_run:
            try:
                archive_dir.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise FileExistsError(f"target already exists: {target}")
                shutil.move(str(f), str(target))
            except Exception as e:
                actions["errors"].append({"file": f.name, "error": str(e)})

    return actions


# ---------------------------------------------------------------------------
# Mode: archive-timeline
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(r"^### (\d{4}-\d{2})\b.*$", re.MULTILINE)
NEXT_HEADER_RE = re.compile(r"^##+ ", re.MULTILINE)


def archive_timeline(
    memory_md: Path,
    timeline_archive: Path,
    dry_run: bool,
) -> dict:
    if not memory_md.exists():
        return {"error": f"MEMORY.md not found: {memory_md}"}

    today = datetime.now().date()
    current_ym = f"{today.year}-{today.month:02d}"

    text = memory_md.read_text(encoding="utf-8")
    matches = list(SECTION_RE.finditer(text))

    sections_to_archive: list[dict] = []
    for m in matches:
        ym = m.group(1)
        if ym >= current_ym:
            continue  # 本月或未來月份留著
        start = m.start()
        # End：下一個 ## 或 ### header（同層或上層），或 EOF
        rest = text[m.end():]
        next_m = NEXT_HEADER_RE.search(rest)
        end = m.end() + next_m.start() if next_m else len(text)
        section_text = text[start:end].rstrip() + "\n"
        sections_to_archive.append({
            "ym": ym,
            "start": start,
            "end": end,
            "text": section_text,
            "lines": section_text.count("\n"),
        })

    result: dict = {
        "current_month": current_ym,
        "sections_archived": [],
        "dry_run": dry_run,
    }

    if not sections_to_archive:
        return result

    if dry_run:
        for s in sections_to_archive:
            result["sections_archived"].append({
                "section": s["ym"], "lines": s["lines"], "dry_run": True,
            })
        return result

    # Append to timeline-archive.md
    timeline_archive.parent.mkdir(parents=True, exist_ok=True)
    with open(timeline_archive, "a", encoding="utf-8") as f:
        for s in sections_to_archive:
            f.write(f"\n\n<!-- auto-archived from MEMORY.md on {today.isoformat()} -->\n")
            f.write(s["text"])
            result["sections_archived"].append({
                "section": s["ym"], "lines": s["lines"],
            })

    # Remove from MEMORY.md（reverse order 保 offset）
    new_text = text
    for s in reversed(sections_to_archive):
        new_text = new_text[:s["start"]] + new_text[s["end"]:]
    # 清理多餘空行（>=3 個 newline 壓回 2 個）
    new_text = re.sub(r"\n{3,}", "\n\n", new_text)
    memory_md.write_text(new_text, encoding="utf-8")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Mac/Linux portable memory janitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--mode", choices=["rotate-journal", "archive-timeline", "both"],
                    required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--respect-access-log", default=None,
                    help="Path to ~/.claude/state/mem-access.jsonl (enables pinning)")
    ap.add_argument("--rotate-days", type=int, default=DEFAULT_ROTATE_DAYS)
    ap.add_argument("--access-window-days", type=int, default=DEFAULT_ACCESS_WINDOW_DAYS)
    ap.add_argument("--access-threshold", type=int, default=DEFAULT_ACCESS_THRESHOLD)
    ap.add_argument("--memory-dir", default="memory")
    ap.add_argument("--memory-md", default="MEMORY.md")
    ap.add_argument("--timeline-archive", default="memory/timeline-archive.md")
    args = ap.parse_args()

    memory_dir = Path(args.memory_dir).resolve()
    memory_md = Path(args.memory_md).resolve()
    timeline_archive = Path(args.timeline_archive).resolve()

    counts: Counter = Counter()
    if args.respect_access_log:
        log_path = Path(os.path.expanduser(args.respect_access_log))
        counts = load_access_counts(log_path, args.access_window_days)

    result: dict = {
        "mode": args.mode,
        "dry_run": args.dry_run,
        "access_pinning": bool(args.respect_access_log),
        "access_log_entries_in_window": sum(counts.values()) if counts else 0,
    }

    if args.mode in ("rotate-journal", "both"):
        result["rotate"] = rotate_journal(
            memory_dir, args.rotate_days, counts, args.access_threshold, args.dry_run,
        )

    if args.mode in ("archive-timeline", "both"):
        result["timeline"] = archive_timeline(memory_md, timeline_archive, args.dry_run)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
