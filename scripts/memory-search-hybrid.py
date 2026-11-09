#!/usr/bin/env python3
"""
memory-search-hybrid.py — Hybrid search scoring for memory/*.md files
Default mode: BM25(jieba 分詞) + temporal boost + hall type boost
Fallback mode: keyword-overlap (when jieba/rank_bm25 unavailable or --no-bm25)
Optional dense leg: when scripts/embed-server.py is running for this workspace,
its semantic ranking is fused in (and, with EMBED_RERANK=1, the top 10 are
cross-encoder reranked). No server → plain BM25, nothing to configure.

Usage: python3 memory-search-hybrid.py "query" [--days N] [--json] [--top N] [--no-bm25] [--graph-expand]
                                       [--no-dense] [--no-rerank]
"""
import argparse, math, re, os, json, sys, time
_T0 = time.monotonic()   # --budget counts from here (before the jieba/rank_bm25 imports)
import urllib.parse, urllib.request
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
    # The warning above goes nowhere when a hook or cron job runs us, so also
    # raise a flag for the next session. Typical cause: Homebrew moved python3
    # to a new minor version and the packages stayed with the old one.
    _flag = Path(__file__).resolve().parent.parent / ".claude" / "flags" / "search-deps-missing.flag"
    if _flag.parent.is_dir() and not _flag.exists():
        try:
            _flag.write_text(
                "Memory search fell back to keyword mode: jieba / rank_bm25 missing\n"
                f"Seen in {sys.executable} (Python {sys.version.split()[0]}). After a Python upgrade the "
                "packages stay with the old version. Run `bash scripts/health-check.sh`, offer the install "
                "command it prints for each interpreter, re-run it to confirm, then: "
                "rm .claude/flags/search-deps-missing.flag\n")
        except OSError:
            pass

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


_HEADING_RE = re.compile(r'^#{1,3}\s+(.+)$', re.M)


def field_text(content: str) -> str:
    """抽出 frontmatter fence 內文 + H1-H3 heading 文字（hall_boost 的加權對象）。"""
    parts = []
    if content.startswith('---'):
        end = content.find('\n---', 3)
        if end != -1:
            parts.append(content[3:end])
    parts.extend(_HEADING_RE.findall(content))
    return '\n'.join(parts)


def temporal_boost(mtime: float, cutoff: float, now: float, days: int,
                   is_journal: bool = True) -> float:
    """Closer files get up to 40% boost; expired files get 30% penalty.

    notes/ 不吃時間衰減（is_journal=False → 恆 1.0）：curated reference 的價值
    不隨時間掉，mtime 反映的是「上次被編輯」而非「還準不準」。notes 沒有事件
    日期只能吃 mtime，超過搜尋窗就一律重罰，常青筆記結構性地浮不上來；剛被
    批次工具掃過的反而拿高分。journal 的日期來自 date_from_filename（事件
    日期），衰減對它才有意義。
    """
    if not is_journal:
        return 1.0
    age = (now - mtime) / 86400
    if age > days:
        return 0.3
    recency = max(0.0, 1.0 - age / days)
    return 1.0 + 0.4 * recency


# Durable halls: discoveries / advice / preferences don't expire with the event
# date, so past the --days window they get DURABLE_TEMPORAL instead of 0.3.
# events/facts keep decaying: events go stale, facts get replaced by newer ones.
DURABLE_HALLS = frozenset({"discoveries", "advice", "preferences"})
DURABLE_TEMPORAL = 0.7
HALL_MIN_HITS = 2
# ponytail: only used to pick the hit entry; STOPWORDS is single-char, so multi-char
# filler words need their own list. Add your language's fillers here.
_HALL_QUERY_STOP = frozenset({
    "之前", "上次", "後來", "最後", "當時", "那次", "這次", "我們", "你們", "這個", "那個",
    "什麼", "怎麼", "為什麼", "是不是", "有沒有", "要不要", "到底", "其實", "一下", "可以",
    "還是", "然後", "已經", "如果", "因為", "所以", "問題", "現在", "目前", "做過",
    "before", "last", "time", "what", "when", "how", "why", "did", "we",
})
_HALL_TAG_RE = re.compile(r'\[hall_(\w+)\]')
_DAILY_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def has_event_date(fp: Path) -> bool:
    """Same rule as date_from_filename: only a YYYY-MM-DD filename or an
    archive-YYYY-MM/ parent carries an event date. Everything else (reflections,
    dreams, monthly digests) falls back to mtime, which means "last rewritten",
    not "when it happened" — so it must not get the recency boost."""
    return bool(_DAILY_RE.search(fp.name) or re.search(r'\d{4}-\d{2}', fp.parent.name))


