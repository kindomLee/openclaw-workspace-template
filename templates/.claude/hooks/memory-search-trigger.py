#!/usr/bin/env python3
"""UserPromptSubmit hook: detect memory-search hard-trigger keywords AND
auto-run the search, injecting top-N results into the next turn's context.

The goal is to remove "should I search memory?" as a judgment call:

  1. Hard-trigger detection — if the user mentions a tracked proper noun,
     a cross-host intent, a temporal reference, or asks about credentials,
     we know we want a memory lookup.
  2. Auto-search — instead of just reminding Claude to run the search,
     this hook runs `scripts/memory-search-hybrid.py` itself and injects
     the top-N results into `additionalContext`. Claude opens the next
     turn with the search output already in front of it.
  3. Three reranking layers on top of the raw hybrid score:
       - Query classification (historical / recent / default) picks a
         different search window per mode.
       - Domain routing scores results higher when they live under the
         expected path prefix for the matched keyword.
       - Category dedup keeps only the highest-scoring file per category
         so a chatty file (e.g. reflections.md) doesn't crowd out other
         hits.
  4. 300s TTL cache — repeated prompts don't re-spawn the search process.

  5. Always-on proactive recall (LMM-inspired). When no keyword fires but
     the prompt is substantive (>= MIN_PROMPT_CHARS, not a slash command,
     not a trivial reply), still run a stricter search (smaller window +
     higher score floor). Silently exits on no high-confidence hit so
     irrelevant prompts don't pollute context. Removes the keyword
     whitelist as a hard gate without spamming low-signal recalls.

  6. Graph 1-hop associative recall. If `graphify-out/graph.json` exists,
     match high-degree node labels (and distinctive single tokens, e.g.
     `gepa` from `concept:gepa`) against the prompt and inject 1-hop
     neighbors with `[relation w=…] source_file`. Modeled after
     associative recall in human memory (and Engramme/Memorious's "LMM").
     Gracefully no-ops when graph file is absent.

  7. Access logging (used by `scripts/memory-archive.py`). Every injected
     file path appends one line to ~/.claude/state/mem-access.jsonl
     (configurable). The companion `memory-archive.py` reads this log to
     pin frequently-accessed memories from age-based archival —
     "use-dependent" memory consolidation. Fail-open: any IO error is
     swallowed.

The keyword lists, hints, and domain map are intentionally minimal in
this template. **Edit the CUSTOMIZE section below for your workspace.**

Wire it up in `.claude/settings.json`:

    "hooks": {
      "UserPromptSubmit": [{
        "hooks": [{
          "type": "command",
          "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/memory-search-trigger.py\"",
          "timeout": 10
        }]
      }]
    }

`$CLAUDE_PROJECT_DIR` is set by Claude Code to the workspace root. Using
it makes the hook robust against cwd drift (e.g. an earlier Bash call
that `cd`'d into a subdirectory and never restored cwd).

Self-test: `python3 memory-search-trigger.py --self-test` runs the
framework's pure-function tests without making a real search call.
"""
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

# ============================================================================
# CUSTOMIZE THIS SECTION FOR YOUR WORKSPACE
# ============================================================================

