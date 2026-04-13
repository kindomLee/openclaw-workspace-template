#!/usr/bin/env python3
"""UserPromptSubmit hook: 偵測 memory-search 硬觸發關鍵字，直接跑 search
並把 top-N 結果注入 additionalContext。

靈感：OpenClaw 2026.4.10 active-memory plugin 的 before_prompt_build hook，
但簡化：不用 blocking sub-agent（省 Haiku token + 延遲），直接把 search 結果
塞進 context，讓主 agent 自己判斷怎麼用。

設計重點（2026-04-13 升級）：
- Query classification：歷史題 vs 新版題 vs 一般題 → 不同 search window
- Domain routing：根據 hit 關鍵字對結果做路徑加權，壓低離題檔案
- Deduplication：同類型檔案只保留最高分（避免 reflections.md 佔 3 格）
- TTL 60s cache：避免短時間重算同個 query
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# 關鍵字觸發清單
# ---------------------------------------------------------------------------

# 會 trigger search 的專有名詞（大小寫不敏感 substring 匹配）
KEYWORDS = [
    "Oracle VPS", "OpenClaw", "clawd", "Polymarket", "chatgpt-cli", "chat2api",
    "WireGuard", "fnOS", "NAS", "ComfyUI", "CosyVoice", "MiniMax", "nanoOracle",
    "馬克",
    "裡面有沒有", "上面有沒有", "去拿", "去抓", "去找",
    "連線", "帳號", "ssh key",
    "之前", "上次", "剛剛", "還記得", "我們做過", "上週", "上個月",
    "裝了沒", "有沒有這個 skill", "有沒有這個 script",
]
# 需要 word-boundary 的關鍵字（避免誤觸）
WORD_BOUNDARY_KEYWORDS = ["IP", "port", "token"]

# ---------------------------------------------------------------------------
# Query classification
# ---------------------------------------------------------------------------

# 模式：historical 歷史題 / recent 只看近況 / default 標準
HISTORICAL_HINTS = ["之前", "上次", "剛剛", "還記得", "我們做過", "上週", "上個月", "以前", "原本"]
RECENT_HINTS = ["最新", "目前", "現在", "要不要裝", "要不要升", "有沒有更新", "新版"]

# 對應的 search window 和處理參數
MODE_PARAMS = {
    "historical": {"days": 365, "top": 8},  # 歷史題：看久一點
    "recent":     {"days": 7,   "top": 5},  # 新版題：只看最近
    "default":    {"days": 90,  "top": 5},  # 一般：90 天夠用
}


def classify_query(prompt: str) -> str:
    lower = prompt.lower()
    for h in HISTORICAL_HINTS:
        if h in prompt:
            return "historical"
    for h in RECENT_HINTS:
        if h in prompt:
            return "recent"
    return "default"


# ---------------------------------------------------------------------------
# Domain routing：根據 keyword 決定期望的路徑前綴
# ---------------------------------------------------------------------------

# keyword → 期望的路徑前綴（prefix match）
# NOTE: memory-search-hybrid.py 回傳的 `file` 欄位不含 `notes/` 前綴
# （例如 `02-Areas/Tech/OpenClaw/openclaw-updates-2026.md`），
# 所以 DOMAIN_MAP 和 category_of() 都要用相對於 notes/ 的前綴。
DOMAIN_MAP = {
    # Tech topics
    "OpenClaw":    ["02-Areas/Tech/OpenClaw/", "02-Areas/Tech/", "03-Resources/", "MEMORY.md"],
    "clawd":       ["02-Areas/Tech/OpenClaw/", "02-Areas/Tech/", "MEMORY.md"],
    "chat2api":    ["02-Areas/Tech/", "03-Resources/", "MEMORY.md"],
    "chatgpt-cli": ["02-Areas/Tech/", "03-Resources/", "MEMORY.md"],
    "MiniMax":     ["02-Areas/Tech/", "03-Resources/", "MEMORY.md"],
    "ComfyUI":     ["02-Areas/Tech/", "MEMORY.md"],
    "CosyVoice":   ["02-Areas/Tech/", "MEMORY.md"],
    # Infrastructure
    "Oracle VPS":  ["02-Areas/Infrastructure/", "03-Resources/infrastructure/", "MEMORY.md"],
    "WireGuard":   ["02-Areas/Infrastructure/", "MEMORY.md"],
    "fnOS":        ["02-Areas/Infrastructure/", "02-Areas/Home/", "MEMORY.md"],
    "NAS":         ["02-Areas/Infrastructure/", "02-Areas/Home/", "MEMORY.md"],
    # Finance / Projects
    "Polymarket":  ["02-Areas/Finance/", "01-Projects/", "03-Resources/polymarket/"],
    "nanoOracle":  ["01-Projects/", "02-Areas/Tech/"],
}

# 未在 DOMAIN_MAP 中的 keyword 的 fallback（全開）
FALLBACK_DOMAIN = []

# 路徑加權：符合預期 domain 加分，完全不符扣分
DOMAIN_BONUS = 0.10
DOMAIN_PENALTY = 0.15


def expected_prefixes(hits: list[str]) -> list[str]:
    """從命中的 keywords 推出期望的 path prefixes（集合聯集）。"""
    prefixes: set[str] = set()
    for hit in hits:
        mapped = DOMAIN_MAP.get(hit, [])
        prefixes.update(mapped)
    return sorted(prefixes)


def rerank_by_domain(results: list[dict], prefixes: list[str]) -> list[dict]:
    """根據 domain 期望 reranking。沒有期望就不動。"""
    if not prefixes:
        return results
    reranked = []
    for r in results:
        file_ = r.get("file", "")
        score = r.get("score", 0)
        matched = any(file_.startswith(p) or p == file_ for p in prefixes)
        new_score = score + DOMAIN_BONUS if matched else score - DOMAIN_PENALTY
        # 複製一份避免動到 cache
        r2 = dict(r)
        r2["score"] = new_score
        r2["_domain_match"] = matched
        reranked.append(r2)
    reranked.sort(key=lambda x: x["score"], reverse=True)
    return reranked


# ---------------------------------------------------------------------------
# Deduplication：同類型檔案只留最高分
# ---------------------------------------------------------------------------

def category_of(path: str) -> str:
    """把檔案分類，同類只保留最高分。
    注意：memory-search-hybrid.py 的 file 欄位不含 notes/ 前綴，
    且 memory/ 子目錄會被 flatten（例如 reflections.md 而非 memory/reflections.md）。
    """
    # 特殊檔案先處理
    if path in ("MEMORY.md", "MEMORY_COMPACT.md", "LEARNINGS.md"):
        return "memory-index"
    if path == "reflections.md":
        return "reflections"
    if path == "dreams.md":
        return "dreams"
    if path in ("timeline-archive.md",):
        return "timeline-archive"

    # notes/ 相對路徑
    if path.startswith("01-Projects/Archive/"):
        return "projects-archive"
    if path.startswith("01-Projects/"):
        return "projects"
    if path.startswith("02-Areas/Tech/OpenClaw/"):
        return "tech-openclaw"
    if path.startswith("02-Areas/Tech/"):
        return "tech"
    if path.startswith("02-Areas/Infrastructure/"):
        return "infra"
    if path.startswith("02-Areas/Home/"):
        return "home"
    if path.startswith("02-Areas/"):
        return "areas-other"
    if path.startswith("03-Resources/"):
        return "resources"
    if path.startswith("04-Archive/"):
        return "archive"

    # memory/ 子目錄（archive-YYYY-MM/xxx.md）
    if path.startswith("archive-"):
        return "journal-archive"
    # 日期檔 2026-04-13.md
    if re.match(r"^\d{4}-\d{2}-\d{2}.*\.md$", path):
        return "journal"

    return "other"


def dedupe_by_category(results: list[dict], limit: int) -> list[dict]:
    """每個 category 只保留分數最高的那筆，最多 limit 筆。"""
    seen: dict[str, dict] = {}
    for r in results:
        cat = category_of(r.get("file", ""))
        if cat not in seen:
            seen[cat] = r
        # 同類型但分數更高就取代
        elif r.get("score", 0) > seen[cat].get("score", 0):
            seen[cat] = r
    unique = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
    return unique[:limit]


# ---------------------------------------------------------------------------
# Core: search + cache + filters
# ---------------------------------------------------------------------------

MIN_SCORE = 0.5            # 低於此分數的結果不注入（噪音過濾）
CACHE_TTL_SEC = 60
SEARCH_TIMEOUT_SEC = 6
CACHE_DIR = "/tmp"

PROJECT_DIR = os.environ.get(
    "CLAUDE_PROJECT_DIR",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)


def detect_hits(prompt: str) -> list[str]:
    lower = prompt.lower()
    hits = [kw for kw in KEYWORDS if kw.lower() in lower]
    for kw in WORD_BOUNDARY_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", prompt, re.IGNORECASE):
            hits.append(kw)
    return sorted(set(hits))


def run_search_cached(query: str, days: int, top: int) -> list[dict]:
    """跑 memory-search-hybrid，TTL cache。失敗返回空列表。
    Cache key 含 days+top 以避免不同 mode 互相污染。
    """
    cache_key = f"{query}|days={days}|top={top}"
    query_hash = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:16]
    cache_path = os.path.join(CACHE_DIR, f"mem-search-{query_hash}.json")

    # Cache hit 且未過期
    if os.path.exists(cache_path):
        try:
            age = time.time() - os.path.getmtime(cache_path)
            if age < CACHE_TTL_SEC:
                with open(cache_path) as f:
                    return json.load(f).get("results", [])
        except Exception:
            pass

    # 跑 search
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


def format_context(hits: list[str], mode: str, prefixes: list[str], results: list[dict]) -> str:
    """產生要注入 additionalContext 的字串。"""
    header = f"偵測到 memory-search 硬觸發關鍵字：{', '.join(hits)}（mode={mode}）"

    good = [r for r in results if r.get("score", 0) >= MIN_SCORE]

    if not good:
        return (
            header
            + "。已自動搜尋但無高分結果，必要時可手動執行：\n"
            + 'python3 scripts/memory-search-hybrid.py "<關鍵字>" --days 90 --top 10'
        )

    lines = [header + f"。已自動搜尋並注入 top {len(good)} 結果（已依 domain 加權 + 去重）："]
    if prefixes:
        lines.append(f"  期望 domain: {', '.join(prefixes[:4])}" + ("..." if len(prefixes) > 4 else ""))
    lines.append("")
    for i, r in enumerate(good, 1):
        score = r.get("score", 0)
        file_ = r.get("file", "?")
        date = r.get("date", "?")
        matched = "✓" if r.get("_domain_match") else " "
        snippet = (r.get("snippet", "") or "").replace("\n", " ")[:160]
        lines.append(f"[{i}]{matched} {file_} (score={score:.2f}, {date})")
        lines.append(f"    {snippet}")
    lines.append("")
    lines.append("如需更深入的脈絡，再用 Read/Grep 讀具體檔案。")
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

    # 1. Query classification
    mode = classify_query(prompt)
    params = MODE_PARAMS[mode]

    # 2. Pull search results (寬鬆一點，給 domain filter 和 dedupe 後還有料)
    query = prompt[:200].strip()
    raw_results = run_search_cached(query, days=params["days"], top=max(params["top"] * 2, 10))

    # 3. Domain routing (加分 / 扣分)
    prefixes = expected_prefixes(hits)
    reranked = rerank_by_domain(raw_results, prefixes)

    # 4. Dedupe by category
    deduped = dedupe_by_category(reranked, limit=params["top"])

    # 5. Format + inject
    reminder = format_context(hits, mode, prefixes, deduped)
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