def split_entries(content: str) -> list:
    """Split a daily journal into [(hall, text, start_line)] (1-based).
    A line with [hall_x] starts a new entry; an untagged heading starts an
    untyped section; other lines append to the current entry. No tags at all
    -> one entry with hall=None."""
    if not _HALL_TAG_RE.search(content):
        return [(None, content, 1)]
    out, hall, buf, start, fence = [], None, [], 1, False
    for n, line in enumerate(content.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
        # `# comment` / `[hall_x]` literals inside a code fence are not split points
        m = None if fence else _HALL_TAG_RE.search(line)
        if m or (not fence and _HEADING_RE.match(line)):
            if any(x.strip() for x in buf):
                out.append((hall, "\n".join(buf), start))
            hall, buf, start = (m.group(1).lower() if m else None), [], n
        buf.append(line)
    if any(x.strip() for x in buf):
        out.append((hall, "\n".join(buf), start))
    return out


def pick_entries(entries: list, entry_scores: list, query_tokens: list) -> dict:
    """Pick which entry of each file is the hit. entries = [(doc_idx, hall,
    text, start_line)], entry_scores = aligned entry-level BM25. Returns
    {doc_idx: (hall, text, start_line)}. Ranks by matched-term count first
    (fillers removed, tag literals stripped, ASCII word boundary), then BM25,
    since BM25 length normalization favours short entries. Fewer than
    HALL_MIN_HITS terms -> hall None, so one stray term can't exempt a file
    from the age penalty."""
    # dedupe: tokenize_bm25 keeps repeats; "docker ... docker" must not fill HALL_MIN_HITS alone
    qtoks = [t for t in dict.fromkeys(query_tokens) if t not in _HALL_QUERY_STOP]
    top, best = {}, {}
    for (i, h, t, ln), r in zip(entries, entry_scores):
        if r <= 0:
            continue
        body = _HALL_TAG_RE.sub(" ", t.lower())
        key = (sum(label_hit(q, body) for q in qtoks), r)
        if key > top.get(i, (0, 0.0)):
            top[i] = key
            best[i] = (h if key[0] >= HALL_MIN_HITS else None, t, ln)
    return best


def hall_boost(text: str) -> float:
    """Hall 類型加權。呼叫端只餵 field_text()（frontmatter + H1-H3），不餵正文。

    掃全文時會退化成長度加分：「決定」「選擇」是任何 2K 字以上中文文件的必然
    詞，長文幾乎必中。加成等級與檔案長度相關，且會抵銷 BM25 自身的 length
    normalization。改吃結構化欄位後，heading 出現「決定」是刻意標記，正文
    散句不再誤觸。
    """
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


# ---------------------------------------------------------------------------
# Graph query expansion (--graph-expand): when the query hits a graphify
# god-node label, add its 1-hop neighbor labels to the BM25 query. Covers
# BM25's blind spot for "same thing, different name". No-op without a graph.
# Rules mirror .claude/hooks/memory-search-trigger.py (deg>=4, label>=4 chars).
GRAPH_PATH = Path(__file__).resolve().parent.parent / "graphify-out" / "graph.json"
GRAPH_MIN_DEGREE = 4
GRAPH_MAX_NODES = 4
GRAPH_MAX_NEIGHBORS = 4
GRAPH_MIN_LABEL_LEN = 4
_GRAPH_TOKEN_SPLIT = re.compile(r"[_:.\-/\s\(\)\[\]]+")
_GRAPH_TOKEN_STOP = frozenset({
    "system", "concept", "model", "blog", "tool", "file", "pilot", "post",
    "used", "with", "this", "that", "type", "core", "test", "data",
    "code", "from", "into", "have", "your", "more", "auto", "user",
    "memory", "archive", "notes", "journal", "skill", "agent", "claude",
})


def label_hit(label: str, text: str) -> bool:
    """ASCII labels must sit on a word boundary ("home" must not match
    "homekit", "guard" must not match "wireguard"); CJK has no spaces, so it
    stays substring. The hook has a function of the same name and rule."""
    if label.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(label)}(?![a-z0-9])", text) is not None
    return label in text


