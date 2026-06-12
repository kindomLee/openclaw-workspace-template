#!/usr/bin/env python3
"""
Generic skill evolution script.
Usage: evolve_skill.py --skill SKILL.md --output DIR [--iterations N] [--eval-cases FILE] [--reuse-cases]

Eval case lifecycle:
    1. If --eval-cases FILE is given and exists → use it (canonical, won't regenerate).
    2. Else if <output_dir>/eval_cases.json exists → reuse it (from a prior run).
    3. Else → auto-generate from SKILL.md and persist to <output_dir>/eval_cases.json.

    With --reuse-cases, step 3 is disabled: refuses to auto-generate, forcing the
    user to either supply --eval-cases or pre-populate <output_dir>/eval_cases.json.

    Why this matters: eval cases are LLM-generated and non-deterministic. Across
    different runs of the same SKILL.md, baseline scores can drift ±20 points
    just from drawing different cases. To compare deltas reliably (baseline vs
    evolved, or across skills), pin the eval set with --reuse-cases.
"""

import argparse
import os
import json
import re
import statistics
import time
import httpx
from datetime import datetime
from difflib import unified_diff
from pathlib import Path

# Any Anthropic-compatible /v1/messages endpoint works (Anthropic, MiniMax, self-hosted proxy).
API_URL = os.environ.get("LLM_API_URL", "https://api.minimax.io/anthropic/v1/messages")
API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("MINIMAX_API_KEY") or ""
if not API_KEY:
    raise SystemExit("LLM_API_KEY (or legacy MINIMAX_API_KEY) not set")
MODEL = os.environ.get("LLM_MODEL", "MiniMax-M3")

# Timeouts scale with task complexity
TIMEOUT_EVAL = 90       # Eval: short output but thinking takes time
TIMEOUT_EVOLVE = 300    # Evolve: full SKILL.md generation, needs room
TIMEOUT_GENERATE = 180  # Eval case generation

# Retry config
MAX_RETRIES = 2
RETRY_DELAY = 5


def call_llm(prompt: str, max_tokens: int = 4000, timeout: int = 90) -> str:
    """Call MiniMax with retry on timeout/transient errors."""
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = httpx.post(
                API_URL,
                headers={
                    "x-api-key": API_KEY,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": MODEL,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content")
            if content:
                for c in content:
                    if c.get("type") == "text":
                        return c["text"]
                for c in content:
                    if c.get("type") == "thinking":
                        return c.get("thinking", "")
            if data.get("stop_reason") == "max_tokens":
                return '{"score": 50, "feedback": "truncated"}'
            raise RuntimeError(f"No text in response: {json.dumps(data)[:200]}")

        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            last_err = e
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"    ⏳ Timeout (attempt {attempt+1}/{MAX_RETRIES+1}), retry in {wait}s...")
                time.sleep(wait)
            else:
                raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 500, 502, 503, 504):
                last_err = e
                if attempt < MAX_RETRIES:
                    # Respect Retry-After if present
                    retry_after = int(e.response.headers.get("retry-after", RETRY_DELAY * (attempt + 1)))
                    print(f"    ⏳ HTTP {e.response.status_code} (attempt {attempt+1}), retry in {retry_after}s...")
                    time.sleep(retry_after)
                else:
                    raise
            else:
                raise


def generate_eval_cases(skill_text: str, skill_name: str) -> list:
    """Auto-generate eval cases from skill content."""
    prompt = f"""You are an AI skill evaluator. Given a SKILL.md, generate 5 evaluation test cases.

SKILL.md ({skill_name}):
---
{skill_text[:4000]}
---

Generate 5 JSON test cases. Each has:
- "id": number (1-5)
- "task": a realistic user request this skill should handle
- "criteria": list of 4-5 things the skill should ensure
- "bad_signals": list of 3-5 things that should NOT appear in output

Respond ONLY with a JSON array. No commentary."""

    raw = call_llm(prompt, max_tokens=2000, timeout=TIMEOUT_GENERATE)
    match = re.search(r'\[[\s\S]*\]', raw)
    if match:
        return json.loads(match.group())
    raise RuntimeError(f"Could not parse eval cases: {raw[:200]}")


