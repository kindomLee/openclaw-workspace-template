#!/usr/bin/env python3
"""check-broken-wikilinks.py — standalone broken-wikilink detector.

Scans a single file (or the whole `notes/` tree) for `[[wikilinks]]` whose
targets do not exist. Pure regex, no external dependencies, no embeddings.

Usage:
    python3 scripts/check-broken-wikilinks.py notes/some-file.md
    python3 scripts/check-broken-wikilinks.py --all
    python3 scripts/check-broken-wikilinks.py --all --json

Intended for manual triage. The cron-flag pipeline
(`scripts/cron-broken-links-check.sh`) uses the same detection logic but
wraps it with threshold + flag writing.
"""
import argparse
import json
import re
import sys
from pathlib import Path

WIKI = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]")


def find_workspace() -> Path:
    return Path(__file__).resolve().parent.parent


def build_index(notes_root: Path):
    all_md = list(notes_root.rglob("*.md"))
    stems = {p.stem.lower() for p in all_md}
    basenames = {p.name.lower() for p in all_md}
    return all_md, stems, basenames


def scan_file(md: Path, stems: set, basenames: set) -> list[str]:
    broken: list[str] = []
    try:
        text = md.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return broken
    for m in WIKI.finditer(text):
        target = m.group(1).strip().split("/")[-1].lower()
        if not target:
            continue
        if target in stems or f"{target}.md" in basenames:
            continue
        broken.append(m.group(1).strip())
    return broken


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", nargs="?", help="A single .md file to scan")
    ap.add_argument("--all", action="store_true", help="Scan every .md under notes/")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    if not args.file and not args.all:
        ap.print_help()
        return 1

    workspace = find_workspace()
    notes_root = workspace / "notes"
    if not notes_root.is_dir():
        print(f"error: {notes_root} does not exist", file=sys.stderr)
        return 2

    _, stems, basenames = build_index(notes_root)

    results: list[dict] = []
    if args.all:
        for md in sorted(notes_root.rglob("*.md")):
            broken = scan_file(md, stems, basenames)
            if broken:
                results.append(
                    {"file": str(md.relative_to(notes_root)), "broken": broken}
                )
    else:
        md = Path(args.file).resolve()
        if not md.exists():
            print(f"error: {md} not found", file=sys.stderr)
            return 2
        broken = scan_file(md, stems, basenames)
        results.append(
            {
                "file": str(md.relative_to(notes_root))
                if md.is_relative_to(notes_root)
                else str(md),
                "broken": broken,
            }
        )

    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        return 0

    total = sum(len(r["broken"]) for r in results)
    if total == 0:
        print("no broken wikilinks found")
        return 0
    print(f"found {total} broken wikilinks:")
    for r in results:
        if not r["broken"]:
            continue
        print(f"  {r['file']}")
        for link in r["broken"]:
            print(f"    - [[{link}]]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
