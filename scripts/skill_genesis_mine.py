#!/usr/bin/env python3
"""skill_genesis_mine — 從 LEARNINGS 的重複程序型信號「萃取候選新 skill」（生成軸）。

與 evolve_skill 互補：evolve = 精煉「既有」skill；genesis = 從經驗長出「新」skill。

信號源（程序型、重複 = 值得自動化）：
  LEARNINGS.md 中 type ∈ {manual_repeat, best_practice} 且有 suggested_action（具體步驟）
  且 recurring_count ≥ MIN_RC 的條目。correction/knowledge_gap/regression 多屬「事實/修正」
  非「可重用程序」，預設不挖。

流程：候選 → MM-M3 判斷 worth_skill + 是否與既有 skill 重複 + 草擬 SKILL.md skeleton
  → **絕不自動建檔**（genesis 比 refine 高風險：錯的 skill 污染 catalogue + 誤觸發 + 吃 token）。
  worth 且不重複且信度夠 → 寫草稿 `cron/state/skill-genesis/<slug>/SKILL.draft.md`
  + per-candidate flag 等人覆審；核准後由人 + skill-creator scaffold，再進 evolve 迴路。

6/15 約束：只用 MM `MiniMax-M3`，禁 `claude -p`。

Usage:
    skill_genesis_mine.py [--min-rc 2] [--gate 0.7] [--dry-run] [--limit N]
    skill_genesis_mine.py --report
"""
import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

# 複用 evolve 的 robust JSON 解析（string-aware 括號配對）
from skill_evolve_apply import _extract_json_obj  # noqa: E402  (同 scripts/ 目錄)

REPO = Path(__file__).resolve().parent.parent
LEARNINGS_PATH = REPO / "LEARNINGS.md"
SKILLS_DIR = REPO / ".claude" / "skills"
DRAFT_DIR = REPO / "cron" / "state" / "skill-genesis"
TELEMETRY = REPO / "cron" / "state" / "skill-genesis-log.jsonl"
FLAG_DIR = REPO / ".claude" / "flags"

API_URL = "https://api.minimax.io/anthropic/v1/messages"
MODEL = "MiniMax-M3"

# 程序型 type（值得成 skill 的本質是「可重用步驟」）
PROCEDURAL_TYPES = {"manual_repeat", "best_practice"}


# ── LEARNINGS 解析 ────────────────────────────────────────────────────────

def parse_learnings(text: str) -> list[dict]:
    """解析 ## [TYPE-YYYYMMDD-NNN] 區塊，抽 type/rc/title/claim/suggested_action/status。"""
    entries = []
    blocks = re.split(r'(?m)^## \[([A-Z_]+-\d{8}-\d{3})\]\s+(.+)$', text)
    for i in range(1, len(blocks), 3):
        if i + 2 >= len(blocks):
            break
        eid, title, body = blocks[i].strip(), blocks[i + 1].strip(), blocks[i + 2]
        e = {"id": eid, "title": title}
        for field in ("claim", "type", "recurring_count", "status", "promoted_to", "blast_radius"):
            m = re.search(rf'\*\*{field}\*\*:\s*(.+?)(?:\n|$)', body)
            if m:
                e[field] = m.group(1).strip()
        # recurring_count 也可能寫成 `**recurring_count: 3**`
        if "recurring_count" not in e:
            m = re.search(r'\*\*recurring_count:\s*(\d+)\*\*', body)
            if m:
                e["recurring_count"] = m.group(1)
        # suggested_action：抓到下一個 **field** 或區塊結束
        m = re.search(r'\*\*suggested_action\*\*:\s*\n(.*?)(?:\n\*\*\w|\Z)', body, re.DOTALL)
        e["suggested_action"] = m.group(1).strip() if m else ""
        ev = re.search(r'\*\*evidence:\*\*\s*\n((?:\s*-\s.+\n?)+)', body)
        e["evidence_count"] = len([l for l in ev.group(1).splitlines() if l.strip().startswith('-')]) if ev else 0
        entries.append(e)
    return entries


def candidates(entries: list[dict], min_rc: int) -> list[dict]:
    """挑程序型、重複夠、有具體步驟、尚未被做成 skill 的條目。"""
    out = []
    for e in entries:
        t = (e.get("type") or "").lower()
        rc = int(re.sub(r'\D', '', e.get("recurring_count", "1")) or "1")
        if t not in PROCEDURAL_TYPES:
            continue
        if rc < min_rc:
            continue
        if not e.get("suggested_action"):
            continue
        # 已 promote 到某個 skill 就跳（promote 到 MEMORY.md 不算，仍可能 skill 化）
        if "skill" in (e.get("promoted_to") or "").lower():
            continue
        e["_rc"] = rc
        out.append(e)
    return out


# ── 既有 skill 清單（dedup 上下文）────────────────────────────────────────

