Manage the dodocs-workflow installation. Supports: `init`, `version`, `upgrade`.

## Commands

### `init` (or no arguments)
Initialize the scrum-team workflow for the current project:
1. Copy `~/.opencode/scrum-team-config.template.md` to `.opencode/scrum-team-config.md`
2. Tell the user to fill in the project-specific values
3. Show which sections need to be configured

### `version`
Show the installed version by reading `~/.opencode/.dodocs-workflow-version`

### `upgrade`
Run the install script again to update all files:
```bash
bash ~/.opencode/../dodocs-workflow/install-opencode.sh
```
Or from remote:
```bash
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/main/install-opencode.sh | bash
```

Parse `$ARGUMENTS` to determine which subcommand to run.
$ARGUMENTS
