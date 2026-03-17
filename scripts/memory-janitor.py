#!/usr/bin/env python3
"""Memory Janitor v2 - 壓縮式記憶管理。

不再刪除過期條目，改為壓縮：
- Events Timeline: 舊月份（>90天）折疊成一行摘要
- P1 技術區塊: >90天穩定運行的，細節移到 reference/，索引保留
- P2 實驗區塊: >30天壓縮成結論行，刪掉過程
- P0 / Cases / Patterns: 永久保留，不動

同時清理 memory/*.md 原始日誌：>90天歸檔到 memory/archive/

用法：
  python3 memory-janitor.py              # 掃描 + 報告（不修改）
  python3 memory-janitor.py --force      # 執行壓縮 + 歸檔日誌
  python3 memory-janitor.py --dry-run    # 同預設，明確預覽
  python3 memory-janitor.py --notify     # 預覽 + 發 Telegram 通知
  python3 memory-janitor.py --force --notify  # 執行 + 發通知
"""

import json
import re
import sys
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path("/root/clawd")
MEMORY_FILE = WORKSPACE / "MEMORY.md"
MEMORY_DIR = WORKSPACE / "memory"
ARCHIVE_DIR = MEMORY_DIR / "archive"
REFERENCE_DIR = WORKSPACE / "reference"
OPENCLAW_CONFIG = Path("/root/.openclaw/openclaw.json")

# Thresholds
TIMELINE_COMPRESS_DAYS = 90   # 舊月份折疊
P1_COMPRESS_DAYS = 90         # P1 細節移到 reference
P2_COMPRESS_DAYS = 30         # P2 壓縮成結論
DAILY_LOG_ARCHIVE_DAYS = 90   # 原始日誌歸檔

# Telegram config
TELEGRAM_CHAT_ID = "925735798"


def get_telegram_token():
    """Read Telegram bot token from openclaw config."""
    if not OPENCLAW_CONFIG.exists():
        return None
    try:
        config = json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
        return config.get("channels", {}).get("telegram", {}).get("botToken")
    except Exception:
        return None


def send_telegram_notification(actions, section_count, dry_run=True):
    """Send Telegram notification with summary."""
    token = get_telegram_token()
    if not token:
        print("⚠️ 無法讀取 Telegram bot token")
        return False

    # Count action types
    timeline_compress = [a for a in actions if "Timeline 壓縮" in a]
    p2_compress = [a for a in actions if "P2 壓縮" in a]
    p1_pending = [a for a in actions if "P1 過期待審" in a]
    archive_logs = [a for a in actions if "日誌歸檔" in a]

    # Build message
    mode = "🔍 預覽" if dry_run else "⚡ 執行"
    msg_lines = [f"📊 Memory Janitor {mode}", ""]

    if not actions:
        msg_lines.append("✨ 沒有需要處理的項目")
    else:
        msg_lines.append(f"📋 共 {len(actions)} 個待處理項目：")
        if timeline_compress:
            msg_lines.append(f"  • 📦 Timeline 待壓縮: {len(timeline_compress)} 個月")
        if p2_compress:
            msg_lines.append(f"  • 🗜️ P2 待壓縮: {len(p2_compress)} 個區塊")
        if p1_pending:
            msg_lines.append(f"  • ⏳ P1 過期待審: {len(p1_pending)} 個區塊")
        if archive_logs:
            for a in archive_logs:
                msg_lines.append(f"  • 📁 {a}")

    msg_lines.append("")
    if dry_run:
        msg_lines.append("💡 執行 --force 套用變更")
    else:
        msg_lines.append("✅ 已執行變更")

    message = "\n".join(msg_lines)

    # Send via curl
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    cmd = [
        "curl", "-s", "-X", "POST", url,
        "-H", "Content-Type: application/json",
        "-d", json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        })
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception as e:
        print(f"⚠️ Telegram 通知失敗: {e}")
        return False