def existing_skills() -> list[dict]:
    out = []
    if not SKILLS_DIR.exists():
        return out
    for d in sorted(SKILLS_DIR.iterdir()):
        sk = d / "SKILL.md"
        if not sk.is_file():
            continue
        txt = sk.read_text(encoding="utf-8", errors="ignore")
        desc = ""
        m = re.search(r'(?m)^description:\s*(.+)$', txt) or re.search(r'(?m)^#\s+(.+)$', txt)
        if m:
            desc = m.group(1).strip().strip('"')[:200]
        out.append({"name": d.name, "desc": desc})
    return out


# ── MM-M3 判斷 + 草擬 ─────────────────────────────────────────────────────

def call_m3(prompt: str, timeout: int = 120) -> str | None:
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        return None
    body = {
        "model": MODEL, "max_tokens": 2000,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": prompt}],
    }
    for attempt in range(3):
        try:
            resp = httpx.post(API_URL, headers={
                "x-api-key": api_key, "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            }, json=body, timeout=timeout)
            resp.raise_for_status()
            for c in resp.json().get("content", []):
                if c.get("type") == "text":
                    return c["text"]
            return None
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError):
            if attempt < 2:
                time.sleep(5 * (attempt + 1)); continue
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(5 * (attempt + 1)); continue
            return None
    return None


def assess(entry: dict, skills: list[dict]) -> dict | None:
    skill_list = "\n".join(f"- {s['name']}: {s['desc']}" for s in skills)
    prompt = f"""你要把一條 LEARNINGS 紀錄**嚴格三分類**。多數紀錄是「原則/心法」而非「skill」——
預設傾向 PRINCIPLE，只有明確通過 SKILL 全部條件才歸 SKILL。寧可漏判也不要把原則當 skill。

分類定義：
- **SKILL** = 可重用的「多步驟程序」，同時滿足：(a) 有明確觸發情境（看到某類請求就啟動）
  (b) 步驟是可執行操作（含指令/工具/具體動作）而非心態提醒 (c) 跨情境會反覆發生。
- **PRINCIPLE** = 一句心法/原則/提醒（「不要假設 X」「先驗證再 Y」「對 Z 要保守」）。
  即使重複多次、即使有「建議做法」，只要本質是「該記住的判斷準則」就是 PRINCIPLE，**不是 skill**，
  它該進 CLAUDE.md / notes，不是 .claude/skills/。
- **ONE_OFF** = 一次性事實/某次特定修正，不會重複成固定流程。

判別測試（任一為「否」就不可歸 SKILL）：
  Q1 能寫出「觸發時機」讓 agent 自動辨識何時該叫它嗎？
  Q2 步驟主體是「做某操作」而非「記得某件事/抱持某心態」嗎？
  Q3 換個專案/情境仍會原樣重跑這套步驟嗎？

範例校準：
- 「遷移前掃硬編碼路徑/個資並改 env」→ SKILL（觸發=遷移前；步驟=grep+改寫；跨專案重複）
- 「整合外部工具輸出前不要假設 format，先實跑看一次」→ PRINCIPLE（本質是心法，Q2 否）
- 「GEPA 對已人工演化的 skill marginal gain 不值得自動化」→ PRINCIPLE（是判斷準則，無觸發、無操作步驟）

【既有 skills（若涵蓋則 duplicate）】
{skill_list}

【待分類紀錄】
標題：{entry['title']}
重複次數：{entry.get('_rc')}
描述：{entry.get('claim', '')}
建議做法：
{entry.get('suggested_action', '')[:1500]}

先逐一回答 Q1/Q2/Q3，再分類。只回 JSON：
{{"category": "SKILL|PRINCIPLE|ONE_OFF", "q1_trigger": true/false, "q2_actions": true/false,
  "q3_recurs": true/false, "duplicate_of": "既有skill名或null", "confidence": 0.0-1.0,
  "proposed_name": "kebab-case（僅 SKILL 需要）", "description": "一句話含觸發時機",
  "trigger": "何時用", "steps": ["步驟1", "步驟2"], "reason": "為何是此類別"}}"""
    raw = call_m3(prompt)
    if raw is None:
        return None
    v = _extract_json_obj(re.sub(r"```(?:json)?", "", raw))
    if v is None:
        return None
    # 三 Q 任一為否 → 不可能是真 SKILL（deterministic 收緊，補 M3 過寬）
    v["worth_skill"] = (
        v.get("category") == "SKILL"
        and bool(v.get("q1_trigger")) and bool(v.get("q2_actions")) and bool(v.get("q3_recurs"))
    )
    return v


# ── 草稿 + flag + telemetry ───────────────────────────────────────────────

def _slug(name: str) -> str:
    return re.sub(r"[^\w.-]+", "-", name).strip("-").lower() or "skill"


def write_draft(v: dict, entry: dict) -> Path:
    slug = _slug(v.get("proposed_name") or entry["id"])
    d = DRAFT_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(v.get("steps", []), 1))
    draft = f"""---
name: {v.get('proposed_name', slug)}
description: {v.get('description', '')}
status: DRAFT (genesis 自動產出，未經人工核准，未啟用)
source: {entry['id']} (LEARNINGS, rc={entry.get('_rc')})
---

# {v.get('proposed_name', slug)}

> ⚠️ 這是 skill_genesis_mine 自動草擬的 skeleton，**尚未核准、尚未放進 .claude/skills/**。
> 覆審後若採納，用 skill-creator scaffold 正式建立，再進 evolve_skill 精煉。

## 觸發時機
{v.get('trigger', '')}

## 步驟
{steps}

## 來源信號
- LEARNINGS `{entry['id']}`：{entry['title']}（重複 {entry.get('_rc')} 次）
- M3 評估：worth={v.get('worth_skill')} confidence={v.get('confidence')} reason={v.get('reason', '')}
"""
    (d / "SKILL.draft.md").write_text(draft, encoding="utf-8")
    return d / "SKILL.draft.md"


