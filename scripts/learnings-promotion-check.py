#!/usr/bin/env python3
"""learnings-promotion-check — 計算 LEARNINGS.md 條目的 confidence + promotion_score
並回報 promotion 候選 / 過期 sunset。

仿 OpenClaw 2026.4.12 dreaming light-sleep confidence + promotion threshold pattern。
不直接修檔，只回報；人工確認後再 promote 到 MEMORY.md。

Usage:
    python3 scripts/learnings-promotion-check.py            # 印 promotion 候選 + sunset 警告
    python3 scripts/learnings-promotion-check.py --json     # JSON 輸出給其他 script 用
    python3 scripts/learnings-promotion-check.py --gate 0.6 # 自訂 gate（預設 0.7）

Confidence 公式：
    confidence = min(1.0,
        (log(recurring_count + 1) / log(5)) *      # 重複 4 次飽和到 1.0
        (min(evidence_count, 3) / 3) *             # 3 個 evidence 飽和
        time_span_factor                            # 跨度大於 30 天才滿分
    )

Promotion score 公式：
    promotion_score = confidence * type_weight
    type_weight: correction=1.0, regression=0.95, best_practice=0.85,
                 manual_repeat=0.8, knowledge_gap=0.7, error=0.6
"""
import argparse
import json
import math
import re
import sys
from datetime import datetime, date
from pathlib import Path

LEARNINGS_PATH = Path(__file__).resolve().parent.parent / "LEARNINGS.md"

TYPE_WEIGHTS = {
    "correction": 1.0,
    "regression": 0.95,
    "best_practice": 0.85,
    "manual_repeat": 0.8,
    "knowledge_gap": 0.7,
    "error": 0.6,
}


def parse_entries(text: str) -> list[dict]:
    """解析 LEARNINGS.md 的 ## [TYPE-YYYYMMDD-NNN] 條目區塊。"""
    entries = []
    # split by H2 header that matches the schema id pattern
    blocks = re.split(r'(?m)^## \[([A-Z_]+-\d{8}-\d{3})\]\s+(.+)$', text)
    # blocks[0] = preamble, then triplets of (id, title, body)
    for i in range(1, len(blocks), 3):
        if i + 2 >= len(blocks):
            break
        entry_id = blocks[i].strip()
        title = blocks[i + 1].strip()
        body = blocks[i + 2]
        entry = {"id": entry_id, "title": title, "body": body}
        # parse fields
        for field in ("claim", "type", "recurring_count", "status",
                      "blast_radius", "promoted_to", "sunset_date"):
            m = re.search(rf'\*\*{field}\*\*:\s*(.+?)(?:\n|$)', body)
            if m:
                entry[field] = m.group(1).strip()
        # evidence count = number of lines starting with "  - YYYY-..." in evidence section
        ev_match = re.search(r'\*\*evidence\*\*:\s*\n((?:\s*-\s.+\n?)+)', body)
        if ev_match:
            ev_lines = [l for l in ev_match.group(1).strip().split('\n') if l.strip().startswith('-')]
            entry["evidence_count"] = len(ev_lines)
            # extract dates from evidence
            dates = re.findall(r'(\d{4}-\d{2}-\d{2})', ev_match.group(1))
            entry["evidence_dates"] = sorted(set(dates))
        else:
            entry["evidence_count"] = 0
            entry["evidence_dates"] = []
        entries.append(entry)
    return entries


def compute_confidence(entry: dict) -> float:
    rc = int(entry.get("recurring_count", "1") or "1")
    ec = entry.get("evidence_count", 0)
    dates = entry.get("evidence_dates", [])

    rc_factor = min(1.0, math.log(rc + 1) / math.log(5))
    ec_factor = min(ec, 3) / 3

    if len(dates) >= 2:
        d_first = datetime.strptime(dates[0], "%Y-%m-%d").date()
        d_last = datetime.strptime(dates[-1], "%Y-%m-%d").date()
        span_days = (d_last - d_first).days
        time_factor = min(1.0, span_days / 30)
    else:
        time_factor = 0.3  # 單日訊號折扣

    return round(rc_factor * ec_factor * time_factor, 3)


