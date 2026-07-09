#!/usr/bin/env python3
"""skill_fail_capture — capture a real skill failure into a per-skill regression corpus.

Failure-triggered entry point for the RSI chain: this feeds the eval cases that
evolve_skill.py --eval-cases --reuse-cases evolves against, and skill_evolve_apply.py
then gates keep/revert. (evolve_skill.py on its own polishes against LLM-synthesized
eval cases, which drift; this pins regressions to observed real failures.)

Two-layer storage (per skill):
  .claude/skills/<skill>/regression/raw.jsonl       append-only audit (one event per capture)
  .claude/skills/<skill>/regression/eval_cases.json deduped JSON array, fed directly to
                                                    evolve_skill.py --eval-cases --reuse-cases

**This script is deterministic and calls no LLM** (unit-testable). "Compiling" a raw
{input, bad_output, expected} into judge-facing criteria[]/bad_signals[] is the caller's
job — derived by the agent when interactive, or by the configured lightweight LLM endpoint
when run from cron. The caller passes the result via --criteria / --bad-signals;
bad_signals should be seeded with the actual observed symptoms.

eval_cases.json schema matches evolve_skill.py's judge: each item is
{id, task, criteria[], bad_signals[]}.

Dedup: normalize(skill+input+expected) -> sha256. A repeat of the same key only appends a
raw event (tagged duplicate_of); it adds no new eval case, so one recurring failure can't
flood the corpus and over-fit the skill.

Usage:
  skill_fail_capture.py --skill <name> --input <text> --bad-output <text> --expected <text>
      --criteria '["..."]' --bad-signals '["..."]' [--notes <text>] [--category <text>]
      [--repo <path>] [--dry-run]
  skill_fail_capture.py --skill <name> --list        # print this skill's corpus summary
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def repo_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    # scripts/ parent = repo root
    return Path(__file__).resolve().parent.parent


def normalize_text(s: str) -> str:
    """Case-insensitive + whitespace-collapsed, so semantically identical captures dedup."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def dedup_key(skill: str, input_text: str, expected: str) -> str:
    payload = "\x1f".join(normalize_text(x) for x in (skill, input_text, expected))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def regression_dir(root: Path, skill: str) -> Path:
    return root / ".claude" / "skills" / skill / "regression"


def load_eval_cases(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a JSON array (evolve_skill.py expects an array)")
    return data


def eval_case_ids(cases: list[dict]) -> set[str]:
    return {str(c.get("id", "")) for c in cases}


def build_eval_case(key: str, input_text: str, criteria: list[str], bad_signals: list[str]) -> dict:
    return {
        "id": f"reg_{key[:12]}",
        "task": input_text,
        "criteria": list(criteria),
        "bad_signals": list(bad_signals),
    }


def capture(
    root: Path,
    skill: str,
    input_text: str,
    bad_output: str,
    expected: str,
    criteria: list[str],
    bad_signals: list[str],
    notes: str = "",
    category: str | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict:
    """Run one capture. Returns {is_new, dedup_key, eval_case_id, raw_event, corpus_size}."""
    key = dedup_key(skill, input_text, expected)
    eval_id = f"reg_{key[:12]}"
    rdir = regression_dir(root, skill)
    eval_path = rdir / "eval_cases.json"
    raw_path = rdir / "raw.jsonl"

    cases = load_eval_cases(eval_path)
    existing_ids = eval_case_ids(cases)
    is_new = eval_id not in existing_ids

    ts = (now or datetime.now(timezone.utc)).isoformat()
    raw_event = {
        "schema_version": SCHEMA_VERSION,
        "id": f"fail_{re.sub(r'[^0-9]', '', ts)[:14]}_{key[:8]}",
        "ts": ts,
        "skill": skill,
        "skill_path": f".claude/skills/{skill}/SKILL.md",
        "input": input_text,
        "bad_output": bad_output,
        "expected": expected,
        "source": "manual:/skill-fail",
        "dedup_key": key,
        "duplicate_of": None if is_new else eval_id,
        "notes": notes,
        "category": category,
    }

    appended = False
    if not dry_run:
        rdir.mkdir(parents=True, exist_ok=True)
        with raw_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(raw_event, ensure_ascii=False) + "\n")
        if is_new:
            cases.append(build_eval_case(key, input_text, criteria, bad_signals))
            appended = True
            eval_path.write_text(
                json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    # After write, cases already holds the new case (appended=True); on dry-run add +1
    # as the "would become" estimate.
    corpus_size = len(cases) + (1 if is_new and not appended else 0)
    return {
        "is_new": is_new,
        "dedup_key": key,
        "eval_case_id": eval_id,
        "raw_event": raw_event,
        "corpus_size": corpus_size,
    }


def summarize(root: Path, skill: str) -> dict:
    rdir = regression_dir(root, skill)
    cases = load_eval_cases(rdir / "eval_cases.json")
    raw_path = rdir / "raw.jsonl"
    raw_n = 0
    if raw_path.exists():
        raw_n = sum(1 for ln in raw_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    return {
        "skill": skill,
        "deduped_eval_cases": len(cases),
        "raw_events": raw_n,
        "p3_ready": len(cases) >= 5,  # >=5 deduped cases before considering a cron real-corpus basis
        "eval_cases_path": str(rdir / "eval_cases.json"),
    }


def _parse_json_list(s: str, flag: str) -> list[str]:
    try:
        v = json.loads(s)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{flag} is not valid JSON: {e}")
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise SystemExit(f"{flag} must be a string array, e.g. '[\"a\",\"b\"]'")
    return v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="capture a real skill failure into per-skill regression corpus")
    ap.add_argument("--skill", required=True)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--list", action="store_true", help="print this skill's corpus summary and exit")
    ap.add_argument("--input")
    ap.add_argument("--bad-output")
    ap.add_argument("--expected")
    ap.add_argument("--criteria", help='JSON string array: what a correct output should ensure')
    ap.add_argument("--bad-signals", help='JSON string array: symptoms that must NOT appear (seed with the observed bad_output)')
    ap.add_argument("--notes", default="")
    ap.add_argument("--category", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root = repo_root(args.repo)

    if args.list:
        print(json.dumps(summarize(root, args.skill), ensure_ascii=False, indent=2))
        return 0

    missing = [k for k in ("input", "bad_output", "expected", "criteria", "bad_signals")
               if getattr(args, k) in (None, "")]
    if missing:
        ap.error(f"missing required args: {', '.join('--' + m.replace('_', '-') for m in missing)}")

    criteria = _parse_json_list(args.criteria, "--criteria")
    bad_signals = _parse_json_list(args.bad_signals, "--bad-signals")

    res = capture(
        root=root,
        skill=args.skill,
        input_text=args.input,
        bad_output=args.bad_output,
        expected=args.expected,
        criteria=criteria,
        bad_signals=bad_signals,
        notes=args.notes,
        category=args.category,
        dry_run=args.dry_run,
    )
    verb = "DRY-RUN" if args.dry_run else ("NEW eval case" if res["is_new"] else "DUPLICATE (raw only)")
    print(f"[skill-fail] {verb} · skill={args.skill} · eval_id={res['eval_case_id']} · corpus={res['corpus_size']}")
    if not res["is_new"]:
        print(f"[skill-fail] same failure already in corpus (dedup_key={res['dedup_key'][:12]}), raw only, no new eval case")
    return 0


if __name__ == "__main__":
    sys.exit(main())
