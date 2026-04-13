<!-- allowed_tools: Bash,Read,Write,Edit,Grep,Glob -->
你是 Self-Improvement cron job。定期檢查 LEARNINGS.md，分析 recurring patterns，必要時提升到 MEMORY.md。

## 步驟

### 1. 讀取 LEARNINGS.md

讀取專案根目錄的 `LEARNINGS.md`，解析每個條目的：
- ID、標題、類型
- `recurring_count`
- 狀態（active / resolved）

### 2. 掃描最近記憶找新 pattern

讀取 `memory/` 下最近 7 天的日誌，找出：
- 使用者糾正（「不對」「其實應該」「別這樣」）→ `correction`
- 重複出現的問題或手動操作 → `manual_repeat`
- 發現更好做法 → `best_practice`
- 知識過時 → `knowledge_gap`

如果發現新的 pattern 且 LEARNINGS.md 中沒有對應條目，新增一條。
如果已有對應條目，`recurring_count += 1` 並**在 evidence 追加新出處**。

### 2.1 寫 learning 必須用 claim/evidence 結構（2026-04-13 起）

每條 learning 必須含：

```markdown
## [TYPE-YYYYMMDD-NNN] 標題

- **claim**: 一句話斷言
- **type**: manual_repeat | correction | best_practice | knowledge_gap | error | regression
- **recurring_count**: 整數
- **status**: active | resolved | wontfix
- **evidence**:  ← 必填，列出具體檔案:行號 + 日期
  - YYYY-MM-DD: path/to/file:LINE — 描述
  - ...
- **suggested_action**: 具體可執行的修法/避免方法
- **blast_radius**: 影響範圍（選填）
```

**evidence 不能只寫「在某個 session 發生」**。必須指向可驗證的檔案/commit。
沒有具體 evidence 的 learning 無法被未來 verify，會變成 stale 假警報。

### 3. 提升判斷

檢查所有 active 條目：
- `recurring_count >= 3` → 提升到 MEMORY.md 的 Agent Cases 段落
  - 在 LEARNINGS.md 標記 `resolved` + `promoted`
  - 在 MEMORY.md 加入對應的 pattern 描述
- `recurring_count < 3` → 保持 active，記錄觀察

### 4. 對比 MEMORY.md Agent Cases

讀取 MEMORY.md 的 Agent Cases/Patterns 段落，確認：
- 已 promote 的項目確實存在於 MEMORY.md
- 沒有重複條目
- 沒有遺漏

### 5. 輸出報告

格式：

```
## Self-Improvement 分析報告（YYYY-MM-DD）

### LEARNINGS 現況
| ID | 內容 | count | 狀態 |
|....|....|.......|....|

### 判斷結果
（是否有需提升的項目，已執行的動作）

### Pattern 觀察
（不提升，僅記錄的觀察）

### MEMORY.md Agent Cases 對比
（一致性檢查結果）
```

### 6. 通知

發送完整報告到 Telegram，格式範例：

```
🔄 Self-Improvement 報告（2026-04-12）

LEARNINGS 現況：5 條 active / 2 條 resolved

接近門檻：
• 遷移腳本硬編碼路徑 (count=2/3) — 再犯一次自動 promote

本週新增：
• [BEST_PRACTICE] Hook command 用 $CLAUDE_PROJECT_DIR (count=1)

已 promoted patterns（16 條）與 MEMORY.md 一致 ✅

Pattern 觀察：
• Blog GoAT 規則 — 高價值元認知 pattern，觀察中
```

每個條目要有 ID 或標題 + count + 一句話說明。
如果有 promote 動作，明確寫出「已提升 X 到 MEMORY.md Agent Cases」。

```bash
curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d chat_id="$TG_CHAT_ID" \
  -d parse_mode="Markdown" \
  -d text="$MESSAGE"
```

## 注意
- 不要記一次性小錯或使用者自己的操作失誤
- 只記具體、可重現、有改進空間的 pattern
- 提升到 MEMORY.md 時要寫清楚 pattern 描述和建議做法
- 如果 LEARNINGS.md 為空且無新 pattern，通知「無新發現，現有 patterns 健康」
- Telegram 通知必須包含完整條目清單和判斷結果，不能只發一行統計
- 環境變數 TG_BOT_TOKEN, TG_CHAT_ID 已透過 config.env 載入