def compute_promotion_score(entry: dict, confidence: float) -> float:
    t = entry.get("type", "").lower()
    weight = TYPE_WEIGHTS.get(t, 0.5)
    return round(confidence * weight, 3)


def days_until(date_str: str) -> int:
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return 99999
    return (target - date.today()).days


# Cluster detection: Jaccard similarity over claim+title keywords
# 仿 OpenClaw 2026.4.12 dreaming "raise phase reinforcement for repeated revisits"
# 但 LEARNINGS 場景：手動寫入容易碎成多 rc=1 → 用 keyword 找出可合併的 family

_CN_RE = re.compile(r'[一-鿿]{2,}')
_EN_RE = re.compile(r'[A-Za-z][A-Za-z0-9_-]{2,}')
_STOP = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "should", "must",
    "or", "of", "to", "in", "on", "by", "at", "an",
    "claim", "type", "evidence", "status", "active", "suggested", "action",
    "blast", "radius", "knowledge", "gap", "best", "practice", "correction",
    "regression", "manual", "repeat", "error",
    "的", "了", "是", "在", "和", "有", "也", "都", "不", "會", "要",
    "不要", "需要", "可能", "如果", "因為", "所以", "但是",
})


def _keywords_of(entry: dict) -> set[str]:
    text = " ".join([
        entry.get("title", ""),
        entry.get("claim", ""),
        " ".join(entry.get("evidence_dates", [])),
    ]).lower()
    cn = set(_CN_RE.findall(text))
    en = {w.lower() for w in _EN_RE.findall(text)}
    return {k for k in (cn | en) if k.lower() not in _STOP and len(k) >= 2}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def detect_clusters(entries: list[dict], threshold: float = 0.3) -> list[dict]:
    """Greedy 聚合：對每對 entry 算 keyword Jaccard，>= threshold 加同 cluster。
    回傳 [{keywords, entries: [...]}]，size >= 2 的 cluster。
    """
    eligible = [e for e in entries
                if e.get("status", "active") == "active" and not e.get("promoted_to")]
    kws = {e["id"]: _keywords_of(e) for e in eligible}
    parent: dict[str, str] = {e["id"]: e["id"] for e in eligible}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    ids = list(kws.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if _jaccard(kws[ids[i]], kws[ids[j]]) >= threshold:
                union(ids[i], ids[j])

    groups: dict[str, list[dict]] = {}
    for e in eligible:
        root = find(e["id"])
        groups.setdefault(root, []).append(e)

    clusters = []
    for members in groups.values():
        if len(members) >= 2:
            shared = set.intersection(*(kws[e["id"]] for e in members))
            clusters.append({
                "size": len(members),
                "keywords": sorted(shared, key=lambda k: -len(k))[:8],
                "entries": members,
            })
    clusters.sort(key=lambda c: -c["size"])
    return clusters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gate", type=float, default=0.7,
                    help="promotion_score 門檻（預設 0.7），≥ 此值列為 promote 候選")
    ap.add_argument("--cluster", action="store_true",
                    help="偵測同主題 cluster（keyword Jaccard ≥ threshold）；helpful "
                         "before writing new LEARNINGS entry to find +1 candidates。"
                         "注意：Jaccard 對短 claim 偏嚴，預設 0.05 會包含弱相關，"
                         "需人工 review 哪些是真同 family。0.10+ 為強匹配")
    ap.add_argument("--cluster-threshold", type=float, default=0.05,
                    help="cluster Jaccard 門檻，預設 0.05（包含弱相關，需人工 filter）")
    args = ap.parse_args()

    if not LEARNINGS_PATH.exists():
        print(f"missing: {LEARNINGS_PATH}", file=sys.stderr)
        sys.exit(1)

    text = LEARNINGS_PATH.read_text(encoding="utf-8")
    entries = parse_entries(text)

    candidates = []   # promotion_score >= gate, status active, not yet promoted
    sunsets = []      # sunset_date 過期或 7 天內到
    stale_low = []    # active 但分數低（可能 noise，建議 wontfix 或補 evidence）

    for e in entries:
        if e.get("status", "active") != "active":
            continue
        if e.get("promoted_to"):
            continue
        c = compute_confidence(e)
        p = compute_promotion_score(e, c)
        e["confidence"] = c
        e["promotion_score"] = p

        if p >= args.gate:
            candidates.append(e)
        elif p < 0.2 and int(e.get("recurring_count", "1") or "1") == 1:
            stale_low.append(e)

        if e.get("sunset_date"):
            d = days_until(e["sunset_date"])
            if d <= 7:
                e["sunset_in_days"] = d
                sunsets.append(e)

    clusters = detect_clusters(entries, threshold=args.cluster_threshold) if args.cluster else []

    if args.json:
        out = {
            "gate": args.gate,
            "candidates": [{k: v for k, v in e.items() if k != "body"} for e in candidates],
            "sunsets": [{k: v for k, v in e.items() if k != "body"} for e in sunsets],
            "stale_low_signal": [{k: v for k, v in e.items() if k != "body"} for e in stale_low],
            "total_active": sum(1 for e in entries if e.get("status", "active") == "active"
                                and not e.get("promoted_to")),
        }
        if args.cluster:
            out["cluster_threshold"] = args.cluster_threshold
            out["clusters"] = [
                {
                    "size": c["size"],
                    "keywords": c["keywords"],
                    "entries": [{k: v for k, v in e.items() if k != "body"}
                                for e in c["entries"]],
                }
                for c in clusters
            ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print(f"📊 LEARNINGS promotion check (gate={args.gate})")
    print(f"   Total active unpromoted: {sum(1 for e in entries if e.get('status', 'active') == 'active' and not e.get('promoted_to'))}")
    print()

    if candidates:
        print(f"⭐ Promotion candidates ({len(candidates)})：建議補欄位 promoted_to: <MEMORY.md section> 並升級")
        for e in sorted(candidates, key=lambda x: -x["promotion_score"]):
            print(f"   [{e['id']}] score={e['promotion_score']:.2f} "
                  f"(conf={e['confidence']:.2f}, rc={e.get('recurring_count', '?')}, "
                  f"ev={e['evidence_count']}, span={len(e['evidence_dates'])}日)")
            print(f"      {e['title'][:90]}")
        print()

    if sunsets:
        print(f"⏰ Sunset 即將到期 ({len(sunsets)})：人工 review 是否還有效")
        for e in sorted(sunsets, key=lambda x: x.get("sunset_in_days", 0)):
            d = e.get("sunset_in_days", 0)
            tag = "已過期" if d < 0 else f"{d} 天後"
            print(f"   [{e['id']}] sunset={e['sunset_date']} ({tag})  {e['title'][:80]}")
        print()

    if stale_low:
        print(f"💤 Low-signal 候選（{len(stale_low)}）：1 次發生且 evidence/span 不足，可考慮 wontfix 或補 evidence")
        for e in stale_low[:5]:
            print(f"   [{e['id']}] score={e['promotion_score']:.2f}  {e['title'][:80]}")
        if len(stale_low) > 5:
            print(f"   ... 共 {len(stale_low)} 條")
        print()

    if args.cluster and clusters:
        print(f"🔗 主題 cluster（Jaccard ≥ {args.cluster_threshold}, size ≥ 2）：{len(clusters)} 群")
        print("   寫新 LEARNINGS 前若主題撞到任一 cluster，先考慮 +1 既有 entry 而非新建")
        for c in clusters[:6]:
            kws = ", ".join(c["keywords"][:5])
            ids = ", ".join(e["id"] for e in c["entries"])
            print(f"   ⚙️  size={c['size']}  keywords=[{kws}]")
            print(f"      members: {ids}")
        if len(clusters) > 6:
            print(f"   ... 共 {len(clusters)} 群（用 --json 看全部）")
        print()

    if not (candidates or sunsets or stale_low or (args.cluster and clusters)):
        print("✅ 無 promotion 候選、無 sunset 警告、無 low-signal stale、無 cluster。")


if __name__ == "__main__":
    main()
