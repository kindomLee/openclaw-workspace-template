#!/bin/bash
# memory-retire-candidates.sh — monthly retirement-candidate report for
# feedback memories (zero LLM; never deletes or edits anything).
#
# Scans the Claude Code auto-memory dir (*.md except MEMORY.md) plus
# LEARNINGS.md and writes a report of merge / demote candidates, stale
# evidence paths and LEARNINGS growth, then raises a flag for a review
# session. Forgetting is a demotion pipeline (demote → archive → merge →
# delete), and the test is "does this rule still carry risk", not "how long
# since it fired" — so the script only emits mechanical signals and leaves
# every decision to a human-in-the-loop review.
#
# Config:
#   AUTO_MEMORY_DIR — auto-memory dir (default: derived from the workspace
#                     path the way Claude Code encodes ~/.claude/projects/)
#   RETIRE_NO_NOTIFY=1 — skip the notification (testing)
#   TG_BOT_TOKEN / TG_CHAT_ID (or SLACK_WEBHOOK_URL) — see scripts/lib/notify.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_DIR/cron/logs"
LOG_FILE="$LOG_DIR/memory-retire-candidates-$(date +%Y%m%d-%H%M%S).log"
STATE_DIR="$PROJECT_DIR/cron/state"
FLAG_DIR="$PROJECT_DIR/.claude/flags"
FLAG_FILE="$FLAG_DIR/retire-review.flag"
CONFIG_FILE="$PROJECT_DIR/cron/config.env"

# Claude Code names project dirs by replacing "/" and "." in the path with "-".
AUTO_MEMORY_DIR="${AUTO_MEMORY_DIR:-$HOME/.claude/projects/$(echo "$PROJECT_DIR" | sed 's#[/.]#-#g')/memory}"

mkdir -p "$LOG_DIR" "$FLAG_DIR" "$STATE_DIR"

if [ -f "$CONFIG_FILE" ]; then
  set -a
  source "$CONFIG_FILE"
  set +a
fi
# shellcheck source=../../scripts/lib/notify.sh
source "$PROJECT_DIR/scripts/lib/notify.sh"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

MONTH="$(date +%Y-%m)"
REPORT_FILE="$STATE_DIR/retirement-review-$MONTH.md"
IDENTITY="retire:$MONTH"

log "Starting memory-retire-candidates for $MONTH"
log "AUTO_MEMORY_DIR=$AUTO_MEMORY_DIR"

if [ ! -d "$AUTO_MEMORY_DIR" ]; then
  # No auto-memory yet (fresh install, or OpenClaw mode) — nothing to review.
  log "auto-memory dir not found — nothing to review, no flag"
  exit 0
fi

cd "$PROJECT_DIR"

# Zero-LLM analysis → markdown report. "Canonical" files are where a rule
# ends up once it is load-bearing; high overlap with them = demote candidate.
python3 - "$AUTO_MEMORY_DIR" "$PROJECT_DIR" "$REPORT_FILE" "$MONTH" <<'PY' | tee -a "$LOG_FILE"
import sys, os, glob, re, datetime

auto_dir, project_dir, report_file, month = sys.argv[1:5]
home = os.path.expanduser("~")

# canonical 準則檔：規則若已被這些覆蓋 → demote 候選
canon_paths = [
    os.path.join(project_dir, "CLAUDE.md"),
    os.path.join(project_dir, "SOUL.md"),
    os.path.join(project_dir, "USER.md"),
    os.path.join(project_dir, "AGENTS.md"),
]
canon_paths += glob.glob(os.path.join(project_dir, "spec", "*.md"))
canon_text = ""
for p in canon_paths:
    try:
        canon_text += open(p, encoding="utf-8").read() + "\n"
    except Exception:
        pass

def cjk_bigrams(s):
    # 取 CJK 連續段的 bigram + ascii 詞（len>=3）當 token，給粗略 overlap 信號用
    toks = set()
    for run in re.findall(r'[一-鿿]{2,}', s):
        for i in range(len(run) - 1):
            toks.add(run[i:i+2])
    for w in re.findall(r'[A-Za-z][A-Za-z0-9_\-]{2,}', s):
        toks.add(w.lower())
    return toks

def parse_frontmatter(text):
    name = desc = typ = sev = None
    m = re.match(r'^---\s*\n(.*?)\n---', text, re.S)
    fm = m.group(1) if m else ""
    for line in fm.splitlines():
        line = line.rstrip()
        if re.match(r'^\s*name:\s*', line) and name is None:
            name = re.sub(r'^\s*name:\s*', '', line).strip().strip('"\'')
        elif re.match(r'^\s*description:\s*', line) and desc is None:
            desc = re.sub(r'^\s*description:\s*', '', line).strip().strip('"\'')
        elif re.match(r'^\s*type:\s*', line) and typ is None:
            typ = re.sub(r'^\s*type:\s*', '', line).strip()
        elif re.match(r'^\s*severity:\s*', line) and sev is None:
            sev = re.sub(r'^\s*severity:\s*', '', line).strip()
    return name, desc, typ, sev, fm

