#!/usr/bin/env python3
"""learnings-archive — 把 LEARNINGS.md 裡不再需要常駐的條目移到 memory/archive/learnings-archive.md。

一律 dry-run，加 --apply 才搬移。挑選條件：
- 預設：status 為 resolved / superseded / wontfix 的條目（內容已升級或已作廢）
- --ids ID1,ID2：指定條目（覆審 session 決定後用）
- --ids stale：learnings-promotion-check 的 stale_low_signal 且 ID 日期超過 90 天的條目
- --restore ID1,ID2：反方向，把歸檔條目整條搬回 LEARNINGS.md（同主題再發生時用，之後再加 rc 與證據）

rc=1 舊條目不自動搬：退役判準是「是否仍承擔風險」不是 age（見 cron/bin/memory-retire-candidates.sh），
所以只由 weekly-review-digest 列成候選，人決定後才用 --ids。搬移可用 git 還原。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEARNINGS = REPO / "LEARNINGS.md"
ARCHIVE = REPO / "memory" / "archive" / "learnings-archive.md"

# 歸檔檔每條前面有一行 archived 戳記，算進該條目本身，搬回時一起拿掉
ENTRY_RE = re.compile(r"^(?:<!-- archived [\d-]+ -->\n)?## \[([A-Z_]+-(\d{8})-\d{3})\]", re.M)
STAMP_RE = re.compile(r"^<!-- archived [\d-]+ -->\n")
STATUS_RE = re.compile(r"^- \*\*status(?::\s*|\*\*:\s*)([a-z_]+)", re.M)
DONE = {"resolved", "superseded", "wontfix"}
STALE_DAYS = 90


def split(text: str) -> tuple[str, list[tuple[str, str]]]:
    """回傳 (檔頭, [(id, 條目全文)])；條目到下一個 `## [ID]` 為止。"""
    ms = list(ENTRY_RE.finditer(text))
    if not ms:
        return text, []
    head = text[: ms[0].start()]
    entries = [(m.group(1), text[m.start(): ms[i + 1].start() if i + 1 < len(ms) else len(text)])
               for i, m in enumerate(ms)]
    return head, entries


def status_of(body: str) -> str:
    m = STATUS_RE.search(body)
    return m.group(1) if m else ""


def stale_ids() -> set[str]:
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "learnings-promotion-check.py"), "--json"],
                         capture_output=True, text=True, check=True).stdout
    cutoff = (date.today() - timedelta(days=STALE_DAYS)).strftime("%Y%m%d")
    return {e["id"] for e in json.loads(out)["stale_low_signal"] if e["id"].split("-")[-2] < cutoff}


def restore(ids: set[str], apply: bool) -> int:
    if not ARCHIVE.exists():
        print("沒有歸檔檔")
        return 1
    head, entries = split(ARCHIVE.read_text(encoding="utf-8"))
    back = [(i, STAMP_RE.sub("", b).rstrip() + "\n\n") for i, b in entries if i in ids]
    print(f"找到 {len(back)} / {len(ids)} 條：{', '.join(i for i, _ in back) or '無'}")
    if not apply or not back:
        print("（dry-run；加 --apply 才搬回）")
        return 0 if back else 1
    learnings = LEARNINGS.read_text(encoding="utf-8").rstrip() + "\n\n"
    LEARNINGS.write_text(learnings + "".join(b for _, b in back), encoding="utf-8")
    ARCHIVE.write_text(head + "".join(b for i, b in entries if i not in ids), encoding="utf-8")
    print("已搬回 LEARNINGS.md 末尾；記得 recurring_count += 1 並追加 evidence")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真的搬移（否則只列出）")
    ap.add_argument("--ids", help="逗號分隔 ID，或 stale")
    ap.add_argument("--restore", help="逗號分隔 ID，從歸檔搬回 LEARNINGS.md")
    args = ap.parse_args()
    if args.restore:
        return restore({x.strip() for x in args.restore.split(",") if x.strip()}, args.apply)
    if not LEARNINGS.exists():
        print("沒有 LEARNINGS.md，略過")
        return 0

    head, entries = split(LEARNINGS.read_text(encoding="utf-8"))
    if args.ids == "stale":
        pick = stale_ids()
    elif args.ids:
        pick = {x.strip() for x in args.ids.split(",") if x.strip()}
    else:
        pick = {i for i, b in entries if status_of(b) in DONE}

    move = [(i, b) for i, b in entries if i in pick]
    for i, b in move:
        print(f"{i}  [{status_of(b) or '?'}]  {b.splitlines()[0][len(i) + 6:][:60]}")
    print(f"共 {len(move)} 條 / 全部 {len(entries)} 條")
    if not args.apply or not move:
        print("（dry-run；加 --apply 才搬移）")
        return 0

    keep = [b for i, b in entries if i not in pick]
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    if not ARCHIVE.exists():
        ARCHIVE.write_text("# LEARNINGS 歸檔\n\n> 由 scripts/learnings-archive.py 從 LEARNINGS.md 搬來；"
                           "要復活就整段搬回去。\n\n", encoding="utf-8")
    stamp = f"<!-- archived {date.today().isoformat()} -->\n"
    with ARCHIVE.open("a", encoding="utf-8") as fh:
        for _, b in move:
            fh.write(stamp + b.rstrip() + "\n\n")
    LEARNINGS.write_text(head + "".join(keep), encoding="utf-8")
    print(f"已搬到 {ARCHIVE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
