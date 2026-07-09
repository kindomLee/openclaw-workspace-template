---
title: Plan 檔政策（強制觸發 + lifecycle）
status: active
---

# Plan File Policy

> 規範「何時必須建 plan 檔」與 plan 檔完整生命週期。
> 意圖：把「要不要規劃」從語意判斷題變成 pattern match，避免多步驟任務被誤判成「小改動」而直接動手——這是「亂按按鈕型」Agent 的入口。
>
> 搭配 SessionStart hook `.claude/hooks/plan-resume-check.sh`：掃到含未完成 stage 的 plan 檔就注入接續提示。

## 1. Location & naming

- 路徑：`.claude/plans/<YYYY-MM-DD>-<slug>.md`
- 建議 gitignore（屬 session 工作檔，不進版控）；若要保留可移出 `.claude/plans/`。

## 2. Hard triggers（看到就建，不判斷語意）

下列任一命中 → **第一個編輯動作前**先建 plan 檔：

1. 預期改動 ≥ 3 個檔案
2. 任務含不可逆 / 外部副作用動作：git push、發訊/發信、刪檔、改 production config、cron 變更、套件升級
3. 任務描述為多步驟且步驟 ≥ 3（「先…再…然後」或編號清單）
4. 跨 ≥ 2 類工具協作（如 改 code + 改 cron + 跑驗證）
5. 使用者明說「規劃 / 計畫 / 分階段」
6. 預估跨 session，或會中途交回使用者確認

**不觸發**（維持免 plan 檔）：單檔小改、純查詢/讀取、回答問題、單一指令執行。

## 3. Plan file format

```markdown
# Plan: <一句話任務>
created: <YYYY-MM-DD HH:MM>
status: in-progress

## Stages
- [ ] Stage 1: ...
- [ ] Stage 2: ...

## Notes
（決策、卡關、驗證結果隨做隨記）
```

- Stage 一律用頂格 `- [ ]` / `- [x]` checkbox；SessionStart hook 靠頂格 `- [ ]` 偵測未完成，勿縮排。

## 4. Lifecycle

| 階段 | 規則 |
|---|---|
| 建立 | 觸發清單命中 → 動手前建檔 |
| 更新 | 每個 stage 開始/完成即改 checkbox；完成的 stage 在 Notes 補一行驗證結果 |
| 中斷 | session 中止 → **保留**檔案當 recovery anchor，不刪 |
| 完成刪除 | 所有 stage `- [x]` **且**驗證通過 → 刪檔；未驗證不准刪 |
| Recovery | SessionStart hook `plan-resume-check.sh` 掃到含頂格 `- [ ]` 的 plan 檔 → 注入提示接續 |

## 5. Plan file vs. `.claude/specs/`

若使用 `.claude/specs/` 這類重量級規格流程，兩者分工：

| | plan 檔 | `.claude/specs/` |
|---|---|---|
| 量級 | 輕量 | 重量（需求/設計/實作追溯） |
| 生命 | 單～數 session，用完刪 | 長期，進版控 |
| 進 git | 否 | 是 |
| 何時用 | 觸發清單 1–6 | 觸發清單第 6 條且需正式追溯 / 長期專案 → 升級走 specs |