rules = []
# auto-memory 檔名慣例已從 feedback_*.md 改成 kebab-case slug + frontmatter type:
# 一律掃全部 *.md（排除索引 MEMORY.md），type 欄留給人工覆審判斷
for path in sorted(glob.glob(os.path.join(auto_dir, "*.md"))):
    if os.path.basename(path) == "MEMORY.md":
        continue
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        continue
    name, desc, typ, sev, fm = parse_frontmatter(text)
    base = os.path.basename(path)
    name = name or base[:-3]
    desc = desc or "(無 description)"
    # rc：body 裡找 rc=N
    rcm = re.search(r'\brc\s*=\s*(\d+)', text)
    rc = int(rcm.group(1)) if rcm else None
    mtime = datetime.date.fromtimestamp(os.path.getmtime(path))
    age = (datetime.date.today() - mtime).days
    body = text[m.end():] if (m := re.match(r'^---\s*\n.*?\n---', text, re.S)) else text
    toks = cjk_bigrams(name + " " + desc + " " + body[:600])
    # coverage：rule token 有多少比例出現在 canonical 準則檔
    if toks:
        hit = sum(1 for t in toks if t in canon_text)
        cov = hit / len(toks)
    else:
        cov = 0.0
    # evidence 路徑存活：記憶內引用的本機絕對路徑若已不存在 → 可能指向已退役的 script/檔案。
    # 只認本機家目錄開頭的絕對路徑：`~/xxx` 可能指遠端主機、`~60g` 是近似值波浪號，
    # 都不能拿本機 exists() 判死。ponytail: 遠端路徑留給覆審 session 自行確認。
    dead = []
    for p in set(re.findall(re.escape(home) + r'/[\w@./-]+', text)):
        p = p.rstrip('.')
        if not os.path.exists(p):
            dead.append(p)
    rules.append(dict(base=base, name=name, desc=desc, typ=typ or "feedback",
                      sev=sev, rc=rc, age=age, cov=cov, toks=toks, dead=sorted(dead)))

# dup hint：pairwise token Jaccard，挑 >=0.18 的對（保守，寧缺勿濫；只當候選）
dups = []
for i in range(len(rules)):
    for j in range(i + 1, len(rules)):
        a, b = rules[i]["toks"], rules[j]["toks"]
        if not a or not b:
            continue
        inter = len(a & b)
        union = len(a | b)
        jac = inter / union if union else 0
        if jac >= 0.18 and inter >= 4:
            dups.append((jac, rules[i], rules[j]))
dups.sort(key=lambda x: -x[0])

# demote 候選：coverage 高（>0.5）→ 概念可能已寫進 canonical 準則
demote = sorted([r for r in rules if r["cov"] > 0.5], key=lambda r: -r["cov"])

# LEARNINGS 膨脹監控
learn_path = os.path.join(project_dir, "LEARNINGS.md")
learn_size = learn_entries = 0
if os.path.exists(learn_path):
    learn_size = os.path.getsize(learn_path)
    lt = open(learn_path, encoding="utf-8").read()
    learn_entries = len(re.findall(r'\[(CORRECTION|BEST_PRACTICE|PATTERN|ANTIPATTERN|LEARNING)-', lt))

def sev_label(r):
    return r["sev"] if r["sev"] else "unknown"

out = []
out.append(f"# Memory Retirement Review — {month}")
out.append("")
out.append("> 機械收集報告（零 LLM）。下列全部是**候選**，需覆審 session 做語意判斷後才動手。")
out.append("> 判準是「是否仍承擔風險」不是「多久沒觸發」——age 大 ≠ 該砍。severity 未標 = 只能進人工覆審。")
out.append(f"> 來源：`{os.path.relpath(auto_dir, project_dir) if auto_dir.startswith(project_dir) else auto_dir}`/*.md（共 {len(rules)} 條，排除 MEMORY.md）+ LEARNINGS.md")
out.append("")

out.append("## 1. 全量盤點（inventory）")
out.append("")
out.append("| feedback | severity | rc | age(天) | coverage | type |")
out.append("|----------|----------|----|---------|----------|------|")
for r in sorted(rules, key=lambda r: -r["age"]):
    out.append(f"| `{r['base']}` | {sev_label(r)} | {r['rc'] if r['rc'] is not None else '—'} "
               f"| {r['age']} | {r['cov']:.0%} | {r['typ']} |")
out.append("")

out.append("## 2. Merge 候選（dup hint — token 重疊高，需語意確認是否真重疊）")
out.append("")
if dups:
    out.append("| Jaccard | 規則 A | 規則 B |")
    out.append("|---------|--------|--------|")
    for jac, a, b in dups[:15]:
        out.append(f"| {jac:.2f} | `{a['base']}` | `{b['base']}` |")
    out.append("")
    out.append("> ⚠️ token overlap 只是粗信號（CJK bigram），可能誤報。覆審時讀兩條原文確認 failure mode 是否真同源，"
               "確認才 merge（保留 incident link，不丟歷史）。")