# Substring-matched (case-insensitive). Good for proper nouns, multi-word
# phrases, Chinese, and intent phrases. Trim or extend liberally — every
# entry here is a "we definitely want to search memory before answering"
# vote.
KEYWORDS: list[str] = [
    # === Proper nouns / project names ===
    # Replace these placeholders with your actual project / service / infra
    # names. Example (uncomment and adapt):
    #
    #   "MyProject", "production-db", "staging-cluster", "vendor-foo",
    #   "the-one-ingest-pipeline", "acme-api",
    #
    # Tip: include *every* nickname you use for the same thing. If you
    # sometimes call a service "the ingest pipeline" and sometimes
    # "ingest", list both. The hook does substring match, so shorter
    # entries subsume longer ones.
    #
    # Note on Chinese: matching is pure substring (no word-boundary),
    # which means "去拿" will fire inside "他去拿包裹" too. That's usually
    # fine because the reranker + MIN_SCORE filter cleans up noise, but
    # if you see false positives on a specific short keyword, make it
    # longer (e.g. "去拿一下" instead of "去拿").

    # === Cross-host / retrieval intent (English) ===
    "is there",
    "do we have",
    "fetch from",
    "pull from",
    "go grab",
    # === Cross-host / retrieval intent (Chinese) ===
    "裡面有沒有",
    "上面有沒有",
    "去拿",
    "去抓",
    "去找",

    # === Temporal references (English) ===
    "last time",
    "previously",
    "earlier",
    "we did",
    "remember when",
    # === Temporal references (Chinese) ===
    "之前",
    "上次",
    "剛剛",
    "還記得",
    "上週",
    "上個月",

    # === Connection / credential questions ===
    "credentials",
    "how do i connect",
    "ssh key",
    "連線",
    "帳號",
]

# Tokens that need word-boundary matching (avoid false positives on
# substrings inside unrelated words). Always-on; trim if you don't care.
WORD_BOUNDARY_KEYWORDS: list[str] = ["IP", "port", "token", "URL"]

# Hints used by `classify_query` to pick a search window. Bilingual by
# default; trim or extend to match the languages your team works in.
HISTORICAL_HINTS: list[str] = [
    "last time", "previously", "earlier", "we did", "remember when",
    "之前", "上次", "還記得", "上週", "上個月", "以前", "原本",
]
RECENT_HINTS: list[str] = [
    "latest", "current", "right now", "do i need to update", "new version",
    "最新", "目前", "現在", "新版", "要不要升", "有沒有更新",
]

# Search window + top-N per query mode. The `default` row applies when
# the prompt has no historical/recent hints.
MODE_PARAMS: dict[str, dict[str, int]] = {
    "historical": {"days": 365, "top": 8},
    "recent":     {"days": 7,   "top": 5},
    "default":    {"days": 90,  "top": 5},
}

# Map keyword → expected file-path prefixes. When a keyword fires, results
# whose path begins with one of the listed prefixes get a small score
# bonus, others get a small penalty. Leave empty to disable domain
# reranking entirely (the hook will still inject results, just without
# path-aware scoring).
#
# The path prefixes are matched against whatever `memory-search-hybrid.py`
# returns in the `file` field — usually a path relative to your workspace
# root with `notes/` and `memory/` already trimmed.
#
# Example:
#     DOMAIN_MAP = {
#         "MyProject": ["areas/tech/myproject/", "resources/myproject/"],
#         "production-db": ["areas/infrastructure/", "MEMORY.md"],
#     }
DOMAIN_MAP: dict[str, list[str]] = {}

# Score tuning knobs.
MIN_SCORE          = 0.5     # don't inject results below this score
DOMAIN_BONUS       = 0.10    # added when result matches an expected prefix
DOMAIN_PENALTY     = 0.15    # subtracted when prefixes are set but result misses them all
# Cache TTL: a single Claude turn commonly runs 60-120+ seconds, so a
# 60-second TTL is effectively zero — the user's next prompt always
# misses cache. 300s (5 min) covers a few consecutive turns where the
# same keyword fires, and is still short enough that stale memory
# entries don't persist beyond a single conversational thread.
CACHE_TTL_SEC      = 300
SEARCH_TIMEOUT_SEC = 6       # subprocess timeout for memory-search-hybrid.py

# --- Always-on proactive recall ----------------------------------------
# When no KEYWORDS fire, run a stricter search anyway so memory still
# surfaces. Set ALWAYS_ON_TOP=0 to disable.
ALWAYS_ON_DAYS      = 30
ALWAYS_ON_TOP       = 3
ALWAYS_ON_MIN_SCORE = 0.7    # higher bar than MIN_SCORE → less noise
MIN_PROMPT_CHARS    = 8      # below this, prompt is too short to bother
                             # (8 catches dense CJK like 「看一下 X 怎樣」 while
                             #  staying above trivial English replies — those
                             #  are caught by TRIVIAL_REPLIES anyway)
