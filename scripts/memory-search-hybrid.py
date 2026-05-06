#!/usr/bin/env python3
"""
memory-search-hybrid.py — Hybrid search scoring for memory/*.md files
Default mode: BM25(jieba 分詞) + temporal boost + hall type boost
Fallback mode: keyword-overlap (when jieba/rank_bm25 unavailable or --no-bm25)

Usage: python3 memory-search-hybrid.py "query" [--days N] [--json] [--top N] [--no-bm25]
"""
import argparse, re, os, json, sys
from pathlib import Path
from datetime import datetime

try:
    import jieba
    jieba.setLogLevel(60)  # 抑制 "Building prefix dict" 訊息到 stderr
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False

STOPWORDS = frozenset(
    "的了是在和有你他她它這那也就都不會能要以被從到或與等著過把讓向對為就還可但而如則"
    "如果因為所以但是而且或者以及"
)

_TOKEN_FILTER_RE = re.compile(r'[\w一-鿿]')


def tokenize_bm25(text: str) -> list:
    """jieba search 模式分詞，過濾停用詞/長度/純標點。對中英混合都適用。"""
    text = text.lower()
    out = []
    for t in jieba.cut_for_search(text):
        t = t.strip()
        if not t or len(t) < 2 or t in STOPWORDS:
            continue
        if not _TOKEN_FILTER_RE.search(t):
            continue
        out.append(t)
    return out


def extract_keywords(text: str) -> set:
    # Lowercase on extraction so a "PostgreSQL" mention in content matches
    # a "postgresql" query. Chinese is already case-insensitive.
    # Used by snippet() for hit-finding and by --no-bm25 fallback path.
    words = re.findall(r'[\w一-鿿—、。（）【】]{2,}', text.lower())
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
    m = re.search(r'(\d{4}-\d{2})', fp.parent.name)
    if m:
        try:
            return datetime.strptime(m.group(1) + "-15", "%Y-%m-%d").timestamp()
        except ValueError:
            pass
    return os.path.getmtime(fp)


def snippet(content: str, keywords: set, radius: int = 40) -> tuple:
    """Return (text, hit_offset, hit_line)."""
    for kw in sorted(keywords, key=len, reverse=True)[:3]:
        idx = content.lower().find(kw.lower())
        if idx >= 0:
            start = max(0, idx - radius)
            end = min(len(content), idx + radius + 40)
            line_no = content.count('\n', 0, idx) + 1
            return content[start:end].strip().replace('\n', ' '), start, line_no
    return content[:150].strip().replace('\n', ' '), -1, 0


def collect_files(memory_dir: Path, notes_dir: Path):
    """Walk memory/ + notes/, return list of (fp, base_dir, content, mtime)."""
    docs = []
    for base_dir in [memory_dir, notes_dir]:
        if not base_dir.exists():
            continue
        for fp in base_dir.rglob("*.md"):
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if len(content) < 20:
                    continue
                mtime = date_from_filename(fp)
                docs.append((fp, base_dir, content, mtime))
            except Exception:
                continue
    return docs


def score_bm25(docs, query: str):
    """Return list of bm25 raw scores, aligned with docs。"""
    corpus_tokens = [tokenize_bm25(content) for _, _, content, _ in docs]
    # rank_bm25 對空 doc 會炸；過濾後重新對齊。
    valid_idx = [i for i, toks in enumerate(corpus_tokens) if toks]
    if not valid_idx:
        return [0.0] * len(docs)
    valid_corpus = [corpus_tokens[i] for i in valid_idx]
    bm25 = BM25Okapi(valid_corpus)
    qtok = tokenize_bm25(query)
    if not qtok:
        return [0.0] * len(docs)
    valid_scores = bm25.get_scores(qtok)
    scores = [0.0] * len(docs)
    for j, i in enumerate(valid_idx):
        scores[i] = float(valid_scores[j])
    return scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--preview-chars", type=int, default=200,
                    help="Cap each snippet to N chars (default 200). 仿 OpenClaw 4.15 bounded excerpts。")
    ap.add_argument("--no-bm25", action="store_true",
                    help="Force legacy keyword-overlap mode (skip BM25 even if available).")
    args = ap.parse_args()

    query = args.query
    if not query:
        print("Usage: memory-search-hybrid.py 'query' [--days N] [--json] [--top N] [--no-bm25]",
              file=sys.stderr)
        sys.exit(1)

    use_bm25 = HAS_BM25 and not args.no_bm25
    query_kw = extract_keywords(query)
    now = datetime.now().timestamp()
    cutoff = now - args.days * 86400

    project_root = Path(__file__).resolve().parent.parent
    memory_dir = project_root / "memory"
    notes_dir = project_root / "notes"

    docs = collect_files(memory_dir, notes_dir)

    bm25_raw = score_bm25(docs, query) if use_bm25 else [0.0] * len(docs)
    bm25_max = max(bm25_raw) if bm25_raw else 0.0

    results = []
    for i, (fp, base_dir, content, mtime) in enumerate(docs):
        kw = extract_keywords(content)
        kw_overlap = len(query_kw & kw) / len(query_kw) if query_kw else 0.0
        t_boost = temporal_boost(mtime, cutoff, now, args.days)
        h_boost = hall_boost(content)

        if use_bm25 and bm25_max > 0:
            # BM25 主排序：normalize 到 [0,1]，再乘 temporal/hall。
            # 沒命中 (bm25_raw=0) 的文件給極小 baseline，避免完全消失。
            bm25_norm = bm25_raw[i] / bm25_max
            base = bm25_norm if bm25_norm > 0 else 0.02
            fused = base * t_boost * h_boost
        else:
            # Legacy fallback：keyword-overlap + size scaling。
            size_factor = min(1.0, (len(content) / 5000) ** 0.5)
            base = size_factor * (0.3 if kw_overlap > 0 else 0.05)
            fused = base * (1 + 0.3 * kw_overlap) * t_boost * h_boost

        snip_text, snip_start, snip_line = snippet(content, query_kw)
        full_lines = content.count('\n') + 1
        bounded_snip = snip_text[:args.preview_chars]
        more_lines = max(0, full_lines - snip_line) if snip_line else full_lines
        truncated = len(snip_text) > args.preview_chars

        results.append({
            "file": str(fp.relative_to(base_dir)),
            "path": str(fp),
            "score": round(fused, 4),
            "bm25_raw": round(bm25_raw[i], 3) if use_bm25 else None,
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

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:args.top]

    if args.json:
        print(json.dumps(
            {"query": query, "mode": "bm25" if use_bm25 else "legacy", "results": top},
            ensure_ascii=False, indent=2,
        ))
    else:
        mode_tag = "BM25+jieba" if use_bm25 else "legacy keyword"
        print(f"🔍 Query: {query}  [mode={mode_tag}]")
        print(f"📂 Days back: {args.days} | Top: {args.top} | Keywords: {', '.join(sorted(query_kw))}")
        print()
        for i, r in enumerate(top, 1):
            extra = f" bm25={r['bm25_raw']}" if r.get("bm25_raw") is not None else ""
            print(f"[{i}] {r['file']}  score={r['score']}{extra}  kw={r['kw_overlap']}  temp={r['temporal']}  "
                  f"{r['date']} ({r['age_days']}d ago)")
            print(f"    {r['snippet'][:120]}")
            if r.get("snippet_truncated") or r.get("more_lines", 0) > 5:
                hint = f"    … (line {r.get('hit_line', '?')} of {r.get('full_lines', '?')}; {r.get('more_lines', 0)} lines after hit)"
                print(f"{hint}; full: Read {r['path']}")
            print()


if __name__ == "__main__":
    main()