def graph_expand_terms(query: str):
    """Return (matched_labels, neighbor_labels). Missing/broken graph -> ([], [])."""
    if not GRAPH_PATH.exists():
        return [], []
    try:
        g = json.loads(GRAPH_PATH.read_text())
    except Exception:
        return [], []
    nodes = {n["id"]: n for n in g.get("nodes", [])}
    deg, adj = {}, {}
    for e in g.get("links") or g.get("edges") or []:
        s_, t_ = e.get("source"), e.get("target")
        if not s_ or not t_:
            continue
        deg[s_] = deg.get(s_, 0) + 1
        deg[t_] = deg.get(t_, 0) + 1
        adj.setdefault(s_, []).append(t_)
        adj.setdefault(t_, []).append(s_)

    q = query.lower()
    hits = {}
    for nid, n in nodes.items():
        if deg.get(nid, 0) < GRAPH_MIN_DEGREE:
            continue
        cands = set()
        for key in ("label", "norm_label"):
            v = (n.get(key) or "").strip().lower()
            if len(v) >= GRAPH_MIN_LABEL_LEN:
                cands.add(v)
        pool = " ".join(filter(None, [nid, n.get("label") or "", n.get("norm_label") or ""]))
        for t in (t.lower() for t in _GRAPH_TOKEN_SPLIT.split(pool) if t):
            if len(t) >= GRAPH_MIN_LABEL_LEN and not t.isdigit() and t not in _GRAPH_TOKEN_STOP:
                cands.add(t)
        if any(label_hit(c, q) for c in cands):
            hits[nid] = deg[nid]

    # tie-break on id: set/dict order isn't stable across processes (PYTHONHASHSEED)
    top_nodes = sorted(hits, key=lambda k: (-hits[k], k))[:GRAPH_MAX_NODES]
    matched = [nodes[n].get("label") or n for n in top_nodes]
    neighbors = []
    for nid in top_nodes:
        nb = sorted(set(adj.get(nid, [])), key=lambda k: (-deg.get(k, 0), k))[:GRAPH_MAX_NEIGHBORS]
        for x in nb:
            lab = (nodes.get(x, {}).get("label") or "").strip()
            if lab and lab not in neighbors:
                neighbors.append(lab)
    return matched, neighbors


# Token cache: jieba over the whole corpus dominates search latency (seconds on a
# few hundred files), which eats the hook's timeout. Keyed on content md5 so only
# changed files are re-tokenized.
TOKEN_CACHE = Path(os.environ.get("MEMORY_CACHE_DIR")
                   or Path.home() / ".cache" / "memory-search") / "bm25-tokens.pkl"
ENTRY_TOKEN_CACHE = TOKEN_CACHE.with_name("bm25-entry-tokens.pkl")  # separate file so the two calls don't overwrite each other


def _token_rules() -> str:
    """Tokenizer fingerprint: changing tokenize_bm25 / stopwords / filter regex /
    jieba version invalidates every cache key, otherwise a rule change keeps
    serving old tokens and looks like it had no effect."""
    import inspect
    return "|".join([
        inspect.getsource(tokenize_bm25), "".join(sorted(STOPWORDS)),
        _TOKEN_FILTER_RE.pattern, getattr(jieba, "__version__", "?"),
    ])