# Trivial replies that should never trigger always-on (case-insensitive).
TRIVIAL_REPLIES: frozenset[str] = frozenset({
    "ok", "good", "go", "yes", "no", "next", "thanks", "thx", "lgtm",
    "好", "嗯", "對", "繼續", "可以", "沒問題",
})

# --- Graph 1-hop associative recall ------------------------------------
# Loaded from $CLAUDE_PROJECT_DIR/graphify-out/graph.json (NetworkX
# node-link export). Hook gracefully no-ops if the file is absent — you
# only get this layer if you've built a graph with the `graphify` tool.
GRAPH_PATH               = "graphify-out/graph.json"  # relative to PROJECT_DIR
MIN_NODE_DEGREE          = 4   # only "god-ish" nodes can fire
MAX_TRIGGER_NODES        = 4   # cap entities expanded per prompt
MAX_NEIGHBORS_PER_NODE   = 4   # cap neighbors listed per entity
MIN_LABEL_LEN            = 4   # ignore very short label strings
# Tokens that match too broadly when extracted from labels/ids.
TOKEN_STOPWORDS: frozenset[str] = frozenset({
    "system", "concept", "model", "blog", "tool", "file", "pilot", "post",
    "used", "with", "this", "that", "type", "core", "test", "data",
    "code", "from", "into", "have", "your", "more", "auto", "user",
    "node", "edge", "path", "name", "page", "main", "task",
})

# --- Access log (use-aware pinning, consumed by memory-archive.py) -----
# Append-only JSONL. Each line: {"ts","file","kind","score?"|"node_id?"}.
# Set ACCESS_LOG_PATH to "" to disable logging entirely.
ACCESS_LOG_PATH = os.path.expanduser("~/.claude/state/mem-access.jsonl")

# ============================================================================
# Framework — generally don't edit unless you're extending the hook
# ============================================================================

CACHE_DIR = "/tmp"

PROJECT_DIR = os.environ.get(
    "CLAUDE_PROJECT_DIR",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)


def detect_hits(prompt: str) -> list[str]:
    """Return the sorted, de-duplicated list of trigger keywords that fire
    for the given prompt. Substring-matched keywords are case-insensitive;
    word-boundary keywords use \\b anchors."""
    lower = prompt.lower()
    hits = [kw for kw in KEYWORDS if kw.lower() in lower]
    for kw in WORD_BOUNDARY_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", prompt, re.IGNORECASE):
            hits.append(kw)
    return sorted(set(hits))


def is_substantive_prompt(prompt: str) -> bool:
    """Decide whether to run an always-on search when no keyword fires.

    Filter out: too short, pure slash command, trivial confirmations.
    Permissive on purpose — false positives cost a search subprocess,
    false negatives cost the recall we're trying to surface.
    """
    p = prompt.strip()
    if len(p) < MIN_PROMPT_CHARS:
        return False
    if re.match(r"^/[\w-]+\s*$", p):
        return False
    if p.lower() in TRIVIAL_REPLIES:
        return False
    return True


