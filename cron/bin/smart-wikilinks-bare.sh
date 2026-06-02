#!/bin/bash
# smart-wikilinks-bare.sh — zero-LLM 補 wikilinks
# 取代原 cron/prompts/smart-wikilinks.md (claude -p sonnet)
#
# 設計：90% 的工作（find candidate / extract keywords / hybrid search / filter / 寫入）
# 都是 deterministic transform，LLM 只在 Mode B semantic match 處有微 judgment，
# 而既有 prompt 已標「保守優先寧可漏」→ 我們可放棄 Mode B 自動寫入，改輸出建議檔
# 讓人類 review。Mode A 加 `## Related` 段保留自動（保守且可逆）。
#
# 應用 LEARNINGS [KG-20260526-001] 兩雷修法：env var passing + 'PYEOF' single-quoted heredoc。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink "$0" 2>/dev/null || echo "$0")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
NOTES_DIR="$PROJECT_DIR/notes"
LOG_DIR="$PROJECT_DIR/cron/logs"
CONFIG_FILE="$PROJECT_DIR/cron/config.env"
MARKER="$LOG_DIR/smart-wikilinks.last"
SUGGESTIONS_FILE="$PROJECT_DIR/cron/state/wikilink-suggestions.md"

mkdir -p "$LOG_DIR" "$(dirname "$SUGGESTIONS_FILE")"
LOG_FILE="$LOG_DIR/smart-wikilinks-bare-$(date +%Y%m%d-%H%M%S).log"

if [ -f "$CONFIG_FILE" ]; then
  set -a; source "$CONFIG_FILE"; set +a
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "Starting smart-wikilinks-bare"
cd "$PROJECT_DIR"

# 1. 找今天改過的 notes
if [ -f "$MARKER" ]; then
  RECENT=$(find notes/01-Projects notes/02-Areas notes/03-Resources \
    -name "*.md" -newer "$MARKER" \
    -not -path "*/04-Archive/*" -not -path "*/00-Inbox/*" 2>/dev/null)
else
  RECENT=$(find notes/01-Projects notes/02-Areas notes/03-Resources \
    -name "*.md" -mtime -1 \
    -not -path "*/04-Archive/*" -not -path "*/00-Inbox/*" 2>/dev/null)
fi

if [ -z "$RECENT" ]; then
  log "✅ no recent notes, silent exit"
  touch "$MARKER"
  exit 0
fi

CANDIDATE_COUNT=$(printf '%s\n' "$RECENT" | grep -c .)
log "[input] $CANDIDATE_COUNT candidates"