# Match ## headers with [P0/P1/P2] and optional [date]
SECTION_TAG = re.compile(r"\[(P[012])\](?:\s+\[(\d{4}-\d{2}-\d{2})\])?")
# Match ### YYYY-MM month headers in Events Timeline
MONTH_HEADER = re.compile(r"^### (\d{4})-(\d{2})\s*$")
# Match timeline entries like "- **02-22** description"
TIMELINE_ENTRY = re.compile(r"^- \*\*(\d{2})-(\d{2})\*\*\s+(.+)$")
# Match daily memory files
DAILY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-.+)?\.md$")


def parse_sections(text: str):
    """Parse MEMORY.md into sections."""
    lines = text.splitlines(keepends=True)
    sections = []
    preamble = []
    current_header = None
    current_body = []
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
                    if m.group(2)
                    else None
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


def compress_timeline(section, today):
    """Compress old months in Events Timeline into summary lines."""
    cutoff = today - timedelta(days=TIMELINE_COMPRESS_DAYS)
    new_body = []
    current_month_year = None
    current_month_entries = []
    compressed_months = []

    def flush_month():
        nonlocal current_month_year, current_month_entries
        if not current_month_year:
            return
        year, month = current_month_year
        month_date = datetime(year, month, 1).date()
        if month_date < cutoff.replace(day=1) and len(current_month_entries) > 3:
            # Compress: keep first and last entry, summarize count
            summaries = [e[1] for e in current_month_entries]
            # Take up to 5 key items
            key_items = summaries[:5]
            summary_text = "、".join(key_items)
            if len(summaries) > 5:
                summary_text += f" 等共 {len(summaries)} 項"
            new_body.append(f"### {year}-{month:02d}\n")
            new_body.append(f"- **{month:02d}月摘要** {summary_text}\n")
            new_body.append("\n")
            compressed_months.append(f"{year}-{month:02d} ({len(current_month_entries)} → 1)")
        else:
            # Keep as-is
            new_body.append(f"### {year}-{month:02d}\n")
            for raw_line in current_month_entries:
                new_body.append(raw_line[2])  # original line
            # Keep trailing newline if any
            if current_month_entries:
                new_body.append("\n") if not current_month_entries[-1][2].endswith("\n\n") else None
        current_month_year = None
        current_month_entries = []

    for line in section["body"]:
        stripped = line.rstrip("\n")
        month_match = MONTH_HEADER.match(stripped)
        if month_match:
            flush_month()
            current_month_year = (int(month_match.group(1)), int(month_match.group(2)))
            continue

        entry_match = TIMELINE_ENTRY.match(stripped)
        if entry_match and current_month_year:
            current_month_entries.append((
                entry_match.group(1),  # day (MM)
                entry_match.group(3),  # description
                line,                  # original line
            ))
            continue

        if current_month_year is None:
            new_body.append(line)
        else:
            # Non-entry line inside a month (comments, blank lines)
            if stripped and not stripped.startswith("<!--"):
                current_month_entries.append(("", stripped, line))
            elif stripped.startswith("<!--"):
                new_body.append(line)

    flush_month()

    return new_body, compressed_months


def compress_p2_section(section):
    """Compress P2 section: keep only header + first 3 lines as conclusion."""
    body = section["body"]
    # Count non-blank content lines
    content_lines = [l for l in body if l.strip() and not l.strip().startswith("<!--")]
    if len(content_lines) <= 3:
        return body, False  # Already compact

    # Keep comment line + up to 3 content lines
    new_body = []
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
            new_body.append(f"- *(已壓縮 {len(content_lines) - 3} 行細節)*\n")
            break

    new_body.append("\n")
    return new_body, True


def archive_old_daily_logs(today, force=False):
    """Move daily memory logs older than threshold to archive/."""
    cutoff = today - timedelta(days=DAILY_LOG_ARCHIVE_DAYS)
    archived = []

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    for f in sorted(MEMORY_DIR.iterdir()):
        if f.is_dir():
            continue
        m = DAILY_FILE.match(f.name)
        if not m:
            continue
        file_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if file_date < cutoff:
            if force:
                dest = ARCHIVE_DIR / f.name
                shutil.move(str(f), str(dest))
            archived.append(f.name)

    return archived


