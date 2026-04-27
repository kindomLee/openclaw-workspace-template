#!/usr/bin/env python3
"""
memory-search-hybrid.py — Hybrid search scoring for memory/*.md files
Applies: keyword overlap boost + temporal boost + hall type boost
Usage: python3 memory-search-hybrid.py "query" [--days N] [--json] [--top N]
"""
import argparse, re, os, json
from pathlib import Path
from datetime import datetime

STOPWORDS = frozenset(
    "的了是在和有你他她它這那也就都不會能要以被從到或與等著過把讓向對為就還可但而如則"
    "如果因為所以但是而且或者以及"
)

def extract_keywords(text: str) -> set:
    # Lowercase on extraction so a "PostgreSQL" mention in content matches
    # a "postgresql" query. Chinese is already case-insensitive.
    words = re.findall(r'[\w\u4e00-\u9fff—、。（）【】]{2,}', text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}

def temporal_boost(mtime: float, cutoff: float, now: float, days: int) -> float:
    """Closer files get up to 40% boost; expired files get 30% penalty."""
    age = (now - mtime) / 86400
    if age > days:
        return 0.3
    recency = max(0.0, 1.0 - age / days)
    return 1.0 + 0.4 * recency

def hall_boost(text: str) -> float:
    t = text.lower()
    if re.search(r'決定|决策|選擇|選用|採用|decided|chose|selected|adopted|locked', t):
        return 1.3
    if re.search(r'發現|研究|評估|分析|實驗|discover|found|research|analyze', t):
        return 1.15
    if re.search(r'偏好|喜歡|想要|習慣|prefer|like|want|habit', t):
        return 1.1
    if re.search(r'建議|推薦|應該|最好|recommend|suggest|should|advice', t):
        return 1.1
    return 1.0

def date_from_filename(fp: Path) -> float:
    """Extract YYYY-MM-DD from filename and return as timestamp.
    Falls back to mtime if no date pattern found."""
    m = re.search(r'(\d{4}-\d{2}-\d{2})', fp.name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").timestamp()
        except ValueError:
            pass
    # Check parent dir name (e.g. archive-2026-03/)
    m = re.search(r'(\d{4}-\d{2})', fp.parent.name)
    if m:
        try:
            return datetime.strptime(m.group(1) + "-15", "%Y-%m-%d").timestamp()
        except ValueError:
            pass
    return os.path.getmtime(fp)

def snippet(content: str, keywords: set, radius: int = 40) -> tuple[str, int, int]:
    """Return (text, hit_offset, hit_line).

    hit_offset = char offset in full file where this snippet starts
                 (-1 if no keyword hit, snippet is just file head)
    hit_line   = 1-indexed line number of the first hit (0 if none)

    Caller can use these for continuation: `Read <path> --offset <hit_line>`
    or sed-like slicing.
    """
    for kw in sorted(keywords, key=len, reverse=True)[:3]:
        idx = content.lower().find(kw.lower())
        if idx >= 0:
            start = max(0, idx - radius)
            end = min(len(content), idx + radius + 40)
            line_no = content.count('\n', 0, idx) + 1
            return content[start:end].strip().replace('\n', ' '), start, line_no
    return content[:150].strip().replace('\n', ' '), -1, 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--preview-chars", type=int, default=200,
                    help="Cap each snippet to N chars (default 200). 仿 OpenClaw 4.15 bounded excerpts pattern。")
    args = ap.parse_args()

    query = args.query
    if not query:
        print("Usage: memory-search-hybrid.py 'query' [--days N] [--json] [--top N]", file=__import__('sys').stderr)
        exit(1)

    query_kw = extract_keywords(query)
    now = datetime.now().timestamp()
    cutoff = now - args.days * 86400

    # Portable: derive project root from script location (scripts/ → project root)
    project_root = Path(__file__).resolve().parent.parent
    memory_dir = project_root / "memory"
    notes_dir = project_root / "notes"

    results = []
    for base_dir in [memory_dir, notes_dir]:
        if not base_dir.exists():
            continue
        for fp in base_dir.rglob("*.md"):
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if len(content) < 20:
                    continue
                mtime = date_from_filename(fp)
                kw = extract_keywords(content)
                kw_overlap = len(query_kw & kw) / len(query_kw) if query_kw else 0.0
                t_boost = temporal_boost(mtime, cutoff, now, args.days)
                h_boost = hall_boost(content)
                # sqrt scaling：caps 在 5KB 附近但不讓 50KB topic note 壓過
                # 2KB 聚焦 journal entry（linear 版對長檔太寬容）。
                size_factor = min(1.0, (len(content) / 5000) ** 0.5)
                base = size_factor * (0.3 if kw_overlap > 0 else 0.05)
                fused = base * (1 + 0.3 * kw_overlap) * t_boost * h_boost
                snip_text, snip_start, snip_line = snippet(content, query_kw)
                full_lines = content.count('\n') + 1
                bounded_snip = snip_text[:args.preview_chars]
                # 4.15 continuation metadata: 讓 caller 知道是否有 cap，去哪 Read
                more_lines = max(0, full_lines - snip_line) if snip_line else full_lines
                truncated = len(snip_text) > args.preview_chars
                results.append({
                    "file": str(fp.relative_to(base_dir)),
                    "path": str(fp),
                    "score": round(fused, 4),
                    "kw_overlap": round(kw_overlap, 3),
                    "temporal": round(t_boost, 3),
                    "hall_boost": round(h_boost, 1),
                    "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
                    "age_days": round((now - mtime) / 86400, 1),
                    "snippet": bounded_snip,
                    "snippet_truncated": truncated,
                    "hit_line": snip_line,
                    "more_lines": more_lines,
                    "full_lines": full_lines,
                })
            except Exception:
                continue

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:args.top]

    if args.json:
        print(json.dumps({"query": query, "results": top}, ensure_ascii=False, indent=2))
    else:
        print(f"🔍 Query: {query}")
        print(f"📂 Days back: {args.days} | Top: {args.top} | Keywords: {', '.join(sorted(query_kw))}")
        print()
        for i, r in enumerate(top, 1):
            print(f"[{i}] {r['file']}  score={r['score']}  kw={r['kw_overlap']}  temp={r['temporal']}  "
                  f"{r['date']} ({r['age_days']}d ago)")
            print(f"    {r['snippet'][:120]}")
            # 4.15 continuation hint：printable form
            if r.get("snippet_truncated") or r.get("more_lines", 0) > 5:
                hint = f"    … (line {r.get('hit_line', '?')} of {r.get('full_lines', '?')}; {r.get('more_lines', 0)} lines after hit)"
                print(f"{hint}; full: Read {r['path']}")
            print()

if __name__ == "__main__":
    main()
