# OpenClaw Workspace Template

**語言**: [English](README.md) | 繁體中文

從一個在 production 跑了 4 個多月的 agent 抽出來的 workspace template，同時支援 Claude Code（預設）和 OpenClaw。

剛開機的 Claude Code / OpenClaw agent 是 stateless 的 —— 它醒來、幫你做事、然後忘光。這份 template 把它變成**會持續記憶、會學習、會自我改進**的 agent。

## 你會得到什麼

裝完之後：

- 🧠 **Agent 會記得你** — 每日 journal（`memory/YYYY-MM-DD.md`）+ 長期記憶（`MEMORY.md`，P0/P1/P2 三級優先度 + 自動過期）。每個 session 開始都會讀昨天跟今天的 journal。

- 🔧 **Agent 會從錯誤中學習** — 三級自我改進系統（修復 / 優化 / 創新）追蹤錯誤、糾正、知識缺口。同一問題重複 3 次以上自動 promote 到長期記憶。

- 🤖 **Agent 會委派任務** — 實戰過的 sub-agent 模式，帶結果驗證與 delivery 確認。Main agent 保持專注，sub-agent 處理 heavy lifting。

- 🌙 **Agent 會做夢** — 每週「cold memory association」把不相關的記憶隨機配對找出跨領域洞見。每週三 21:03「rumination」比對近期與長期記憶找矛盾。每月自動歸檔保持記憶清爽。

- 📋 **Agent 會自我維護** — Routine checks 框架（Type A: 固定邏輯 / Type B: 需要 LLM），不讓 agent 浪費 token 在 shell script 就能做完的事情。

- 🛡️ **Agent 會驗證每件事** — 四防線：create → execute → deliver → alert。「我做了」從來不算數，它會確認使用者**真的收到**結果。

- 👤 **Agent 有人格** — `SOUL.md` 定義它是誰、`IDENTITY.md` 給它名字跟 emoji、`USER.md` 幫它認識你。

- 🧬 **Agent 的靈魂會演化** — 行為糾正累積成 proposal，同類糾正 ≥ 3 次就提議更新 `SOUL.md`（需你核可）。

- 📚 **Agent 會建立知識庫** — 主題化筆記（`notes/areas/`、`notes/resources/`）補足 daily journal 的不足。Knowledge layer 採 merge-first 策略，避免碎片化。把 `notes/` 加到 `memorySearch.extraPaths` 就能全文搜。詳見 [Context Tree 指南](guides/context-tree.md)。

- 🔍 **Agent 找東西更快** — Hybrid memory search（`scripts/memory-search-hybrid.py`）用「關鍵字覆蓋率 × 時間新鮮度 × hall 類型加權」對 `memory/` 和 `notes/` 評分。MemPalace 啟發的 hall taxonomy（`hall_facts` / `hall_events` / `hall_discoveries` / `hall_preferences` / `hall_advice`）把 journal entry 標類型強化檢索，搭配 UserPromptSubmit hook 在偵測到硬觸發關鍵字時**強制搜尋** —— 「要不要搜記憶」不再是判斷題。

- 🚩 **Agent 有待辦收件匣** — **cron → flag → SessionStart hook** pipeline 把固定邏輯的背景檢查（broken wikilinks、TODO backlog、stale cache）變成 `.claude/flags/` 下的 flag 檔。Cron 只做偵測，下一次 Claude session 會透過 SessionStart hook 接住處理。Cron 不直接叫 LLM —— 「hard trigger, soft action」。詳見 [flag-system 指南](guides/flag-system.md)。

## 功能一覽