# ---------------------------------------------------------------------------
# Graph traversal — associative recall over graphify-out/graph.json
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def load_graph() -> dict | None:
    """Load graph.json once per process (LRU sized to 1). Returns None when
    the file is absent or malformed — callers must None-check.

    Index built:
      nodes : dict[id -> node]
      adj   : dict[id -> list[(neighbor_id, relation, weight)]]
      deg   : dict[id -> int]
      labels: list[(matchable_lowercase_string, node_id)] — only god nodes
              (degree >= MIN_NODE_DEGREE), and only after stopword filter.
    """
    graph_file = os.path.join(PROJECT_DIR, GRAPH_PATH)
    if not os.path.exists(graph_file):
        return None
    try:
        with open(graph_file) as f:
            g = json.load(f)
    except Exception:
        return None

    nodes = {n["id"]: n for n in g.get("nodes", []) if "id" in n}
    edges = g.get("links") or g.get("edges") or []

    deg: dict[str, int] = {}
    adj: dict[str, list[tuple[str, str, float]]] = {}
    for e in edges:
        s = e.get("source") or e.get("_src")
        t = e.get("target") or e.get("_tgt")
        if not s or not t:
            continue
        rel = e.get("relation", "?")
        try:
            w = float(e.get("weight", 1.0) or 1.0)
        except (TypeError, ValueError):
            w = 1.0
        deg[s] = deg.get(s, 0) + 1
        deg[t] = deg.get(t, 0) + 1
        adj.setdefault(s, []).append((t, rel, w))
        adj.setdefault(t, []).append((s, rel, w))

    labels: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    token_split_re = re.compile(r"[_:.\-/\s\(\)\[\]]+")
    for nid, n in nodes.items():
        if deg.get(nid, 0) < MIN_NODE_DEGREE:
            continue
        candidates: set[str] = set()
        # Full label / norm_label — for users who quote the entity verbatim.
        for key in ("label", "norm_label"):
            v = (n.get(key) or "").strip().lower()
            if len(v) >= MIN_LABEL_LEN:
                candidates.add(v)
        # Distinctive single tokens from id + label — handles cases like
        # `concept:gepa` matching when the prompt only contains "gepa".
        text_pool = " ".join(filter(None, [
            nid, n.get("label") or "", n.get("norm_label") or "",
        ]))
        for tok in token_split_re.split(text_pool):
            tok = tok.lower()
            if not tok or len(tok) < MIN_LABEL_LEN or tok.isdigit():
                continue
            if tok in TOKEN_STOPWORDS:
                continue
            candidates.add(tok)
        for c in candidates:
            pair = (c, nid)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            labels.append(pair)

    return {"nodes": nodes, "adj": adj, "deg": deg, "labels": labels}


def detect_graph_nodes(prompt: str) -> list[str]:
    """Return up to MAX_TRIGGER_NODES god-degree node ids whose label or
    distinctive token appears (lowercase substring) in the prompt, sorted
    by degree descending. Empty list when graph is absent."""
    g = load_graph()
    if not g:
        return []
    p = prompt.lower()
    hits: list[tuple[str, int]] = []
    seen: set[str] = set()
    for label, nid in g["labels"]:
        if nid in seen:
            continue
        if label and label in p:
            hits.append((nid, g["deg"].get(nid, 0)))
            seen.add(nid)
    hits.sort(key=lambda x: -x[1])
    return [nid for nid, _ in hits[:MAX_TRIGGER_NODES]]


