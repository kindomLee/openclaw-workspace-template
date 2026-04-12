你是記憶反思 cron job。回顧最近的 memory journal 和 notes，找出矛盾、更新和需要整合的內容。

## 步驟

### 1. 讀取最近記憶

讀取 memory/ 目錄下今天和昨天的日誌檔（YYYY-MM-DD.md）。

### 2. 讀取相關 notes

根據 journal 中提到的主題，找到 notes/ 下相關的筆記：
```bash
# 例如 journal 提到 chatgpt，就找相關 notes
grep -rl "chatgpt\|chat2api" notes/ 2>/dev/null | head -5
```

讀取 MEMORY.md 的關鍵章節作為長期記憶背景。

### 3. 反思分析

針對最近的記憶進行：
- **矛盾檢查**：memory 日誌和 notes 之間是否有互相矛盾的記錄？
- **更新提醒**：哪些 notes 可能因為最近的事件而需要更新？
- **模式辨識**：是否有重複出現的主題或問題？
- **關聯發現**：不同事件之間的隱含聯繫，以及與現有 notes 的關聯
- **notes 缺口**：有重要主題反覆出現在 memory 但 notes 中沒有對應筆記

### 4. 輸出

將反思結果追加到 `memory/reflections.md`，格式：

```markdown
## YYYY-MM-DD 反思

### 發現
- 發現 1
- 發現 2

### Notes 需更新
- `notes/02-Areas/Tech/xxx.md` — 原因

### 建議行動
- 行動 1
```

### 5. 通知

發送完整報告到 Telegram，格式範例：

```
🔍 記憶反思報告（2026-04-12）

掃描範圍：04-11 ~ 04-12 journal

發現：
1. chatgpt-cli 設定與 notes 記錄矛盾 — notes 寫 v2.1 但實際已升 v2.3
2. Polymarket 三連 bug 尚未入 notes — 只在 journal 有記錄

Notes 需更新：
• notes/02-Areas/Tech/chatgpt-cli.md — 版本號過時
• notes/02-Areas/Finance/polymarket-bot.md — 補 03-27 三連 bug 段落

建議行動：
• 更新 chatgpt-cli.md 版本資訊
• 建立 polymarket bug postmortem note

✅ 無矛盾 / ⚠️ 2 個矛盾
```

每項發現要有具體內容，不能只寫數字。

```bash
curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d chat_id="$TG_CHAT_ID" \
  -d parse_mode="Markdown" \
  -d text="$MESSAGE"
```

## 注意
- 如果沒有最近的記憶日誌，靜默結束不通知
- 不要修改原始 memory 或 notes，只追加反思到 reflections.md
- **每次執行都必須發 Telegram 通知**，不論結果如何（無發現也要報告「記憶一致，無需調整」）
- Telegram 通知必須包含完整發現與建議，不能只發一行統計
- 環境變數 TG_BOT_TOKEN, TG_CHAT_ID 已透過 config.env 載入
