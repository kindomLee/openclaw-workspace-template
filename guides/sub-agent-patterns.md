# Sub-agent Patterns Guide — 子代理模式指南

> ⚠️ **This guide is OpenClaw-specific.** It documents OpenClaw's
> multi-session architecture (`sessions_spawn` / `sessions_send` /
> `announce` / `STATUS_PENDING` marker files / MiniMax-as-sub-agent).
>
> **Claude Code users**: use the built-in `Agent` tool with a
> `subagent_type` argument instead. Claude Code sub-agents are
> synchronous — the `Agent` call blocks until the sub-agent returns a
> single result message, so you don't need `sessions_send`,
> `STATUS_PENDING` marker files, or a `REVIEW_THEN_DELIVER` protocol.
> A future revision of this guide will split the Claude Code and
> OpenClaw tracks; until then, treat this doc as OpenClaw-only and
> refer to Anthropic's Claude Code docs for the native sub-agent API.

## 為什麼需要 Sub-agent？

Main agent 負責與使用者互動、維護上下文、做重要決策。但某些任務適合委派：

- **資料處理任務**: 爬取、解析、格式轉換
- **研究型任務**: 查詢資料、比較方案、分析報告
- **批次操作**: 檔案整理、批次上傳、程式碼生成
- **「試試看」任務**: 使用者說「試試看」「去測試」的探索性任務

## Inject-Rules 模板

每次使用 `sessions_spawn` 時，task prompt **開頭**必須加上此規則 block：

```markdown
## 規則
- 繁體中文回覆
- 完成後用 sessions_send(sessionKey: "agent:main:main") 回傳摘要
- 回覆 ANNOUNCE_SKIP

## 任務：[具體任務描述]

[詳細任務內容...]

## 完成後（強制遵守）

1. 建立標記檔：`echo "pending" > <workspace>/tmp/[task-name]/STATUS_PENDING`
2. 用 sessions_send 回傳摘要，包含關鍵結果

sessionKey: "agent:main:main"
message:

---
🔔 REVIEW_THEN_DELIVER: [task-name]

📄 結果摘要：
[具體結果內容，不只是檔案路徑]

📎 路徑：/tmp/[task-name]/
---

3. 回覆 ANNOUNCE_SKIP
```

## REVIEW_THEN_DELIVER 流程

當收到帶有 `REVIEW_THEN_DELIVER` 的 sessions_send 訊息時，**立即**按順序執行四個步驟：

### Step 1: READ
讀取實際的結果檔案，不要只看 announce 摘要
```bash
read /tmp/[task-name]/result.md
```

### Step 2: VERIFY
對照實際檔案內容驗證 announce 摘要的準確性
- MiniMax 常會虛構細節
- 檢查數據、檔案數量、實際內容是否符合摘要

### Step 3: SEND
用 `message` tool 把**驗證過的結果**發給使用者
- 基於實際檔案內容，不是 announce 摘要
- 包含重要發現和關鍵資訊

### Step 4: CLEAN
清理標記檔，標示任務已處理完成
```bash
rm /tmp/[task-name]/STATUS_PENDING
```

## STATUS_PENDING 機制

### 目的
防止 sub-agent 結果遺失或被忽略

### 機制
1. Sub-agent 完成時建立 `STATUS_PENDING` 標記檔
2. Main agent 處理完後刪除標記檔
3. Fallback script 定期掃描未處理的標記檔

### Fallback Script
```bash
# routine-checks.sh 中的片段
find /tmp/*/STATUS_PENDING -mmin +5 2>/dev/null | while read file; do
    task_dir=$(dirname "$file")
    task_name=$(basename "$task_dir")
    echo "⚠️ Unprocessed sub-agent result: $task_name ($(stat -c %y "$file"))"
done
```

## sessions_send vs announce

### 使用 sessions_send 的情況
- **Sub-agent 完成任務時**（必須用）
- 需要確保 main agent 收到結果
- 重要的完成通知

**格式**:
```javascript
sessions_send({
    sessionKey: "agent:main:main",
    message: "具體的結果內容和摘要"
})
```