| 能力 | 位置 | 做什麼 |
|------|------|--------|
| **Memory journal** | `memory/YYYY-MM-DD.md` | 每日日誌，用 `[hall_*]` 分類 tag |
| **長期記憶** | `MEMORY.md` | 策劃過的事實、基礎設施、模式（P0/P1/P2） |
| **AAAK compact** | `MEMORY_COMPACT.md` | 每個 session 必載的 ~200 token 壓縮快照 |
| **知識庫** | `notes/areas/`、`notes/resources/` | 主題化筆記，補足 journal 的碎片感 |
| **Hybrid search** | `scripts/memory-search-hybrid.py` | 關鍵字 × 時間 × hall 類型綜合評分 |
| **Hall-type tags** | `[hall_facts]` `[hall_events]` `[hall_discoveries]` `[hall_preferences]` `[hall_advice]` | 分類 journal entry 強化檢索 |
| **Self-improvement** | `.learnings/`、`LEARNINGS.md` | 追蹤 correction / error / gap，≥ 3 次自動 promote |
| **Memory dreaming** | `cron/prompts/memory-dream.md` | 每週跨領域記憶關聯 |
| **Memory rumination** | `cron/prompts/memory-reflect.md` | 每週矛盾偵測 + action tracking + stale check |
| **Memory expiry** | `cron/prompts/memory-expire.md` | 每月自動歸檔 30 天以上的 journal |
| **Memory janitor** | `cron/prompts/memory-janitor.md` | Hall tag 補標 + 重複偵測 + notes 品質檢查 |
| **Cron → flag → hook** | `.claude/flags/`、`.claude/hooks/session-start-flags.sh` | 背景檢查寫 flag，下一個 session 接手 |
| **人格** | `SOUL.md`、`IDENTITY.md`、`USER.md` | 決策偏好、名字/emoji、使用者資料 |
| **Sub-agent 模式** | `guides/sub-agent-patterns.md` | 實戰的委派 + delivery 驗證 |
| **四防線** | `AGENTS.md` | create → execute → deliver → alert 驗證鏈 |
| **硬觸發 memory search** | `.claude/hooks/memory-search-trigger.py` | UserPromptSubmit hook 碰到關鍵字就強搜 |
| **Cron 系統 (Mac)** | `cron/install-mac.sh` | launchd plists + placeholder 替換 |
| **Cron 系統 (Linux)** | `cron/install-linux.sh` | 自動把 plist 轉成 user crontab |
| **網路就緒等待** | `cron/runner.sh` | `claude -p` 執行前等待睡眠喚醒後的網路就緒 |

## Quick Start

> **OpenAI Codex CLI 使用者**：Codex 僅支援 **互動式 second-opinion**，
> `cron/` 路徑是 Claude-only by design。在跑 `bootstrap.sh` 之前請先讀
> [`.codex/README.md`](.codex/README.md)（單一英文來源，避免雙語漂移）。

1. 安裝你要的 runtime：
```bash
# Claude Code（預設）— 見 https://docs.claude.com/claude-code 的安裝方式
# OpenClaw（替代方案）
curl -fsSL https://openclaw.ai/install.sh | bash
# OpenAI Codex（僅互動式 — 不支援 cron）— 見 .codex/README.md
```

2. Clone 這份 template：
```bash
git clone https://github.com/kindomLee/openclaw-workspace-template.git
cd openclaw-workspace-template
```

3. 跑 bootstrap script（預設裝到當前目錄）：
```bash
./bootstrap.sh
# 或：./bootstrap.sh --path ~/my-workspace --yes
```

4. 跑 health check：
```bash
cd <your-workspace>
bash scripts/health-check.sh
```

5. 編輯 template 檔個人化：
   - `IDENTITY.md` — 名字、emoji、人格
   - `USER.md` — 你的資料讓 agent 認識你
   - `SOUL.md` — Agent 人格與決策偏好
   - `TOOLS.md` — 你常用的工具與連線
   - `cron/config.env` — 從 `cron/config.env.example` 複製後填 `TG_BOT_TOKEN` / `TG_CHAT_ID` 才會發 Telegram 通知

6. 設定 cron jobs：

```bash
# Claude Code 模式（預設）— macOS
bash cron/install-mac.sh

# Claude Code 模式（預設）— Linux
bash cron/install-linux.sh

# OpenClaw 模式（替代）
bash scripts/install-cron.sh --install
```

詳細排程與設定見 [cron/README.md](cron/README.md)，裝完驗證見 [Post-Install Checklist](guides/post-install-checklist.md)。

## 架構