def main():
    dry_run = "--dry-run" in sys.argv or "--force" not in sys.argv
    force = "--force" in sys.argv
    notify = "--notify" in sys.argv
    today = datetime.now().date()

    if not MEMORY_FILE.exists():
        print("ERROR: MEMORY.md not found")
        sys.exit(1)

    text = MEMORY_FILE.read_text(encoding="utf-8")
    preamble, sections = parse_sections(text)

    actions = []

    # Process each section
    new_sections = []
    for s in sections:
        header_name = s["header"].strip().split("[")[0].strip().lstrip("#").strip()
        p = s["priority"]

        # Events Timeline: compress old months
        if "Events Timeline" in s["header"]:
            new_body, compressed = compress_timeline(s, today)
            if compressed:
                actions.append(f"📦 Timeline 壓縮: {', '.join(compressed)}")
                s = {**s, "body": new_body}
            new_sections.append(s)

        # P0 / Cases / Patterns: never touch
        elif p == "P0":
            new_sections.append(s)

        # P1 with date: check if > 90 days
        elif p == "P1" and s["date"]:
            age = (today - s["date"]).days
            if age > P1_COMPRESS_DAYS:
                # Flag for manual review (don't auto-compress P1, needs judgment)
                actions.append(f"⏳ P1 過期待審: {header_name} ({age}天)")
            new_sections.append(s)

        # P2 with date: compress if > 30 days
        elif p == "P2" and s["date"]:
            age = (today - s["date"]).days
            if age > P2_COMPRESS_DAYS:
                new_body, was_compressed = compress_p2_section(s)
                if was_compressed:
                    actions.append(f"🗜️ P2 壓縮: {header_name} ({age}天)")
                    s = {**s, "body": new_body}
            new_sections.append(s)

        else:
            new_sections.append(s)

    # Archive old daily logs
    archived_logs = archive_old_daily_logs(today, force=force)
    if archived_logs:
        actions.append(f"📁 日誌歸檔: {len(archived_logs)} 個檔案 (>{DAILY_LOG_ARCHIVE_DAYS}天)")

    # Report
    print(f"📊 Memory Janitor v2 掃描結果 ({today})")
    print(f"   MEMORY.md 章節: {len(sections)}")
    print()

    for s in new_sections:
        name = s["header"].strip().split("[")[0].strip().lstrip("#").strip()
        tag = s["priority"] or "無標籤"
        date_str = str(s["date"]) if s["date"] else "-"
        if s["priority"] and s["date"]:
            age = (today - s["date"]).days
            print(f"   [{tag}] {name} ({age}天)")
        else:
            print(f"   [{tag}] {name}")

    print()
    if actions:
        print("📋 待執行動作:")
        for a in actions:
            print(f"   {a}")
    else:
        print("✨ 沒有需要處理的項目")

    if dry_run:
        print(f"\n🔍 {'DRY RUN' if '--dry-run' in sys.argv else '預覽模式'} — 加 --force 執行")

        if notify:
            print("\n📱 發送 Telegram 通知...")
            if send_telegram_notification(actions, len(sections), dry_run=True):
                print("✅ 已發送通知")
            else:
                print("⚠️ 通知發送失敗")
        return

    # Write updated MEMORY.md
    new_content = "".join(preamble)
    for s in new_sections:
        new_content += s["header"]
        new_content += "".join(s["body"])

    if new_content != text:
        MEMORY_FILE.write_text(new_content, encoding="utf-8")
        saved = len(text) - len(new_content)
        print(f"\n✅ MEMORY.md 已更新 ({len(text)} → {len(new_content)} bytes, 節省 {saved})")
    else:
        print("\n✅ MEMORY.md 無變更")

    if archived_logs:
        print(f"✅ 已歸檔 {len(archived_logs)} 個日誌到 memory/archive/")

    if notify:
        print("\n📱 發送 Telegram 通知...")
        if send_telegram_notification(actions, len(sections), dry_run=False):
            print("✅ 已發送通知")
        else:
            print("⚠️ 通知發送失敗")


if __name__ == "__main__":
    main()
