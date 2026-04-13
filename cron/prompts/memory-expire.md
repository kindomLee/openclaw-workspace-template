你是記憶清理 cron job。歸檔過期的 memory 日誌和 notes。

## 步驟

### 1. Memory 歸檔

找出 memory/ 下超過 60 天的日誌：
```bash
find memory/ -name "20??-??-??.md" -mtime +60 -not -path "*/archive*" 2>/dev/null
```

移到對應的 archive 目錄：
```bash
mkdir -p memory/archive-YYYY-MM
mv memory/2026-01-15.md memory/archive-2026-01/
```

### 2. Notes 歸檔檢查

找出 notes/01-Projects/Active/ 下超過 90 天未修改的專案：
```bash
find notes/01-Projects/Active/ -name "*.md" -mtime +90 2>/dev/null
```

讀取這些檔案的 frontmatter，如果 status 不是 `active`，或內容明顯已完成，建議歸檔到 `notes/01-Projects/Archive/`。

**注意：只建議，不自動搬移。** 列出清單讓使用者確認。

### 3. 超舊 archive 清理

刪除 5 年以上的 archive 內容。

### 4. 報告

發送完整報告到 Telegram，格式範例：

```
🗄️ 記憶歸檔報告（2026-04-01）

Memory 歸檔：
• 8 份日誌 → archive-2026-02/
  2026-02-01 ~ 2026-02-08

Notes 建議歸檔（需確認）：
• budget-tokens-verification-2026-03.md — 90 天未修改，status: done
• gpu-infrastructure-2026.md — 內容已完成

現況：12 份活躍日誌 / 5 個月份 archive
```

列出實際歸檔的檔案範圍和建議歸檔的具體筆記名稱。

```bash
curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d chat_id="$TG_CHAT_ID" \
  -d parse_mode="Markdown" \
  -d text="$MESSAGE"
```

## 注意
- 每月 1 日 03:33 執行
- Memory 日誌直接歸檔（自動）
- Notes 專案只建議不搬移（需確認）
- **每次執行都必須發 Telegram 通知**，不論結果如何（無變動也報告「無需歸檔」）
- Telegram 通知必須包含具體歸檔清單，不能只發一行統計
- 環境變數 TG_BOT_TOKEN, TG_CHAT_ID 已透過 config.env 載入