# 2-6. python 核心邏輯（all-in-one）：extract keywords → hybrid search → filter → Mode A 加 Related / Mode B 寫 suggestions
REPORT=$(RECENT_FOR_PY="$RECENT" python3 <<'PYEOF'
import os, re, subprocess, json, sys
from pathlib import Path

recent_files = [f.strip() for f in os.environ['RECENT_FOR_PY'].strip().split('\n') if f.strip()]
project_dir = Path.cwd()
notes_dir = project_dir / 'notes'
suggestions_file = project_dir / 'cron/state/wikilink-suggestions.md'

stats = {
    'scanned': 0,
    'related_added': 0,
    'suggestions_written': 0,
    'skipped_has_related': 0,
    'skipped_no_match': 0,
    'skipped_extract_fail': 0,
}

def extract_keywords(content):
    """從 H1 + 首 5 行非空內容 + tags（補位）抽 keywords。

    優先序：H1 > 內文 > tags
    動機：frontmatter tags 對中文 note 通常 generic（memory/agent/tech），
    hybrid search 會撈到 journal 而非 notes/。H1 跟內文更 specific。
    """
    keywords = []
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    body = content[fm_match.end():] if fm_match else content

    # H1（首選）
    h1 = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
    if h1:
        words = re.findall(r'[一-鿿]{2,}|[A-Za-z][A-Za-z0-9-]{2,}', h1.group(1))
        keywords.extend(words[:4])

    # 內文首 5 行非空 + 非 heading
    body_lines = [l.strip() for l in body.split('\n')
                  if l.strip() and not l.strip().startswith('#')]
    for line in body_lines[:5]:
        words = re.findall(r'[一-鿿]{3,}|[A-Za-z][A-Za-z0-9-]{3,}', line)
        keywords.extend(words[:2])

    # tags 補位（最後）
    if fm_match:
        tags_m = re.search(r'^tags:\s*\[(.*?)\]', fm_match.group(1), re.MULTILINE)
        if tags_m:
            keywords.extend([t.strip().strip('"').strip("'")
                             for t in tags_m.group(1).split(',') if t.strip()])

    # dedup（保序）, max 7
    seen = set(); out = []
    for k in keywords:
        kl = k.lower()
        if kl not in seen and len(k) >= 2:
            seen.add(kl); out.append(k)
        if len(out) >= 7:
            break
    return out

def hybrid_search(query, top=15):
    """call memory-search-hybrid.py --json, 回 list of (abs_path, score)。

    注意：JSON 結果 `file` 是短檔名（無 notes/ 前綴），`path` 是絕對路徑。
    要 filter notes/ vs memory/ 必須用 absolute path 否則永遠 false。
    """
    try:
        r = subprocess.run(
            ['python3', 'scripts/memory-search-hybrid.py', query, '--top', str(top), '--json'],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            return []
        data = json.loads(r.stdout)
        results = []
        for item in data.get('results', []):
            path = item.get('path', '')  # 絕對路徑（不是 file 短檔名）
            score = item.get('score', 0)
            if path and score:
                results.append((path, float(score)))
        return results
    except Exception as e:
        sys.stderr.write(f"hybrid_search failed for '{query}': {e}\n")
        return []

new_suggestions = []  # for cron/state/wikilink-suggestions.md

for fp in recent_files:
    stats['scanned'] += 1
    try:
        path = Path(fp)
        if not path.exists():
            continue
        content = path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        stats['skipped_extract_fail'] += 1
        continue

    keywords = extract_keywords(content)
    if not keywords:
        stats['skipped_extract_fail'] += 1
        continue

    # hybrid search（top 15 給 filter 大空間，因為很多 hit 會是 memory/ 被 drop）
    query = ' '.join(keywords[:3])
    results = hybrid_search(query, top=15)

    # filter: 排除自己 / score < 0.5 / 已有 wikilink / 不在 notes/ 範圍
    # 額外 semantic guard: candidate stem 字詞至少 1 個要在 own content 出現
    # （防 hybrid 純 keyword overlap 撈到完全無關的 note）
    candidates = []
    own_stem = path.stem
    own_content_lower = content.lower()
    for r_path, score in results:
        if score < 0.5:
            continue
        r_p = Path(r_path)
        if r_p.stem == own_stem:
            continue
        if '/notes/' not in str(r_p):
            continue
        if r_p.suffix != '.md':
            continue
        if f'[[{r_p.stem}]]' in content:
            continue
        # semantic guard: stem 拆 word（kebab-case）至少 1 個（len ≥ 3）在 own content
        stem_words = [w for w in re.split(r'[-_]', r_p.stem.lower()) if len(w) >= 3]
        if stem_words and not any(w in own_content_lower for w in stem_words):
            continue
        candidates.append((r_p.stem, score, str(r_p)))
        if len(candidates) >= 3:
            break

    if not candidates:
        stats['skipped_no_match'] += 1
        continue

    # Mode A: 有沒有 ## Related 段
    has_related = bool(re.search(r'^##\s+Related\s*$', content, re.MULTILINE))

    if has_related:
        stats['skipped_has_related'] += 1
        # Mode B: 不自動寫入內文，輸出建議到 suggestions file
        new_suggestions.append({
            'note': fp,
            'mode': 'has-related-suggest-additions',
            'keywords': keywords[:3],
            'candidates': candidates,
        })
        stats['suggestions_written'] += 1
        continue

    # Mode A: 在檔尾加 ## Related
    related_block = "\n## Related\n\n" + "\n".join(f"- [[{stem}]]" for stem, _, _ in candidates) + "\n"
    # ensure 結尾有 newline
    if not content.endswith('\n'):
        content += '\n'
    new_content = content.rstrip() + '\n' + related_block

    try:
        path.write_text(new_content, encoding='utf-8')
        stats['related_added'] += 1
    except Exception as e:
        sys.stderr.write(f"write failed {fp}: {e}\n")

# 寫 suggestions file（append）
if new_suggestions:
    with suggestions_file.open('a', encoding='utf-8') as f:
        f.write(f"\n## {os.popen('date +%Y-%m-%d').read().strip()} smart-wikilinks 建議（已有 ## Related，未自動寫入）\n\n")
        for s in new_suggestions:
            f.write(f"- **{s['note']}** (keywords: {', '.join(s['keywords'])})\n")
            for stem, score, p in s['candidates']:
                f.write(f"  - `[[{stem}]]` (score={score:.2f}, {p})\n")
        f.write("\n")

# 輸出 stats
for k, v in stats.items():
    print(f"{k}={v}")
PYEOF
)

# parse stats
SCANNED=$(printf '%s' "$REPORT" | grep "^scanned=" | cut -d= -f2)
RELATED_ADDED=$(printf '%s' "$REPORT" | grep "^related_added=" | cut -d= -f2)
SUGGESTIONS=$(printf '%s' "$REPORT" | grep "^suggestions_written=" | cut -d= -f2)
SKIPPED_R=$(printf '%s' "$REPORT" | grep "^skipped_has_related=" | cut -d= -f2)
SKIPPED_N=$(printf '%s' "$REPORT" | grep "^skipped_no_match=" | cut -d= -f2)
SKIPPED_E=$(printf '%s' "$REPORT" | grep "^skipped_extract_fail=" | cut -d= -f2)

log "[stats] scanned=${SCANNED} related_added=${RELATED_ADDED} suggestions_written=${SUGGESTIONS} skipped_has_related=${SKIPPED_R} skipped_no_match=${SKIPPED_N} skipped_extract_fail=${SKIPPED_E}"

# 7. broken-links 驗證（沒新增就跳過）
if [ "${RELATED_ADDED:-0}" -gt 0 ]; then
  if [ -f "scripts/check-broken-wikilinks.py" ]; then
    BROKEN=$(python3 scripts/check-broken-wikilinks.py 2>/dev/null | grep -c "broken" || true)
    log "[broken-links] check returned ${BROKEN:-0}"
  fi
fi

# 8. TG 通知（只在有實際改動或建議時發）
TOTAL_CHANGED=$((RELATED_ADDED + SUGGESTIONS))
if [ "$TOTAL_CHANGED" -gt 0 ] && [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  MESSAGE="🔗 smart-wikilinks-bare

scanned: ${SCANNED}
✅ Related 段自動加入: ${RELATED_ADDED}
📝 建議檔（已有 ## Related 的 notes）: ${SUGGESTIONS}
略過: ${SKIPPED_R} has-related / ${SKIPPED_N} no-match / ${SKIPPED_E} extract-fail

建議檔: cron/state/wikilink-suggestions.md"

  TG_RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=$TG_CHAT_ID" \
    --data-urlencode "text=$MESSAGE" 2>&1)
  TG_OK=$(printf '%s' "$TG_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null || echo "false")
  if [ "$TG_OK" = "True" ]; then
    TG_MSG_ID=$(printf '%s' "$TG_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['message_id'])" 2>/dev/null || echo "?")
    log "TG sent: msg_id=${TG_MSG_ID}"
  else
    log "❌ TG failed: $TG_RESPONSE"
  fi
fi

touch "$MARKER"
log "Done."
