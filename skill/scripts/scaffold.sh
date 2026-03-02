#!/usr/bin/env bash
#
# Scaffold Script - OpenClaw Memory Architecture
# 從 ClawHub skill 安裝時使用
# 用法: bash scaffold.sh [workspace_dir]
#

set -e

# 取得 skill 目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# 預設值
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

# 複製模板
copy_template() {
    local src="$1"
    local dest="$2"
    local desc="$3"
    
    if [ -f "$dest" ] && [ "$FORCE_OVERWRITE" = false ]; then
        echo -e "${YELLOW}⏭  跳過 (已存在): $desc${NC}"
        return 1
    fi
    
    if [ -f "$src" ]; then
        cp "$src" "$dest"
        echo -e "${GREEN}✓ 建立: $desc${NC}"
        return 0
    else
        echo -e "${RED}✗ 模板不存在: $src${NC}"
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
    echo -e "${BOLD}  OpenClaw Memory Architecture Scaffold${NC}"
    echo -e "${BOLD}========================================${NC}"
    echo ""
    echo -e "Skill 目錄: ${GREEN}$SKILL_DIR${NC}"
    echo -e "Workspace:  ${GREEN}$WORKSPACE${NC}"
    echo ""
    
    # 確保 workspace 目錄存在
    ensure_dir "$WORKSPACE"
    
    # 追蹤結果
    local created=()
    local skipped=()
    
    # 1. 建立必要目錄
    ensure_dir "$WORKSPACE/memory"
    created+=("memory/")
    
    ensure_dir "$WORKSPACE/scripts"
    created+=("scripts/")
    
    echo ""
    echo -e "${BOLD}開始建立記憶架構...${NC}"
    echo ""
    
    # 2. 複製模板（從 GitHub 下載最新版本）
    GITHUB_REPO="https://raw.githubusercontent.com/kindomLee/openclaw-memory-arch/main"
    
    # 嘗試從 GitHub 下載模板
    for template in MEMORY AGENTS SOUL USER; do
        src="$GITHUB_REPO/templates/${template}.md"
        dest="$WORKSPACE/${template}.md"
        
        if [ -f "$dest" ] && [ "$FORCE_OVERWRITE" = false ]; then
            echo -e "${YELLOW}⏭  跳過 (已存在): ${template}.md${NC}"
            skipped+=("${template}.md")
        else
            if curl -fsSL -o "$dest" "$src" 2>/dev/null; then
                echo -e "${GREEN}✓ 建立: ${template}.md${NC}"
                created+=("${template}.md")
            else
                echo -e "${RED}✗ 失敗: ${template}.md${NC}"
            fi
        fi
    done
    
    # 3. 建立當天 daily-log
    TODAY=$(date +%Y-%m-%d)
    DAILY_LOG="$WORKSPACE/memory/${TODAY}.md"
    if [ -f "$DAILY_LOG" ] && [ "$FORCE_OVERWRITE" = false ]; then
        echo -e "${YELLOW}⏭  跳過 (已存在): memory/${TODAY}.md${NC}"
        skipped+=("memory/${TODAY}.md")
    else
        if curl -fsSL -o "$DAILY_LOG" "$GITHUB_REPO/templates/daily-log.md" 2>/dev/null; then
            echo -e "${GREEN}✓ 建立: memory/${TODAY}.md${NC}"
            created+=("memory/${TODAY}.md")
        else
            echo -e "${RED}✗ 失敗: memory/${TODAY}.md${NC}"
        fi
    fi
    
    # 4. 複製或下載 memory-janitor.py
    JANITOR_SRC="$SCRIPT_DIR/memory-janitor.py"
    JANITOR_DEST="$WORKSPACE/scripts/memory-janitor.py"
    
    if [ -f "$JANITOR_SRC" ]; then
        cp "$JANITOR_SRC" "$JANITOR_DEST"
        chmod +x "$JANITOR_DEST"
        echo -e "${GREEN}✓ 建立: scripts/memory-janitor.py${NC}"
        created+=("scripts/memory-janitor.py")
    else
        # 嘗試從 GitHub 下載
        if curl -fsSL -o "$JANITOR_DEST" "$GITHUB_REPO/scripts/memory-janitor.py" 2>/dev/null; then
            chmod +x "$JANITOR_DEST"
            echo -e "${GREEN}✓ 建立: scripts/memory-janitor.py${NC}"
            created+=("scripts/memory-janitor.py")
        else
            echo -e "${RED}✗ 失敗: scripts/memory-janitor.py${NC}"
        fi
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
    
    # 提示下一步
    echo -e "${BOLD}下一步${NC}"
    echo ""
    echo "1. 填寫 MEMORY.md、USER.md、SOUL.md 中的 placeholder"
    echo "2. 設定每日 cron 執行 memory-janitor.py："
    echo ""
    echo -e "   ${BLUE}openclaw cron add --name 'memory-janitor' --at '20h' --system-event 'Memory janitor' --session main${NC}"
    echo ""
    echo -e "${GREEN}完成！記憶架構已建立。${NC}"
}

main "$@"
