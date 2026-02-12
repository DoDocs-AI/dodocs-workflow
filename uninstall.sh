#!/usr/bin/env bash
set -euo pipefail

# dodocs-workflow uninstaller

CLAUDE_DIR="$HOME/.claude"
VERSION_FILE="$CLAUDE_DIR/.dodocs-workflow-version"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ ! -f "$VERSION_FILE" ]; then
    echo -e "${YELLOW}dodocs-workflow is not installed.${NC}"
    exit 0
fi

CURRENT_VERSION=$(cat "$VERSION_FILE")
echo -e "${YELLOW}Uninstalling dodocs-workflow v$CURRENT_VERSION...${NC}"

# Agent files to remove
AGENTS=(
    "architect"
    "backend-dev"
    "code-reviewer"
    "frontend-dev"
    "manual-tester"
    "product-owner"
    "qa-automation"
    "qa-engineer"
    "scrum-master"
    "tech-lead"
    "ux-designer"
)

for agent in "${AGENTS[@]}"; do
    rm -f "$CLAUDE_DIR/agents/$agent.md"
done

rm -f "$CLAUDE_DIR/commands/scrum-team.md"
rm -f "$CLAUDE_DIR/scrum-team-config.template.md"
rm -f "$VERSION_FILE"

echo -e "${GREEN}dodocs-workflow uninstalled.${NC}"
echo ""
echo "Note: Project-specific .claude/scrum-team-config.md files were NOT removed."