def graph_traversal_section(matched_ids: list[str]) -> str:
    """Format a 1-hop neighbor block for the matched entities. Empty
    string when nothing to render. Neighbors ranked by edge weight (desc)
    then neighbor degree (desc)."""
    if not matched_ids:
        return ""
    g = load_graph()
    if not g:
        return ""
    nodes = g["nodes"]
    adj = g["adj"]
    deg = g["deg"]

    lines = [
        "🕸 GRAPH_RECALL — auto associative recall (graphify 1-hop):",
        "⚠️ Edge relations are LLM-extracted; confidence is not always EXACT. "
        "Read the source_file before treating any neighbor as fact.",
    ]
    for nid in matched_ids:
        n = nodes.get(nid, {})
        label = n.get("label") or nid
        d = deg.get(nid, 0)
        src = n.get("source_file") or "?"
        lines.append("")
        lines.append(f"• {label}  (id={nid}, degree={d}, src={src})")
        neighbors = list(adj.get(nid, []))
        neighbors.sort(key=lambda x: (-x[2], -deg.get(x[0], 0)))
        for tgt, rel, w in neighbors[:MAX_NEIGHBORS_PER_NODE]:
            tnode = nodes.get(tgt, {})
            tlabel = tnode.get("label") or tgt
            tsource = tnode.get("source_file") or "?"
            lines.append(f"    →[{rel} w={w:.1f}] {tlabel}  ({tsource})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Access log — fail-open writer for memory-archive.py to consume
# ---------------------------------------------------------------------------

def log_access(events: list[dict]) -> None:
    """Append events as JSONL to ACCESS_LOG_PATH. Any IO error is
    swallowed; the hook's main path (context injection) must never fail
    because of logging. Set ACCESS_LOG_PATH = "" to disable."""
    if not events or not ACCESS_LOG_PATH:
        return
    try:
        os.makedirs(os.path.dirname(ACCESS_LOG_PATH), exist_ok=True)
        ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with open(ACCESS_LOG_PATH, "a") as f:
            for ev in events:
                rec = {"ts": ts}
                rec.update(ev)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def classify_query(prompt: str) -> str:
    """Pick a search-window mode based on temporal hints in the prompt.
    Case-insensitive match against `HISTORICAL_HINTS` then `RECENT_HINTS`,
    falls back to `default`. Mirrors `detect_hits`'s lowercasing so a user
    typing 'Last time' is treated the same as 'last time'."""
    lower = prompt.lower()
    for h in HISTORICAL_HINTS:
        if h.lower() in lower:
            return "historical"
    for h in RECENT_HINTS:
        if h.lower() in lower:
            return "recent"
    return "default"


def expected_prefixes(hits: list[str]) -> list[str]:
    """Union the expected path-prefix lists for every fired keyword."""
    prefixes: set[str] = set()
    for hit in hits:
        prefixes.update(DOMAIN_MAP.get(hit, []))
    return sorted(prefixes)


def rerank_by_domain(results: list[dict], prefixes: list[str]) -> list[dict]:
    """Bonus results whose `file` matches an expected prefix; penalize the
    rest. Returns a new list sorted by adjusted score (descending). If
    `prefixes` is empty (no DOMAIN_MAP entries fired), returns `results`
    unchanged."""
    if not prefixes:
        return results
    reranked = []
    for r in results:
        file_ = r.get("file", "")
        score = r.get("score", 0)
        matched = any(file_.startswith(p) or p == file_ for p in prefixes)
        new_score = score + DOMAIN_BONUS if matched else score - DOMAIN_PENALTY
        # Copy so we don't mutate cached entries.
        r2 = dict(r)
        r2["score"] = new_score
        r2["_domain_match"] = matched
        reranked.append(r2)
    reranked.sort(key=lambda x: x["score"], reverse=True)
    return reranked


def category_of(path: str) -> str:
    """Best-effort categorization for `dedupe_by_category`. The intent is
    that two hits in the same "kind" of file (e.g. two reflections, two
    project notes) collapse to the highest-scoring one, so a single chatty
    file can't crowd out other hits.

    The default rules cover common workspace shapes:
      * `MEMORY.md` family -> memory-index
      * `reflections.md` / `dreams.md` -> memory-system
      * `YYYY-MM-DD.md` files -> journal
      * `archive-*` files -> journal-archive
      * Otherwise: top-level directory of the path

    Workspaces with custom layouts can extend this with their own rules.
    """
    if path in ("MEMORY.md", "MEMORY_COMPACT.md", "LEARNINGS.md"):
        return "memory-index"
    if path in ("reflections.md", "dreams.md", "timeline-archive.md"):
        return "memory-system"
    if path.startswith("archive-"):
        return "journal-archive"
    if re.match(r"^\d{4}-\d{2}-\d{2}.*\.md$", path):
        return "journal"
    head = path.split("/", 1)[0]
    return head or "other"


def dedupe_by_category(results: list[dict], limit: int) -> list[dict]:
    """Keep at most one entry per `category_of(file)`, picking the highest
    score. Returns at most `limit` entries, sorted by score descending."""
    seen: dict[str, dict] = {}
    for r in results:
        cat = category_of(r.get("file", ""))
        existing = seen.get(cat)
        if existing is None or r.get("score", 0) > existing.get("score", 0):
            seen[cat] = r
    unique = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
    return unique[:limit]


def run_search_cached(query: str, days: int, top: int) -> list[dict]:
    """Run `memory-search-hybrid.py` (with `--json`), cache the result for
    `CACHE_TTL_SEC` seconds keyed on (query, days, top). Returns the list
    of results, or an empty list on any error (network, subprocess, JSON,
    etc.)."""
    cache_key = f"{query}|days={days}|top={top}"
    query_hash = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:16]
    cache_path = os.path.join(CACHE_DIR, f"mem-search-{query_hash}.json")

    if os.path.exists(cache_path):
        try:
            age = time.time() - os.path.getmtime(cache_path)
            if age < CACHE_TTL_SEC:
                with open(cache_path) as f:
                    return json.load(f).get("results", [])
        except Exception:
            pass

    try:
        proc = subprocess.run(
            [
                "python3",
                os.path.join(PROJECT_DIR, "scripts", "memory-search-hybrid.py"),
                query,
                "--days", str(days),
                "--top", str(top),
                "--json",
            ],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=SEARCH_TIMEOUT_SEC,
        )
        if proc.returncode != 0:
            return []
        data = json.loads(proc.stdout)
        results = data.get("results", [])
        try:
            with open(cache_path, "w") as f:
                json.dump({"results": results}, f)
        except Exception:
            pass
        return results
    except Exception:
        return []


