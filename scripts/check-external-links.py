#!/usr/bin/env python3
"""check-external-links — scan external URLs in notes/ and count only 404/410 as broken.

Timeouts, 403, 405, 429 and 5xx mean blocked or transient; they are listed as
"unverified" and never count toward the threshold. When broken >= threshold,
writes .claude/flags/broken-external-links.flag. If the network looks down
(more than half the URLs unreachable) it prints "skipped" and exits 0, keeping
the previous report and flag.

Usage: python3 scripts/check-external-links.py [--threshold N]
Env:   OPENCLAW_WORKSPACE / CLAUDE_PROJECT_DIR (workspace root, else script-relative)
       EXTERNAL_LINKS_THRESHOLD (default 5), EXTERNAL_LINKS_SKIP_HOSTS (comma-separated)
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE") or os.environ.get("CLAUDE_PROJECT_DIR")
            or Path(__file__).resolve().parent.parent)
NOTES = ROOT / "notes"
FLAG = ROOT / ".claude/flags/broken-external-links.flag"
REPORT = ROOT / ".claude/flags/broken-external-links-report.txt"

URL = re.compile(r'https?://[^\s)>"`～「」（）\]，。、；：！？]+')
FENCED = re.compile(r"```.*?```", re.DOTALL)
INLINE = re.compile(r"`[^`\n]*`")
# Login walls, POST-only APIs, or sites that answer 200 for dead links: checking them is meaningless.
# Add your own private / login-only hosts via EXTERNAL_LINKS_SKIP_HOSTS.
SKIP_HOSTS = {
    "localhost", "x.com", "twitter.com", "youtube.com", "www.youtube.com", "youtu.be",
    "api.anthropic.com", "api.openai.com", "fonts.googleapis.com", "fonts.gstatic.com",
    "api.telegram.org",
} | {h.strip().lower() for h in os.environ.get("EXTERNAL_LINKS_SKIP_HOSTS", "").split(",") if h.strip()}
SKIP_SUFFIXES = (".local", ".internal", ".lan", ".ts.net")
BROKEN = {404, 410}


def extract_urls(text: str) -> set[str]:
    text = INLINE.sub("", FENCED.sub("", text))
    return {re.sub(r"[.,;:!?'*_]+$", "", u) for u in URL.findall(text)}


def skip(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:  # e.g. `https://[placeholder` -> urlsplit raises Invalid IPv6 URL
        return True
    if not host or "." not in host or host in SKIP_HOSTS or host.endswith(SKIP_SUFFIXES):
        return True
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return False


def classify(status: int | None) -> str:
    if status in BROKEN:
        return "broken"
    if status is not None and status < 400:
        return "ok"
    return "unverified"


def fetch(url: str) -> int | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=int(os.environ.get("EXTERNAL_LINKS_THRESHOLD", 5)))
    args = ap.parse_args()

    sources: dict[str, str] = {}
    for md in sorted(NOTES.rglob("*.md")):
        if "04-Archive" in md.parts:
            continue
        for u in extract_urls(md.read_text(encoding="utf-8", errors="ignore")):
            sources.setdefault(u, str(md.relative_to(NOTES)))
    urls = sorted(u for u in sources if not skip(u))

    with ThreadPoolExecutor(max_workers=8) as ex:
        statuses = dict(zip(urls, ex.map(fetch, urls)))

    # More than half unreachable = network problem; keep last report and flag instead of overwriting with partial data
    down = sum(s is None for s in statuses.values())
    if urls and down * 2 > len(urls):
        print(f"[external-links] skipped: {down}/{len(urls)} URLs unreachable, network may be down")
        return 0

    groups: dict[str, list[str]] = {"broken": [], "unverified": []}
    for u, s in statuses.items():
        kind = classify(s)
        if kind in groups:
            groups[kind].append(f"  {sources[u]} → {u} ({s if s is not None else 'timeout'})")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        f"Broken external links (404/410): {len(groups['broken'])}\n" + "\n".join(groups["broken"])
        + f"\n\nUnverified (timeout/403/405/429/5xx, not counted): {len(groups['unverified'])}\n"
        + "\n".join(groups["unverified"]) + "\n",
        encoding="utf-8",
    )
    n = len(groups["broken"])
    print(f"[external-links] checked={len(urls)} broken={n} unverified={len(groups['unverified'])}")
    if n >= args.threshold:
        FLAG.write_text(
            f"notes/ has {n} external links returning 404/410 (threshold {args.threshold})\n"
            f"Read {REPORT.relative_to(ROOT)} for the list; fix the URL (new address or a Wayback copy) or remove it.\n"
            f"When done: rm {FLAG.relative_to(ROOT)}\n",
            encoding="utf-8",
        )
    else:
        FLAG.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
