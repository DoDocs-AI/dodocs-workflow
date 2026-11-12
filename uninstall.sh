#!/usr/bin/env bash
set -euo pipefail

# dodocs-workflow uninstaller
# The AGENTS and COMMANDS arrays must mirror install.sh (checked by tests/validate-install.sh)

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
    "quality-metrics-collector"
    "project-supervisor"
    "scrum-master"
    "tech-lead"
    "ux-designer"
    "ux-reviewer"
    "security-auditor"
    "performance-engineer"
    "product-launch-orchestrator"
    "accessibility-auditor"
    "seo-analyst"
    "devops-engineer"
    "error-handler"
    "dependency-auditor"
    "api-documenter"
    "db-analyst"
    "load-tester"
    "brainstorm-facilitator"
    "feature-manager"
    "mockup-designer"
    "mockup-validator"
    "ux-requirements-critic"
    "business-requirements-critic"
    "requirements-enricher"
    "gtm-community"
    "gtm-copywriter"
    "gtm-crm"
    "gtm-experiment"
    "gtm-icp-discovery"
    "gtm-lead-scoring"
    "gtm-localization"
    "gtm-market-research"
    "gtm-metrics"
    "gtm-outbound"
    "gtm-paid-ads"
    "gtm-proposal"
    "gtm-reporting"
    "gtm-seo-content"
    "gtm-trend-monitor"
    "gtm-strategist"
    "plc-architect-agent"
    "plc-competitive-intel"
    "plc-copy-agent"
    "plc-customer-voice"
    "plc-dev-agent"
    "plc-distribution-agent"
    "plc-feature-inventor"
    "plc-growth-hacker"
    "plc-icp-profiler"
    "plc-market-scout"
    "plc-orchestrator"
    "plc-pricing-architect"
    "plc-product-strategist"
    "plc-qa-agent"
    "plc-retention-engineer"
    "plc-revenue-agent"
    "plc-roadmap-planner"
    "plc-seo-content-agent"
    "plc-validation-agent"
    "plc-mvp-scoper"
    "plc-analytics-agent"
    "plc-product-owner"
    "plc-ux-designer"
    "plc-architect"
    "plc-scrum-master"
    "plc-frontend-dev"
    "plc-backend-dev"
    "plc-code-reviewer"
    "plc-tech-lead"
    "plc-qa-engineer"
    "plc-qa-automation"
    "plc-manual-tester"
    "plc-mockup-designer"
    "plc-mockup-validator"
    "doc-sync-agent"
    "test-estate-maintainer"
    "regression-analyst"
    "web-designer"
    "design-validator"
    "wiki-maintainer"
    "spec-bootstrapper"
)

for agent in "${AGENTS[@]}"; do
    rm -f "$CLAUDE_DIR/agents/$agent.md"
done

# Command files to remove
COMMANDS=(
    "scrum-team"
    "prepare-for-production"
    "product-launch"
    "product-lifecycle"
    "dodocs-workflow"
    "dw-upgrade"
    "container-team"
    "merge-features"
    "fix-the-issue"
    "rebase"
    "brainstorm"
    "batch-features"
    "prepare-feature"
    "prepare-features"
    "change-request"
    "gtm-team"
    "apollo"
    "linkedin"
    "pipedrive"
    "semrush"
    "plc-scrum-team"
    "supervisor"
    "ship"
    "fix-and-ship"
    "web-design"
    "wiki"
    "spec-bootstrap"
    "control"
)

for cmd in "${COMMANDS[@]}"; do
    rm -f "$CLAUDE_DIR/commands/$cmd.md"
done

# Control point: take the guard entry and hooks block out while dw still exists, then
# remove the program. registry.json, runs/ and dw.log are never touched.
DW_HOME_DIR="${DW_INSTALL_HOME:-$HOME/.dodocs-workflow}"
CONTROL_FILES=(
    "dw"
    "guard-rules.json"
    "dwlib/__init__.py"
    "dwlib/agterm.py"
    "dwlib/autoapprove.py"
    "dwlib/events.py"
    "dwlib/guard.py"
    "dwlib/guard_git.py"
    "dwlib/guard_paths.py"
    "dwlib/guard_shell.py"
    "dwlib/paths.py"
    "dwlib/runs.py"
    "dwlib/setup.py"
    "dwlib/status.py"
    "dwlib/store.py"
)

if [ -x "$DW_HOME_DIR/bin/dw" ]; then
    if ! "$DW_HOME_DIR/bin/dw" setup --remove --yes >/dev/null 2>&1; then
        echo -e "${YELLOW}Warning: 'dw setup --remove' failed; check ~/.claude/settings.json and the terminal hooks file by hand.${NC}"
    fi
fi
for item in "${CONTROL_FILES[@]}"; do
    case "$item" in
        dw) rm -f "$DW_HOME_DIR/bin/dw" ;;
        guard-rules.json) rm -f "$DW_HOME_DIR/guard-rules.default.json" ;;
        *) rm -f "$DW_HOME_DIR/lib/$item" ;;
    esac
done
rm -rf "$DW_HOME_DIR/lib/dwlib/__pycache__"
rmdir "$DW_HOME_DIR/lib/dwlib" "$DW_HOME_DIR/lib" "$DW_HOME_DIR/bin" 2>/dev/null || true
if [ -L "$HOME/.local/bin/dw" ] && [ "$(readlink "$HOME/.local/bin/dw")" = "$DW_HOME_DIR/bin/dw" ]; then
    rm -f "$HOME/.local/bin/dw"
fi

rm -f "$CLAUDE_DIR/docker/agent-env.Dockerfile"
rm -f "$CLAUDE_DIR/docker/agent-entrypoint.sh"
rm -f "$CLAUDE_DIR/skills/gtm-api-config.template.md"
rm -f "$CLAUDE_DIR/statusline-dodocs-workflow.sh"
rm -f "$CLAUDE_DIR/scrum-team-config.template.md"
rm -f "$CLAUDE_DIR/openspec-conventions.md"
rm -f "$VERSION_FILE"

echo -e "${GREEN}dodocs-workflow uninstalled.${NC}"
echo ""
echo "Note: the control point's registry.json, runs/ and dw.log under $DW_HOME_DIR were kept."
echo "Note: Project-specific .claude/scrum-team-config.md files were NOT removed."
