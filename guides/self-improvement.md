# Self-Improvement Guide — AI Agent 自我改進指南

## 為什麼 AI Agent 需要 Self-Improvement？

AI Agent 在長期運行過程中會遇到各種問題：
- 指令執行失敗
- 知識過時或錯誤
- 使用者糾正行為
- 重複手動操作
- 新需求無法滿足

傳統的 AI 系統會忘記這些經驗，但一個真正有用的 Agent 應該能從錯誤中學習，不斷改進自己的能力。

## 三級信號分類系統

### 🔴 Repair — 需要修復的問題

| 觸發條件 | 記錄位置 | 類型 | 範例 |
|----------|----------|------|------|
| 指令/操作失敗 | `.learnings/ERRORS.md` | `error` | API 調用失敗、檔案讀取錯誤 |
| 使用者糾正（「不對」「其實應該...」） | `LEARNINGS.md` | `correction` | 理解錯誤、參數設定錯誤 |
| 之前修好的問題又壞了 | `.learnings/ERRORS.md` | `regression` | 程式碼回歸、設定重置 |

### 🟡 Optimize — 可以改進的地方

| 觸發條件 | 記錄位置 | 類型 | 範例 |
|----------|----------|------|------|
| 知識過時或錯誤 | `LEARNINGS.md` | `knowledge_gap` | API 版本更新、文檔變更 |
| 發現更好的做法 | `LEARNINGS.md` | `best_practice` | 更有效的指令、更好的流程 |
| 手動重複操作 2+ 次 | `LEARNINGS.md` | `manual_repeat` | 應該自動化的重複任務 |

### 🟢 Innovate — 新需求

| 觸發條件 | 記錄位置 | 類型 | 範例 |
|----------|----------|------|------|
| 使用者要求不存在的功能 | `.learnings/FEATURE_REQUESTS.md` | `feature` | 新的整合、新的工作流程 |
| 想做但目前做不到 | `.learnings/FEATURE_REQUESTS.md` | `capability_gap` | 缺少工具、需要新技能 |

## 格式規範

`LEARNINGS.md` 放在 workspace 根目錄，用 claim／evidence 欄位，格式寫在該檔開頭；`learnings-promotion-check`、`learnings-archive`、週檢查都會解析那些欄位名稱，不要改。

`.learnings/ERRORS.md`、`.learnings/FEATURE_REQUESTS.md` 沒有程式解析，用以下格式：

```markdown
## [TYPE-YYYYMMDD-XXX] 標題

**Summary:** 一句話概述問題/改進點

**Details:**
詳細描述情況，包含：
- 觸發條件
- 實際發生狀況
- 預期結果 vs 實際結果

**Suggested Action:**
建議的解決方案或改進方法

**Fields:**
- recurring_count: 1 (同一模組/問題出現次數)
- module: [相關模組/功能名稱]
- severity: [low/medium/high]
- status: [pending/resolved/archived]
```

### 必填欄位說明

- **recurring_count**: 記錄同一問題出現的次數，初次為 1
- **module**: 相關的功能模組（如：memory, email, cron, browser）
- **severity**: 問題嚴重程度
- **status**: 處理狀態

## Recurring Count 機制

### 提升規則
當 `recurring_count ≥ 3` 時，該問題應該提升到 `MEMORY.md` 的相關區塊：
- **Agent Cases** - 重複出現的問題模式
- **Patterns** - 常見的行為模式
- **Learnings** - 重要的知識點

### 計數原則
- 同一個功能模組的相同類型問題 +1
- 不同根本原因的問題分開計算
- 已解決但再次出現的問題重新計數

## 什麼不要記錄

- **一次性小錯誤**: 打字錯誤、偶發網路問題
- **已知系統限制**: 無法改變的外部限制
- **使用者操作失誤**: 非 Agent 問題的錯誤
- **測試性質操作**: 刻意的實驗和測試

## 實際範例

### 範例 1: Error 類型
```markdown
## [ERROR-20241201-001] Cron 任務無法正確設定

**Summary:** OpenClaw cron add 指令執行成功但任務未運行

**Details:**
觸發條件：使用 `openclaw cron add --at "1h"` 設定提醒
實際狀況：指令回傳成功，但檢查 `openclaw cron list` 沒有任務
預期結果：任務應該出現在列表中並正常執行

**Suggested Action:**
1. 檢查 gateway 狀態
2. 驗證 cron 語法格式
3. 加入執行後驗證步驟

**Fields:**
- recurring_count: 1
- module: cron
- severity: medium
- status: pending
```

### 範例 2: Knowledge Gap 類型
```markdown
## [KNOWLEDGE-20241201-002] GitHub API 限制不熟悉

**Summary:** 不知道 GitHub API 有 rate limit，導致批次操作失敗

**Details:**
觸發條件：執行大量 GitHub 操作
實際狀況：API 回傳 403 錯誤
學到的知識：GitHub API 有每小時 5000 次請求限制

**Suggested Action:**
更新 MEMORY.md 記錄 GitHub API 限制和解決方案

**Fields:**
- recurring_count: 1
- module: github
- severity: low
- status: resolved
```

## 整合到 AGENTS.md

在 `AGENTS.md` 中加入自我改進檢查機制：

```markdown
## 自我改進（Self-Improvement）
偵測到以下情況時，立即記錄到 `LEARNINGS.md` 或 `.learnings/`：

### 信號分類（三級）
[插入完整的觸發條件表格]

### 格式
`LEARNINGS.md`：依該檔開頭的 claim／evidence 欄位；`.learnings/*.md`：`## [TYPE-YYYYMMDD-XXX] 標題` + Summary + Details + Suggested Action
- **必填欄位：** `recurring_count`（同一模組/問題出現幾次，首次為 1）
- **提升規則：** recurring_count ≥ 3 → 提升到 MEMORY.md 的 Agent Cases/Patterns
- **不要記的：** 一次性小錯、已知限制、使用者自己的操作失誤

**原則：** 立即記、要具體、附重現步驟、建議具體修法
```

## 維護週期

### 每週檢查
- 檢視 `LEARNINGS.md`（status: active）與 `.learnings/`（status: pending）的項目
- 更新已解決項目的 status
- 將 recurring_count ≥ 3 的項目提升到 MEMORY.md

### 每月整理
- 歸檔已解決且穩定的問題
- 分析問題模式，更新預防措施
- 更新相關文檔和流程

記住：**立即記錄比完美格式更重要**。有問題就先記下來，格式可以後續整理。
