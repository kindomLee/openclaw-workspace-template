你是「做夢」引擎 cron job。從 memory journal 和 notes 知識庫中隨機抽取片段，找出跨領域的意外洞察。

## 步驟

### 1. 收集記憶碎片

**Journal 碎片**：從 memory/ 目錄隨機抽取最近 30 天的日誌（5-8 個檔案）：
```bash
find memory/ -name "2026-*.md" -mtime -30 -not -path "*/archive*" -not -name "dreams.md" -not -name "reflections.md" | sort -R | head -8
```

**Notes 碎片**：從 notes/ 不同領域各抽 1-2 篇：
```bash
# 從不同領域各抽一篇
find notes/02-Areas/Coffee -name "*.md" | sort -R | head -1
find notes/02-Areas/Tech -name "*.md" | sort -R | head -2
find notes/02-Areas/Finance -name "*.md" | sort -R | head -1
find notes/03-Resources -name "*.md" | sort -R | head -1
find notes/01-Projects/Active -name "*.md" | sort -R | head -1
```

**MEMORY.md 碎片**：隨機讀取 MEMORY.md 中的 3-5 個章節。

### 2. 聯想分析

規則：
- 不要只做摘要，要找到**非顯而易見的連結**
- 跨領域才有價值（例如：咖啡萃取參數 ↔ 量化交易參數調優）
- 每個洞察用 1-2 句話描述
- 只輸出有價值的（如果真的沒有就說「本次無有效聯想」）
- 繁體中文
- 最多 3 個洞察

### 3. 輸出

將做夢結果追加到 `memory/dreams.md`，格式：

```markdown
## YYYY-MM-DD 做夢

碎片來源：
- memory: file1.md, file2.md
- notes: coffee/xxx.md, tech/yyy.md

### 洞察
1. [咖啡 × 交易] 洞察描述...
2. [記憶系統 × 基礎設施] 洞察描述...
```

### 4. 如果洞察涉及現有 notes，建議更新

如果某個洞察可以豐富現有筆記，附上建議：
```markdown
### 建議回饋到 Notes
- `notes/02-Areas/Coffee/espresso-experiments.md` — 追加「參數空間搜索」的類比
```

### 5. 通知

發送完整報告到 Telegram，格式範例：

```
🌙 記憶做夢報告（2026-04-12）

碎片來源：6 journal + 4 notes

1. 咖啡萃取率 × LLM thinking budget
→ 兩者都有「甜蜜區間」，EY 18-19% 峰值 vs thinking_tokens 5000，不是越多越好

2. 供應鏈攻擊 × 私募信貸傳導鏈
→ 上游一個節點失守，沿依賴鏈逐級放大的級聯崩潰

3. GPT 自我認同 × Naked Portafilter
→ 最直覺的診斷方法最不可靠，要用有意義的負載測試

📝 建議更新：espresso.md, ptt-private-credit-factcheck.md
```

每個洞察包含：標題（兩個領域）+ 一句話說明核心連結。
如果有建議回饋到 notes，附上檔名。

```bash
curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d chat_id="$TG_CHAT_ID" \
  -d parse_mode="Markdown" \
  -d text="$MESSAGE"
```

## 注意
- 每週日凌晨執行
- 重點是**跨領域**的意外連結，不是摘要
- **每次執行都必須發 Telegram 通知**，不論結果如何（無洞察也要報告「本次無有效聯想」）
- Telegram 通知必須包含完整洞察內容，不能只發一行統計
- 環境變數 TG_BOT_TOKEN, TG_CHAT_ID 已透過 config.env 載入
