#!/usr/bin/env python3
"""UserPromptSubmit hook: force a memory search when hard-trigger keywords hit.

The goal is to remove "should I search memory?" as a judgment call. Any time
the user mentions a tracked proper noun, a cross-host intent, or a temporal
reference, we inject a reminder telling Claude to run the memory-search
script before answering.

The keyword lists are intentionally boring. Edit them to fit your workspace:
  * KEYWORDS — substring match, case-insensitive (good for proper nouns,
    phrases, Chinese or English).
  * WORD_BOUNDARY_KEYWORDS — matched with \\b word boundaries, used for
    short tokens like "IP" or "port" that would otherwise match too much.

Wire it up in .claude/settings.json:
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/memory-search-trigger.py\"",
        "timeout": 5
      }]
    }]
  }

$CLAUDE_PROJECT_DIR is set by Claude Code to the workspace root. Using it
makes the hook robust against cwd drift (for example, a previous Bash call
that `cd`'d into a subdirectory and never restored cwd).
"""
import json
import re
import sys

# Proper nouns, services, infrastructure, temporal cues — edit for your workspace.
KEYWORDS = [
    # === project / infra proper nouns (examples — replace with your own) ===
    # "MyProject", "production-db", "staging cluster",
    # === cross-host / retrieval intents ===
    "裡面有沒有", "上面有沒有", "去拿", "去抓", "去找",
    "is there", "do we have", "fetch from", "pull from",
    # === temporal references ===
    "之前", "上次", "剛剛", "還記得", "上週", "上個月",
    "last time", "previously", "earlier", "we did", "remember when",
    # === connection / credential questions ===
    "連線", "帳號", "ssh key", "credentials", "how do i connect",
]

# Tokens that need word-boundary matching (avoid false positives).
WORD_BOUNDARY_KEYWORDS = ["IP", "port", "token", "URL"]

SEARCH_CMD = 'python3 scripts/memory-search-hybrid.py "<keyword>" --days 90 --top 10'


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = payload.get("prompt", "") or ""
    if not prompt:
        return 0

    lower = prompt.lower()
    hits = [kw for kw in KEYWORDS if kw.lower() in lower]
    for kw in WORD_BOUNDARY_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", prompt, re.IGNORECASE):
            hits.append(kw)

    if not hits:
        return 0

    reminder = (
        "Memory-search hard-trigger keywords detected: "
        + ", ".join(sorted(set(hits)))
        + f". Before answering, run: {SEARCH_CMD}"
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": reminder,
        }
    }
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
