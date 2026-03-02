---
name: memory-arch
description: 為 AI Agent 建立多層次記憶系統（三層儲存、P 級優先、漸進檢索、自動維護）
user-invocable: true
trigger-keys:
  - 設定記憶系統
  - 建立記憶架構
  - 初始化記憶
  - memory architecture
  - 記憶系統
---

# Memory Architecture Skill

為 AI Agent 建立多層次記憶系統，讓 Agent 告別「每次重啟都是新人」的困擾。

## 觸發時機

當使用者說：
- 「設定記憶系統」
- 「建立記憶架構」
- 「初始化記憶」
- 或新 workspace 首次對話

## 使用方式

### 快速建立

```bash
# 方法 1：執行 scaffold.sh
bash /path/to/skill/scripts/scaffold.sh /path/to/workspace

# 方法 2：一行指令（推薦）
curl -fsSL https://raw.githubusercontent.com/kindomLee/openclaw-memory-arch/main/bootstrap.sh | bash -s -- /path/to/workspace
```

### 執行後

1. 填寫模板中的 placeholder（使用者資訊、偏好等）
2. 每次對話開始時讀取：
   - `SOUL.md` — 了解自己是誰
   - `USER.md` — 了解使用者
   - `memory/YYYY-MM-DD.md` — 今日工作日誌
   - `MEMORY.md` — 長期記憶（main session 專用）

## 核心概念（精簡版）

### 三層儲存

| 層級 | 檔案 | 用途 | 生命周期 |
|------|------|------|----------|
| Session | 記憶體 | 當前對話上下文 | 會話結束丟棄 |
| Daily | `memory/*.md` | 每日工作日誌 | 90 天後歸檔 |
| Long-term | `MEMORY.md` | 重要知識庫 | 永久保留 |

### P 級優先級

- **P0**：永久保留 — 基礎設施、使用者偏好、核心原則
- **P1**：90 天審視 — 技術方案、專案資訊
- **P2**：30 天壓縮 — 實驗記錄、臨時任務

### 檢索策略

三段式漸進檢索：
1. **搜尋**：用 `memory_search` 查詢
2. **改寫**：結果不夠？改寫關鍵詞再搜
3. **讀檔**：還不夠？直接讀取相關 daily-log

### 自動化維護

設定每日 cron 執行 `memory-janitor.py`：

```bash
# 每日 20:02 執行
02 20 * * * python3 /path/to/workspace/scripts/memory-janitor.py --force
```

或使用 OpenClaw cron：
```bash
openclaw cron add --name 'memory-janitor' --at '20h' --session main
```

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `MEMORY.md` | 長期知識庫，包含 Events、User Profile、Infrastructure 等 |
| `AGENTS.md` | Agent 行為準則、工具偏好、session 規則 |
| `SOUL.md` | Agent 人格設定（名稱、性格、風格） |
| `USER.md` | 使用者資訊（名字、偏好、設備） |
| `memory/YYYY-MM-DD.md` | 每日工作日誌 |
| `scripts/memory-janitor.py` | 自動化維護腳本 |

## 詳細文件

- [architecture.md](https://github.com/kindomLee/openclaw-memory-arch/blob/main/architecture.md) — 完整架構說明
- [comparisons.md](https://github.com/kindomLee/openclaw-memory-arch/blob/main/comparisons.md) — 與其他方案比較

## 維護紀錄

- **建立**：Agent 首次初始化時自動建立
- **更新**：重要決策/設定變更時寫入 `memory/YYYY-MM-DD.md`
- **整理**：每日自動執行 janitor 腳本
