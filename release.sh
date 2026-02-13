#!/usr/bin/env bash
set -euo pipefail

# dodocs-workflow release script
# Usage: bash release.sh [patch|minor|major]
#   No argument: release current VERSION as-is
#   patch/minor/major: bump VERSION accordingly

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/VERSION"
CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"
INSTALL_SH="$SCRIPT_DIR/install.sh"
INSTALL_OPENCODE_SH="$SCRIPT_DIR/install-opencode.sh"

die() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# Ensure we're in a clean git state
if ! git diff --quiet HEAD 2>/dev/null; then
    die "Working tree is dirty. Commit or stash changes before releasing."
fi

# Read current version
[ -f "$VERSION_FILE" ] || die "VERSION file not found"
CURRENT_VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")
echo -e "${BLUE}Current version:${NC} $CURRENT_VERSION"

# Parse current version
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Bump if requested
BUMP_TYPE="${1:-}"
case "$BUMP_TYPE" in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MAJOR=$MAJOR
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        MAJOR=$MAJOR
        MINOR=$MINOR
        PATCH=$((PATCH + 1))
        ;;
    "")
        # Release current version as-is
        ;;
    *)
        die "Usage: bash release.sh [patch|minor|major]"
        ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
TAG="v${NEW_VERSION}"

echo -e "${BLUE}Releasing:${NC} $TAG"

# Check tag doesn't already exist
if git rev-parse "$TAG" >/dev/null 2>&1; then
    die "Tag $TAG already exists. Bump the version or delete the tag first."
fi

# Prompt for changelog entry
echo ""
echo -e "${YELLOW}Enter changelog entry for $TAG (end with empty line):${NC}"
CHANGELOG_ENTRY=""
while IFS= read -r line; do
    [ -z "$line" ] && break
    CHANGELOG_ENTRY="${CHANGELOG_ENTRY}${line}
"
done

if [ -z "$CHANGELOG_ENTRY" ]; then
    die "Changelog entry is required."
fi

# Update VERSION file
echo "$NEW_VERSION" > "$VERSION_FILE"

# Update CHANGELOG.md
DATE=$(date +%Y-%m-%d)
NEW_CHANGELOG_SECTION="## [$TAG] - $DATE

$CHANGELOG_ENTRY"

if [ -f "$CHANGELOG_FILE" ]; then
    # Insert after the header line
    TEMP_FILE=$(mktemp)
    awk -v section="$NEW_CHANGELOG_SECTION" '
        /^## \[v/ && !inserted {
            print section
            print ""
            inserted=1
        }
        { print }
    ' "$CHANGELOG_FILE" > "$TEMP_FILE"
    mv "$TEMP_FILE" "$CHANGELOG_FILE"
else
    cat > "$CHANGELOG_FILE" <<EOF
# Changelog

All notable changes to dodocs-workflow will be documented in this file.

$NEW_CHANGELOG_SECTION
EOF
fi

# Update REPO_URL in install scripts
TAG_REF="refs/tags/$TAG"
sed -i '' "s|REPO_URL=\"https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/[^\"]*\"|REPO_URL=\"https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/$TAG_REF\"|" "$INSTALL_SH"
sed -i '' "s|REPO_URL=\"https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/[^\"]*\"|REPO_URL=\"https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/$TAG_REF\"|" "$INSTALL_OPENCODE_SH"

echo -e "${GREEN}Updated install.sh REPO_URL${NC}"
echo -e "${GREEN}Updated install-opencode.sh REPO_URL${NC}"

# Commit
git add VERSION CHANGELOG.md install.sh install-opencode.sh
git commit -m "release: $TAG"

# Tag
git tag -a "$TAG" -m "Release $TAG"

echo -e "${GREEN}Created commit and tag: $TAG${NC}"

# Push
echo ""
echo -e "${YELLOW}Pushing commit and tag to origin...${NC}"
git push origin HEAD
git push origin "$TAG"

echo -e "${GREEN}Pushed to origin${NC}"

# Create GitHub release
if command -v gh >/dev/null 2>&1; then
    echo ""
    echo -e "${YELLOW}Creating GitHub release...${NC}"
    gh release create "$TAG" --title "$TAG" --notes "$CHANGELOG_ENTRY"
    echo -e "${GREEN}GitHub release created${NC}"
else
    echo ""
    echo -e "${YELLOW}[!] gh CLI not found. Create the GitHub release manually:${NC}"
    echo "    gh release create $TAG --title \"$TAG\" --notes \"...\""
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Released: $TAG${NC}"
echo -e "${GREEN}========================================${NC}"
