#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default workspace path
DEFAULT_WORKSPACE="./clawd"

echo -e "${BLUE}OpenClaw Workspace Template Bootstrap${NC}"
echo -e "${BLUE}=====================================${NC}"
echo

# Ask for workspace path
echo -e "${YELLOW}Enter workspace directory path (default: ${DEFAULT_WORKSPACE}):${NC}"
read -r WORKSPACE_PATH

# Use default if empty
if [ -z "$WORKSPACE_PATH" ]; then
    WORKSPACE_PATH="$DEFAULT_WORKSPACE"
fi

# Convert to absolute path
# macOS compat: realpath may not exist
if command -v realpath &>/dev/null; then
    WORKSPACE_PATH=$(realpath "$WORKSPACE_PATH")
else
    WORKSPACE_PATH=$(cd "$(dirname "$WORKSPACE_PATH")" && pwd)/$(basename "$WORKSPACE_PATH")
fi

echo -e "${BLUE}Setting up workspace at: ${WORKSPACE_PATH}${NC}"
echo

# Create workspace directory if it doesn't exist
if [ ! -d "$WORKSPACE_PATH" ]; then
    echo -e "${YELLOW}Creating workspace directory...${NC}"
    mkdir -p "$WORKSPACE_PATH"
fi

# Check if workspace is empty
if [ "$(ls -A "$WORKSPACE_PATH" 2>/dev/null)" ]; then
    echo -e "${RED}Warning: Workspace directory is not empty!${NC}"
    echo -e "${YELLOW}Continue? (y/N):${NC}"
    read -r CONTINUE
    if [[ ! "$CONTINUE" =~ ^[Yy]$ ]]; then
        echo -e "${RED}Aborted.${NC}"
        exit 1
    fi
fi

# Copy template files
echo -e "${YELLOW}Copying template files...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$SCRIPT_DIR/templates" ]; then
    echo -e "${RED}Error: templates/ directory not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# Smart copy: skip files that already exist, only add missing ones
SKIPPED=0
COPIED=0
cd "$SCRIPT_DIR/templates"
find . -type f | while read -r file; do
    target="$WORKSPACE_PATH/$file"
    if [ -f "$target" ]; then
        echo -e "  ${YELLOW}skip${NC} $file (already exists)"
        SKIPPED=$((SKIPPED + 1))
    else
        mkdir -p "$(dirname "$target")"
        cp "$file" "$target"
        echo -e "  ${GREEN}copy${NC} $file"
        COPIED=$((COPIED + 1))
    fi
done
cd "$SCRIPT_DIR"
echo -e "${GREEN}✓ Template files processed (existing files preserved)${NC}"

# Copy skills (same skip-if-exists logic)
if [ -d "$SCRIPT_DIR/skills" ]; then
    echo -e "${YELLOW}Copying starter skills...${NC}"
    cd "$SCRIPT_DIR/skills"
    find . -type f | while read -r file; do
        target="$WORKSPACE_PATH/skills/$file"
        if [ -f "$target" ]; then
            echo -e "  ${YELLOW}skip${NC} skills/$file (already exists)"
        else
            mkdir -p "$(dirname "$target")"
            cp "$file" "$target"
            echo -e "  ${GREEN}copy${NC} skills/$file"
        fi
    done
    cd "$SCRIPT_DIR"
    echo -e "${GREEN}✓ Starter skills installed${NC}"
fi

# Copy scripts
if [ -d "$SCRIPT_DIR/scripts" ]; then
    echo -e "${YELLOW}Copying scripts...${NC}"
    cd "$SCRIPT_DIR/scripts"
    find . -type f | while read -r file; do
        target="$WORKSPACE_PATH/scripts/$file"
        if [ -f "$target" ]; then
            echo -e "  ${YELLOW}skip${NC} scripts/$file (already exists)"
        else
            mkdir -p "$(dirname "$target")"
            cp "$file" "$target"
            echo -e "  ${GREEN}copy${NC} scripts/$file"
        fi
    done
    cd "$SCRIPT_DIR"
    echo -e "${GREEN}✓ Scripts installed${NC}"
fi

# Create additional directories
echo -e "${YELLOW}Creating additional directories...${NC}"
mkdir -p "$WORKSPACE_PATH/memory"
mkdir -p "$WORKSPACE_PATH/.learnings"
mkdir -p "$WORKSPACE_PATH/scripts"
mkdir -p "$WORKSPACE_PATH/skills"
mkdir -p "$WORKSPACE_PATH/reference"
mkdir -p "$WORKSPACE_PATH/tmp"
echo -e "${GREEN}✓ Directory structure created${NC}"

# Set permissions
echo -e "${YELLOW}Setting permissions...${NC}"
chmod 755 "$WORKSPACE_PATH"
chmod 644 "$WORKSPACE_PATH"/*.md
if [ -d "$WORKSPACE_PATH/scripts" ]; then
    find "$WORKSPACE_PATH/scripts" -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
fi
echo -e "${GREEN}✓ Permissions set${NC}"

# Success message
echo
echo -e "${GREEN}✨ Workspace setup complete!${NC}"
echo
echo -e "${BLUE}Next steps:${NC}"
echo -e "1. ${YELLOW}Fill in USER.md with your information${NC}"
echo -e "2. ${YELLOW}Customize IDENTITY.md for your agent's personality${NC}"
echo -e "3. ${YELLOW}Configure OpenClaw to use workspace: ${WORKSPACE_PATH}${NC}"
echo -e "4. ${YELLOW}Review and customize AGENTS.md for your workflows${NC}"
echo -e "5. ${YELLOW}Add your specific tools and services to TOOLS.md${NC}"
echo
echo -e "${BLUE}Workspace location: ${WORKSPACE_PATH}${NC}"
echo -e "${BLUE}Documentation: ${WORKSPACE_PATH}/guides/${NC}"
echo
echo -e "${GREEN}Happy agent building! 🤖${NC}"