def corpus_tokens_cached(docs, cache_path: Path = None) -> list:
    import hashlib, pickle
    cache_path = cache_path or TOKEN_CACHE
    try:
        cache = pickle.loads(cache_path.read_bytes())
    except Exception:
        cache = {}
    rules = _token_rules()
    out, fresh, dirty = [], {}, False
    for fp, _, content, _ in docs:
        key = str(fp)
        h = hashlib.md5((rules + content).encode("utf-8")).hexdigest()
        hit = cache.get(key)
        if hit and hit[0] == h:
            toks = hit[1]
        else:
            toks = tokenize_bm25(content)
            dirty = True
        fresh[key] = (h, toks)
        out.append(toks)
    if dirty or len(fresh) != len(cache):   # write back only on new/changed/deleted files
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_bytes(pickle.dumps(fresh, protocol=pickle.HIGHEST_PROTOCOL))
            os.replace(tmp, cache_path)    # atomic: a concurrent hook never reads half a file
        except Exception:
            pass  # can't write -> just re-tokenize next time
    return out


def score_bm25(docs, query: str, extra_terms=(), query_weight: int = 8, cache_path: Path = None):
    """Return list of bm25 raw scores, aligned with docs。"""
    corpus_tokens = corpus_tokens_cached(docs, cache_path)
    # rank_bm25 對空 doc 會炸；過濾後重新對齊。
    valid_idx = [i for i, toks in enumerate(corpus_tokens) if toks]
    if not valid_idx:
        return [0.0] * len(docs)
    valid_corpus = [corpus_tokens[i] for i in valid_idx]
    bm25 = BM25Okapi(valid_corpus)
    qtok = tokenize_bm25(query)
    if extra_terms:
        # original query tokens repeated so they dominate; expansion is a side signal
        qtok = qtok * query_weight + tokenize_bm25(" ".join(extra_terms))
    if not qtok:
        return [0.0] * len(docs)
    valid_scores = bm25.get_scores(qtok)
    scores = [0.0] * len(docs)
    for j, i in enumerate(valid_idx):
        scores[i] = float(valid_scores[j])
    return scores


# Dense leg (optional): scripts/embed-server.py (EmbeddingGemma 2) returns a
# semantic ranking that is fused with the final BM25 ranking by weighted RRF —
# it only reorders. In the author's evaluation equal-weight RRF lost to pure
# dense and dense×3 won on both query sets. RRF scores are flat, so they are
# never used as a base for further boosts (that measurably hurt MRR).
# No server, a timeout, or a server for another workspace → None → plain BM25.
DENSE_URL = os.environ.get("EMBED_URL", "http://127.0.0.1:8766")
DENSE_WEIGHT = 3
DENSE_TIMEOUT_SEC = 1  # queries take ~40–110 ms when the server is up
RRF_K = 60
RRF_POOL = 200
# Protect an overwhelming BM25 hit: RRF only sees ranks, so a rare proper noun
# that dense misses can be pushed out of the top 10 by dense×3. Only when the
# top BM25 hit is not in dense's top PIN_DENSE_MISS_RANK and its raw score is
# >= PIN_RATIO × every other hit, it is pinned back to rank 0.
PIN_RATIO = 1.5
PIN_DENSE_MISS_RANK = 50


def dense_search(query: str, root: Path):
    """Ask embed-server for a relpath ranking; None on any failure or when the
    server indexes a different workspace (its results would not line up)."""
    if not DENSE_URL:
        return None
    try:
        url = f"{DENSE_URL}/search?" + urllib.parse.urlencode({"q": query, "k": RRF_POOL})
        with urllib.request.urlopen(url, timeout=DENSE_TIMEOUT_SEC) as r:
            body = json.load(r)
        if Path(body.get("root") or "/nonexistent").resolve() != root.resolve():
            return None
        return [p for p, _ in body["results"]]
    except Exception:
        return None


RERANK_K = 10
RERANK_TIMEOUT_SEC = 2.5   # ~1.45 s median on Apple-silicon MPS
RERANK_MIN_SEC = 1.0       # less time left than this → don't send: the server keeps working after a client timeout


def rerank_order(scores: list) -> list:
    """New order (index list) from a 1:1 RRF (k=60) of the original rank and
    the cross-encoder rank; ties keep the original order. Pure cross-encoder
    order hurt long, instruction-style prompts; 1:1 fusion lost on neither."""
    ce_pos = {i: r for r, i in enumerate(sorted(range(len(scores)), key=lambda i: -scores[i]))}
    return sorted(range(len(scores)), key=lambda i: -(1 / (RRF_K + 1 + i) + 1 / (RRF_K + 1 + ce_pos[i])))