```
workspace/
├── AGENTS.md          # Operating manual（每個 session 必讀）
├── SOUL.md            # 人格與決策偏好
├── IDENTITY.md        # 名字與 emoji
├── USER.md            # 關於使用者
├── TOOLS.md           # 工具與連線 cheat sheet
├── MEMORY.md          # 策劃過的長期記憶（P0/P1/P2）
├── HEARTBEAT.md       # Cron 排程架構
├── BOOTSTRAP.md       # Pre-generation task classification
├── memory/            # 每日 journal（YYYY-MM-DD.md）
│   ├── dreams.md      # 每週跨領域洞見
│   ├── reflections.md # 每週記憶反芻（週三 21:03）
│   └── archive-*/     # 自動歸檔的舊記憶
├── notes/             # 知識庫 — 選用、merge-first（見 guides/context-tree.md）
│   ├── 00-Inbox/      # 草稿、待分類
│   ├── 01-Projects/   # 進行中專案（Active/Archive）
│   ├── 02-Areas/      # 持續領域
│   ├── 03-Resources/  # 參考資料
│   └── 04-Archive/    # 冷藏
├── .learnings/        # 自我改進追蹤
│   ├── ERRORS.md
│   ├── LEARNINGS.md
│   └── FEATURE_REQUESTS.md
├── cron/                  # Claude Code 排程任務（claude -p）
│   ├── runner.sh          # 通用 job wrapper
│   ├── install-mac.sh     # macOS launchd 安裝
│   ├── install-linux.sh   # Linux crontab 安裝
│   ├── prompts/           # Job prompt（Markdown）
│   └── launchd/           # 排程定義（plist）
├── .claude/
│   ├── flags/            # Pending-work flags（cron 寫到這裡）
│   ├── hooks/            # SessionStart + UserPromptSubmit hooks
│   └── skills/           # Workspace-local skills（Claude Code 自動載入）
│       ├── curate-memory/
│       ├── telegram-html-reply/
│       └── write-tmp/
├── scripts/
│   ├── lib/              # 共用 helpers（workspace / notify / flag）
│   ├── cron-broken-links-check.sh  # Broken wikilink > N 就寫 flag
│   ├── cron-notes-todo-check.sh    # TODO backlog > N 就寫 flag
│   ├── memory-dream.sh    # 每週 "dreaming" — 冷記憶聯想
│   ├── memory-reflect.sh  # 每週 rumination — 矛盾偵測
│   ├── memory-expire.sh   # 每月歸檔舊 daily 檔
│   ├── memory-compress.py # 長期記憶壓縮（MEMORY.md + archive）
│   ├── memory-search-hybrid.py   # Hybrid 關鍵字 × 時間 × hall 評分
│   ├── hall-tagger.sh             # 回補 journal bullet 的 hall_* tag
│   ├── compact-update.py          # 從 marker 生成 MEMORY_COMPACT.md
│   ├── check-broken-wikilinks.py  # 獨立 broken-link 掃描
│   ├── check-schedule-drift.py    # 驗證 doc 排程表跟 plist 對齊
│   ├── install-cron.sh            # 印 / 安裝 crontab snippet
│   └── health-check.sh            # 裝完驗證
└── guides/            # 參考文件
    ├── self-improvement.md
    ├── sub-agent-patterns.md
    ├── routine-checks.md
    └── multi-instance.md
```

## 記憶系統

### 三層架構

```
Daily Notes (memory/YYYY-MM-DD.md)
    ↓ 抽取 + 策劃
Long-term Memory (MEMORY.md)
    ↓ 模式升級
Knowledge Base (notes/)     # 選用 — 主題化
Reference (reference/*.md)
```

> **選用**：把 `notes/` 加到 `memorySearch.extraPaths` 就能全文搜知識庫（OpenClaw 模式）。Claude Code 模式已內建掃 `memory/` + `notes/`，不需要額外 config。詳見 [Context Tree 指南](guides/context-tree.md)。

### Sleep-Inspired 記憶生命週期

