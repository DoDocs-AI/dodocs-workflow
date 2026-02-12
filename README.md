# dodocs-workflow

Scrum Team workflow for Claude Code. Spawns a 13-agent autonomous development team that takes a feature request from requirements through architecture, implementation, code review, testing, and PR creation.

## Quick Install

**From a local clone:**
```bash
git clone https://github.com/dodocs/dodocs-workflow.git
cd dodocs-workflow
bash install.sh
```

**From GitHub (one-liner):**
```bash
curl -fsSL https://raw.githubusercontent.com/dodocs/dodocs-workflow/main/install.sh | bash
```

## Setup Per Project

After installing, configure each project:

```bash
# Copy the config template into your project
cp ~/.claude/scrum-team-config.template.md <your-project>/.claude/scrum-team-config.md

# Edit the config with your project's values
# Fill in: tech stack, ports, source paths, commands
```

## Usage

In Claude Code, from your project directory:

```
/scrum-team <feature-name>
```

This spawns the full team and runs the 7-phase workflow autonomously.

### Retest Mode

Re-run testing for an existing feature without rebuilding:

```
/scrum-team --retest <feature-name>
```

## What Gets Installed

| Path | Description |
|------|-------------|
| `~/.claude/agents/*.md` | 11 agent definitions (architect, backend-dev, code-reviewer, frontend-dev, manual-tester, product-owner, qa-automation, qa-engineer, scrum-master, tech-lead, ux-designer) |
| `~/.claude/commands/scrum-team.md` | The `/scrum-team` command |
| `~/.claude/scrum-team-config.template.md` | Config template to copy into each project |

## Team Roles

| Agent | Model | Role |
|-------|-------|------|
| product-owner | opus | Gathers requirements, produces Feature Brief |
| ux-designer | opus | Designs user flows consistent with existing UI |
| architect | opus | Designs technical solution, produces Architecture doc |
| scrum-master | opus | Breaks architecture into tasks, assigns to team |
| code-reviewer | opus | Reviews all code before it moves to testing |
| tech-lead | sonnet | Manages git, compile gate, app startup, PR creation |
| frontend-dev-1 | sonnet | Implements frontend tasks |
| frontend-dev-2 | sonnet | Implements frontend tasks (coordinates with dev-1) |
| backend-dev-1 | sonnet | Implements backend tasks, owns all migrations |
| backend-dev-2 | sonnet | Implements backend tasks (no migrations) |
| qa-engineer | sonnet | Writes manual test cases |
| manual-tester | sonnet | Tests features in browser via Playwright |
| qa-automation | sonnet | Writes Playwright E2E tests |

## Workflow Phases

1. **Requirements + Early UX Research** (parallel)
2. **UX Design + User Validation** (user checkpoint)
3. **Architecture** (plan approval required)
4. **Task Breakdown + Git Setup**
5. **Build + Incremental Test** (all agents in parallel)
6. **Integration Verification**
7. **Ship** (PR creation)

## Upgrade

```bash
# Re-run the installer to upgrade all files
cd dodocs-workflow && git pull && bash install.sh
```

Or from remote:
```bash
curl -fsSL https://raw.githubusercontent.com/dodocs/dodocs-workflow/main/install.sh | bash
```

## Uninstall

```bash
bash uninstall.sh
```

This removes all agent definitions, the command, and the template. Project-specific config files are not touched.

## Project Config Reference

The `.claude/scrum-team-config.md` file tells the agents about your project:

- **App Identity** — name and description
- **Tech Stack** — frameworks, database, auth, build tools
- **Ports & URLs** — frontend/backend ports, dev domain
- **Source Paths** — where backend, frontend, and test files live
- **Commands** — how to start DB, backend, frontend, compile
- **Routing** — route prefix for workspace pages
- **Testing** — Playwright session name and flags