def rerank_top(query: str, results: list, root: Path, timeout: float = RERANK_TIMEOUT_SEC):
    """Send the top RERANK_K to embed-server /rerank and reorder them, each rank
    keeping its old score. Any failure, timeout, malformed reply or all-unreadable
    → None (keep the order; mode is not tagged rerank). A hit pinned by
    fuse_dense stays at rank 0."""
    if not DENSE_URL or not results or timeout < RERANK_MIN_SEC:
        return None
    fixed = 1 if results[0].get("_pinned") else 0
    head = results[fixed:RERANK_K]
    if len(head) < 2:
        return None
    try:
        rels = [str(Path(r["path"]).relative_to(root)) for r in head]
        req = urllib.request.Request(f"{DENSE_URL}/rerank", method="POST",
                                     data=json.dumps({"q": query, "paths": rels}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            scores = json.load(r)["scores"]
    except Exception:
        return None
    if not (isinstance(scores, list) and len(scores) == len(head)
            and all(s is None or (type(s) in (int, float) and math.isfinite(s)) for s in scores)):
        return None
    if all(s is None for s in scores):
        return None
    scores = [float("-inf") if s is None else s for s in scores]   # unreadable files sink
    old = [r["score"] for r in head]
    new = [dict(head[i], score=old[k]) for k, i in enumerate(rerank_order(scores))]
    return results[:fixed] + new + results[RERANK_K:]


def fuse_dense(results: list, rel_paths: list, dense: list) -> list:
    """results are sorted by the BM25 formula; reorder by RRF(original rank,
    dense×DENSE_WEIGHT). Scores keep the original distribution (rank k gets the
    k-th highest old score), so downstream thresholds (the recall hook) still hold."""
    pos = {p: r for r, p in enumerate(dense)}
    rel = dict(zip((r["path"] for r in results), rel_paths))
    def rrf(rank, r):
        s = 1 / (RRF_K + rank + 1) if rank < RRF_POOL else 0.0
        d = pos.get(rel[r["path"]])
        return s + (DENSE_WEIGHT / (RRF_K + d + 1) if d is not None else 0.0)
    keyed = [(rrf(k, r), -k, r) for k, r in enumerate(results)]
    keyed.sort(key=lambda x: (x[0], x[1]), reverse=True)
    old_scores = [r["score"] for r in results]
    fused = [r for _, _, r in keyed]
    top = results[0] if results else None
    top_raw = (top or {}).get("bm25_raw") or 0
    others = max(((r.get("bm25_raw") or 0) for r in results[1:]), default=0)
    dense_missed = pos.get(rel[top["path"]], PIN_DENSE_MISS_RANK) >= PIN_DENSE_MISS_RANK if top else False
    if top_raw > 0 and dense_missed and top_raw >= PIN_RATIO * others:
        fused.remove(top)
        fused.insert(0, top)
        top["_pinned"] = True   # rerank_top must not move it
    for r, s in zip(fused, old_scores):
        r["score"] = s
    return fused


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
    ap.add_argument("--graph-expand", action="store_true",
                    help="When the query hits a graphify god-node, add its 1-hop neighbor labels to the BM25 query")
    ap.add_argument("--graph-weight", type=int, default=8,
                    help="With --graph-expand: repeat factor for original query tokens (higher = less expansion influence)")
    ap.add_argument("--no-dense", action="store_true",
                    help="Don't ask embed-server; BM25 only (for comparison)")
    ap.add_argument("--no-rerank", action="store_true", help="Skip cross-encoder rerank (for comparison)")
    ap.add_argument("--budget", type=float, default=0,
                    help="Time budget in seconds for the whole search (the recall hook passes one); "
                         "the rerank only uses what is left. 0 = no limit")
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
    # Entry-level index: a daily journal mixes several halls in one day. Ranking
    # stays file-level (scoring entries as documents lets short entries dominate
    # via length normalization); entry-level BM25 only picks which entry of a
    # file is the hit, which decides its age weighting (that entry's hall) and snippet.
    entries = [(i, h, t, ln) for i, (fp, base_dir, content, _) in enumerate(docs)
               if base_dir == memory_dir and _DAILY_RE.search(fp.name)
               for h, t, ln in split_entries(content)]

    graph_matched, graph_terms = graph_expand_terms(query) if args.graph_expand else ([], [])
    if graph_terms and not args.json:
        print(f"🕸 graph-expand: {graph_matched} → +{graph_terms}", file=sys.stderr)
    bm25_raw = score_bm25(docs, query, graph_terms, args.graph_weight) if use_bm25 else [0.0] * len(docs)
    best_entry = {}   # doc idx -> (hall, text, start_line)
    if use_bm25 and entries:
        # no graph expansion terms here: they are broad and would sway which entry "hit"
        e_raw = score_bm25([(f"{docs[i][0]}#{ln}", None, t, 0) for i, _, t, ln in entries],
                           query, cache_path=ENTRY_TOKEN_CACHE)
        best_entry = pick_entries(entries, e_raw, tokenize_bm25(query))
    bm25_max = max(bm25_raw) if bm25_raw else 0.0
    dense = None if (args.no_dense or not use_bm25) else dense_search(query, project_root)

    results = []
    for i, (fp, base_dir, file_content, mtime) in enumerate(docs):
        hall, content, start_line = best_entry.get(i, (None, file_content, 1))
        kw = extract_keywords(content)
        kw_overlap = len(query_kw & kw) / len(query_kw) if query_kw else 0.0
        # only files with an event date decay; digests' mtime is "last rewritten",
        # and cron rewrites them often, so they'd always look recent
        t_boost = temporal_boost(mtime, cutoff, now, args.days,
                                 is_journal=(base_dir == memory_dir and has_event_date(fp)))
        if t_boost < 1.0 and hall in DURABLE_HALLS:
            t_boost = DURABLE_TEMPORAL
        h_boost = hall_boost(field_text(file_content))
        c_boost = 1.0 if args.no_confidence else confidence_boost(fp, file_content)

        if use_bm25 and bm25_max > 0:
            # BM25 主排序：normalize 到 [0,1]，再乘 temporal/hall/confidence。
            # 沒命中 (bm25_raw=0) 的文件給極小 baseline，避免完全消失。
            bm25_norm = bm25_raw[i] / bm25_max
            base = bm25_norm if bm25_norm > 0 else 0.02
            fused = base * t_boost * h_boost * c_boost
        else:
            # Legacy fallback：keyword-overlap + size scaling。
            size_factor = min(1.0, (len(file_content) / 5000) ** 0.5)
            base = size_factor * (0.3 if kw_overlap > 0 else 0.05)
            fused = base * (1 + 0.3 * kw_overlap) * t_boost * h_boost * c_boost

        snip_text, snip_start, snip_line = snippet(content, query_kw)
        snip_line = snip_line + start_line - 1 if snip_line else (start_line if i in best_entry else 0)
        full_lines = file_content.count('\n') + 1
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
            "hall_boost": round(h_boost, 2),  # 1 decimal shows 1.15 as 1.1
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
    if dense:
        results = fuse_dense(results, [str(Path(r["path"]).relative_to(project_root)) for r in results], dense)
    reranked = None
    if dense and not args.no_rerank:
        left = args.budget - (time.monotonic() - _T0) if args.budget else RERANK_TIMEOUT_SEC
        reranked = rerank_top(query, results, project_root, min(RERANK_TIMEOUT_SEC, left))
    results = reranked or results
    top = results[:args.top]

    if args.json:
        print(json.dumps(
            {"query": query, "mode": (("bm25+dense+rerank" if reranked else "bm25+dense") if dense else "bm25")
                                     if use_bm25 else "legacy",
             "results": top},
            ensure_ascii=False, indent=2,
        ))
    else:
        mode_tag = (("BM25+jieba+dense+rerank" if reranked else "BM25+jieba+dense") if dense else "BM25+jieba") \
            if use_bm25 else "legacy keyword"
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
