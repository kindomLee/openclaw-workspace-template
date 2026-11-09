#!/usr/bin/env python3
"""
embed-server.py — optional resident embedding service for the dense leg of
memory-search-hybrid.py (EmbeddingGemma 2, plus an optional cross-encoder).

The model loads once; memory/ + notes/ chunks are embedded into
~/.local/share/oracle-embed/index.npz and refreshed incrementally by mtime
(each /search more than 60s after the last check refreshes in a background
thread). The server only starts listening once the index is built, so until
then memory-search-hybrid.py simply falls back to BM25.

API: GET  http://127.0.0.1:8766/search?q=<query>&k=50 → {"root": ..., "results": [[relpath, score], ...]}
     GET  /health → {"chunks": N, "docs": M, "root": ..., "rerank": bool}
     POST /rerank {"q": str, "paths": [relpath, ...]} → {"scores": [logit|null, ...]} (only with EMBED_RERANK=1)
Env: EMBED_DEVICE (default mps when available, else cpu), EMBED_PORT (default 8766),
     EMBED_ROOT (corpus root, default this workspace), EMBED_STATE (index dir),
     EMBED_RERANK=1 (load the cross-encoder; +2 GB download, +1–2 GB RAM, +~1.5 s per search)
Install: pip install -r requirements-dense.txt — see guides/dense-search.md.
"""
import importlib.util, json, math, os, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import torch
from sentence_transformers import CrossEncoder, SentenceTransformer

ROOT = Path(os.environ.get("EMBED_ROOT") or Path(__file__).resolve().parent.parent)
# EMBED_ROOT without EMBED_STATE → keep that root's index inside it, so serving
# another corpus never overwrites the default index.
STATE = Path(os.environ.get("EMBED_STATE")
             or (ROOT / "state" if os.environ.get("EMBED_ROOT") else Path.home() / ".local" / "share" / "oracle-embed"))
INDEX = STATE / "index.npz"
MODEL = "google/embeddinggemma-2"
DIM = 256           # Matryoshka truncation to 256 dims (reported near-lossless)
CHUNK = 800         # chars; documents score by max-pool over chunks
MAX_SEQ = 512
BATCH = 4           # hold the lock per 4 chunks and clear the MPS cache: short lock < the client's 1s timeout,
                    # and without clearing, MPS memory grows until OOM on a 16 GB machine
REFRESH_SEC = 60
PORT = int(os.environ.get("EMBED_PORT", 8766))
if os.environ.get("EMBED_ROOT") and PORT == 8766:
    sys.exit("EMBED_ROOT serves a different corpus — give it its own EMBED_PORT (8766 is the default workspace's)")
DEVICE = os.environ.get("EMBED_DEVICE", "mps" if torch.backends.mps.is_available() else "cpu")

# Load the search script next to this file (not ROOT/scripts) and borrow its
# collect_files, so the dense corpus is exactly the BM25 corpus.
_spec = importlib.util.spec_from_file_location("mshy", Path(__file__).resolve().parent / "memory-search-hybrid.py")
_mshy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mshy)

model = SentenceTransformer(MODEL, truncate_dim=DIM, device=DEVICE)
model.max_seq_length = MAX_SEQ
# Cross-encoder rerank (second stage): the top 10 after fusion; per file, the 2
# passages with the most query terms are scored and the max kept. Fused 1:1
# with the original ranking on the client — pure cross-encoder order hurt
# long, instruction-style prompts in the author's evaluation.
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
RERANK_MAXLEN, RERANK_PASSAGES, RERANK_QMAX, RERANK_PMAX = 384, 2, 200, 1500
# Off by default: only EMBED_RERANK=1 loads it. Without it /rerank returns 404
# and the client keeps the fused order.
reranker = None
if os.environ.get("EMBED_RERANK") == "1":
    reranker = CrossEncoder(RERANK_MODEL, device=DEVICE, max_length=RERANK_MAXLEN)
    if DEVICE == "mps":
        reranker.model.half()
lock = threading.Lock()          # models aren't thread-safe; held per batch so queries can interleave with refresh
idx = {"paths": np.array([], dtype=str), "emb": np.zeros((0, DIM), dtype=np.float32), "mtimes": {}}
last_check = 0.0
refreshing = threading.Event()


