#!/usr/bin/env bash
set -euo pipefail

# Directories — entrypoint runs as root, then drops to botuser
CLAUDE_HOST_DIR="/root/.claude-host"
KUBE_HOST="/root/.kube/config"
BOT_HOME="/home/botuser"
CLAUDE_DIR="$BOT_HOME/.claude"

echo "[support-bot] Starting DoDocs Support Bot..."

# ── Copy Claude config from host ────────────────────────────────────────────
if [ -d "$CLAUDE_HOST_DIR" ]; then
    echo "[support-bot] Copying Claude config from host..."
    mkdir -p "$CLAUDE_DIR"
    rsync -a --exclude='projects/' "$CLAUDE_HOST_DIR/" "$CLAUDE_DIR/" 2>/dev/null \
        || cp -r "$CLAUDE_HOST_DIR/." "$CLAUDE_DIR/" 2>/dev/null \
        || true
    echo "[support-bot] Claude config copied."
else
    echo "[support-bot] WARNING: No host Claude config found at $CLAUDE_HOST_DIR"
fi

# ── Copy kubectl config for botuser ──────────────────────────────────────────
if [ -f "$KUBE_HOST" ]; then
    mkdir -p "$BOT_HOME/.kube"
    cp "$KUBE_HOST" "$BOT_HOME/.kube/config"
    echo "[support-bot] kubectl config copied."
fi

# ── Copy bot-specific Claude assets on top ──────────────────────────────────
if [ -d "/app/claude/commands" ]; then
    mkdir -p "$CLAUDE_DIR/commands"
    cp -f /app/claude/commands/*.md "$CLAUDE_DIR/commands/" 2>/dev/null || true
    echo "[support-bot] Bot commands installed."
fi

if [ -d "/app/claude/agents" ]; then
    mkdir -p "$CLAUDE_DIR/agents"
    cp -f /app/claude/agents/*.md "$CLAUDE_DIR/agents/" 2>/dev/null || true
    echo "[support-bot] Bot agents installed."
fi

if [ -f "/app/claude/CLAUDE.md" ]; then
    cp -f /app/claude/CLAUDE.md "$CLAUDE_DIR/CLAUDE.md"
    echo "[support-bot] Bot CLAUDE.md installed."
fi

# ── Git safe directory ──────────────────────────────────────────────────────
su -s /bin/bash botuser -c 'git config --global --add safe.directory "*" 2>/dev/null || true'
su -s /bin/bash botuser -c 'git config --global user.email "support-bot@dodocs.ai" 2>/dev/null || true'
su -s /bin/bash botuser -c 'git config --global user.name "DoDocs Support Bot" 2>/dev/null || true'

# ── Init state files if missing ─────────────────────────────────────────────
mkdir -p /app/state/audit
for f in telegram_state.json slack_state.json pending_conversations.json; do
    [ -f "/app/state/$f" ] || echo '{}' > "/app/state/$f"
done

# ── Fix ownership ────────────────────────────────────────────────────────────
chown -R botuser:botuser "$BOT_HOME" /app/state

# ── Validate Claude auth ───────────────────────────────────────────────────
echo "[support-bot] Checking Claude auth..."
if su -s /bin/bash botuser -c 'claude auth status' 2>&1 | grep -qi "logged in\|authenticated\|active"; then
    echo "[support-bot] Claude auth OK."
else
    echo "[support-bot] WARNING: Claude auth may not be configured. Bot will attempt to run anyway."
fi

# ── Validate kubectl ───────────────────────────────────────────────────────
if su -s /bin/bash botuser -c 'kubectl version --client --short' 2>/dev/null; then
    echo "[support-bot] kubectl available."
else
    echo "[support-bot] WARNING: kubectl not working."
fi

# ── Validate AWS auth ───────────────────────────────────────────────────────
if su -s /bin/bash botuser -c 'aws sts get-caller-identity' 2>/dev/null; then
    echo "[support-bot] AWS auth OK."
else
    echo "[support-bot] WARNING: AWS auth not configured. EKS kubectl will not work."
fi

# ── Start the Python gateway as botuser ──────────────────────────────────────
echo "[support-bot] Starting gateway..."
exec su -s /bin/bash botuser -c 'exec /app/.venv/bin/python -u /app/gateway/main.py'