else:
    out.append("（無 token 重疊達閾值的對）")
out.append("")

out.append("## 3. Demote 候選（coverage 高 — 概念可能已寫進 canonical 準則）")
out.append("")
if demote:
    out.append("| feedback | coverage | severity | 處置提示 |")
    out.append("|----------|----------|----------|----------|")
    for r in demote:
        hint = "需人工覆審（severity 未標，不自動 demote）" if not r["sev"] else "可考慮 demote 為短句索引"
        out.append(f"| `{r['base']}` | {r['cov']:.0%} | {sev_label(r)} | {hint} |")
    out.append("")
    out.append("> ⚠️ coverage 是 token 出現比例，不代表概念真被覆蓋。覆審時確認該規則的 corrective action "
               "是否已被 SOUL/spec/AGENTS 的某條硬規則接住；接住才 demote，否則保留 active。")
else:
    out.append("（無 coverage 超過 50% 的規則）")
out.append("")

out.append("## 4. 需人工覆審（severity 未標 → 一律不自動處理）")
out.append("")
unknown = [r for r in rules if not r["sev"]]
out.append(f"目前 **{len(unknown)}/{len(rules)}** 條 feedback 未標 severity。"
           "這些都**只能人工決定**，腳本不建議 auto-archive/delete。")
out.append("")
out.append("> 要安全自動化降載，先給每條 feedback 補 `severity:`（low/medium/high/critical）+ `opportunity_count`"
           "（被正確避開的次數）。")
out.append("")

out.append("## 5. LEARNINGS.md 膨脹監控")
out.append("")
out.append(f"- 檔案大小：**{learn_size/1024:.0f} KB**")
out.append(f"- entry 數（CORRECTION/BEST_PRACTICE/...）：**{learn_entries}**")
out.append("- 這裡只監控成長，不處理 LEARNINGS 內部 dedup。")
out.append("")

out.append("## 6. Evidence 路徑存活檢查（引用的檔案已不存在 → 更新/退役信號）")
out.append("")
stale_ev = [r for r in rules if r["dead"]]
if stale_ev:
    out.append("| feedback | 失效路徑 |")
    out.append("|----------|----------|")
    for r in stale_ev:
        out.append(f"| `{r['base']}` | " + "<br>".join(f"`{p}`" for p in r["dead"][:5]) + " |")
    out.append("")
    out.append("> ⚠️ 路徑失效 ≠ 記憶錯誤（可能只是搬家/改名）。覆審時更新路徑或標 stale，不自動刪。")
else:
    out.append("（所有引用路徑都存在）")
out.append("")

out.append("---")
out.append("")
out.append("## 覆審收尾 checklist")
out.append("")
out.append("1. 逐條看上面候選，**讀原文**確認語意（不要只信機械信號）")
out.append("2. 決定每條：保留 active / merge / demote / 暫不處理")
out.append("3. 真要動手：merge 保留 incident link、demote 留短句索引、**archive/delete 一律經你同意**")
out.append("4. 處理完 `rm .claude/flags/retire-review.flag` 收尾")

open(report_file, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"rules={len(rules)} dups={len(dups)} demote={len(demote)} stale_evidence={len(stale_ev)} learn_kb={learn_size//1024}")
PY

ANALYSIS="$(tail -1 "$LOG_FILE" 2>/dev/null || true)"
log "report written: $REPORT_FILE"

# Flag identity = retire:YYYY-MM → idempotent within a month. The review
# session removes the flag when done; this producer never auto-clears it.
EXISTING_ID=""
if [ -f "$FLAG_FILE" ]; then
  EXISTING_ID="$(sed -n 's/^identity: //p' "$FLAG_FILE" | head -1)"
fi
if [ "$EXISTING_ID" = "$IDENTITY" ]; then
  log "flag identity unchanged ($IDENTITY) → no rewrite/notify"
  exit 0
fi

TMP="$(mktemp)"
{
  echo "Memory retirement review pending — $MONTH candidate report is ready"
  echo "identity: $IDENTITY"
  echo "Report: $REPORT_FILE"
  echo "Action: read the report → review each candidate against the original text (mechanical signals are hints, not verdicts) → confirm with the user what to merge / demote / archive → apply (merge keeps incident links, demote leaves a one-line index, archive/delete only with consent)."
  echo "When done: rm .claude/flags/retire-review.flag"
} > "$TMP"
mv -f "$TMP" "$FLAG_FILE"
log "wrote flag (identity=$IDENTITY)"

if [ -z "${RETIRE_NO_NOTIFY:-}" ]; then
  notify "Memory retirement review ($MONTH): candidate report ready"
fi

find "$LOG_DIR" -name "memory-retire-candidates-*.log" -mtime +60 -delete 2>/dev/null || true

log "Done ($ANALYSIS)"
exit 0
