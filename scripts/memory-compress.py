#!/usr/bin/env python3
"""memory-compress.py — Compression-based long-term memory maintenance.

Rather than deleting expired entries, this script *compresses* them:
  * Events Timeline: month blocks older than 90 days → fold to one summary line.
  * P1 technical blocks: flag entries older than 90 days for manual review
    (don't auto-compress — they usually need human judgment).
  * P2 experimental blocks: older than 30 days → compress to conclusion line,
    drop the how-we-got-there details.
  * P0 / Cases / Patterns: permanent, never touched.

Separately: archive raw daily logs in `memory/*.md` older than 90 days into
`memory/archive/`.

Not to be confused with `cron/prompts/memory-janitor.md`, which is a
different job (LLM-driven hall-tag backfill / duplicate detection / notes
quality check — run by the cron runner, not this script).

Usage:
  python3 memory-compress.py                    # dry run: scan + report
  python3 memory-compress.py --force            # execute compression + archive
  python3 memory-compress.py --dry-run          # explicit preview
  python3 memory-compress.py --notify           # dry run + Telegram report
  python3 memory-compress.py --force --notify   # execute + Telegram report
  python3 memory-compress.py --workspace DIR    # override workspace root

Configuration (environment variables, typically in cron/config.env):
  TG_BOT_TOKEN       Telegram bot token (required for --notify)
  TG_CHAT_ID         Telegram chat id   (required for --notify)
  OPENCLAW_WORKSPACE Workspace root (otherwise derived from this script's path)

Any hardcoded personal credentials have intentionally been removed. The
earlier version of this file had `WORKSPACE = Path("/root/clawd")` and a
hardcoded Telegram chat id — do not reintroduce either.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path

# Thresholds (days)
TIMELINE_COMPRESS_DAYS = 90   # fold old month blocks
P1_COMPRESS_DAYS = 90         # flag P1 entries for review
P2_COMPRESS_DAYS = 30         # compress P2 blocks
DAILY_LOG_ARCHIVE_DAYS = 90   # archive raw daily logs


def resolve_workspace(cli_value: str | None) -> Path:
    """Resolve workspace root. Priority:
    1. --workspace CLI flag
    2. OPENCLAW_WORKSPACE env var
    3. Script-relative: parent of scripts/ (scripts/../ )
    """
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    env = os.environ.get("OPENCLAW_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def send_telegram_notification(message: str) -> bool:
    """Send a Telegram message via TG_BOT_TOKEN / TG_CHAT_ID env vars.
    Returns True on success, False on any failure (config missing, network, etc).
    Never raises."""
    token = os.environ.get("TG_BOT_TOKEN")
    chat_id = os.environ.get("TG_CHAT_ID")
    if not token or not chat_id:
        print("⚠️  TG_BOT_TOKEN / TG_CHAT_ID not set, skipping Telegram notification")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    cmd = [
        "curl", "-s", "-X", "POST", url,
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception as e:
        print(f"⚠️  Telegram notification failed: {e}")
        return False


def build_notification_message(actions: list[str], dry_run: bool) -> str:
    mode = "🔍 Preview" if dry_run else "⚡ Execute"
    lines = [f"📊 memory-compress {mode}", ""]

    if not actions:
        lines.append("✨ Nothing to process")
    else:
        timeline_compress = [a for a in actions if "Timeline" in a]
        p2_compress = [a for a in actions if "P2" in a]
        p1_pending = [a for a in actions if "P1" in a]
        archive_logs = [a for a in actions if "Archive" in a]
        lines.append(f"📋 {len(actions)} item(s):")
        if timeline_compress:
            lines.append(f"  • 📦 Timeline folded: {len(timeline_compress)}")
        if p2_compress:
            lines.append(f"  • 🗜️ P2 compressed: {len(p2_compress)}")
        if p1_pending:
            lines.append(f"  • ⏳ P1 flagged: {len(p1_pending)}")
        for a in archive_logs:
            lines.append(f"  • 📁 {a}")

    lines.append("")
    lines.append("💡 Run --force to apply" if dry_run else "✅ Applied")
    return "\n".join(lines)


# Regex: MEMORY.md section / timeline parsing
SECTION_TAG = re.compile(r"\[(P[012])\](?:\s+\[(\d{4}-\d{2}-\d{2})\])?")
MONTH_HEADER = re.compile(r"^### (\d{4})-(\d{2})\s*$")
TIMELINE_ENTRY = re.compile(r"^- \*\*(\d{2})-(\d{2})\*\*\s+(.+)$")
DAILY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-.+)?\.md$")


def parse_sections(text: str):
    """Parse MEMORY.md into (preamble, [section_dict, ...])."""
    lines = text.splitlines(keepends=True)
    sections: list[dict] = []
    preamble: list[str] = []
    current_header = None
    current_body: list[str] = []
    current_priority = None
    current_date = None

    for line in lines:
        if line.startswith("## "):
            if current_header is not None:
                sections.append({
                    "header": current_header,
                    "body": current_body,
                    "priority": current_priority,
                    "date": current_date,
                })
            elif current_body or preamble:
                preamble = (preamble or []) + current_body

            current_header = line
            current_body = []

            m = SECTION_TAG.search(line)
            if m:
                current_priority = m.group(1)
                current_date = (
                    datetime.strptime(m.group(2), "%Y-%m-%d").date()
                    if m.group(2) else None
                )
            else:
                current_priority = None
                current_date = None
        else:
            if current_header is None:
                preamble.append(line)
            else:
                current_body.append(line)

    if current_header is not None:
        sections.append({
            "header": current_header,
            "body": current_body,
            "priority": current_priority,
            "date": current_date,
        })

    return preamble, sections


def compress_timeline(section: dict, today):
    """Fold old months (>TIMELINE_COMPRESS_DAYS ago) in Events Timeline into one line each."""
    cutoff = today - timedelta(days=TIMELINE_COMPRESS_DAYS)
    new_body: list[str] = []
    current_month_year = None
    current_month_entries: list[tuple[str, str, str]] = []
    compressed_months: list[str] = []

    def flush_month():
        nonlocal current_month_year, current_month_entries
        if not current_month_year:
            return
        year, month = current_month_year
        month_date = datetime(year, month, 1).date()
        if month_date < cutoff.replace(day=1) and len(current_month_entries) > 3:
            summaries = [e[1] for e in current_month_entries]
            key_items = summaries[:5]
            summary_text = "、".join(key_items)
            if len(summaries) > 5:
                summary_text += f" 等共 {len(summaries)} 項"
            new_body.append(f"### {year}-{month:02d}\n")
            new_body.append(f"- **{month:02d}月摘要** {summary_text}\n")
            new_body.append("\n")
            compressed_months.append(f"{year}-{month:02d} ({len(current_month_entries)} → 1)")
        else:
            new_body.append(f"### {year}-{month:02d}\n")
            for raw in current_month_entries:
                new_body.append(raw[2])
        current_month_year = None
        current_month_entries = []

    for line in section["body"]:
        stripped = line.rstrip("\n")
        m = MONTH_HEADER.match(stripped)
        if m:
            flush_month()
            current_month_year = (int(m.group(1)), int(m.group(2)))
            continue
        em = TIMELINE_ENTRY.match(stripped)
        if em and current_month_year:
            current_month_entries.append((em.group(1), em.group(3), line))
            continue
        if current_month_year is None:
            new_body.append(line)
        else:
            if stripped and not stripped.startswith("<!--"):
                current_month_entries.append(("", stripped, line))
            elif stripped.startswith("<!--"):
                new_body.append(line)

    flush_month()
    return new_body, compressed_months


def compress_p2_section(section: dict):
    """Compress a P2 block to at most 3 lines + a 'collapsed' marker."""
    body = section["body"]
    content_lines = [l for l in body if l.strip() and not l.strip().startswith("<!--")]
    if len(content_lines) <= 3:
        return body, False

    new_body: list[str] = []
    content_count = 0
    for line in body:
        if line.strip().startswith("<!--"):
            new_body.append(line)
            continue
        if not line.strip():
            new_body.append(line)
            continue
        content_count += 1
        if content_count <= 3:
            new_body.append(line)
        elif content_count == 4:
            new_body.append(f"- *(collapsed {len(content_lines) - 3} detail line(s))*\n")
            break

    new_body.append("\n")
    return new_body, True


def archive_old_daily_logs(memory_dir: Path, archive_dir: Path, today, force: bool) -> list[str]:
    cutoff = today - timedelta(days=DAILY_LOG_ARCHIVE_DAYS)
    archived: list[str] = []
    archive_dir.mkdir(parents=True, exist_ok=True)

    for f in sorted(memory_dir.iterdir()):
        if f.is_dir():
            continue
        m = DAILY_FILE.match(f.name)
        if not m:
            continue
        file_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if file_date < cutoff:
            if force:
                shutil.move(str(f), str(archive_dir / f.name))
            archived.append(f.name)
    return archived


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workspace", help="Workspace root (default: auto-detect)")
    ap.add_argument("--force", action="store_true", help="Apply changes (default: dry run)")
    ap.add_argument("--dry-run", action="store_true", help="Explicit preview mode (default)")
    ap.add_argument("--notify", action="store_true", help="Send Telegram notification when done")
    args = ap.parse_args()

    dry_run = not args.force
    workspace = resolve_workspace(args.workspace)
    memory_file = workspace / "MEMORY.md"
    memory_dir = workspace / "memory"
    archive_dir = memory_dir / "archive"

    if not memory_file.exists():
        print(f"ERROR: {memory_file} not found", file=sys.stderr)
        return 1

    today = datetime.now().date()
    text = memory_file.read_text(encoding="utf-8")
    preamble, sections = parse_sections(text)
    actions: list[str] = []
    new_sections: list[dict] = []

    for s in sections:
        header_name = s["header"].strip().split("[")[0].strip().lstrip("#").strip()
        p = s["priority"]

        if "Events Timeline" in s["header"]:
            new_body, compressed = compress_timeline(s, today)
            if compressed:
                actions.append(f"📦 Timeline compressed: {', '.join(compressed)}")
                s = {**s, "body": new_body}
            new_sections.append(s)
        elif p == "P0":
            new_sections.append(s)
        elif p == "P1" and s["date"]:
            age = (today - s["date"]).days
            if age > P1_COMPRESS_DAYS:
                actions.append(f"⏳ P1 flagged for review: {header_name} ({age}d)")
            new_sections.append(s)
        elif p == "P2" and s["date"]:
            age = (today - s["date"]).days
            if age > P2_COMPRESS_DAYS:
                new_body, was_compressed = compress_p2_section(s)
                if was_compressed:
                    actions.append(f"🗜️ P2 compressed: {header_name} ({age}d)")
                    s = {**s, "body": new_body}
            new_sections.append(s)
        else:
            new_sections.append(s)

    if memory_dir.exists():
        archived_logs = archive_old_daily_logs(memory_dir, archive_dir, today, force=args.force)
        if archived_logs:
            actions.append(f"📁 Archive: {len(archived_logs)} daily file(s) >{DAILY_LOG_ARCHIVE_DAYS}d")
    else:
        archived_logs = []

    print(f"📊 memory-compress scan ({today})")
    print(f"   Workspace: {workspace}")
    print(f"   Sections:  {len(sections)}")
    print()
    for s in new_sections:
        name = s["header"].strip().split("[")[0].strip().lstrip("#").strip()
        tag = s["priority"] or "no-tag"
        if s["priority"] and s["date"]:
            age = (today - s["date"]).days
            print(f"   [{tag}] {name} ({age}d)")
        else:
            print(f"   [{tag}] {name}")

    print()
    if actions:
        print("📋 Actions:")
        for a in actions:
            print(f"   {a}")
    else:
        print("✨ Nothing to process")

    if dry_run:
        print("\n🔍 DRY RUN — pass --force to apply")
    else:
        new_content = "".join(preamble)
        for s in new_sections:
            new_content += s["header"]
            new_content += "".join(s["body"])
        if new_content != text:
            memory_file.write_text(new_content, encoding="utf-8")
            saved = len(text) - len(new_content)
            print(f"\n✅ MEMORY.md updated ({len(text)} → {len(new_content)} bytes, saved {saved})")
        else:
            print("\n✅ MEMORY.md unchanged")
        if archived_logs:
            print(f"✅ Archived {len(archived_logs)} daily file(s) to {archive_dir}")

    if args.notify:
        print("\n📱 Sending Telegram notification...")
        if send_telegram_notification(build_notification_message(actions, dry_run)):
            print("✅ Sent")
        else:
            print("⚠️  Notification failed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
