---
name: migration-hardcode-sweep
description: >
  把腳本/config 推上遠端、template、或跨主機同步前，系統化掃描硬編碼的絕對路徑、
  個人 ID/token、生產環境值，並改寫為 env var / $SCRIPT_DIR，避免個資外洩與環境
  相依。流程：grep 一組固定 pattern（路徑 + 個資 + secret）→ 命中即 fail → 分類
  改寫（路徑→相對/env、secret→env 讀取）→ 重掃確認歸零 → 回報。
  觸發時機：使用者說「推 template」「同步到遠端/另一台」「push 這個 repo」「這個能不能
  公開/分享」「檢查有沒有寫死路徑/個資」，或自己準備把含路徑/token 的檔案推到遠端/共享前。
user-invocable: true
---

# Migration Hardcode Sweep Skill

> **要解決的問題**：跨主機 / template sync 時，腳本與 config 幾乎每次都殘留某台機器的
> 絕對路徑（如 `/root/<service>/`、`/home/<user>/`、`/Users/<you>/`），有時還寫死個人
> ID / token。最嚴重的型態：某支會自動發訊息的 script 寫死了**個人通訊 ID**（如
> `CHAT_ID="<your-id>"`）→ 任何人 clone 這個 template 跑它，就會發訊息到你的帳號，屬
> privacy leak 級別。本 skill 把「想到哪掃到哪」變成固定掃描流程。

## 何時用

- 推 template / workspace 範本、開源某個 repo、把檔案分享給別人
- 跨主機（A → B）的腳本/config 遷移、cross-host sync
- 準備 commit 含路徑/token 的 config 前（pre-commit 心智）

**不用**：純 notes/文件改動（無執行風險）、確定只在本機跑且不外流的腳本。

## 執行流程

### 1. 跑固定掃描（路徑 + 個資 + secret 三類）

> **先把下面的 pattern 清單換成你環境的真實值**（你常用的絕對路徑前綴、你的個人
> ID/通訊 ID）。清單放 `cron/config.env` 之類的本機檔，不要寫死在 skill 裡。

```bash
# 硬編碼絕對路徑 + 個人 ID（PERSONAL_PATTERNS 換成你環境的真實值）
PERSONAL_PATTERNS='/root/<service>|/home/<user>|/Users/<you>|<your-personal-id>'
grep -rnE "$PERSONAL_PATTERNS" \
  --include='*.sh' --include='*.py' --include='*.json' --include='*.md' \
  . 2>/dev/null | grep -v -E '\.git/|/archive|/logs/'

# secret / token pattern（明文 key）
grep -rnE '(api[_-]?key|token|secret|password|bearer)\s*[:=]\s*["'\'']?[A-Za-z0-9_\-]{16,}' \
  --include='*.sh' --include='*.py' --include='*.json' . 2>/dev/null | grep -v -E '\.git/|config\.env\.example'
```
命中清單 = 待處理。**任一命中即視為 fail，不可推出去。**

### 2. 分類改寫

| 命中類型 | 改寫方式 |
|----------|----------|
| 絕對路徑（`/root/...`、`/Users/...`） | `$SCRIPT_DIR`（`SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"`）/ `$WORKSPACE_DIR` / `$PROJECT_DIR` |
| 服務 workspace | env var（預設值才放真實路徑） |
| secret / token / 個人 ID | 改由 env 讀取（`$BOT_TOKEN` / `$CHAT_ID` / `$API_KEY`），檔案只留 key 名；真值進 `config.env`（gitignore）+ 附 `config.env.example` 留空 |
| 範例/註解裡的生產值 | 直接刪或換成佔位（即使「只是範例」也不可留真 ID/token/path） |

### 3. 重掃確認歸零
改完**重跑步驟 1**，必須 0 命中才算過。

### 4. 回報
- 命中幾筆、分幾類、各改成什麼
- 哪些進了 `config.env`（env 化）、`.example` 是否同步
- 重掃結果（應 0）
- 若有刻意保留的（如本機專用 wrapper 不外流），列出原因

## 反模式
- ❌ 只掃 `*.sh` 漏掉 `*.py` / `*.json` config
- ❌ 把 secret 從程式碼搬進 `config.env` 卻忘了加 `.gitignore` / 忘了 `.example`
- ❌ 改完不重掃就推出去（漏網的還在）
- ❌ 連 `config.env.example` 的佔位值都當命中刪掉（example 本就該留空殼）
- ❌ 一次掃太多 repo 混在一起回報

## 來源
- 由 `scripts/skill_genesis_mine.py` 從一條「遷移殘留硬編碼路徑/個資」的重複手動操作紀錄
  （LEARNINGS `manual_repeat`）自動萃取為候選，人工覆審後 scaffold。
- 與 `fact-drift-sweep` 互補：fact-drift 修「副本漂移」，本 skill 修「外流前的清毒」。
