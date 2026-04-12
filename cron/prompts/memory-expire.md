你是記憶過期歸檔 cron job。將超過 30 天的日誌自動搬到歸檔目錄。

## 步驟

### 1. 掃描過期檔案

列出 memory/ 目錄下所有 YYYY-MM-DD.md 檔案，找出超過 30 天的。
排除：dreams.md、reflections.md、timeline-archive.md 等非日誌檔。

### 2. 歸檔

將過期的日誌搬到 `memory/archive-YYYY-MM/` 目錄：

```bash
# 例如 2026-01-15.md → memory/archive-2026-01/2026-01-15.md
mkdir -p memory/archive-2026-01
mv memory/2026-01-15.md memory/archive-2026-01/
```

### 3. 統計報告

計算：
- 歸檔了幾個檔案
- 目前 memory/ 還剩幾個活躍日誌
- archive 總共有幾個月份

### 4. 通知

```bash
curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d chat_id="$TG_CHAT_ID" \
  -d text="📦 記憶歸檔完成：N 個檔案歸檔，M 個活躍日誌"
```

## 注意
- 如果沒有需要歸檔的檔案，靜默結束不通知
- 環境變數 TG_BOT_TOKEN, TG_CHAT_ID 已透過 config.env 載入
