Manage the dodocs-workflow installation. Supports: `init`, `version`, `upgrade`, `doctor`.

## Commands

### `init` (or no arguments)
Initialize the scrum-team workflow for the current project:
1. Copy `~/.claude/scrum-team-config.template.md` to `.claude/scrum-team-config.md`
2. Run the `doctor` checks (below). If Node.js >= 20 is missing, warn but continue —
   OpenSpec setup can be finished later by re-running `init`.
3. Scaffold OpenSpec (skip if `openspec/` already exists):
   ```bash
   npx -y @fission-ai/openspec@1.6.0 init --tools none
   ```
   This is non-interactive and writes only `openspec/config.yaml`. Then fill the
   `context:` block in `openspec/config.yaml` with the project's tech stack from the
   scrum-team config (once the user has filled it in).
4. Smoke-check: `npx -y @fission-ai/openspec@1.6.0 validate --all` (an empty project
   passes trivially).
5. If the project has existing feature docs (`docs/features/*/FEATURE-BRIEF.md`) but no
   `openspec/specs/`, suggest running `/spec-bootstrap` to derive living specs from them.
6. If `.claude/commands/opsx/` exists (user installed OpenSpec's own slash commands),
   leave it alone and note: the dodocs pipeline drives the `openspec` CLI directly;
   `/opsx:*` commands are optional extras and should be kept on the same pinned version.
7. Tell the user to fill in the project-specific values
8. Show which sections need to be configured

### `doctor`
Verify the OpenSpec toolchain for this project:
1. `node --version` — must be >= 20. If missing/old, print install instructions
   (e.g. `brew install node` on macOS) and STOP.
2. `npx -y @fission-ai/openspec@1.6.0 --version` — must succeed and print `1.6.0`.
3. If `openspec/` exists: `npx -y @fission-ai/openspec@1.6.0 validate --all --strict`
   and report the result.
4. Report the pinned CLI line from `.claude/scrum-team-config.md` (`## OpenSpec` section);
   warn if the section is missing (older config — copy it from the current template).

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
