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
  4. 60s TTL cache — repeated prompts don't re-spawn the search process.

The keyword lists, hints, and domain map are intentionally minimal in
this template. **Edit the CUSTOMIZE section below for your workspace.**

Wire it up in `.claude/settings.json`:

    "hooks": {
      "UserPromptSubmit": [{
        "hooks": [{
          "type": "command",
          "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/memory-search-trigger.py\"",
          "timeout": 5
        }]
      }]
    }

`$CLAUDE_PROJECT_DIR` is set by Claude Code to the workspace root. Using
it makes the hook robust against cwd drift (e.g. an earlier Bash call
that `cd`'d into a subdirectory and never restored cwd).

Self-test: `python3 memory-search-trigger.py --self-test` runs the
framework's pure-function tests without making a real search call.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

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
    # names. Examples:
    #   "MyProject", "production-db", "staging-cluster", "vendor-foo",

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
CACHE_TTL_SEC      = 60      # don't re-run a search whose results are this fresh
SEARCH_TIMEOUT_SEC = 6       # subprocess timeout for memory-search-hybrid.py

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
) -> str:
    """Build the additionalContext string injected into the next turn."""
    header = f"Memory-search hard-trigger keywords: {', '.join(hits)} (mode={mode})"

    good = [r for r in results if r.get("score", 0) >= MIN_SCORE]

    if not good:
        return (
            header
            + ". Auto-search returned no high-confidence results. If you need"
            + " more context, run manually:\n"
            + '  python3 scripts/memory-search-hybrid.py "<keyword>" --days 90 --top 10'
        )

    lines = [
        header
        + f". Auto-searched and injected top {len(good)} results"
        + " (domain-reranked, deduped by category):"
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
        lines.append(f"[{i}]{marker} {file_} (score={score:.2f}, {date})")
        lines.append(f"    {snippet}")
    lines.append("")
    lines.append("If you need deeper context, Read/Grep the specific files.")
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = payload.get("prompt", "") or ""
    if not prompt:
        return 0

    hits = detect_hits(prompt)
    if not hits:
        return 0

    mode = classify_query(prompt)
    params = MODE_PARAMS[mode]

    # Pull more raw results than we need so the rerank + dedupe stages have
    # something to work with. `top * 2` (min 10) is a reasonable buffer.
    query = prompt[:200].strip()
    raw_results = run_search_cached(
        query,
        days=params["days"],
        top=max(params["top"] * 2, 10),
    )

    prefixes = expected_prefixes(hits)
    reranked = rerank_by_domain(raw_results, prefixes)
    deduped = dedupe_by_category(reranked, limit=params["top"])

    reminder = format_context(hits, mode, prefixes, deduped)
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": reminder,
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
