#!/usr/bin/env python3
"""
memory-recall-bench.py — objective retrieval benchmark for the memory system.

Runs a golden set through memory-search-hybrid.py and reports
MRR / recall@k / mean-rank, listing misses. Read-only; never mutates memory.

The golden set is YOUR data, not shipped. A synthetic example lives at
scripts/recall-bench-golden-example.jsonl (schema documented inline). Copy it,
replace the rows with real queries → expected memory files, then point --golden
at your copy.

Golden line schema (one JSON object per line; "#"/blank lines ignored):
  {"id": "<short-id>", "query": "<search query>",
   "answers": ["<expected file path or basename>", ...]}
  - "answers" match against the "path" field of memory-search-hybrid.py --json
    results, by exact path or endswith (so a basename like "2026-01-15.md" works).

Usage:
  python3 scripts/memory-recall-bench.py [--golden PATH] [--days N] [--top N] [--json]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEARCH = ROOT / "scripts" / "memory-search-hybrid.py"
DEFAULT_GOLDEN = ROOT / "scripts" / "recall-bench-golden-example.jsonl"
K_VALUES = (1, 3, 5, 10)


def load_golden(path: Path) -> list:
    items = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            items.append(json.loads(ln))
    return items


def run_search(query: str, days: int, top: int) -> list:
    """Call memory-search-hybrid.py --json, return results list (score-sorted)."""
    proc = subprocess.run(
        [sys.executable, str(SEARCH), query, "--days", str(days), "--top", str(top), "--json"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"  ! search failed for query={query!r}: {proc.stderr.strip()[:200]}", file=sys.stderr)
        return []
    try:
        return json.loads(proc.stdout).get("results", [])
    except json.JSONDecodeError:
        print(f"  ! bad JSON for query={query!r}", file=sys.stderr)
        return []


def first_hit_rank(results: list, answers: list) -> int:
    """1-based rank of the first result matching any answer; 0 if none. endswith on abs path."""
    for idx, r in enumerate(results, start=1):
        p = r.get("path", "")
        for ans in answers:
            ans = ans.lstrip("/")
            if p == ans or p.endswith("/" + ans) or p.endswith(ans):
                return idx
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    ap.add_argument("--days", type=int, default=365, help="passed to search --days (default 365 neutralizes temporal penalty)")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true", help="emit scoreboard JSON")
    args = ap.parse_args()

    golden = load_golden(Path(args.golden))
    if not golden:
        print("golden set is empty", file=sys.stderr)
        sys.exit(1)

    per_query = []
    for g in golden:
        results = run_search(g["query"], args.days, args.top)
        rank = first_hit_rank(results, g["answers"])
        rr = 1.0 / rank if rank else 0.0
        top3 = [Path(r.get("path", "")).name for r in results[:3]]
        per_query.append({
            "id": g["id"], "query": g["query"], "answers": g["answers"],
            "rank": rank, "rr": round(rr, 4), "top3": top3,
        })

    n = len(per_query)
    mrr = sum(q["rr"] for q in per_query) / n
    recall = {k: sum(1 for q in per_query if q["rank"] and q["rank"] <= k) / n for k in K_VALUES}
    hits = [q["rank"] for q in per_query if q["rank"]]
    mean_rank = sum(hits) / len(hits) if hits else 0.0
    misses = [q for q in per_query if not q["rank"]]

    scoreboard = {
        "golden": str(args.golden), "n": n, "days": args.days, "top": args.top,
        "mrr": round(mrr, 4),
        "recall_at": {str(k): round(v, 4) for k, v in recall.items()},
        "mean_rank_hits": round(mean_rank, 2),
        "n_miss": len(misses),
        "per_query": per_query,
    }

    if args.json:
        print(json.dumps(scoreboard, ensure_ascii=False, indent=2))
        return

    print(f"=== Memory Recall Benchmark ===")
    print(f"golden={args.golden}  n={n}  days={args.days}  top={args.top}")
    print(f"MRR            : {mrr:.4f}")
    for k in K_VALUES:
        print(f"recall@{k:<2}      : {recall[k]:.3f}  ({sum(1 for q in per_query if q['rank'] and q['rank']<=k)}/{n})")
    print(f"mean-rank(hit) : {mean_rank:.2f}  (hits {len(hits)}/{n})")
    print()
    print(f"{'id':<18}{'rank':>5}   top-3 filenames")
    print("-" * 78)
    for q in per_query:
        rank_s = str(q["rank"]) if q["rank"] else "MISS"
        print(f"{q['id']:<18}{rank_s:>5}   {', '.join(q['top3'])}")
    if misses:
        print()
        print("=== MISS diagnosis ===")
        for q in misses:
            print(f"[{q['id']}] {q['query']}")
            print(f"    expected: {q['answers']}")
            print(f"    top3: {q['top3']}")


if __name__ == "__main__":
    main()
