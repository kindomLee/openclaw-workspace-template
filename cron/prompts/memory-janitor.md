<!-- expected_interval: 86400 -->
你是記憶品質整理 cron job。檢查 memory/ 和 notes/ 的品質並進行維護。

## 步驟

### 1. Hall Tag 補標

掃描檔名日期在最近 7 天內的日誌（含已輪替到 `memory/archive-YYYY-MM/` 的：`find memory/ -name "20??-??-??.md" | awk -F/ -v c="$(date -v-7d +%F 2>/dev/null || date -d '7 days ago' +%F)" '{n=$NF; sub(/\.md$/, "", n); if (n >= c) print}'`），找出缺少 hall tag 的 entry。

每條 entry 應該以 `[hall_*]` 開頭：
- `[hall_facts]` — 決定、決策、選擇
- `[hall_events]` — 錯誤、修復、更新（預設）
- `[hall_discoveries]` — 發現、研究、分析
- `[hall_preferences]` — 偏好、喜歡、習慣
- `[hall_advice]` — 建議、推薦

對缺少 tag 的 entry，根據內容自動補上適當的 hall tag。

### 2. 重複檢查

檢查最近 7 天的日誌中是否有重複或高度相似的 entry，如有則標記（在行尾加 `<!-- dup? -->`）。

### 3. Notes 品質檢查

掃描 notes/ 下最近修改的筆記（7 天內），檢查：
- **Frontmatter 完整性**：是否有 title、date、tags、status
- **Wikilink 互連**：是否有 `## Related` 區塊且至少 2 個 wikilink
- **檔名規範**：是否符合 kebab-case，有無日期前綴

輸出缺陷清單，但不自動修復（避免破壞筆記結構）。

### 4. MEMORY_COMPACT.md 更新

MEMORY_COMPACT.md 是產生檔，不要直接改。若 MEMORY.md 的 compact block（`<!-- compact:start -->` 到 `<!-- compact:end -->`）需要加入最近重要事件，改 MEMORY.md，然後執行 `python3 scripts/compact-update.py` 重新產生。沒有要改也照樣執行一次，讓 MEMORY_COMPACT.md 跟 MEMORY.md 同步。

### 5. 報告

發送完整報告到 Telegram，格式範例：

```
🧹 Memory Janitor 報告（2026-04-12）

Hall Tag 補標：
• 2026-04-12.md — 補標 3 條（2× hall_events, 1× hall_discoveries）
• 2026-04-11.md — 全部已標記 ✅

重複檢查：
• 2026-04-12.md 第 15 行 ≈ 第 23 行（疑似重複，已標記）

Notes 品質：
• research-notes.md — 缺 tags
• blog-content-2026.md — 缺 Related 區塊

MEMORY_COMPACT：L1_RECENT 已更新
```

列出具體修改的檔案和行為，不能只發統計數字。

```bash
curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d chat_id="$TG_CHAT_ID" \
  -d parse_mode="Markdown" \
  -d text="$MESSAGE"
```

## 注意
- 直接修改 memory 檔案（補 hall tag、標記重複）是允許的
- notes 檔案只報告缺陷，不自動修改
- 不要刪除任何 entry
- **每次執行都必須發 Telegram 通知**，不論結果如何（無變動也報告「全部乾淨」）
- Telegram 通知必須包含具體修改和發現，不能只發一行統計
- 環境變數 TG_BOT_TOKEN, TG_CHAT_ID 已透過 config.env 載入