靈感來自 [生物睡眠鞏固記憶的研究](https://x.com/karry_viber/status/2033671561421721821)：

| 機制 | Script | 排程 | 做什麼 |
|------|--------|------|--------|
| **Curate** | `cron/prompts/curate-memory.md` | 每小時 (:02) | Early-return wrapper；有新 journal entry 就 promote 到 MEMORY.md / notes/ / LEARNINGS.md |
| **Dreaming** | `memory-dream.sh` | 每週日 3am | 隨機跨領域記憶聯想找意外洞見 |
| **Rumination** | `memory-reflect.sh` | 每週三 9pm | 比對近期 vs 長期記憶找矛盾 |
| **Forgetting** | `memory-expire.sh` | 每月 1 日 | 歸檔 30 天以上的 daily 檔 |
| **Janitor** | `cron/prompts/memory-janitor.md` | 每日 20:07 | LLM-driven hall-tag 補標 + 重複偵測 + notes 品質檢查 |
| **Compress** | `scripts/memory-compress.py` | 手動或月 1 次 | 長期記憶壓縮（摺舊 timeline、壓縮 P2、歸檔 >30d daily 到 `memory/archive/YYYY-MM/` 並寫 `MANIFEST.jsonl`；支援 `--list-archive` / `--restore YYYY-MM-DD` 審計 + 回滾） |

### 優先級

- **P0** — 個人偏好、基礎設施、核心模式（永久）
- **P1** — 技術方案，帶日期（定期 review）
- **P2** — 實驗性、暫時（30 天後自動過期）

## 核心概念

### Decision Priors (SOUL.md)

Agent 會隨時間累積決策偏好，寫在 `SOUL.md`，overrides 通用 best practice：
- Action bias：「做了再說」勝過「問了再做」
- Risk calibration：內部大膽、外部謹慎
- Communication style：簡潔、結構化、結論先行

### 四防線 (AGENTS.md)

每個動作都要過四道驗證：
1. **Create** — 初始設定真的生效了嗎？
2. **Execute** — Output 正確嗎？
3. **Deliver** — 使用者真的收到了嗎？
4. **Alert** — 任何一步失敗就立刻通知

### Task Classification (BOOTSTRAP.md)

回覆前先分類每則訊息：
- ⚡ Instant（閒聊、狀態查詢）→ 直接回
- 🔧 Execute（清楚指令）→ 做
- 🔍 Research（需要分析）→ 委派
- ⚠️ Confirm（外部動作）→ 先問
- 🧩 Compound（多任務）→ 拆開分別處理

## 指南

- [Self-Improvement System](guides/self-improvement.md) — 三級錯誤學習
- [Sub-agent Patterns](guides/sub-agent-patterns.md) — 委派、驗證、送達
- [Routine Checks](guides/routine-checks.md) — Type A/B 監控框架
- [Multi-workspace Setup](guides/multi-instance.md) — 跑多個 workspace（Claude Code 模式為主，OpenClaw 作 legacy）
- [Post-Install Checklist](guides/post-install-checklist.md) — 裝完驗證每個東西真的能跑
- [Flag System](guides/flag-system.md) — `cron → flag → SessionStart hook` 背景工作 triage
- [Smart Wikilinks (選用)](guides/smart-wikilinks.md) — Embedding-based 相關筆記推薦配方
- [Context Tree](guides/context-tree.md) — 兩層記憶架構（journal + knowledge）
- [升級指南](guides/upgrading.md) — 當 template 發新版時如何更新既有 workspace

## 升級

Template 發新版時：

```bash
cd /path/to/openclaw-workspace-template && git pull
bash bootstrap.sh --path /your/workspace --yes    # 只加新檔案
bash scripts/template-diff.sh /your/workspace      # 顯示哪些檔案有差異
```

`bootstrap.sh` 用 **skip-if-exists** — 不會覆蓋你客製過的檔案。更新過的 template 檔案（`CLAUDE.md`、hooks、scripts）需要自己看 diff 手動合併。完整流程見 [guides/upgrading.md](guides/upgrading.md)。

## 客製化

這份 template 是起點。跑一週之後 agent 會自然演化：
- `SOUL.md` 從糾正累積決策偏好
- `MEMORY.md` 填入你的基礎設施跟偏好
- `.learnings/` 記錄你工作流程特有的 pattern
- 新 skills 可以加到 `.claude/skills/`

## License

MIT
