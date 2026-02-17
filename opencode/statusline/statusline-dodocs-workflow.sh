#!/usr/bin/env bash

# dodocs-workflow status line for OpenCode
# Displays:
# Line 1: Model, project folder, git branch, update notification
# Line 2: Context usage bar, percentage, cost, duration

# Cache paths
UPDATE_CACHE="/tmp/dodocs-workflow-update-check-opencode"
GIT_CACHE="/tmp/dodocs-workflow-git-cache-opencode"

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# OpenCode JSON input (passed via stdin)
read -r -d '' OPENCODE_JSON

# Parse JSON using jq (fallback to basic parsing if jq not available)
if command -v jq &> /dev/null; then
    MODEL=$(echo "$OPENCODE_JSON" | jq -r '.model.display_name // "Sonnet"')
    FOLDER=$(echo "$OPENCODE_JSON" | jq -r '.workspace.current_dir // "~"' | xargs basename)
    CONTEXT_PCT=$(echo "$OPENCODE_JSON" | jq -r '.context_window.used_percentage // 0')
    COST=$(echo "$OPENCODE_JSON" | jq -r '.cost.total_cost_usd // 0')
    DURATION_MS=$(echo "$OPENCODE_JSON" | jq -r '.cost.total_duration_ms // 0')
else
    # Fallback: basic parsing without jq
    MODEL=$(echo "$OPENCODE_JSON" | grep -o '"display_name"[^,}]*' | cut -d'"' -f4 | head -n1)
    FOLDER=$(echo "$OPENCODE_JSON" | grep -o '"current_dir"[^,}]*' | cut -d'"' -f4 | xargs basename)
    CONTEXT_PCT=$(echo "$OPENCODE_JSON" | grep -o '"used_percentage"[^,}]*' | cut -d':' -f2 | tr -d ' ')
    COST=$(echo "$OPENCODE_JSON" | grep -o '"total_cost_usd"[^,}]*' | cut -d':' -f2 | tr -d ' ')
    DURATION_MS=$(echo "$OPENCODE_JSON" | grep -o '"total_duration_ms"[^,}]*' | cut -d':' -f2 | tr -d ' ')
fi

# Default values if parsing failed
MODEL=${MODEL:-"Sonnet"}
FOLDER=${FOLDER:-"~"}
CONTEXT_PCT=${CONTEXT_PCT:-0}
COST=${COST:-0}
DURATION_MS=${DURATION_MS:-0}

# Format model name (shorten if needed)
case "$MODEL" in
    *"Opus"*) MODEL_SHORT="Opus" ;;
    *"Sonnet"*) MODEL_SHORT="Sonnet" ;;
    *"Haiku"*) MODEL_SHORT="Haiku" ;;
    *) MODEL_SHORT="$MODEL" ;;
esac

# Line 1 components
LINE1="[$MODEL_SHORT] 📁 $FOLDER"

# Get git branch (with caching)
GIT_BRANCH=""
if [ -d ".git" ]; then
    # Check cache freshness (5 seconds)
    if [ -f "$GIT_CACHE" ]; then
        CACHE_AGE=$(($(date +%s) - $(stat -f %m "$GIT_CACHE" 2>/dev/null || echo 0)))
        if [ "$CACHE_AGE" -lt 5 ]; then
            GIT_BRANCH=$(cat "$GIT_CACHE")
        fi
    fi

    # Refresh cache if stale or missing
    if [ -z "$GIT_BRANCH" ]; then
        GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
        echo "$GIT_BRANCH" > "$GIT_CACHE"
    fi

    if [ -n "$GIT_BRANCH" ]; then
        LINE1="$LINE1 | 🌿 $GIT_BRANCH"
    fi
fi

# Check for updates (with 24-hour caching)
UPDATE_MSG=""
if command -v gh &> /dev/null; then
    CACHE_VALID=false

    # Check cache freshness (24 hours = 86400 seconds)
    if [ -f "$UPDATE_CACHE" ]; then
        CACHE_AGE=$(($(date +%s) - $(stat -f %m "$UPDATE_CACHE" 2>/dev/null || echo 86401)))
        if [ "$CACHE_AGE" -lt 86400 ]; then
            CACHE_VALID=true
        fi
    fi

    # Refresh cache if needed
    if [ "$CACHE_VALID" = false ]; then
        INSTALLED_VERSION=""
        LATEST_VERSION=""

        if [ -f "$HOME/.opencode/.dodocs-workflow-version" ]; then
            INSTALLED_VERSION=$(cat "$HOME/.opencode/.dodocs-workflow-version" | tr -d '[:space:]' | tr -d 'v')
        fi

        LATEST_VERSION=$(gh api repos/DoDocs-AI/dodocs-workflow/releases/latest --jq '.tag_name' 2>/dev/null | tr -d '[:space:]' | tr -d 'v')

        if [ -n "$INSTALLED_VERSION" ] && [ -n "$LATEST_VERSION" ] && [ "$INSTALLED_VERSION" != "$LATEST_VERSION" ]; then
            echo "$(date +%s)|$INSTALLED_VERSION|$LATEST_VERSION|true" > "$UPDATE_CACHE"
        else
            echo "$(date +%s)|$INSTALLED_VERSION|$LATEST_VERSION|false" > "$UPDATE_CACHE"
        fi
    fi

    # Read from cache
    if [ -f "$UPDATE_CACHE" ]; then
        UPDATE_AVAILABLE=$(cut -d'|' -f4 "$UPDATE_CACHE")
        if [ "$UPDATE_AVAILABLE" = "true" ]; then
            LATEST=$(cut -d'|' -f3 "$UPDATE_CACHE")
            UPDATE_MSG=" | ⬆️  v$LATEST available"
        fi
    fi
fi

LINE1="$LINE1$UPDATE_MSG"

# Line 2: Context window visualization
# Convert context percentage to integer for calculations
CONTEXT_INT=$(printf "%.0f" "$CONTEXT_PCT")

# Determine color based on usage
if [ "$CONTEXT_INT" -ge 90 ]; then
    BAR_COLOR="$RED"
elif [ "$CONTEXT_INT" -ge 70 ]; then
    BAR_COLOR="$YELLOW"
else
    BAR_COLOR="$GREEN"
fi

# Create progress bar (10 blocks)
FILLED=$((CONTEXT_INT / 10))
EMPTY=$((10 - FILLED))

BAR=""
for i in $(seq 1 $FILLED); do
    BAR="${BAR}▓"
done
for i in $(seq 1 $EMPTY); do
    BAR="${BAR}░"
done

# Format cost (2 decimal places)
COST_FORMATTED=$(printf "%.2f" "$COST")

# Format duration (convert ms to human readable)
DURATION_SEC=$((DURATION_MS / 1000))
DURATION_MIN=$((DURATION_SEC / 60))
DURATION_SEC_REMAIN=$((DURATION_SEC % 60))

if [ "$DURATION_MIN" -gt 0 ]; then
    DURATION_FORMATTED="${DURATION_MIN}m ${DURATION_SEC_REMAIN}s"
else
    DURATION_FORMATTED="${DURATION_SEC}s"
fi

# Assemble line 2
LINE2="${BAR_COLOR}${BAR}${NC} ${CONTEXT_INT}% | \$${COST_FORMATTED} | ⏱️  ${DURATION_FORMATTED}"

# Output both lines
echo -e "$LINE1"
echo -e "$LINE2"
