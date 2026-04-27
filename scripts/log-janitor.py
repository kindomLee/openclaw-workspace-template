#!/usr/bin/env python3
"""log-janitor — 把舊 cron / patrol log 摘要成 archive，原檔刪。

仿 OpenClaw 2026.4.22 Tokenjuice pattern：壓縮 noisy exec/bash 輸出。
不靠 LLM，純規則：保留 ALERT/ERROR/WARN 行 + 統計，丟 INFO 細節。

預設掃以下路徑（可用 --root 覆寫，多個用逗號）：
- {project_root}/cron/logs/*.log
- /Users/cfh00929692/projects/polymarket-bot/logs/cron-*.log
- /Users/cfh00929692/projects/polymarket-bot/logs/patrol-*.log

Usage:
    python3 scripts/log-janitor.py                      # 預設 dry-run
    python3 scripts/log-janitor.py --apply              # 實際處理
    python3 scripts/log-janitor.py --age-days 30        # 30 天以上才壓
    python3 scripts/log-janitor.py --root /path/a,/path/b

設計哲學：保前後各 N 行（時間錨點 + 結尾狀態）+ keep-pattern 行（alert/error/warn）。
這樣即使中段被壓掉，仍能看到「第一次跑何時、最後一次跑何時、跑完是哪種狀態」，
保留 forensic 基本訊號。預設 90 天才動以求保守。
"""
import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 預設只看本 repo 的 cron/logs/。其他來源用 --root 加（多個逗號分隔）。
DEFAULT_ROOTS = [
    PROJECT_ROOT / "cron" / "logs",
]

# 壓縮後保留：包含這些字眼的行（不分大小寫 substring 匹配）
KEEP_PATTERNS = [
    r"\bERROR\b", r"\bFAIL\b", r"\bFAILED\b", r"\bFATAL\b",
    r"\bWARN(ING)?\b", r"\bALERT\b", r"\bCRIT", r"\bEXCEPTION\b",
    r"❌", r"⚠️", r"🛑", r"🔴",
    r"Traceback", r"AssertionError", r"timeout",
    r"interrupted", r"missed", r"blocked",
]
KEEP_RE = re.compile("|".join(KEEP_PATTERNS), re.IGNORECASE)

# 統計用的「正常 run」signature（同 pattern 計數而非保留）
NORMAL_PATTERNS = [
    r"OK\b", r"completed", r"=== .* 開始 ===", r"=== .* 完成 ===",
    r"No signals, skipping", r"\bok\b",
]
NORMAL_RE = re.compile("|".join(NORMAL_PATTERNS), re.IGNORECASE)


def parse_date_from_name(p: Path) -> datetime | None:
    """logs 通常 cron-YYYYMMDD.log 或 patrol-YYYYMMDD.log；解析失敗用 mtime。"""
    m = re.search(r"(\d{4})(\d{2})(\d{2})", p.name)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(p.stat().st_mtime)
    except OSError:
        return None


def compress(content: str, edge_lines: int = 10) -> tuple[str, dict]:
    """回傳 (summary_text, stats)。summary 保前/後各 edge_lines 行 + keep-pattern 行 + 統計。

    保前後各 N 行的目的：給 forensic 一個 time anchor —— 即使中段被壓，
    至少能看到 first run 何時、last run 何時、跑完狀態，避免 silent-fail
    類問題（連續 0 信號）失去診斷材料。
    """
    lines = content.splitlines()
    n = len(lines)
    keep_lines: list[tuple[int, str]] = []      # (line_idx, content)
    normal_count = 0
    other_count = 0
    keep_buckets: dict[str, int] = {}

    # 邊界保留（前 N + 後 N），用 set of indices 去重
    edge_idx: set[int] = set(range(min(edge_lines, n))) | set(range(max(0, n - edge_lines), n))

    for i, line in enumerate(lines):
        is_edge = i in edge_idx
        is_keep = bool(KEEP_RE.search(line))
        if is_edge or is_keep:
            keep_lines.append((i, line))
            if is_keep:
                mm = KEEP_RE.search(line)
                if mm:
                    key = mm.group(0).lower()
                    keep_buckets[key] = keep_buckets.get(key, 0) + 1
        elif NORMAL_RE.search(line):
            normal_count += 1
        else:
            other_count += 1

    stats = {
        "total_lines": n,
        "kept": len(keep_lines),
        "kept_alerts": sum(keep_buckets.values()),
        "kept_edges": len(edge_idx & {idx for idx, _ in keep_lines}),
        "normal": normal_count,
        "other": other_count,
        "buckets": keep_buckets,
    }

    parts = [
        "# Log Summary (compressed by log-janitor)",
        "",
        f"- total lines: {n}",
        f"- kept: {len(keep_lines)} ({stats['kept_alerts']} alerts/errors + {stats['kept_edges']} edge-anchor)",
        f"- normal completions: {normal_count}",
        f"- other (compressed away): {other_count}",
    ]
    if keep_buckets:
        parts.append("")
        parts.append("## Pattern counts")
        for k, v in sorted(keep_buckets.items(), key=lambda x: -x[1]):
            parts.append(f"- `{k}`: {v}")
    if keep_lines:
        parts.append("")
        parts.append("## Kept lines (with original line numbers, gaps = compressed away)")
        parts.append("```")
        # 限 400 行避免 summary 也爆（前 200 + 後 200，按原索引排序）
        keep_lines.sort(key=lambda x: x[0])
        if len(keep_lines) > 400:
            head = keep_lines[:200]
            tail = keep_lines[-200:]
            for idx, l in head:
                parts.append(f"L{idx + 1}: {l}")
            parts.append(f"... ({len(keep_lines) - 400} kept lines truncated in summary) ...")
            for idx, l in tail:
                parts.append(f"L{idx + 1}: {l}")
        else:
            for idx, l in keep_lines:
                parts.append(f"L{idx + 1}: {l}")
        parts.append("```")
    return "\n".join(parts), stats