def format_context(
    hits: list[str],
    mode: str,
    prefixes: list[str],
    results: list[dict],
    min_score: float = MIN_SCORE,
) -> str:
    """Build the additionalContext string injected into the next turn.

    Format inspired by OpenClaw 2026.4.14 active-memory hidden untrusted
    prompt-prefix pattern: explicitly mark recall results as
    non-authoritative so the agent does not treat snippets as ground truth.
    Aligns with the Source-First decision prior used in many SOUL.md files.

    `hits` may be empty when this is an always-on (no-keyword) recall —
    the header reflects that.
    """
    if hits:
        header = f"Memory-search hard-trigger keywords: {', '.join(hits)} (mode={mode})"
    else:
        header = f"Always-on proactive recall (no keyword fired; mode={mode})"

    good = [r for r in results if r.get("score", 0) >= min_score]

    # Untrusted recall banner — printed in every branch
    trust_banner = (
        "⚠️ MEMORY_RECALL — non-authoritative. Snippets are summarized from past "
        "journal/notes; **factual claims (paths, versions, status, IPs, configs) "
        "MUST be verified by Read-ing the source file** before you act on them."
    )

    if not good:
        return (
            header
            + ". Auto-search returned no high-confidence results. If you need"
            + " more context, run manually:\n"
            + '  python3 scripts/memory-search-hybrid.py "<keyword>" --days 90 --top 10\n\n'
            + trust_banner
        )

    lines = [
        header
        + f". Auto-searched and injected top {len(good)} results"
        + " (domain-reranked, deduped by category):",
        trust_banner,
    ]
    if prefixes:
        shown = ", ".join(prefixes[:4]) + ("..." if len(prefixes) > 4 else "")
        lines.append(f"  Expected domain: {shown}")
    lines.append("")
    for i, r in enumerate(good, 1):
        score = r.get("score", 0)
        file_ = r.get("file", "?")
        date = r.get("date", "?")
        marker = "✓" if r.get("_domain_match") else " "
        snippet = (r.get("snippet", "") or "").replace("\n", " ")[:160]
        # path is absolute (for Read), file is relative (for human readability)
        verify_path = r.get("path", file_)
        lines.append(f"[{i}]{marker} {file_} (score={score:.2f}, {date})")
        lines.append(f"    {snippet}")
        lines.append(f"    verify: Read {verify_path}")
    lines.append("")
    lines.append(
        "If you need deeper context, Read the specific files. "
        "**Do NOT treat the snippets above as facts** — verify before acting."
    )
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = payload.get("prompt", "") or ""
    if not prompt:
        return 0

    # === Three trigger signals ===
    hits = detect_hits(prompt)
    graph_ids = detect_graph_nodes(prompt)
    substantive = is_substantive_prompt(prompt)
    always_on = (not hits) and substantive and ALWAYS_ON_TOP > 0

    if not hits and not graph_ids and not always_on:
        return 0  # nothing to do, silent exit

    sections: list[str] = []
    access_events: list[dict] = []

    # === Section 1: memory-search recall (keyword OR always-on) ===
    if hits or always_on:
        mode = classify_query(prompt)
        if hits:
            params = MODE_PARAMS[mode]
            min_score = MIN_SCORE
            top_limit = params["top"]
        else:
            params = {"days": ALWAYS_ON_DAYS, "top": ALWAYS_ON_TOP}
            min_score = ALWAYS_ON_MIN_SCORE
            top_limit = ALWAYS_ON_TOP

        query = prompt[:200].strip()
        raw_results = run_search_cached(
            query,
            days=params["days"],
            top=max(top_limit * 2, 10),
        )

        prefixes = expected_prefixes(hits) if hits else []
        reranked = rerank_by_domain(raw_results, prefixes)
        deduped = dedupe_by_category(reranked, limit=top_limit)

        good = [r for r in deduped if r.get("score", 0) >= min_score]
        # Always-on prints nothing on empty — keyword mode still prints
        # the "no high-confidence result" header so the user knows the
        # hook fired.
        if hits or good:
            sections.append(format_context(hits, mode, prefixes, deduped, min_score=min_score))
            for r in good:
                f = r.get("file") or r.get("path")
                if f:
                    access_events.append({
                        "file": f,
                        "kind": "search",
                        "score": round(r.get("score", 0), 3),
                    })

    # === Section 2: graph 1-hop associative recall ===
    if graph_ids:
        section = graph_traversal_section(graph_ids)
        if section:
            sections.append(section)
            g = load_graph()
            if g:
                for nid in graph_ids:
                    src = g["nodes"].get(nid, {}).get("source_file")
                    if src:
                        access_events.append({
                            "file": src,
                            "kind": "graph",
                            "node_id": nid,
                        })

    if not sections:
        return 0

    log_access(access_events)
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n\n".join(sections),
            }
        },
        sys.stdout,
    )
    return 0