def _free():
    if DEVICE == "mps":
        torch.mps.empty_cache()


def encode(texts, query=False):
    out = []
    for i in range(0, len(texts), BATCH):
        part = texts[i:i + BATCH]
        fn = model.encode_query if query else model.encode_document
        with lock:
            out.append(fn(part, batch_size=4, normalize_embeddings=True).astype(np.float32))
            _free()
    return np.concatenate(out) if out else np.zeros((0, DIM), dtype=np.float32)


def scan():
    """{relpath: (mtime, content)} over the same corpus as memory-search-hybrid."""
    docs = _mshy.collect_files(ROOT / "memory", ROOT / "notes")
    return {str(fp.relative_to(ROOT)): (os.path.getmtime(fp), content) for fp, _, content, _ in docs}


_SECTION_RE = re.compile(r'^(?=#{1,3}\s)', re.M)


def chunk(content):
    """Split on H1–H3, merge adjacent small sections up to CHUNK, hard-split
    oversized sections and repeat the heading on continuation chunks.
    (Heading-only chunks without merging scored worse: a one-line chunk wins
    max-pool too easily.)"""
    out, buf = [], ""
    for sec in _SECTION_RE.split(content):
        if not sec.strip():
            continue
        if buf and len(buf) + len(sec) <= CHUNK:
            buf += sec
            continue
        if buf:
            out.append(buf)
        head = sec.split("\n", 1)[0] + "\n" if sec.startswith("#") else ""
        pieces = [sec[i:i + CHUNK] if i == 0 else head + sec[i:i + CHUNK] for i in range(0, len(sec), CHUNK)]
        out += pieces[:-1]
        buf = pieces[-1]
    if buf:
        out.append(buf)
    return out


def refresh():
    global idx
    cur = scan()
    old = idx["mtimes"]
    changed = [p for p, (m, _) in cur.items() if old.get(p) != m]
    gone = set(old) - set(cur)
    if not changed and not gone:
        return
    t = time.time()
    chunks, cpaths = [], []
    for p in changed:
        for c in chunk(cur[p][1]):
            cpaths.append(p); chunks.append(c)
    new_emb = encode(chunks)
    drop = set(changed) | gone
    keep = np.array([p not in drop for p in idx["paths"]], dtype=bool)
    new = {
        "paths": np.concatenate([idx["paths"][keep], np.array(cpaths, dtype=str)]),
        "emb": np.concatenate([idx["emb"][keep], new_emb]),
        "mtimes": {p: m for p, (m, _) in cur.items()},
    }
    idx = new  # single refresh thread writes; swapping the dict reference is atomic
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = STATE / "index.tmp.npz"
    np.savez(tmp, paths=new["paths"], emb=new["emb"], mtimes=json.dumps(new["mtimes"]))
    tmp.replace(INDEX)
    print(f"[refresh] {len(changed)} changed / {len(gone)} gone → {len(chunks)} chunks "
          f"in {time.time() - t:.1f}s; total {len(new['paths'])}", flush=True)


def _bg_refresh():
    try:
        refresh()
    except Exception as e:  # a failed background refresh never breaks queries; retried next time
        print(f"[refresh] failed: {e}", file=sys.stderr, flush=True)
    finally:
        refreshing.clear()


def search(q, k):
    global last_check
    if time.time() - last_check > REFRESH_SEC and not refreshing.is_set():
        last_check = time.time()
        refreshing.set()
        threading.Thread(target=_bg_refresh, daemon=True).start()
    qv = encode([q], query=True)[0]
    cur = idx
    paths, emb = cur["paths"], cur["emb"]
    best = {}
    for p, s in zip(paths, emb @ qv):
        if s > best.get(p, -2.0):
            best[p] = float(s)
    return sorted(best.items(), key=lambda x: x[1], reverse=True)[:k]


_TITLE_RE = re.compile(r'^title:\s*(.+)$', re.M)


