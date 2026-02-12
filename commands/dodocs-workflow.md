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
Run the install script again to update all files:
```bash
bash ~/.claude/../dodocs-workflow/install.sh
```
Or from remote:
```bash
curl -fsSL https://raw.githubusercontent.com/dodocs/dodocs-workflow/main/install.sh | bash
```

Parse `$ARGUMENTS` to determine which subcommand to run.
$ARGUMENTS