def evaluate_skill(skill_text: str, case: dict) -> dict:
    # Truncate skill for very long files to keep eval focused
    skill_excerpt = skill_text[:3500]
    prompt = f"""You are a strict skill evaluator. Score how well this SKILL.md would guide an AI for the given task.
Score 0-100. Check each criterion and bad_signal.

SKILL.md:
---
{skill_excerpt}
---

Task: {case['task']}
Criteria: {json.dumps(case['criteria'], ensure_ascii=False)}
Bad signals (should NOT appear): {json.dumps(case['bad_signals'], ensure_ascii=False)}

Respond ONLY with JSON: {{"score": N, "feedback": "brief"}}"""

    raw = call_llm(prompt, max_tokens=1000, timeout=TIMEOUT_EVAL)
    try:
        match = re.search(r'\{[^}]*"score"[^}]*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return {"score": int(result["score"]), "feedback": str(result.get("feedback", ""))[:200]}
        score_match = re.search(r'"?score"?\s*[:=]\s*(\d+)', raw)
        if score_match:
            return {"score": int(score_match.group(1)), "feedback": raw[:100]}
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return {"score": 50, "feedback": f"parse error: {raw[:80]}"}


def run_evaluation(skill_text: str, eval_cases: list) -> dict:
    results = []
    for case in eval_cases:
        try:
            result = evaluate_skill(skill_text, case)
        except Exception as e:
            print(f"    Case {case['id']}: ERROR ({e})")
            result = {"score": 50, "feedback": f"error: {str(e)[:80]}"}
        results.append({
            "case_id": case["id"],
            "task": case["task"],
            "score": result["score"],
            "feedback": result["feedback"],
        })
        print(f"    Case {case['id']}: {result['score']}/100")
    avg = sum(r["score"] for r in results) / len(results)
    return {"case_results": results, "average_score": avg}


def evolve_skill(current_skill: str, eval_results: dict, iteration: int) -> str:
    feedback = "\n".join(
        [f"- Case {r['case_id']} ({r['score']}): {r['feedback']}" for r in eval_results["case_results"]]
    )
    prompt = f"""You are an expert at writing AI agent skill definitions.
Improve this SKILL.md based on evaluation feedback.
Keep ALL technical content (commands, paths, config). Make rules clearer and more enforceable.
Output ONLY the improved SKILL.md content, nothing else.

Feedback (avg {eval_results['average_score']:.0f}/100):
{feedback}

Current SKILL.md (iteration {iteration}):
{current_skill}"""

    improved = call_llm(prompt, max_tokens=4000, timeout=TIMEOUT_EVOLVE)
    improved = re.sub(r'^```(?:markdown)?\n', '', improved)
    improved = re.sub(r'\n```$', '', improved)
    return improved.strip()


def save_results(output_dir: Path, history: list, original: str):
    """Save results at any point (called after each iteration for crash safety)."""
    best = max(history, key=lambda x: x["avg_score"])
    delta = best["avg_score"] - history[0]["avg_score"]

    diff = list(unified_diff(
        original.splitlines(keepends=True),
        best["skill_text"].splitlines(keepends=True),
        fromfile="original", tofile=f"best (iter {best['iteration']})", n=2,
    ))
    diff_text = "".join(diff) if diff else "(no changes)"

    def _case_scores(h: dict) -> list:
        """Extract per-case scores from a history entry's results."""
        cr = h.get("results", {}).get("case_results", [])
        return [
            {"case_id": c.get("case_id"), "score": c.get("score"), "feedback": c.get("feedback", "")[:200]}
            for c in cr
        ]

    results_json = {
        "skill": history[0].get("skill_name", "unknown"),
        "baseline": history[0]["avg_score"],
        "best_score": best["avg_score"],
        "best_iteration": best["iteration"],
        "delta": delta,
        "iterations": len(history) - 1,
        "timestamp": datetime.now().isoformat(),
        "history": [
            {
                "iter": h["iteration"],
                "score": h["avg_score"],
                "n_runs": h.get("n_runs", 1),
                "run_scores": h.get("run_scores", [h["avg_score"]]),
                "case_scores": _case_scores(h),
            }
            for h in history
        ],
    }
    (output_dir / "results.json").write_text(json.dumps(results_json, indent=2))
    (output_dir / "diff.patch").write_text(diff_text)
    (output_dir / "best_skill.md").write_text(best["skill_text"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True, help="Path to SKILL.md")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--eval-cases", help="Path to eval cases JSON (auto-generated if absent)")
    parser.add_argument(
        "--reuse-cases",
        action="store_true",
        help=(
            "Refuse to auto-generate eval cases. Forces deterministic comparison: "
            "either --eval-cases must point to a real file, or "
            "<output_dir>/eval_cases.json must already exist from a prior run."
        ),
    )
    parser.add_argument(
        "--n-runs",
        type=int,
        default=1,
        help=(
            "Number of baseline evaluation runs (default 1). When >1, scores the "
            "skill N times against the same eval cases and uses the median as the "
            "representative baseline. Required to cut LLM judge noise (empirical "
            "per-skill range up to ±12 across single runs). Recommended: 3."
        ),
    )
    args = parser.parse_args()

    skill_path = Path(args.skill)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    skill_name = skill_path.parent.name

    original = skill_path.read_text()
    print(f"Skill: {skill_name} ({len(original)} chars, {len(original.splitlines())} lines)")

    # Load or generate eval cases
    eval_cases_path = output_dir / "eval_cases.json"
    if args.eval_cases and Path(args.eval_cases).exists():
        eval_cases = json.loads(Path(args.eval_cases).read_text())
        print(f"Reusing eval cases from {args.eval_cases}")
    elif eval_cases_path.exists():
        eval_cases = json.loads(eval_cases_path.read_text())
        print(f"Reusing eval cases from {eval_cases_path}")
    elif args.reuse_cases:
        raise SystemExit(
            f"--reuse-cases set but no eval cases found.\n"
            f"  Tried: {args.eval_cases or '(--eval-cases not given)'}\n"
            f"  Tried: {eval_cases_path}\n"
            f"  Either pre-populate one or drop --reuse-cases to auto-generate."
        )
    else:
        print("Generating eval cases...")
        eval_cases = generate_eval_cases(original, skill_name)
        eval_cases_path.write_text(json.dumps(eval_cases, ensure_ascii=False, indent=2))
        print(f"Generated {len(eval_cases)} eval cases → {eval_cases_path}")

    history = []

    # Baseline (with optional N-runs median to dampen judge noise)
    n_runs = max(1, args.n_runs)
    print(f"\n[Iter 0] Baseline ({n_runs} run{'s' if n_runs > 1 else ''})...")
    baseline_runs = []
    for run_i in range(n_runs):
        if n_runs > 1:
            print(f"  Run {run_i + 1}/{n_runs}:")
        eval_r = run_evaluation(original, eval_cases)
        print(f"    → Average: {eval_r['average_score']:.1f}/100")
        baseline_runs.append(eval_r)
    run_scores = [r["average_score"] for r in baseline_runs]
    if n_runs > 1:
        representative = statistics.median(run_scores)
        print(
            f"  → Median: {representative:.1f}/100 (n={n_runs}, "
            f"range {max(run_scores) - min(run_scores):.1f})"
        )
    else:
        representative = run_scores[0]
    eval0 = {
        "average_score": representative,
        "case_results": baseline_runs[0]["case_results"],  # for evolve loop seed
        "all_runs": baseline_runs,
    }
    history.append({
        "iteration": 0, "skill_text": original,
        "avg_score": representative, "results": eval0,
        "skill_name": skill_name,
        "n_runs": n_runs,
        "run_scores": run_scores,
    })
    save_results(output_dir, history, original)

    current_skill = original
    for i in range(1, args.iterations + 1):
        print(f"\n[Iter {i}] Evolving...")
        try:
            current_skill = evolve_skill(current_skill, history[-1]["results"], i)
        except Exception as e:
            print(f"  Evolution failed: {e}")
            break

        # evolved 也走 n-runs median（與 baseline 對稱）——否則 delta = median(baseline)
        # − single(evolved)，evolved 單次評測的 ±12 噪音會讓 delta 失真（對抗審查 H1）。
        print(f"[Iter {i}] Evaluating ({len(current_skill)} chars, {n_runs} run{'s' if n_runs > 1 else ''})...")
        ev_runs = []
        for run_i in range(n_runs):
            if n_runs > 1:
                print(f"  Run {run_i + 1}/{n_runs}:")
            ev_runs.append(run_evaluation(current_skill, eval_cases))
        ev_scores = [r["average_score"] for r in ev_runs]
        ev_repr = statistics.median(ev_scores) if n_runs > 1 else ev_scores[0]
        eval_result = dict(ev_runs[0])
        eval_result["average_score"] = ev_repr
        eval_result["all_runs"] = ev_runs
        if n_runs > 1:
            print(f"  → Median: {ev_repr:.1f}/100 (n={n_runs}, range {max(ev_scores) - min(ev_scores):.1f})")
        else:
            print(f"  → Average: {ev_repr:.1f}/100")
        history.append({
            "iteration": i, "skill_text": current_skill,
            "avg_score": ev_repr, "results": eval_result,
            "skill_name": skill_name,
            "n_runs": n_runs, "run_scores": ev_scores,
        })
        # Save after every iteration (crash-safe)
        save_results(output_dir, history, original)

    # Final summary
    best = max(history, key=lambda x: x["avg_score"])
    delta = best["avg_score"] - history[0]["avg_score"]
    print(f"\n{'='*50}")
    print(f"Best: iter {best['iteration']} = {best['avg_score']:.1f} (baseline {history[0]['avg_score']:.1f}, delta {delta:+.1f})")
    print(f"Results: {output_dir}/")


if __name__ == "__main__":
    main()