def passages(rel, qtoks):
    """Rerank passages for one candidate: daily journals split by hall entry,
    everything else by chunk(); keep the RERANK_PASSAGES with the most query
    terms and prefix the frontmatter title (note passages rarely restate it)."""
    try:   # NUL bytes, overlong paths or permission errors empty this file only
        fp = (ROOT / rel).resolve()
        # only indexed corpus files (.md under memory/ or notes/); compared after
        # resolve() so ".." and symlinks can't escape
        if (fp.suffix != ".md" or not fp.is_file()
                or not any(fp.is_relative_to((ROOT / d).resolve()) for d in ("memory", "notes"))):
            return []
        content = fp.read_text(encoding="utf-8", errors="ignore")
    except (OSError, ValueError):
        return []
    # same test as the client's pick_entries: a dated file under memory/
    daily = fp.is_relative_to((ROOT / "memory").resolve()) and bool(_mshy._DAILY_RE.search(fp.name))
    ps = [t for _, t, _ in _mshy.split_entries(content)] if daily else chunk(content)
    m = _TITLE_RE.search(content[:600])
    pre = m.group(1).strip().strip('"') + "\n" if m else ""
    ps = sorted((p[:RERANK_PMAX] for p in ps), key=lambda p: -sum(t in p.lower() for t in qtoks))
    return [pre + p for p in ps[:RERANK_PASSAGES]]


def rerank(q, rels):
    """Cross-encoder logits aligned with rels (max over passages; None when a
    file can't be read). Logits, not sigmoid: under fp16 sigmoid squashes strong
    candidates near 1.0. The lock is held per 4 pairs — holding it for the whole
    predict (~1.5 s) would push concurrent /search calls past the client timeout."""
    qtoks = set(_mshy.tokenize_bm25(q))
    pairs, owner = [], []
    for i, rel in enumerate(rels):
        for p in passages(rel, qtoks):
            pairs.append((q[:RERANK_QMAX], p)); owner.append(i)
    best = [None] * len(rels)
    for k in range(0, len(pairs), BATCH):
        with lock:
            scores = reranker.predict(pairs[k:k + BATCH], batch_size=BATCH, show_progress_bar=False,
                                      activation_fn=torch.nn.Identity())
            _free()
        for i, s in zip(owner[k:k + BATCH], scores):
            s = float(s)
            if math.isfinite(s):   # skip an fp16-overflowed passage instead of failing the response
                best[i] = s if best[i] is None else max(best[i], s)
        time.sleep(0.001)   # threading.Lock isn't FIFO: give a waiting /search a chance
    return best


MAX_BODY = 64 * 1024


class Handler(BaseHTTPRequestHandler):
    timeout = 5   # a Content-Length larger than the body sent must not hang the reader thread

    def do_POST(self):
        if urlparse(self.path).path != "/rerank" or reranker is None:
            self.send_error(404); return
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_error(400); return
        if not 0 < n <= MAX_BODY:
            self.send_error(413 if n > MAX_BODY else 400); return
        try:
            req = json.loads(self.rfile.read(n))
            q, paths = req["q"], req["paths"]
        except Exception:
            self.send_error(400); return
        if not (isinstance(q, str) and isinstance(paths, list) and all(isinstance(p, str) for p in paths)):
            self.send_error(400); return
        self._json({"scores": rerank(q[:2000], paths[:20])})

    def _json(self, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path == "/search" and qs.get("q"):
            # root lets the client refuse results from another workspace's server
            body = {"root": str(ROOT), "results": search(qs["q"][0], int(qs.get("k", ["50"])[0]))}
        elif u.path == "/health":
            body = {"chunks": len(idx["paths"]), "docs": len(idx["mtimes"]), "device": DEVICE, "root": str(ROOT),
                    "rerank": reranker is not None}
        else:
            self.send_error(404); return
        self._json(body)

    def log_message(self, *a):  # keep queries out of the launchd log
        pass


def main():
    global idx, last_check
    if INDEX.exists():
        z = np.load(INDEX)
        idx = {"paths": z["paths"], "emb": z["emb"], "mtimes": json.loads(str(z["mtimes"]))}
    t = time.time()
    refresh()  # first run embeds everything (minutes); later runs only changed files
    last_check = time.time()
    if reranker is not None:   # the first MPS predict compiles kernels; warm up at real shape or the first /rerank times out
        with lock:
            reranker.predict([("warm up query", "warm up passage " * 300)] * BATCH, batch_size=BATCH,
                             show_progress_bar=False, activation_fn=torch.nn.Identity())
            _free()
    print(f"[ready] {len(idx['paths'])} chunks / {len(idx['mtimes'])} docs on {DEVICE} "
          f"(startup {time.time() - t:.1f}s) → 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
