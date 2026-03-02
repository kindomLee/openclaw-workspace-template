#!/usr/bin/env bash
#
# Bootstrap Script - OpenClaw Memory Architecture
# 用法: curl -fsSL https://raw.githubusercontent.com/kindomLee/openclaw-memory-arch/main/bootstrap.sh | bash -s -- [workspace_dir]
#

set -e

# 顏色輸出（CI 環境自動關閉）
if [ -n "$CI" ] || [ "$NO_COLOR" = "1" ]; then
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    BOLD=''
    NC=''
else
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    NC='\033[0m'
fi

# 預設值
GITHUB_REPO="https://raw.githubusercontent.com/kindomLee/openclaw-memory-arch/main"
WORKSPACE="${1:-${CLAWD_WORKSPACE:-./}}"
FORCE_OVERWRITE=false

# 解析參數
while [ $# -gt 0 ]; do
    case "$1" in
        --force)
            FORCE_OVERWRITE=true
            shift
            ;;
        --help|-h)
            echo "用法: $0 [workspace_dir] [--force]"
            echo ""
            echo "參數:"
            echo "  workspace_dir  工作目錄（預設: ./ 或 \$CLAWD_WORKSPACE）"
            echo "  --force        覆蓋已存在的檔案"
            echo ""
            echo "範例:"
            echo "  $0 /path/to/workspace"
            echo "  $0 /path/to/workspace --force"
            exit 0
            ;;
        *)
            WORKSPACE="$1"
            shift
            ;;
    esac
done

# 確保 workspace 是絕對路徑
if [[ "$WORKSPACE" != /* ]]; then
    WORKSPACE="$(pwd)/$WORKSPACE"
fi

# 檢查必要工具
check_curl() {
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}錯誤: curl 未安裝${NC}" >&2
        exit 1
    fi
}

# 檢查網路連線
check_network() {
    echo -e "${BLUE}檢查網路連線...${NC}"
    if ! curl -fsSL --connect-timeout 10 -o /dev/null "$GITHUB_REPO/README.md"; then
        echo -e "${RED}錯誤: 無法連線到 GitHub${NC}" >&2
        exit 1
    fi
    echo -e "${GREEN}✓ 網路連線正常${NC}"
}

# 下載檔案
download_file() {
    local src="$1"
    local dest="$2"
    local desc="$3"
    
    if [ -f "$dest" ] && [ "$FORCE_OVERWRITE" = false ]; then
        echo -e "${YELLOW}⏭  跳過 (已存在): $desc${NC}"
        return 1
    fi
    
    echo -e "${BLUE}↓ 下載: $desc${NC}"
    if curl -fsSL -o "$dest" "$src" 2>/dev/null; then
        echo -e "${GREEN}✓ 建立: $desc${NC}"
        return 0
    else
        echo -e "${RED}✗ 失敗: $desc${NC}"
        return 1
    fi
}

# 建立目錄
ensure_dir() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo -e "${GREEN}✓ 建立目錄: $dir${NC}"
    fi
}

# 主流程
main() {
    echo -e "${BOLD}========================================${NC}"
    echo -e "${BOLD}  OpenClaw Memory Architecture Bootstrap${NC}"
    echo -e "${BOLD}========================================${NC}"
    echo ""
    echo -e "Workspace: ${GREEN}$WORKSPACE${NC}"
    echo -e "GitHub:     ${GREEN}$GITHUB_REPO${NC}"
    echo ""
    
    # 前置檢查
    check_curl
    check_network
    
    # 確保 workspace 目錄存在
    ensure_dir "$WORKSPACE"
    
    echo ""
    echo -e "${BOLD}開始建立記憶架構...${NC}"
    echo ""
    
    # 追蹤結果
    local created=()
    local skipped=()
    
    # 1. 建立 memory 目錄
    ensure_dir "$WORKSPACE/memory"
    created+=("memory/")
    
    # 2. 建立 scripts 目錄
    ensure_dir "$WORKSPACE/scripts"
    created+=("scripts/")
    
    # 3. 下載主要模板
    if download_file "$GITHUB_REPO/templates/MEMORY.md" "$WORKSPACE/MEMORY.md" "MEMORY.md"; then
        created+=("MEMORY.md")
    else
        skipped+=("MEMORY.md")
    fi
    
    if download_file "$GITHUB_REPO/templates/AGENTS.md" "$WORKSPACE/AGENTS.md" "AGENTS.md"; then
        created+=("AGENTS.md")
    else
        skipped+=("AGENTS.md")
    fi
    
    if download_file "$GITHUB_REPO/templates/SOUL.md" "$WORKSPACE/SOUL.md" "SOUL.md"; then
        created+=("SOUL.md")
    else
        skipped+=("SOUL.md")
    fi
    
    if download_file "$GITHUB_REPO/templates/USER.md" "$WORKSPACE/USER.md" "USER.md"; then
        created+=("USER.md")
    else
        skipped+=("USER.md")
    fi
    
    # 4. 建立當天 daily-log
    TODAY=$(date +%Y-%m-%d)
    DAILY_LOG="$WORKSPACE/memory/${TODAY}.md"
    if [ ! -f "$DAILY_LOG" ]; then
        if download_file "$GITHUB_REPO/templates/daily-log.md" "$DAILY_LOG" "memory/${TODAY}.md"; then
            created+=("memory/${TODAY}.md")
        else
            skipped+=("memory/${TODAY}.md")
        fi
    else
        echo -e "${YELLOW}⏭  跳過 (已存在): memory/${TODAY}.md${NC}"
        skipped+=("memory/${TODAY}.md")
    fi
    
    # 5. 下載 memory-janitor.py
    JANITOR_SCRIPT="$WORKSPACE/scripts/memory-janitor.py"
    if download_file "$GITHUB_REPO/scripts/memory-janitor.py" "$JANITOR_SCRIPT" "scripts/memory-janitor.py"; then
        chmod +x "$JANITOR_SCRIPT"
        created+=("scripts/memory-janitor.py")
    else
        skipped+=("scripts/memory-janitor.py")
    fi
    
    # 印出摘要
    echo ""
    echo -e "${BOLD}========================================${NC}"
    echo -e "${BOLD}  摘要${NC}"
    echo -e "${BOLD}========================================${NC}"
    echo ""
    
    if [ ${#created[@]} -gt 0 ]; then
        echo -e "${GREEN}已建立:${NC}"
        for item in "${created[@]}"; do
            echo -e "  ✓ $item"
        done
        echo ""
    fi
    
    if [ ${#skipped[@]} -gt 0 ]; then
        echo -e "${YELLOW}已跳過 (檔案已存在):${NC}"
        for item in "${skipped[@]}"; do
            echo -e "  ⏭ $item"
        done
        echo ""
    fi
    
    # 提示設定 cron
    echo -e "${BOLD}下一步：設定自動化維護${NC}"
    echo ""
    echo "建議設定每日 cron 執行 memory-janitor.py："
    echo ""
    echo -e "${BLUE}crontab -e${NC}"
    echo "# 加入以下行（晚間 20:02 執行）："
    echo "02 20 * * * cd $WORKSPACE && python3 scripts/memory-janitor.py --force"
    echo ""
    echo "或使用 OpenClaw cron："
    echo -e "${BLUE}openclaw cron add --name 'memory-janitor' --at '20h' --system-event 'Memory janitor' --session main${NC}"
    echo ""
    echo -e "${GREEN}完成！記憶架構已建立。${NC}"
    echo ""
    echo "閱讀 MEMORY.md 了解如何填充你的個人資訊。"
}

main "$@"
