#!/usr/bin/env bash
set -euo pipefail

# dodocs-workflow installer
# Installs the Scrum Team workflow for Claude Code

REPO_URL="https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v1.3.8"
CLAUDE_DIR="$HOME/.claude"
VERSION_FILE="$CLAUDE_DIR/.dodocs-workflow-version"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  dodocs-workflow installer${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_success() { echo -e "${GREEN}[OK]${NC} $1"; }
print_warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
print_info()    { echo -e "${BLUE}[*]${NC} $1"; }

# Determine source: local clone or remote
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/VERSION" ] && [ -d "$SCRIPT_DIR/claude/agents" ]; then
    SOURCE="local"
    SOURCE_DIR="$SCRIPT_DIR/claude"
    print_info "Installing from local directory: $SOURCE_DIR"
else
    SOURCE="remote"
    print_info "Installing from GitHub..."
fi

print_header

# Check for existing installation
UPGRADE=false
if [ -f "$VERSION_FILE" ]; then
    CURRENT_VERSION=$(cat "$VERSION_FILE")
    UPGRADE=true
    print_info "Existing installation found: v$CURRENT_VERSION"
fi

# Create directories
mkdir -p "$CLAUDE_DIR/agents"
mkdir -p "$CLAUDE_DIR/commands"

# Agent files to install
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
    "security-auditor"
    "performance-engineer"
    "accessibility-auditor"
    "seo-analyst"
    "devops-engineer"
    "error-handler"
    "dependency-auditor"
    "api-documenter"
    "db-analyst"
    "load-tester"
)

# Install agent files
print_info "Installing agent definitions..."
for agent in "${AGENTS[@]}"; do
    if [ "$SOURCE" = "local" ]; then
        cp "$SOURCE_DIR/agents/$agent.md" "$CLAUDE_DIR/agents/$agent.md"
    else
        curl -fsSL "$REPO_URL/claude/agents/$agent.md" -o "$CLAUDE_DIR/agents/$agent.md"
    fi
    print_success "  $agent"
done

# Install command files
COMMANDS=(
    "scrum-team"
    "prepare-for-production"
    "dodocs-workflow"
    "dw-upgrade"
)

print_info "Installing commands..."
for cmd in "${COMMANDS[@]}"; do
    if [ "$SOURCE" = "local" ]; then
        cp "$SOURCE_DIR/commands/$cmd.md" "$CLAUDE_DIR/commands/$cmd.md"
    else
        curl -fsSL "$REPO_URL/claude/commands/$cmd.md" -o "$CLAUDE_DIR/commands/$cmd.md"
    fi
    print_success "  $cmd command"
done

# Install status line script
print_info "Installing status line script..."
if [ "$SOURCE" = "local" ]; then
    cp "$SOURCE_DIR/statusline/statusline-dodocs-workflow.sh" "$CLAUDE_DIR/statusline-dodocs-workflow.sh"
else
    curl -fsSL "$REPO_URL/claude/statusline/statusline-dodocs-workflow.sh" -o "$CLAUDE_DIR/statusline-dodocs-workflow.sh"
fi
chmod +x "$CLAUDE_DIR/statusline-dodocs-workflow.sh"
print_success "  statusline-dodocs-workflow.sh"

# Install config template
print_info "Installing config template..."
if [ "$SOURCE" = "local" ]; then
    cp "$SOURCE_DIR/templates/scrum-team-config.template.md" "$CLAUDE_DIR/scrum-team-config.template.md"
else
    curl -fsSL "$REPO_URL/claude/templates/scrum-team-config.template.md" -o "$CLAUDE_DIR/scrum-team-config.template.md"
fi
print_success "  scrum-team-config.template.md"

# Write version
if [ "$SOURCE" = "local" ]; then
    VERSION=$(cat "$SCRIPT_DIR/VERSION" | tr -d '[:space:]')
else
    VERSION=$(curl -fsSL "$REPO_URL/VERSION" | tr -d '[:space:]')
fi
echo "$VERSION" > "$VERSION_FILE"

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
if [ "$UPGRADE" = true ]; then
    echo -e "${GREEN}  Upgraded: v$CURRENT_VERSION -> v$VERSION${NC}"
else
    echo -e "${GREEN}  Installed: v$VERSION${NC}"
fi
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Installed to: $CLAUDE_DIR"
echo ""
echo "Files:"
echo "  ~/.claude/agents/          - 21 agent definitions"
echo "  ~/.claude/commands/        - scrum-team + prepare-for-production + dodocs-workflow commands"
echo "  ~/.claude/statusline-dodocs-workflow.sh"
echo "  ~/.claude/scrum-team-config.template.md"
echo ""

if [ "$UPGRADE" = false ]; then
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Copy the template to your project:"
    echo "     cp ~/.claude/scrum-team-config.template.md <project>/.claude/scrum-team-config.md"
    echo "  2. Edit the config with your project's values"
    echo "  3. Use /scrum-team <feature-name> to build features"
    echo "     Use /prepare-for-production to audit production readiness"
    echo ""
fi