def write_flag(v: dict, entry: dict, draft: Path) -> Path:
    FLAG_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(v.get("proposed_name") or entry["id"])
    fp = FLAG_DIR / f"skill-genesis-{slug}.flag"
    fp.write_text(
        f"skill-genesis 候選新 skill：{v.get('proposed_name')}（源 {entry['id']}，信度 {v.get('confidence')}）\n"
        f"審草稿 {draft}；採納則用 skill-creator scaffold 成正式 skill，否則刪。決定後 `rm {fp}` 收尾。\n",
        encoding="utf-8",
    )
    return fp


def log_telemetry(rec: dict):
    TELEMETRY.parent.mkdir(parents=True, exist_ok=True)
    with TELEMETRY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def report():
    if not TELEMETRY.exists():
        print(f"無 telemetry：{TELEMETRY}"); return
    rows = [json.loads(l) for l in TELEMETRY.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        print("telemetry 空"); return
    by, cats = {}, {}
    for r in rows:
        by[r["action"]] = by.get(r["action"], 0) + 1
        c = (r.get("m3") or {}).get("category")
        if c:
            cats[c] = cats.get(c, 0) + 1
    print(f"📊 skill-genesis telemetry（n={len(rows)}）")
    for a in ("DRAFTED", "DUPLICATE", "NOT_WORTH", "M3_UNAVAILABLE"):
        if by.get(a):
            print(f"   {a:<15} {by[a]}")
    if cats:
        print("   M3 三分類：" + " / ".join(f"{k}×{v}" for k, v in sorted(cats.items())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-rc", type=int, default=2, help="最低重複次數（預設 2）")
    ap.add_argument("--gate", type=float, default=0.7, help="worth_skill 信度門檻（預設 0.7）")
    ap.add_argument("--dry-run", action="store_true", help="只列候選，不呼叫 M3、不寫草稿/flag")
    ap.add_argument("--limit", type=int, default=0, help="最多評估幾個候選（0=全部）")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        report(); return

    if not LEARNINGS_PATH.exists():
        print(f"缺 {LEARNINGS_PATH}"); return
    entries = parse_learnings(LEARNINGS_PATH.read_text(encoding="utf-8"))
    cands = candidates(entries, args.min_rc)
    if args.limit:
        cands = cands[:args.limit]
    print(f"程序型候選（type∈{PROCEDURAL_TYPES}, rc≥{args.min_rc}, 有步驟, 未 skill 化）：{len(cands)}")
    for e in cands:
        print(f"   [{e['id']}] rc={e['_rc']}  {e['title'][:70]}")

    if args.dry_run:
        print("\n(--dry-run：不呼叫 M3)")
        return
    if not cands:
        return

    skills = existing_skills()
    for e in cands:
        v = assess(e, skills)
        if v is None:
            action, note = "M3_UNAVAILABLE", "M3 呼叫/解析失敗"
            print(f"🚩 {e['id']}: {note}")
        elif v.get("duplicate_of") and str(v.get("duplicate_of")).lower() not in ("null", "none", ""):
            action, note = "DUPLICATE", f"與既有 skill 重複：{v['duplicate_of']}"
            print(f"⏭️  {e['id']}: {note}")
        elif v.get("worth_skill") and v.get("confidence", 0) >= args.gate:
            draft = write_draft(v, e)
            fp = write_flag(v, e, draft)
            action, note = "DRAFTED", f"{v.get('proposed_name')} (conf {v.get('confidence')})"
            print(f"✅ {e['id']}: 草擬 {note}\n   draft: {draft}\n   flag: {fp}")
        else:
            cat = v.get("category", "?")
            action, note = "NOT_WORTH", f"category={cat} (Q1={v.get('q1_trigger')} Q2={v.get('q2_actions')} Q3={v.get('q3_recurs')}) {v.get('reason','')[:60]}"
            print(f"➖ {e['id']}: {cat} — 非 skill（{v.get('reason','')[:50]}）")
        log_telemetry({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "learning_id": e["id"], "title": e["title"], "rc": e.get("_rc"),
            "action": action, "note": note,
            "m3": v if v else None,
        })


if __name__ == "__main__":
    main()
