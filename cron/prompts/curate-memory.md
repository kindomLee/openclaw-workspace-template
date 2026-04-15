<!-- allowed_tools: Bash,Read,Write,Edit,Grep,Glob -->
Cron curate-memory wrapper（定期跑，預設 no-op 快速返回）。

## 設計原則

這個 cron 大多數時候應該**什麼都不做**。只有在 memory/ journal 有新內容時才真的啟動 `/curate-memory` skill 做完整歸檔流程。目的是「維持低頻主動歸檔」，不要 LLM 空轉燒 token。

## 步驟 1：Early return 檢查（必做）

執行這段檢查，若沒有新資訊則**立刻輸出 `✅ no new info` 並退出**，不啟動 curate 流程：

```bash
MARKER="cron/logs/curate-memory.last"
mkdir -p "$(dirname "$MARKER")"

if [ ! -f "$MARKER" ]; then
  # 第一次跑：marker 不存在，當作有內容要處理
  echo "[first run] no marker, will check all recent journal"
  NEW_FILES=$(find memory/ -maxdepth 1 -name "20??-??-??.md" -mtime -7 2>/dev/null)
else
  # 掃 marker 之後有變動的 daily journal
  NEW_FILES=$(find memory/ -maxdepth 1 -name "20??-??-??.md" -newer "$MARKER" 2>/dev/null)
fi

if [ -z "$NEW_FILES" ]; then
  echo "✅ no new journal entries since last curate ($(date '+%Y-%m-%d %H:%M'))"
  touch "$MARKER"
  exit 0
fi

echo "📝 new journal activity detected:"
echo "$NEW_FILES"
```

**若 `NEW_FILES` 為空 → 立刻結束，不往下做**。不要呼叫 skill、不要啟動任何工具、不要產生 token 消耗。

## 步驟 2：有新資訊才跑 curate-memory

有新 journal 檔案才執行 `/curate-memory` skill 的完整流程：

1. 讀取 `$NEW_FILES` 列出的每個 daily journal
2. 對每條未歸檔的 entry，用 hybrid search 查重：
   ```bash
   python3 scripts/memory-search-hybrid.py "<關鍵字>" --days 90 --top 5
   ```
3. 依 `.claude/skills/curate-memory/SKILL.md` 的 Context Tree 分類決策樹決定存到：
   - `memory/YYYY-MM-DD.md`（事件）
   - `MEMORY.md`（長期索引 P0/P1/P2）
   - `notes/02-Areas/` 或 `notes/03-Resources/`（主題知識，合併優先）
   - `LEARNINGS.md`（錯誤/教訓）
4. 跑完後 `touch cron/logs/curate-memory.last` 紀錄本次時間戳

## 步驟 3：回報 + Telegram 通知

### stdout 輸出格式
- 無新資訊：`✅ no new info (last check: $(date))`
- 有整理：`✅ curated N entries: <摘要每條去哪>`
- 失敗：清楚說明失敗原因 + 保留 marker 不更新

### Telegram 通知（**只在有實際整理時才發**）

**跳過 TG**：
- 無新資訊（early return → 完全靜音，避免 hourly job 每小時噪音）
- 失敗（靠 runner.sh timeout / 四防線第 4 條的 TG fallback）

**發 TG**：步驟 2 真的動了 MEMORY.md / notes/ / LEARNINGS.md 時：

```bash
# 只在有 promote/merge 發生時執行
curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d chat_id="$TG_CHAT_ID" \
  -d parse_mode="Markdown" \
  -d text="📚 curate-memory 完成（$(date '+%Y-%m-%d %H:%M')）
- MEMORY.md Timeline：+N 筆
- MEMORY.md Cases / Learnings：+M 筆
- notes/ merged / new：K / L
- skipped (dup)：S
詳見 cron/logs/curate-memory-*.log" \
  >/dev/null 2>&1 || true
```

TG 訊息必須包含**具體統計數字**，不能只發一行「完成」。
環境變數 `TG_BOT_TOKEN` / `TG_CHAT_ID` 透過 `cron/config.env` 載入。

## 重要限制

- **不要改 SKILL.md 本身**：SKILL.md 是 Mac 和 VPS 共用的，cron 的早退邏輯只放在本 prompt 檔
- **不要觸發其他 skill**：只在「步驟 2」才呼叫 `/curate-memory`，步驟 1 純 bash
- **失敗保留 marker 原狀**：若 curate 過程中出錯，不要 touch marker，讓下次重試
