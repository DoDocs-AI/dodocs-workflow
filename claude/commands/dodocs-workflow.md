Manage the dodocs-workflow installation. Supports: `init`, `version`, `upgrade`.

## Commands

### `init` (or no arguments)
Initialize the scrum-team workflow for the current project:
1. Copy `~/.claude/scrum-team-config.template.md` to `.claude/scrum-team-config.md`
2. Tell the user to fill in the project-specific values
3. Show which sections need to be configured

### `version`
Show the installed version by reading `~/.claude/.dodocs-workflow-version`

### `upgrade`
Automatically upgrade to the latest release from GitHub:

1. Check if `gh` CLI is available
2. Query GitHub for latest release: `gh api repos/DoDocs-AI/dodocs-workflow/releases/latest --jq '.tag_name'`
3. Show current version from `~/.claude/.dodocs-workflow-version`
4. Download and execute install script from the latest tag:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/$LATEST_TAG/install.sh | bash
   ```
5. Clear update check cache: `rm -f /tmp/dodocs-workflow-update-check`
6. Show "Upgraded: v1.3.3 -> v1.3.4" (or appropriate versions)
7. Switch to main branch: Check current branch with `git branch --show-current`, then:
   - If already on main: Skip (no action needed)
   - If on another branch: Run `git switch main`
   - If switch fails (e.g., uncommitted changes): Show warning with current branch name

If `gh` CLI is not available, show:
```
Error: gh CLI not found. Install it with:
  brew install gh (macOS)
  Or visit: https://cli.github.com/

Manual upgrade:
  curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/main/install.sh | bash
```

Parse `$ARGUMENTS` to determine which subcommand to run.
$ARGUMENTS
