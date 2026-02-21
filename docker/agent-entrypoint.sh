#!/usr/bin/env bash
set -euo pipefail

# agent-entrypoint.sh — runs inside the dodocs-agent-env container
# Copies Claude config from the host mount, then runs the scrum-team
# non-interactively via the Claude Code CLI.

FEATURE_NAME="${FEATURE_NAME:-}"
CLAUDE_HOST_DIR="/root/.claude-host"
CLAUDE_DIR="/root/.claude"

# ── Validate ──────────────────────────────────────────────────────────────────

if [ -z "$FEATURE_NAME" ]; then
    echo "[container-team] ERROR: FEATURE_NAME environment variable is not set."
    exit 1
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[container-team] ERROR: ANTHROPIC_API_KEY environment variable is not set."
    exit 1
fi

echo "[container-team] Starting container team for feature: $FEATURE_NAME"
echo "[container-team] Workspace: $(pwd)"

# ── Copy Claude config from host ───────────────────────────────────────────────
# The host mounts ~/.claude as /root/.claude-host (read-only).
# We copy it to /root/.claude so the CLI can read agents, commands, and config.

if [ -d "$CLAUDE_HOST_DIR" ]; then
    echo "[container-team] Copying Claude config from host..."
    mkdir -p "$CLAUDE_DIR"
    # Copy everything except the projects/ directory (conversation history — not needed)
    rsync -a --exclude='projects/' "$CLAUDE_HOST_DIR/" "$CLAUDE_DIR/" 2>/dev/null \
        || cp -r "$CLAUDE_HOST_DIR/." "$CLAUDE_DIR/" 2>/dev/null \
        || true
    echo "[container-team] Claude config copied."
else
    echo "[container-team] WARNING: No host Claude config found at $CLAUDE_HOST_DIR"
    echo "[container-team] Agents will use only bundled definitions."
fi

# ── Ensure workspace has a Claude config ──────────────────────────────────────
# If there's no .claude/scrum-team-config.md in the workspace, the scrum-team
# command will stop with an informative error. Nothing to do here.

# ── Git safe directory ────────────────────────────────────────────────────────
# The workspace is mounted from the host; Git may refuse to operate without this.
git config --global --add safe.directory /workspace 2>/dev/null || true

# ── Configure Git identity if not already set ─────────────────────────────────
if [ -z "$(git config --global user.email 2>/dev/null)" ]; then
    git config --global user.email "container-team@dodocs.ai"
    git config --global user.name "Container Team"
fi

# ── Run the scrum-team non-interactively ──────────────────────────────────────
echo "[container-team] Launching scrum team for: $FEATURE_NAME"
echo "[container-team] ────────────────────────────────────────────────────────"

# claude --dangerously-skip-permissions runs fully autonomously (no prompts).
# The -p flag sends the prompt non-interactively.
claude \
    --dangerously-skip-permissions \
    -p "use the /scrum-team command for feature: $FEATURE_NAME"

EXIT_CODE=$?

echo "[container-team] ────────────────────────────────────────────────────────"
if [ "$EXIT_CODE" -eq 0 ]; then
    echo "[container-team] Scrum team completed successfully for: $FEATURE_NAME"
else
    echo "[container-team] Scrum team exited with code $EXIT_CODE for: $FEATURE_NAME"
fi

exit $EXIT_CODE