# ============================================================================
# Self-test — `python3 memory-search-trigger.py --self-test`
# ============================================================================

def _self_test() -> int:
    """Pure-function tests for the framework. Does NOT spawn a real search.
    Returns 0 on success, non-zero on first failure."""
    # `assert` would short-circuit; collect failures so we see all of them.
    failures: list[str] = []

    def check(label: str, got, want):
        if got != want:
            failures.append(f"FAIL {label}: got {got!r}, want {want!r}")
        else:
            print(f"OK   {label}")

    # detect_hits
    check(
        "detect_hits english phrase",
        detect_hits("Last time we talked about the credentials"),
        sorted({"last time", "credentials"}),
    )
    check(
        "detect_hits chinese phrase",
        detect_hits("還記得上次的連線資訊嗎"),
        sorted({"還記得", "上次", "連線"}),
    )
    check(
        "detect_hits word boundary",
        detect_hits("What's the IP of the prod box?"),
        ["IP"],
    )
    check(
        "detect_hits no match",
        detect_hits("How does merge sort work?"),
        [],
    )

    # classify_query
    check("classify_query historical", classify_query("Last time we shipped"), "historical")
    check("classify_query recent", classify_query("Is the latest version ready?"), "recent")
    check("classify_query default", classify_query("Run the script"), "default")
    check("classify_query historical-zh", classify_query("還記得上週的事"), "historical")
    check("classify_query recent-zh", classify_query("最新的版本"), "recent")

    # expected_prefixes — uses the live DOMAIN_MAP, but with a temp override.
    saved_map = DOMAIN_MAP.copy()
    try:
        DOMAIN_MAP.clear()
        DOMAIN_MAP.update(
            {
                "alpha": ["areas/tech/", "MEMORY.md"],
                "beta": ["resources/beta/"],
            }
        )
        check(
            "expected_prefixes single hit",
            expected_prefixes(["alpha"]),
            ["MEMORY.md", "areas/tech/"],
        )
        check(
            "expected_prefixes union",
            expected_prefixes(["alpha", "beta"]),
            ["MEMORY.md", "areas/tech/", "resources/beta/"],
        )
        check(
            "expected_prefixes unmapped keyword",
            expected_prefixes(["unknown"]),
            [],
        )

        # rerank_by_domain
        sample = [
            {"file": "areas/tech/foo.md", "score": 0.6},
            {"file": "resources/other.md", "score": 0.7},
            {"file": "MEMORY.md", "score": 0.5},
        ]
        reranked = rerank_by_domain(sample, ["areas/tech/", "MEMORY.md"])
        check(
            "rerank_by_domain order",
            [r["file"] for r in reranked],
            ["areas/tech/foo.md", "MEMORY.md", "resources/other.md"],
        )
        check(
            "rerank_by_domain match flags",
            [r["_domain_match"] for r in reranked],
            [True, True, False],
        )
        check(
            "rerank_by_domain noop without prefixes",
            rerank_by_domain(sample, []),
            sample,
        )
    finally:
        DOMAIN_MAP.clear()
        DOMAIN_MAP.update(saved_map)

    # category_of
    check("category_of memory-index", category_of("MEMORY.md"), "memory-index")
    check("category_of memory-system", category_of("reflections.md"), "memory-system")
    check("category_of journal", category_of("2026-04-14.md"), "journal")
    check("category_of journal-archive", category_of("archive-2026-03/2026-03-15.md"), "journal-archive")
    check("category_of areas", category_of("areas/tech/foo.md"), "areas")
    check("category_of unknown root", category_of("nope.md"), "nope.md")

    # dedupe_by_category
    sample2 = [
        {"file": "areas/tech/a.md", "score": 0.9},
        {"file": "areas/tech/b.md", "score": 0.7},  # same category, lower score
        {"file": "resources/x.md", "score": 0.8},
        {"file": "MEMORY.md", "score": 0.4},
    ]
    deduped = dedupe_by_category(sample2, limit=10)
    check(
        "dedupe_by_category keeps best per category",
        sorted(r["file"] for r in deduped),
        sorted({"areas/tech/a.md", "resources/x.md", "MEMORY.md"}),
    )
    check(
        "dedupe_by_category honors limit",
        len(dedupe_by_category(sample2, limit=2)),
        2,
    )

    # is_substantive_prompt
    check("is_substantive_prompt long enough", is_substantive_prompt("Tell me about the thing"), True)
    check("is_substantive_prompt too short", is_substantive_prompt("hi"), False)
    check("is_substantive_prompt slash command", is_substantive_prompt("/clear"), False)
    check("is_substantive_prompt slash with arg", is_substantive_prompt("/note hello world"), True)
    check("is_substantive_prompt trivial reply", is_substantive_prompt("ok"), False)
    check("is_substantive_prompt chinese trivial", is_substantive_prompt("嗯"), False)
    check("is_substantive_prompt chinese substantive", is_substantive_prompt("看一下這個是怎麼回事"), True)

    # graph helpers — None-safe path (no graph file present)
    saved_proj = globals()["PROJECT_DIR"]
    try:
        globals()["PROJECT_DIR"] = "/nonexistent-graph-test-dir"
        load_graph.cache_clear()
        check("load_graph missing returns None", load_graph(), None)
        check("detect_graph_nodes empty when no graph", detect_graph_nodes("anything"), [])
        check("graph_traversal_section empty when no nodes", graph_traversal_section([]), "")
    finally:
        globals()["PROJECT_DIR"] = saved_proj
        load_graph.cache_clear()

    if failures:
        print()
        for f in failures:
            print(f)
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nAll self-tests passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        sys.exit(_self_test())
    sys.exit(main())