def discover_logs(roots: list[Path]) -> list[Path]:
    out = []
    for r in roots:
        if not r.exists():
            continue
        for p in r.glob("*.log"):
            if p.name.endswith(".summary.md"):
                continue
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="實際處理（不加就只 dry-run）")
    ap.add_argument("--age-days", type=int, default=90, help="幾天以上的 log 才壓（預設 90）")
    ap.add_argument("--root", default="", help="覆寫 root 路徑（逗號分隔）")
    ap.add_argument("--min-size-kb", type=int, default=10,
                    help="檔案小於 N KB 不處理（預設 10）")
    ap.add_argument("--edge-lines", type=int, default=10,
                    help="無論如何保前 N + 後 N 行作 forensic 時間錨（預設 10）")
    args = ap.parse_args()

    if args.root:
        roots = [Path(r.strip()) for r in args.root.split(",") if r.strip()]
    else:
        roots = DEFAULT_ROOTS

    cutoff = datetime.now() - timedelta(days=args.age_days)
    logs = discover_logs(roots)

    actions = []
    for p in logs:
        d = parse_date_from_name(p)
        if d is None or d > cutoff:
            continue
        try:
            size_kb = p.stat().st_size / 1024
        except OSError:
            continue
        if size_kb < args.min_size_kb:
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        summary, stats = compress(content, edge_lines=args.edge_lines)

        # 寫到同目錄下 archive/YYYY-MM/<原名>.summary.md
        archive_dir = p.parent / "archive" / d.strftime("%Y-%m")
        archive_path = archive_dir / (p.name + ".summary.md")
        actions.append({
            "src": p,
            "dst": archive_path,
            "size_kb_before": round(size_kb, 1),
            "size_kb_after": round(len(summary.encode("utf-8")) / 1024, 1),
            "stats": stats,
        })

    if not actions:
        print("✅ No logs eligible for compression.")
        return

    saved_kb = 0.0
    print(f"{'[apply]' if args.apply else '[dry-run]'} {len(actions)} logs eligible:")
    for a in actions:
        delta = a["size_kb_before"] - a["size_kb_after"]
        saved_kb += delta
        print(f"  {a['src']}  {a['size_kb_before']} KB → {a['size_kb_after']} KB "
              f"(saved {delta:.1f} KB; kept {a['stats']['kept']}/{a['stats']['total_lines']})")
        if args.apply:
            a["dst"].parent.mkdir(parents=True, exist_ok=True)
            a["dst"].write_text(_render(a, edge_lines=args.edge_lines), encoding="utf-8")
            a["src"].unlink()

    print()
    print(f"Total savings: {saved_kb:.1f} KB across {len(actions)} files")
    if not args.apply:
        print("(dry-run — pass --apply to actually process)")


def _render(a: dict, edge_lines: int = 10) -> str:
    """Render summary file with src filename + stats header."""
    if not a["src"].exists():
        return f"# missing source for {a['src'].name}\n"
    summary, _stats = compress(
        a["src"].read_text(encoding="utf-8", errors="ignore"),
        edge_lines=edge_lines,
    )
    return f"<!-- compressed-from: {a['src']} on {datetime.now().isoformat()} -->\n\n{summary}\n"


if __name__ == "__main__":
    sys.exit(main() or 0)