### 使用 announce 的情況
- 進度更新
- 狀態變化通知
- 非關鍵信息

**問題**:
- announce 會被排隊，可能被忙碌的 main session 延遲處理
- 不適合關鍵完成通知

## 常見陷阱

### 1. MiniMax 虛構細節
**問題**: MiniMax 會在摘要中編造不存在的細節
**解決**: 在 VERIFY 步驟中對照實際檔案內容

**範例**:
```text
摘要說：「找到 15 個相關文章」
實際：只有 8 個文章，其中 3 個不相關
```

### 2. announce 被排隊
**問題**: announce 訊息被 main session 的其他工作排隊
**解決**: 改用 sessions_send，確保即時送達

### 3. stdout 污染
**問題**: sub-agent 在回覆中混入 debug 資訊
**解決**: 
- 明確要求只回覆 ANNOUNCE_SKIP
- 重要內容寫入檔案，不要在 stdout 中

### 4. 未檢查實際結果
**問題**: 信任 announce 摘要，沒有驗證實際檔案
**解決**: 強制執行 READ → VERIFY 流程

### 5. 忘記加 inject-rules
**問題**: 直接寫任務描述，沒有加規則 block
**結果**: sub-agent 不知道如何回報，或格式不對
**解決**: 每次 sessions_spawn 都先檢查是否有規則 block

## Model 分工建議

### Main Session
**模型**: Claude Opus / Sonnet
**職責**:
- 與使用者互動
- 重要決策和判斷
- 品質把關和審查
- 上下文維護

### Sub-agent
**模型**: MiniMax M2.5 (便宜，免費額度)
**職責**:
- 執行具體任務
- 數據處理和整理
- 研究和收集資訊
- 檔案操作

**原則**:
- Main 用強模型保證品質
- Sub-agent 用便宜模型降低成本
- 重要決策留給 main，執行交給 sub-agent

## 委派決策矩陣

| 任務類型 | 委派給 Sub-agent | 留在 Main |
|----------|------------------|-----------|
| 資料收集 | ✅ | ❌ |
| 檔案處理 | ✅ | ❌ |
| 研究分析 | ✅ | ❌ |
| 使用者互動 | ❌ | ✅ |
| 重要設定 | ❌ | ✅ |
| 敏感操作 | ❌ | ✅ |
| 上下文相關決策 | ❌ | ✅ |

## 實際範例

### 好的委派
```markdown
## 規則
- 繁體中文回覆
- 完成後用 sessions_send(sessionKey: "agent:main:main") 回傳摘要
- 回覆 ANNOUNCE_SKIP

## 任務：分析 GitHub Issue 趨勢

收集最近 30 天的 GitHub issues，分析以下內容：
1. 每日新增 issue 數量
2. 主要標籤分佈
3. 平均解決時間

產出 markdown 報告到 `/tmp/github-analysis/report.md`

## 完成後（強制遵守）

1. 建立標記檔：`echo "pending" > <workspace>/tmp/github-analysis/STATUS_PENDING`
2. 用 sessions_send 回傳摘要

sessionKey: "agent:main:main"
message:

---
🔔 REVIEW_THEN_DELIVER: github-analysis

📄 結果摘要：
- 總共分析 [數量] 個 issues
- 主要發現：[具體發現]
- 報告長度：[行數] 行

📎 路徑：/tmp/github-analysis/
---

3. 回覆 ANNOUNCE_SKIP
```

### 錯誤的委派
```markdown
幫我看看這個 GitHub issue 該怎麼回應，需要考慮我們之前的決策...
```
**問題**: 需要上下文和決策，不適合 sub-agent

## 最佳實踐

1. **任務明確化**: 清楚定義輸入、處理、輸出
2. **結果可驗證**: 產出具體檔案，便於檢查
3. **強制規範**: 每次都用 inject-rules，不要例外
4. **及時處理**: 收到 REVIEW_THEN_DELIVER 立即處理
5. **品質把關**: 在 VERIFY 步驟中仔細檢查結果

記住：**Sub-agent 是工具，Main agent 是大腦。工具執行，大腦決策。**