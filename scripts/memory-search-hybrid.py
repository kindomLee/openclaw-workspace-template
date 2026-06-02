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
    print("⚠️ jieba/rank_bm25 不可用，降級 legacy keyword 模式（召回品質會明顯變差，"
          "且偏袒大檔）。請對執行此 script 的 interpreter 裝 deps：pip install jieba rank_bm25",
          file=sys.stderr)

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


# frontmatter status：key 大小寫不敏感（YAML 慣例小寫，但容錯 Status:/STATUS:）。
_STATUS_RE = re.compile(r'^status:\s*(.+?)\s*$', re.M | re.I)
# digest/aggregate「滾動彙整」檔：什麼主題都提一句、字多 → BM25 docstring 點名的
# meta noise 來源。住 memory/ root 故 A 層目錄判斷碰不到，需 filename 顯式降權。
_AGGREGATE_STEMS = ('timeline-archive', 'reflections', 'dreams')
# 超長 digest 安全網門檻（char）：見 confidence_boost A'' 層註解的語料分布依據。
_OVERLONG_CHARS = 20000


def _frontmatter_status(content: str):
    """只從檔首 YAML frontmatter fence（首組 --- ... ---）取 status，回傳 lower 後的值或 None。

    刻意 NOT 掃全文：避免正文出現「status: stale」這類散句被誤判為低可信
    （adversarial review 2026-06-01 抓到的 false-match bug）。
    """
    if not content.startswith('---'):
        return None
    end = content.find('\n---', 3)
    if end == -1:
        return None
    m = _STATUS_RE.search(content[3:end])
    return m.group(1).strip().lower() if m else None


def confidence_boost(fp, content: str) -> float:
    """Deterministic 可信度乘數（Karry Orb 召回退化的對應補強，2026-05-31）。

    純函式：給定 (路徑, 內容) 必回同一分數。但「deterministic」≠「無人為輸入」——
    可信度反映的是「檔案被怎麼歸檔/標 status」這個*組織*訊號，不是內容*被驗證過*。
    歸檔位置與 frontmatter status 仍由 agent/人寫，會 drift；選它們而非內文標記
    （superseded/⚠️）是因為覆蓋廣（notes 432 檔有 frontmatter vs 41 檔有內文標記）
    且可被 lint 強制、結構上與正文分離（不會被散句誤觸）。

    A 層（目錄結構）：看目錄 component，timeline-archive.md 這種檔名含 archive 但
      住 root 的當前資料不被目錄判斷誤降。
    A' 層（aggregate filename）：滾動彙整檔（timeline-archive/reflections/dreams）
      顯式降權——它們正是 Karry bug 的「越常討論越易召回」噪音源，目錄判斷碰不到。
    B 層（frontmatter status）：僅從 frontmatter fence 取，stale/superseded 再懲罰。
    """
    parts = [s.lower() for s in Path(fp).parts]
    name = parts[-1] if parts else ''
    stem = name[:-3] if name.endswith('.md') else name
    dirs = parts[:-1]

    # --- A 層：目錄結構 ---
    if any(d.startswith('archive') or d.startswith('04-') for d in dirs):
        conf = 0.85                      # 歷史歸檔：非錯但非當前
    elif '03-resources' in dirs:
        conf = 1.15                      # 參考資料庫（curated reference）
    elif '02-areas' in dirs:
        conf = 1.1                       # 主題知識（較穩定）
    elif '00-inbox' in dirs:
        conf = 0.7                       # 未整理收件匣
    else:
        conf = 1.0                       # daily journal / active project baseline

    # --- A' 層：scratchpad / aggregate（看 filename，零判斷）---
    if ('proposals' in name or stem.startswith('dreams.pending')
            or stem.startswith('dreams.review') or '.review' in name):
        conf = min(conf, 0.6)            # 未裁決 scratchpad
    if stem in _AGGREGATE_STEMS:
        conf = min(conf, 0.6)            # 滾動彙整 digest noise

    # --- A'' 層：超長 digest 安全網（_AGGREGATE_STEMS 白名單漏網的通用兜底）---
    # threshold 20000 由語料分布定（median≈1700、p95≈11000）：乾淨切開
    # 「最大的真實單日 journal ~19.4K」與「滾動彙整 ~23K+」。輕罰 ×0.9（非 0.6）
    # 因為長 ≠ 低可信（curated changelog 也會很長），只當溫和去噪；min() 堆疊不雙埋。
    if len(content) > _OVERLONG_CHARS:
        conf = min(conf, 0.9)

    # --- B 層：notes frontmatter status ---
    st = _frontmatter_status(content)
    if st in ('stale', 'archived', 'superseded', 'deprecated'):
        conf *= 0.5
    elif st == 'paused':
        conf *= 0.7
    return conf


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
    ap.add_argument("--no-confidence", action="store_true",
                    help="關閉 confidence 維（除錯/對照用，回到 bm25×temporal×hall）")
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
        c_boost = 1.0 if args.no_confidence else confidence_boost(fp, content)

        if use_bm25 and bm25_max > 0:
            # BM25 主排序：normalize 到 [0,1]，再乘 temporal/hall/confidence。
            # 沒命中 (bm25_raw=0) 的文件給極小 baseline，避免完全消失。
            bm25_norm = bm25_raw[i] / bm25_max
            base = bm25_norm if bm25_norm > 0 else 0.02
            fused = base * t_boost * h_boost * c_boost
        else:
            # Legacy fallback：keyword-overlap + size scaling。
            size_factor = min(1.0, (len(content) / 5000) ** 0.5)
            base = size_factor * (0.3 if kw_overlap > 0 else 0.05)
            fused = base * (1 + 0.3 * kw_overlap) * t_boost * h_boost * c_boost

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
            "confidence": round(c_boost, 3),
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
