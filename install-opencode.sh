#!/usr/bin/env bash
set -euo pipefail

# dodocs-workflow installer
# Installs the Scrum Team workflow for OpenCode

REPO_URL="https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v1.2.0"
OPENCODE_DIR="$HOME/.opencode"
VERSION_FILE="$OPENCODE_DIR/.dodocs-workflow-version"

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
if [ -f "$SCRIPT_DIR/VERSION" ] && [ -d "$SCRIPT_DIR/opencode/agents" ]; then
    SOURCE="local"
    SOURCE_DIR="$SCRIPT_DIR/opencode"
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
mkdir -p "$OPENCODE_DIR/agents"
mkdir -p "$OPENCODE_DIR/commands"

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
        cp "$SOURCE_DIR/agents/$agent.md" "$OPENCODE_DIR/agents/$agent.md"
    else
        curl -fsSL "$REPO_URL/opencode/agents/$agent.md" -o "$OPENCODE_DIR/agents/$agent.md"
    fi
    print_success "  $agent"
done

# Install command files
COMMANDS=(
    "scrum-team"
    "prepare-for-production"
)

print_info "Installing commands..."
for cmd in "${COMMANDS[@]}"; do
    if [ "$SOURCE" = "local" ]; then
        cp "$SOURCE_DIR/commands/$cmd.md" "$OPENCODE_DIR/commands/$cmd.md"
    else
        curl -fsSL "$REPO_URL/opencode/commands/$cmd.md" -o "$OPENCODE_DIR/commands/$cmd.md"
    fi
    print_success "  $cmd command"
done

# Install config template
print_info "Installing config template..."
if [ "$SOURCE" = "local" ]; then
    cp "$SOURCE_DIR/templates/scrum-team-config.template.md" "$OPENCODE_DIR/scrum-team-config.template.md"
else
    curl -fsSL "$REPO_URL/opencode/templates/scrum-team-config.template.md" -o "$OPENCODE_DIR/scrum-team-config.template.md"
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
echo "Installed to: $OPENCODE_DIR"
echo ""
echo "Files:"
echo "  ~/.opencode/agents/          - 21 agent definitions"
echo "  ~/.opencode/commands/        - scrum-team + prepare-for-production commands"
echo "  ~/.opencode/scrum-team-config.template.md"
echo ""

if [ "$UPGRADE" = false ]; then
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Copy the template to your project:"
    echo "     cp ~/.opencode/scrum-team-config.template.md <project>/.opencode/scrum-team-config.md"
    echo "  2. Edit the config with your project's values"
    echo "  3. Use /scrum-team <feature-name> to build features"
    echo "     Use /prepare-for-production to audit production readiness"
    echo ""
fi
