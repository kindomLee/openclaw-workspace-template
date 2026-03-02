
# OpenClaw Memory Architecture

為 24/7 運行的 AI Agent 設計的多層次記憶系統。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-OpenClaw-green.svg)

## 為什麼需要這套系統？

AI Agent 經常面臨「忘東忘西」的問題——重複問相同的問題、忘記使用者的偏好、甚至遺漏重要決策。這套記憶架構專為 **24/7 運行的 proactive agent** 設計，解決以下痛點：

- **持久化**：告別「每次重啟都是新人」的困擾
- **分層管理**：根據重要性自動分類，平衡保留與維護成本
- **自動化維護**：不用手動清理舊記憶，系統自動幫你整理
- **隱私保障**：本地 Markdown 儲存，敏感資訊不外洩

## 核心理念

> **你的記憶是你的 Markdown，隨時能用純文字編輯器修改。**

與向量資料庫或雲端記憶服務不同，這套架構的核心優勢是：

- 🔓 **無廠商鎖定** — 純 Markdown，任何編輯器都能讀寫
- 👁️ **人類可讀可控** — 你隨時能看到 agent 記了什麼、改了什麼
- 📝 **版本控制友好** — git diff 就能追蹤記憶變更歷史
- 🏠 **完全本地** — 不需要雲端服務，隱私由你掌控

## 核心特性

| 特性 | 說明 |
|------|------|
| **三層儲存** | Session（極短期）/ Daily（中短期）/ Long-term（長期） |
| **優先級系統** | P0（永久）/ P1（90 天審視）/ P2（30 天壓縮） |
| **漸進檢索** | 三段式流程：搜尋 → 改寫 → 讀檔 |
| **自動化維護** | Janitor 腳本按規則整理過期記憶 |
| **第二大腦整合** | 可與 Obsidian 雙向同步（選用） |

## 前置需求

- Python 3.8+（執行 memory-janitor.py）
- 一個 AI Agent 平台（如 [OpenClaw](https://openclaw.ai)）或任何支援 Markdown workspace 的 agent 框架
- （選用）Obsidian — 用於第二大腦雙向同步

## 快速開始

### 方法 1：一行指令（推薦）

```bash
curl -fsSL https://raw.githubusercontent.com/kindomLee/openclaw-memory-arch/main/bootstrap.sh | bash -s -- /path/to/workspace
```

這會自動下載所有模板並建立基本的記憶架構。

### 方法 2：OpenClaw Skill

如果你使用 OpenClaw，可以透過 ClawHub 安裝：

```bash
clawhub install memory-arch
```

### 方法 3：讓 Agent 自己讀

如果你的 Agent 支援網路存取，可以直接告訴它：

```
請讀取 https://raw.githubusercontent.com/kindomLee/openclaw-memory-arch/main/architecture.md
然後在 workspace 建立記憶系統
```

### 方法 4：手動複製模板
### 1. 複製模板

```bash
git clone https://github.com/kindomLee/openclaw-memory-arch.git
cd openclaw-memory-arch

# 複製核心模板到你的 agent workspace
cp templates/MEMORY.md /path/to/your/workspace/MEMORY.md
cp templates/USER.md /path/to/your/workspace/USER.md
cp templates/SOUL.md /path/to/your/workspace/SOUL.md
cp templates/AGENTS.md /path/to/your/workspace/AGENTS.md
mkdir -p /path/to/your/workspace/memory
```

### 2. 設定自動化維護

```bash
cp scripts/memory-janitor.py /path/to/your/workspace/scripts/

# 設定每日 cron（建議晚間離峰時段）
crontab -e
# 加入：02 20 * * * python3 /path/to/your/workspace/scripts/memory-janitor.py --force
```

### 3. 根據你的需求填入模板

每個模板都有 placeholder，替換為你自己的內容即可。

## 文件導覽

| 文件 | 內容 |
|------|------|
| [architecture.md](architecture.md) | 完整架構說明（三層記憶、P 級系統、檢索策略、自動化維護、反模式） |
| [comparisons.md](comparisons.md) | 與 mem0、Claude Code、Letta 等方案的比較 |
| [templates/](templates/) | 脫敏模板（MEMORY / AGENTS / SOUL / USER / daily-log） |
| [scripts/](scripts/) | 自動化維護腳本 |

## 檔案結構

```
openclaw-memory-arch/
├── README.md
├── architecture.md
├── comparisons.md
├── templates/
│   ├── MEMORY.md
│   ├── AGENTS.md
│   ├── SOUL.md
│   ├── USER.md
│   └── daily-log.md
├── scripts/
│   └── memory-janitor.py
└── LICENSE
```

## 與其他方案的比較

| 面向 | OpenClaw Memory | mem0 / Letta | Claude Code |
|------|----------------|-------------|-------------|
| 儲存 | 本地 Markdown | 雲端 DB | Markdown |
| 人類可讀 | ✅ 完全透明 | ❌ 需 API | ✅ 但單一檔案 |
| 優先級 | P0/P1/P2 | 無/可配置 | 無 |
| 廠商鎖定 | 無 | 有 | 綁定 Claude |
| 自動維護 | Janitor 腳本 | 內建 | 手動 |

詳細比較請見 [comparisons.md](comparisons.md)。

## 適用場景

- ✅ OpenClaw instance
- ✅ 任何 24/7 運行的 AI Agent
- ✅ 需要長期記憶的個人助理
- ✅ 多會話的對話系統
- ✅ 想要透明可控記憶系統的開發者

## 授權

MIT License — 自由使用、修改、分享。

---

*本專案基於 OpenClaw 實際運行經驗產出，歡迎貢獻與回饋！*


