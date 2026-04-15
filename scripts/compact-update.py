#!/usr/bin/env python3
"""
compact-update.py — Generate MEMORY_COMPACT.md from MEMORY.md.

Philosophy:
  MEMORY.md is the human-readable long-term store. MEMORY_COMPACT.md is the
  lightweight wake-up context (~250 tokens) that gets loaded every session.
  This script keeps them in sync.

Design:
  Instead of hard-coding section names, the script looks for HTML marker pairs
  inside MEMORY.md. Everything between the markers is copied verbatim into
  MEMORY_COMPACT.md. This lets each workspace decide its own compact format.

  Markers in MEMORY.md:
    <!-- compact:start -->
    ... content that should appear in MEMORY_COMPACT.md ...
    <!-- compact:end -->

  Optional: recent events get appended automatically when a "Recent" or
  "Events Timeline" section exists (top N bullets).

  If CLAUDE.md contains a matching marker pair, the compact block is also
  mirrored there so the AAAK-style quick context stays in sync.

Usage:
  python3 compact-update.py                    # run in current workspace
  python3 compact-update.py --workspace /path  # explicit workspace root
  python3 compact-update.py --recent-count 5   # how many recent events to pull
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

COMPACT_START = "<!-- compact:start -->"
COMPACT_END = "<!-- compact:end -->"
RECENT_HEADERS = ("Recent", "Events Timeline", "Timeline", "L1_RECENT")


def _strip_fenced_code_blocks(text: str) -> str:
    """Replace every ``` ... ``` (and ~~~ ... ~~~) block with equal-length
    whitespace so regex searches later don't accidentally match markers
    that the user quoted inside example code. We preserve the length so
    line numbers and offsets stay stable in case the caller needs them."""
    fence_re = re.compile(r"(```|~~~)[^\n]*\n.*?\1", re.DOTALL)
    return fence_re.sub(lambda m: " " * len(m.group(0)), text)


def extract_block(text: str, start: str, end: str) -> str | None:
    scrubbed = _strip_fenced_code_blocks(text)
    pattern = re.escape(start) + r"(.*?)" + re.escape(end)
    m = re.search(pattern, scrubbed, re.DOTALL)
    if not m:
        return None
    # Use the offsets from the scrubbed text but slice the original so we
    # return the user's real content (trimmed).
    return text[m.start(1):m.end(1)].strip()


def extract_recent(memory_text: str, count: int) -> list[str]:
    """Pull top N bullet items from the first Recent/Timeline section."""
    for header in RECENT_HEADERS:
        pattern = rf"^#{{1,3}}\s+{re.escape(header)}.*?$(.*?)(?=^#{{1,3}}\s|\Z)"
        m = re.search(pattern, memory_text, re.MULTILINE | re.DOTALL)
        if not m:
            continue
        body = m.group(1)
        bullets = re.findall(r"^\s*[-*]\s+(.+)$", body, re.MULTILINE)
        if bullets:
            return bullets[:count]
    return []


def build_compact(memory_text: str, recent_count: int) -> str | None:
    block = extract_block(memory_text, COMPACT_START, COMPACT_END)
    if block is None:
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    out = [
        "# MEMORY_COMPACT.md",
        f"# Auto-generated from MEMORY.md on {today}. Do not edit by hand.",
        "# To change content: edit the `<!-- compact:start -->` block inside MEMORY.md.",
        "",
        block,
    ]

    recent = extract_recent(memory_text, recent_count)
    if recent:
        out.append("")
        out.append("## Recent")
        out.extend(f"- {line.strip()}" for line in recent)

    out.append("")
    out.append(f"---\n*Last updated: {today}*")
    return "\n".join(out)


def mirror_into_claude_md(claude_path: Path, block: str) -> bool:
    """Replace content between compact markers inside CLAUDE.md if present."""
    if not claude_path.exists():
        return False
    text = claude_path.read_text(encoding="utf-8")
    pattern = re.escape(COMPACT_START) + r".*?" + re.escape(COMPACT_END)
    replacement = f"{COMPACT_START}\n{block}\n{COMPACT_END}"
    new_text = re.sub(pattern, replacement, text, flags=re.DOTALL)
    if new_text == text:
        return False
    claude_path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--workspace",
        default=None,
        help="Workspace root (defaults to parent of this script's directory)",
    )
    ap.add_argument("--recent-count", type=int, default=6)
    args = ap.parse_args()

    workspace = (
        Path(args.workspace).resolve()
        if args.workspace
        else Path(__file__).resolve().parent.parent
    )
    memory_path = workspace / "MEMORY.md"
    compact_path = workspace / "MEMORY_COMPACT.md"
    claude_path = workspace / "CLAUDE.md"

    if not memory_path.exists():
        print(f"error: {memory_path} not found", file=sys.stderr)
        return 1

    memory_text = memory_path.read_text(encoding="utf-8")
    compact = build_compact(memory_text, args.recent_count)
    if compact is None:
        print(
            f"error: no '{COMPACT_START}' ... '{COMPACT_END}' block found in MEMORY.md",
            file=sys.stderr,
        )
        print(
            "hint: wrap the content you want in MEMORY_COMPACT.md with those markers.",
            file=sys.stderr,
        )
        return 2

    compact_path.write_text(compact, encoding="utf-8")
    print(f"wrote {compact_path} ({len(compact)} chars)")

    block = extract_block(memory_text, COMPACT_START, COMPACT_END) or ""
    if mirror_into_claude_md(claude_path, block):
        print(f"mirrored compact block into {claude_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
