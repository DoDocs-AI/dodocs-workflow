# dodocs-workflow

A Scrum Team workflow for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and OpenCode. Spawns a **13-agent autonomous development team** that takes a feature from requirements gathering through architecture, implementation, code review, testing, and PR creation — with minimal human intervention. Also includes a **10-agent production readiness audit** that identifies security, performance, accessibility, and infrastructure issues before you ship.

```
/scrum-team add user billing dashboard
```

That single command launches the full team. You answer a few product questions, approve UX flows and architecture, then watch it build, review, test, and ship.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Installation](#installation)
- [OpenCode Installation](#opencode-installation)
- [Automatic Update Notifications](#automatic-update-notifications)
- [Project Setup](#project-setup)
- [Usage](#usage)
- [Container Team](#container-team)
- [Merge Features](#merge-features)
- [Workflow Phases](#workflow-phases)
- [Team Roles](#team-roles)
- [Prepare for Production](#prepare-for-production)
- [Architecture](#architecture)
- [Project Config Reference](#project-config-reference)
- [Upgrade](#upgrade)
- [Uninstall](#uninstall)
- [Troubleshooting](#troubleshooting)
- [Releases](#releases)
- [Contributing](#contributing)

---

## How It Works

dodocs-workflow is a set of **agent definitions** and **slash commands** for Claude Code and OpenCode. When you run `/scrum-team`, it orchestrates 13 specialized agents that collaborate through a shared task list, message passing, and a phased workflow:

```
You describe the feature
        |
        v
  Phase 1: Product Owner gathers requirements
           UX Designer researches existing UI patterns (parallel)
        |
        v
  Phase 2: UX Designer produces user flows
           YOU approve the UX  <-- human checkpoint
        |
        v
  Phase 3: Architect designs the technical solution
           YOU approve the architecture  <-- human checkpoint
        |
        v
  Phase 4: Scrum Master breaks it into tasks
           Tech Lead creates the feature branch
        |
        v
  Phase 5: ALL agents work in parallel:
           - 4 developers build (atomic commits per task)
           - Code Reviewer reviews each task
           - QA Engineer writes test cases (organized by user story)
           - Tech Lead runs compile gate + starts app
           - Manual Tester tests full feature story by story (after all reviews + test cases ready)
           - QA Automation writes E2E tests per user story
        |
        v
  Phase 6: Integration verification
           Full E2E suite, smoke test, final code review
        |
        v
  Phase 7: Tech Lead creates the PR
           Team lead reports summary to you
```

The key insight is **feature-level testing** in Phase 5: manual testing starts after all dev tasks are code-reviewed and QA engineer's test cases are ready. The manual-tester tests the full feature story by story, and qa-automation writes E2E tests per user story as each story passes. Bugs are filed and fixed in real-time.

---

## Installation

### Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) or OpenCode installed and configured
- Git

### From a Local Clone (recommended)

```bash
git clone https://github.com/DoDocs-AI/dodocs-workflow.git
cd dodocs-workflow
bash install.sh
```

### One-Liner from GitHub

Installs the latest stable release (not HEAD):

```bash
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v1.2.0/install.sh | bash
```

### What Gets Installed

The installer copies files to `~/.claude/` (Claude Code's global config directory):

| Destination | Files | Description |
|-------------|-------|-------------|
| `~/.claude/agents/` | 21 `.md` files | Agent role definitions (11 scrum + 10 production audit) |
| `~/.claude/commands/` | `scrum-team.md`, `prepare-for-production.md`, `container-team.md`, `dodocs-workflow.md`, `dw-upgrade.md`, `merge-features.md` | Slash commands |
| `~/.claude/docker/` | `agent-env.Dockerfile`, `agent-entrypoint.sh` | Container team Docker runtime files |
| `~/.claude/` | `scrum-team-config.template.md` | Config template for new projects |
| `~/.claude/` | `.dodocs-workflow-version` | Installed version tracker |

Nothing is installed into your project directories. Project-specific configuration is done separately (see below).

---

## OpenCode Installation

### From a Local Clone (recommended)

```bash
git clone https://github.com/DoDocs-AI/dodocs-workflow.git
cd dodocs-workflow
bash install-opencode.sh
```

### One-Liner from GitHub

Installs the latest stable release (not HEAD):

```bash
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v1.2.0/install-opencode.sh | bash
```

### What Gets Installed

The OpenCode installer copies files to `~/.opencode/` (OpenCode's global config directory):

| Destination | Files | Description |
|-------------|-------|-------------|
| `~/.opencode/agents/` | 21 `.md` files | Agent role definitions (11 scrum + 10 production audit) |
| `~/.opencode/commands/` | `scrum-team.md`, `prepare-for-production.md` | Slash commands |
| `~/.opencode/` | `scrum-team-config.template.md` | Config template for new projects |
| `~/.opencode/` | `.dodocs-workflow-version` | Installed version tracker |

Nothing is installed into your project directories. Project-specific configuration is done separately (see below).

---

## Automatic Update Notifications

dodocs-workflow includes a status line integration that displays update notifications when a new version is available on GitHub. The status line also shows session information like context usage, cost, and duration.

### Status Line Display

The status line shows two lines of information:

**Line 1**: Session info and update status
- Model name (Opus, Sonnet, or Haiku)
- Current project folder (directory name only)
- Git branch (if in a git repository)
- Update notification (only when update available)

**Line 2**: Context window visualization
- Colored progress bar showing context usage
- Percentage occupied
- Cost tracking (in USD)
- Session duration

**Example output** when update is available:
```
[Opus] 📁 dodocs-workflow | 🌿 main | ⬆️ v1.3.4 available
▓▓▓░░░░░░░ 25% | $0.15 | ⏱️ 8m 42s
```

**Example output** when up-to-date:
```
[Opus] 📁 dodocs-workflow | 🌿 main
▓▓▓░░░░░░░ 25% | $0.15 | ⏱️ 8m 42s
```

**Color coding** for the context bar:
- Green (< 70%): Normal usage
- Yellow (70-89%): Approaching limit
- Red (≥ 90%): Near maximum capacity

### Enable the Status Line

Add this configuration to your `~/.claude/settings.json` (Claude Code) or `~/.opencode/settings.json` (OpenCode):

**Claude Code**:
```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline-dodocs-workflow.sh"
  }
}
```

**OpenCode**:
```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.opencode/statusline-dodocs-workflow.sh"
  }
}
```

The status line will automatically refresh on each interaction.

### How Update Checks Work

- **Frequency**: Checks GitHub for new releases once per day (24-hour cache)
- **API**: Uses `gh api repos/DoDocs-AI/dodocs-workflow/releases/latest` to query the latest release
- **Cache**: Stores result in `/tmp/dodocs-workflow-update-check` to avoid rate limits
- **Git info**: Caches git branch for 5 seconds to avoid performance lag
- **Requirement**: Requires `gh` CLI to be installed (brew install gh on macOS)

If `gh` CLI is not available or the API call fails, the status line continues to work but skips the update check.

### Upgrade to Latest Version

When you see an update notification, run:

**Claude Code**:
```bash
/dodocs-workflow upgrade
```

**OpenCode**:
```bash
/dodocs-workflow upgrade
```

The upgrade command will:
1. Query GitHub for the latest release version
2. Show your current version
3. Download and execute the install script from the latest tag
4. Clear the update check cache
5. Show the before/after versions

**Manual upgrade** (if `gh` CLI is not installed):
```bash
# Claude Code
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/main/install.sh | bash

# OpenCode
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/main/install-opencode.sh | bash
```

### Check Current Version

**Claude Code**:
```bash
/dodocs-workflow version
```

**OpenCode**:
```bash
/dodocs-workflow version
```

Or read the version file directly:
```bash
cat ~/.claude/.dodocs-workflow-version     # Claude Code
cat ~/.opencode/.dodocs-workflow-version   # OpenCode
```

### Troubleshooting

**Update notification not showing?**
- Make sure `gh` CLI is installed: `brew install gh` (macOS) or visit https://cli.github.com/
- Clear the cache to force a refresh: `rm /tmp/dodocs-workflow-update-check*`
- Check GitHub API access: `gh api repos/DoDocs-AI/dodocs-workflow/releases/latest --jq '.tag_name'`

**Status line not displaying?**
- Verify the script is installed: `ls -la ~/.claude/statusline-dodocs-workflow.sh`
- Check it's executable: `chmod +x ~/.claude/statusline-dodocs-workflow.sh`
- Test the script manually: `echo '{"model":{"display_name":"Opus"},"workspace":{"current_dir":"'$(pwd)'"},"context_window":{"used_percentage":25},"cost":{"total_cost_usd":0.15,"total_duration_ms":522000}}' | ~/.claude/statusline-dodocs-workflow.sh`

**Git branch not showing?**
- Make sure you're in a git repository: `git status`
- The cache refreshes every 5 seconds automatically

---

## Project Setup

Each project needs a **config file** that tells the agents about your tech stack, file paths, and commands.

### 1. Copy the Template

```bash
# From your project root (Claude Code)
cp ~/.claude/scrum-team-config.template.md .claude/scrum-team-config.md

# From your project root (OpenCode)
cp ~/.opencode/scrum-team-config.template.md .opencode/scrum-team-config.md
```

### 2. Fill In Your Project Values

Edit `.claude/scrum-team-config.md` (Claude Code) or `.opencode/scrum-team-config.md` (OpenCode) with your project-specific settings. Every section matters — agents read this file before doing any work.

Here's an example for a Quarkus + React project:

```markdown
# Scrum Team Config

## App Identity

- **Name**: MyApp
- **Description**: SaaS platform for invoice management

## Tech Stack

- **Backend Framework**: Quarkus (REST resources with JAX-RS annotations, Hibernate ORM with Panache)
- **Frontend Framework**: React 18+ with TypeScript
- **Database**: PostgreSQL
- **Migration Tool**: Flyway
- **Storage**: MinIO
- **Auth**: JWT-based authentication
- **Build Tool**: Maven
- **API Pattern**: REST resources with JAX-RS annotations

## Ports & URLs

- **Frontend Port**: 3000
- **Backend Port**: 8070
- **Dev Domain**: https://localhost:3000/

## Source Paths — Backend

- **Resources/Controllers**: src/main/java/com/myapp/resource/
- **Entities/Models**: src/main/java/com/myapp/entity/
- **Services**: src/main/java/com/myapp/service/
- **DTOs**: src/main/java/com/myapp/dto/
- **Migrations**: src/main/resources/db/migration/
- **Tests**: src/test/

## Source Paths — Frontend

- **Pages**: src/main/webapp/src/pages/
- **Workspace Pages**: src/main/webapp/src/pages/workspace/
- **Components**: src/main/webapp/src/components/
- **Services (API calls)**: src/main/webapp/src/services/
- **Types**: src/main/webapp/src/types/
- **Router**: src/main/webapp/src/router.tsx

## Source Paths — Testing

- **Test Cases (manual)**: docs/e2e-testcases/
- **Feature Docs**: docs/features/
- **E2E Tests**: src/main/webapp/e2e/tests/
- **Fixtures**: src/main/webapp/e2e/fixtures/
- **Page Objects**: src/main/webapp/e2e/pages/
- **Auth Fixture**: src/main/webapp/e2e/fixtures/auth.fixture.ts
- **Playwright Config**: src/main/webapp/e2e/playwright.config.ts

## Commands

- **Start DB**: docker compose up -d postgres
- **Start Storage**: docker compose up -d minio
- **Start Backend**: ./mvnw quarkus:dev
- **Start Frontend**: cd src/main/webapp && npm run dev
- **Compile Backend**: ./mvnw compile
- **Compile Frontend**: cd src/main/webapp && npx tsc --noEmit

## Routing

- **Route Prefix**: /workspace

## Testing

- **Playwright Session Name**: myapp
- **Playwright Flags**: --headed
```

### 3. Verify

Open Claude Code or OpenCode in your project and type `/scrum-team test`. If the config is found, the workflow starts. If not, you'll get a clear error message telling you what's missing.

---

## Usage

### Build a New Feature

```
/scrum-team <feature-description>
```

Examples:
```
/scrum-team add user billing dashboard with Stripe integration
/scrum-team implement organization member invitation flow
/scrum-team add dark mode toggle to settings page
```

You'll be asked to:
1. Answer product questions from the Product Owner
2. Approve UX flows (Phase 2 checkpoint)
3. Approve the architecture plan (Phase 3 checkpoint)

After that, the team works autonomously through build, review, test, and PR creation.

### Retest an Existing Feature

Skip the full workflow and jump straight to testing with a lighter team:

```
/scrum-team --retest <feature-name>
```

Retest mode:
- Spawns only 5 agents (tech-lead, code-reviewer, manual-tester, frontend-dev, backend-dev)
- Reads existing test cases and feature docs
- Runs all test scenarios
- Files bugs, developers fix, code-reviewer reviews, manual-tester retests
- Loops until all test cases pass

---

## Container Team

`/container-team` runs the same 13-agent scrum workflow as `/scrum-team`, but **inside an isolated Docker container**. Your main Claude Code session stays free while the agents work in the background.

### When to Use It

| Situation | Use |
|-----------|-----|
| You want to keep using Claude Code while the team builds | `/container-team` |
| You need to run multiple features in parallel | `/container-team` (one container per feature) |
| You want the team in your terminal right now | `/scrum-team` |
| Short feature, hands-on oversight | `/scrum-team` |

### Prerequisites

- Docker Desktop running (or a configured Kubernetes cluster for `--k8s` mode)
- `ANTHROPIC_API_KEY` exported in your shell
- `.claude/scrum-team-config.md` present in the project (same as `/scrum-team`)
- dodocs-workflow installed (the Docker files land in `~/.claude/docker/`)

### Quick Start

```bash
/container-team add user billing dashboard
```

This builds the agent image, launches a container, and opens a live monitoring dashboard:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Container Team: add user billing dashboard
Container: ct-add-user-billing-dashboard-1708001234  |  Status: running  |  Uptime: 14m
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROGRESS (docs/features/add-user-billing-dashboard/PROGRESS.md)
  Phase 1: Requirements + UX Research   ✅ Done
  Phase 2: UX Design + Architecture     🔄 In Progress
  Phase 3: Task Breakdown + Git         ⏳ Pending
  Phase 4: Build + Test                 ⏳ Pending
  Phase 5: Integration Verification     ⏳ Pending
  Phase 6: Ship                         ⏳ Pending

RECENT LOGS (last 20 lines):
  [product-owner] Feature Brief written to docs/features/...
  [ux-designer]   Researching existing UI patterns...
  [architect]     Reading Feature Brief, designing architecture...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Refreshing in 15s...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Usage Examples

```bash
# Launch and monitor interactively
/container-team add dark mode toggle

# Launch in background (no monitoring loop)
/container-team implement org invitations --detach

# Re-attach to a running container
/container-team --attach ct-implement-org-invitations-1708001234

# List all running container teams
/container-team --status

# Use Kubernetes instead of Docker
/container-team add billing dashboard --k8s
```

### How It Works

```
Main Claude Code session (your terminal)
  │
  └── docker run -d  dodocs-agent-env  "claude /scrum-team <feature>"
                          │
                          └── Inside container: full 13-agent scrum team
                              ├── product-owner
                              ├── ux-designer
                              ├── architect
                              ├── scrum-master, tech-lead, code-reviewer
                              ├── frontend-dev x2, backend-dev x2
                              ├── qa-engineer, manual-tester, qa-automation
                              └── Agents coordinate via Claude Code's
                                  internal team system (Tasks + SendMessage)

Main session monitors:
  - docker logs -f <container-id>     (stream everything)
  - Periodic reads of PROGRESS.md     (structured phase status)
```

### Viewing Logs

```bash
# Full log stream (from outside Claude Code)
docker logs -f ct-<feature-slug>-<timestamp>

# Inside Claude Code monitoring loop, say "l" or "full logs"
```

### Stopping a Container

```bash
docker stop ct-<feature-name>-<timestamp>
docker rm   ct-<feature-name>-<timestamp>
```

Or tell Claude Code "stop the container" while in the monitoring loop.

### Files Created

- `.container-team/<feature-name>/container.id` — container ID for reattachment
- `.container-team/<feature-name>/container.name` — human-readable container name
- `.container-team/<feature-name>/started.at` — launch timestamp
- `docs/features/<feature-name>/PROGRESS.md` — live progress (written by agents inside the container)

Add `.container-team/` to your `.gitignore` if you don't want to track container metadata.

---

## Merge Features

After running `/scrum-team` or `/container-team` for multiple features, each feature ends with
an open PR (`feature/<name>` → `main`). `/merge-features` collects and merges them all in one
step — with CI gating, auto-rebase on conflicts, and a clear summary report.

### When to Use It

Run `/merge-features` after one or more `/scrum-team` or `/container-team` sessions have
completed and their PRs are open and ready to ship.

### Prerequisites

- `gh` CLI installed and authenticated (`gh auth status`)
- Inside a git repository with an `origin` remote
- At least one open `feature/*` PR targeting `main`

### Usage Examples

```bash
# Merge all open feature/* PRs (CI must pass)
/merge-features

# Assess status without merging anything
/merge-features --dry-run

# Merge only specific PRs by number
/merge-features --only 42,38

# Merge even if CI checks are pending or failing
/merge-features --skip-ci
```

### What Each Status Means

| Symbol | Meaning |
|--------|---------|
| ✅ ready to merge | CI passes, no conflicts — will be squash-merged |
| 🔧 rebase then merge | Conflicts detected — auto-rebased onto main before merging |
| ⏭️ skip (CI pending) | Checks still running — skipped unless `--skip-ci` is set |
| ⏭️ skip (CI failed) | Checks failed — skipped unless `--skip-ci` is set |
| ❌ conflict — manual resolution needed | Auto-rebase failed, needs human intervention |

### How Conflict Auto-Rebase Works

When a `feature/*` branch has conflicts with `main`, `/merge-features` spawns a tech-lead
agent to rebase it:

1. `git fetch origin main`
2. `git checkout feature/<name>`
3. `git rebase origin/main` — for each conflict, new files added by the feature are kept;
   infrastructure / config files prefer the main version
4. `git push --force-with-lease origin feature/<name>`

If the rebase cannot be completed cleanly, the PR is marked `❌ failed` and skipped.
After a successful rebase, CI is re-checked before the PR is merged.

### Merge Order

PRs are processed oldest-first (by PR creation date). After each merge, the remaining PRs
are re-checked for new conflicts (since main has advanced), and auto-rebase is triggered
again if needed.

---

## Workflow Phases

### Phase 1: Requirements + Early UX Research

**Agents**: product-owner, ux-designer (parallel)

The product owner talks to you about the feature — what problem it solves, who uses it, acceptance criteria, edge cases. Meanwhile, the UX designer starts reading your existing pages and components to understand current UI patterns.

**Output**: `docs/features/<feature>/FEATURE-BRIEF.md`

### Phase 2: UX Design + User Validation

**Agents**: ux-designer

The UX designer combines their pattern research with the Feature Brief to produce complete user flows — entry points, happy paths, error paths, state transitions.

**Human checkpoint**: You review and approve the UX flows before architecture begins.

**Output**: `docs/features/<feature>/UX-DESIGN.md`

### Phase 3: Architecture

**Agents**: architect (plan approval mode)

The architect reads the Brief and UX Design, studies your existing codebase patterns, and designs the technical solution — endpoints, entities, services, DTOs, components, routes, API contracts.

**Human checkpoint**: You approve the architecture plan.

**Output**: `docs/features/<feature>/ARCHITECTURE.md`

### Phase 4: Task Breakdown + Git Setup

**Agents**: scrum-master, tech-lead

The tech-lead creates a feature branch. The scrum-master reads the Architecture doc and creates all tasks with proper assignment, dependencies, and migration ownership rules.

### Phase 5: Build + Test

**Agents**: ALL 13 agents in parallel

This is where the magic happens. All agents work simultaneously, updating `PROGRESS.md` as they go:

- **Developers** implement their assigned tasks and make atomic commits
- **Code reviewer** watches for completed tasks and reviews each one
- **QA engineer** writes test cases organized by user story
- **Tech lead** runs compile gate, starts the app, monitors for issues
- **Manual tester** waits for all dev tasks to be code-reviewed and test cases to be ready, then tests the full feature story by story
- **QA automation** writes E2E tests per user story after manual-tester passes all scenarios for that story

The flow:
```
Developers complete tasks -> atomic commits
       |
       v
Code-reviewer reviews each task individually
       |
       v
QA-engineer writes test cases organized by user story (parallel with devs)
       |
       v
ALL tasks reviewed + test cases ready
       |
       v
Manual-tester tests the full feature story by story
       |
       +-- pass -> qa-automation writes E2E for that user story
       +-- fail -> bug task -> developer fixes -> code-reviewer reviews -> manual-tester retests
```

### Phase 6: Integration Verification

**Agents**: tech-lead, qa-automation, manual-tester, code-reviewer

After all user stories pass testing:
- Tech lead does a full app restart and regression check
- QA automation runs the complete E2E test suite
- Manual tester does a final smoke test of the end-to-end flow
- Code reviewer does a full-diff review of all changes

### Phase 7: Ship

**Agents**: tech-lead

The tech lead creates a PR from the feature branch to main with a comprehensive description of all changes.

---

## Team Roles

The scrum team uses 11 agent definitions that are instantiated into 13 running agents (frontend-dev and backend-dev are each used twice). An additional 10 agents are used by `/prepare-for-production`.

| Agent | Model | Phase | Role |
|-------|-------|-------|------|
| [product-owner](claude/docs/agents/product-owner.md) | opus | 1 | Gathers requirements, produces Feature Brief |
| [ux-designer](claude/docs/agents/ux-designer.md) | opus | 1-2 | Researches UI patterns, designs user flows |
| [architect](claude/docs/agents/architect.md) | opus | 3 | Designs technical solution, produces Architecture doc |
| [scrum-master](claude/docs/agents/scrum-master.md) | opus | 4 | Breaks architecture into tasks, assigns to team |
| [code-reviewer](claude/docs/agents/code-reviewer.md) | opus | 5-6 | Reviews all code for quality, security, correctness |
| [tech-lead](claude/docs/agents/tech-lead.md) | sonnet | 4-7 | Git, compile gate, app startup, bug filing, PR creation |
| [frontend-dev](claude/docs/agents/frontend-dev.md) | sonnet | 5 | Implements frontend tasks (2 instances) |
| [backend-dev](claude/docs/agents/backend-dev.md) | sonnet | 5 | Implements backend tasks (2 instances) |
| [qa-engineer](claude/docs/agents/qa-engineer.md) | sonnet | 5 | Writes manual test case documents |
| [manual-tester](claude/docs/agents/manual-tester.md) | sonnet | 5-6 | Tests features in browser via Playwright |
| [qa-automation](claude/docs/agents/qa-automation.md) | sonnet | 5-6 | Writes Playwright E2E tests |

**Model strategy**: Planning and review roles use **opus** (higher reasoning capability). Execution roles use **sonnet** (faster, more cost-effective for code generation).

See the `claude/docs/agents/` directory for detailed documentation of each agent.

---

## Prepare for Production

The `/prepare-for-production` command fills the gap between "feature complete" and "production ready." While `/scrum-team` builds features, `/prepare-for-production` audits the entire codebase for production readiness across 10 dimensions.

### Quick Start

```
/prepare-for-production
```

Or run only specific auditors:

```
/prepare-for-production --only security,performance,db
```

### How It Works

```
Phase 1: Parallel Audit (10 auditors run simultaneously)
    security-auditor ──────┐
    performance-engineer ──┤
    accessibility-auditor ─┤
    seo-analyst ───────────┤  All produce REPORT.md
    devops-engineer ───────┤  in docs/production-audit/
    error-handler ─────────┤
    dependency-auditor ────┤
    api-documenter ────────┤
    db-analyst ────────────┤
    load-tester ───────────┘
         |
         v
Phase 2: Triage + Task Creation
    Read all reports, deduplicate, classify by severity,
    create fix tasks assigned to developers
         |
         v
Phase 3: Fix + Review
    Developers fix Critical/High issues,
    code-reviewer reviews, tech-lead verifies
         |
         v
Phase 4: Re-audit + Sign-off
    Re-run auditors that found Critical/High issues,
    produce SUMMARY.md with pass/fail per area
```

### Auditor Agents

| Agent | Model | What It Checks |
|-------|-------|---------------|
| [security-auditor](claude/docs/agents/security-auditor.md) | opus | OWASP top 10, auth on every endpoint, hardcoded secrets, dependency CVEs |
| [performance-engineer](claude/docs/agents/performance-engineer.md) | opus | N+1 queries, missing DB indexes, frontend bundle size, caching |
| [accessibility-auditor](claude/docs/agents/accessibility-auditor.md) | sonnet | WCAG 2.1 AA, keyboard nav, ARIA, color contrast, screen reader |
| [seo-analyst](claude/docs/agents/seo-analyst.md) | sonnet | Meta tags, Open Graph, sitemap, robots.txt, structured data |
| [devops-engineer](claude/docs/agents/devops-engineer.md) | sonnet | Dockerfile, docker-compose, health checks, CI/CD, env config |
| [error-handler](claude/docs/agents/error-handler.md) | sonnet | Consistent error responses, error boundaries, logging coverage |
| [dependency-auditor](claude/docs/agents/dependency-auditor.md) | sonnet | npm audit, Maven dependency check, outdated packages, licenses |
| [api-documenter](claude/docs/agents/api-documenter.md) | sonnet | OpenAPI spec coverage, endpoint inventory, API reference docs |
| [db-analyst](claude/docs/agents/db-analyst.md) | opus | Schema review, missing indexes/constraints, migration hygiene |
| [load-tester](claude/docs/agents/load-tester.md) | sonnet | Load test scenarios, capacity estimates, breaking points |

### Selective Mode

Run only the auditors you need:

| Short Name | Agent |
|-----------|-------|
| `security` | security-auditor |
| `performance` | performance-engineer |
| `accessibility` | accessibility-auditor |
| `seo` | seo-analyst |
| `devops` | devops-engineer |
| `error-handler` | error-handler |
| `dependency` | dependency-auditor |
| `api-docs` | api-documenter |
| `db` | db-analyst |
| `load-test` | load-tester |

### Output

All reports are written to `docs/production-audit/`:

```
docs/production-audit/
├── security-auditor-REPORT.md
├── performance-engineer-REPORT.md
├── accessibility-auditor-REPORT.md
├── seo-analyst-REPORT.md
├── devops-engineer-REPORT.md
├── error-handler-REPORT.md
├── dependency-auditor-REPORT.md
├── api-documenter-REPORT.md
├── db-analyst-REPORT.md
├── load-tester-REPORT.md
├── TRIAGE.md              # Consolidated findings by severity
└── SUMMARY.md             # Final pass/fail sign-off
```

### Pass Criteria

- **PASS**: Zero Critical, zero High findings remaining
- **PASS WITH WARNINGS**: Zero Critical, some High with documented justification
- **FAIL**: Any Critical findings remaining

---

## Architecture

### File Layout

```
dodocs-workflow/
├── claude/                              # Claude Code workflow
│   ├── agents/                          #   Agent definitions (installed to ~/.claude/agents/)
│   ├── commands/                        #   Slash commands (installed to ~/.claude/commands/)
│   │   ├── scrum-team.md                #     Interactive 13-agent team
│   │   ├── container-team.md            #     Docker/K8s isolated team (background)
│   │   ├── prepare-for-production.md    #     10-agent production audit
│   │   ├── dodocs-workflow.md           #     Version + upgrade command
│   │   └── dw-upgrade.md               #     Upgrade helper
│   ├── docs/                            #   Agent documentation
│   └── templates/                       #   Config template
├── docker/                              # Container team runtime
│   ├── agent-env.Dockerfile             #   Docker image (node:22-slim + claude CLI + tools)
│   └── agent-entrypoint.sh             #   Entrypoint: copies config, runs scrum-team
├── opencode/                            # OpenCode workflow
│   ├── agents/                          #   Agent definitions (installed to ~/.opencode/agents/)
│   ├── commands/                        #   Slash commands (installed to ~/.opencode/commands/)
│   ├── docs/                            #   Agent documentation
│   └── templates/                       #   Config template
├── install.sh                           # Claude Code install/upgrade
├── uninstall.sh                         # Claude Code uninstall
├── install-opencode.sh                  # OpenCode install/upgrade
├── uninstall-opencode.sh                # OpenCode uninstall
├── release.sh                           # Release script (tag + changelog + GitHub release)
├── VERSION                              # Current version
├── CHANGELOG.md                         # Release history
└── README.md
```

### How Agents Communicate

Agents coordinate through three mechanisms:

1. **Shared Task List** — Tasks are created, assigned, blocked, and completed through Claude Code or OpenCode's task system. All agents see the same list.
2. **Direct Messages** — Agents send messages to specific teammates (e.g., code-reviewer notifies tech-lead after approving a task).
3. **Shared Files** — Feature Brief, UX Design, Architecture docs, and test cases are written to disk and read by downstream agents.
4. **Progress File** — A shared `PROGRESS.md` file at `docs/features/<feature>/PROGRESS.md` tracks phase status, artifact completion, development tasks, code reviews, testing, E2E automation, bugs, and a timeline. All agents update it at key milestones, providing a single-file dashboard of workflow progress.

### Key Design Decisions

**Per-project config over convention**: Every project is different — different frameworks, different directory structures, different commands. Rather than guessing, agents read a config file that tells them exactly where things are.

**Migration ownership**: Database migrations are a common source of conflicts when multiple developers work in parallel. Only `backend-dev-1` creates migrations. `backend-dev-2` works on services and endpoints that depend on those migrations.

**Feature-level testing**: Testing starts after all dev tasks are code-reviewed and QA engineer's test cases are ready. The manual-tester tests the full feature story by story using the test cases, and qa-automation writes E2E tests per user story as each story passes. This ensures complete test coverage with well-structured test cases rather than ad-hoc incremental testing.

**Atomic commits**: Each completed task = one commit. This makes code review easier, git history cleaner, and rollbacks possible at the task level.

---

## Project Config Reference

The `.claude/scrum-team-config.md` (Claude Code) or `.opencode/scrum-team-config.md` (OpenCode) file is the single source of truth that all agents read. Every section is required.

| Section | Used By | Purpose |
|---------|---------|---------|
| **App Identity** | All agents | App name and description for context |
| **Tech Stack** | architect, backend-dev, frontend-dev | Framework, DB, auth, build tool details |
| **Ports & URLs** | tech-lead, manual-tester, qa-automation | Where to access the running app |
| **Source Paths — Backend** | architect, backend-dev, code-reviewer | Where backend code lives |
| **Source Paths — Frontend** | architect, frontend-dev, ux-designer, code-reviewer | Where frontend code lives |
| **Source Paths — Testing** | qa-engineer, manual-tester, qa-automation | Where test files live |
| **Commands** | tech-lead, backend-dev, frontend-dev | How to start/compile the app |
| **Routing** | architect, frontend-dev, qa-automation | Route prefix for workspace pages |
| **Testing** | manual-tester | Playwright session name and flags |

See the template file in `claude/templates/scrum-team-config.template.md` or `opencode/templates/scrum-team-config.template.md` for the full structure with examples.

---

## Upgrade

### Automatic Upgrade (Recommended)

Use the built-in upgrade command to automatically fetch and install the latest release:

**Claude Code**:
```bash
/dodocs-workflow upgrade
```

**OpenCode**:
```bash
/dodocs-workflow upgrade
```

This command:
- Queries GitHub for the latest release
- Downloads the install script from the latest tag
- Runs the installation
- Shows before/after versions

**Requires**: `gh` CLI installed (`brew install gh` on macOS)

### From a Local Clone

```bash
cd dodocs-workflow
git pull
bash install.sh              # Claude Code
bash install-opencode.sh     # OpenCode
```

The installer detects the existing installation and shows `Upgraded: v1.0.0 -> v1.1.0`.

### From GitHub (Manual)

Check the [latest release](https://github.com/DoDocs-AI/dodocs-workflow/releases) and run the one-liner from the release notes, or use the tag URL directly:

**Claude Code**:
```bash
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v1.3.3/install.sh | bash
```

**OpenCode**:
```bash
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v1.3.3/install-opencode.sh | bash
```

### Check Current Version

**Using the command**:
```bash
/dodocs-workflow version     # Claude Code or OpenCode
```

**Reading the version file**:
```bash
cat ~/.claude/.dodocs-workflow-version      # Claude Code
cat ~/.opencode/.dodocs-workflow-version    # OpenCode
```

---

## Uninstall

```bash
# From the repo directory
bash uninstall.sh

# Or directly
bash ~/path/to/dodocs-workflow/uninstall.sh
```

This removes:
- All 21 agent definitions from `~/.claude/agents/`
- The `/scrum-team` and `/prepare-for-production` commands from `~/.claude/commands/`
- The config template from `~/.claude/`
- The version file

Project-specific `.claude/scrum-team-config.md` files are **not** removed.

### OpenCode Uninstall

```bash
# From the repo directory
bash uninstall-opencode.sh

# Or directly
bash ~/path/to/dodocs-workflow/uninstall-opencode.sh
```

This removes:
- All 21 agent definitions from `~/.opencode/agents/`
- The `/scrum-team` and `/prepare-for-production` commands from `~/.opencode/commands/`
- The config template from `~/.opencode/`
- The version file

Project-specific `.opencode/scrum-team-config.md` files are **not** removed.

---

## Troubleshooting

### "No scrum-team config found for this project"

You need to create `.claude/scrum-team-config.md` (Claude Code) or `.opencode/scrum-team-config.md` (OpenCode) in your project. See [Project Setup](#project-setup).

### Agents can't find files or commands fail

Double-check your config paths. The most common issues:
- Source paths don't match your actual directory structure
- Commands have typos or assume a different working directory
- Port numbers don't match your app's actual configuration

### Architect's plan gets rejected

The architect runs in `plan` mode — you must approve the architecture before development begins. If you reject it, provide specific feedback about what to change. The architect will revise and resubmit.

### Compile gate fails

The tech-lead will report compilation errors. Usually this means a developer introduced a build error. The tech-lead creates a bug task assigned to the responsible developer.

### Tests fail after all code is reviewed

This is expected and part of the workflow. The manual-tester files bug tasks, developers fix them, code-reviewer re-reviews, and manual-tester retests. The cycle continues until all tests pass.

---

## Releases

dodocs-workflow uses tagged releases so install scripts always pull from a stable version, not HEAD.

### Creating a Release

```bash
# Release the current VERSION as-is
bash release.sh

# Bump and release
bash release.sh patch   # 1.2.0 -> 1.2.1
bash release.sh minor   # 1.2.0 -> 1.3.0
bash release.sh major   # 1.2.0 -> 2.0.0
```

The release script:
1. Bumps `VERSION` (if a bump type is given)
2. Prompts for a changelog entry
3. Updates `CHANGELOG.md`
4. Updates `REPO_URL` in `install.sh` and `install-opencode.sh` to point to the new tag
5. Commits, tags, and pushes
6. Creates a GitHub release via `gh release create`

### How Install Scripts Work

Remote installs (`curl | bash`) pull from a pinned tag URL, e.g.:
```
https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v1.2.0/...
```

Local installs (`git clone` + `bash install.sh`) copy files from disk, so they always use whatever version is checked out.

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes to agent definitions, commands, or scripts
4. Test by running `bash install.sh` locally and using `/scrum-team` in a project
5. Submit a PR

When modifying agent definitions, keep in mind:
- Agents read `scrum-team-config.md` at boot — keep config references generic (use "the **X** path from the project config" rather than hardcoded paths)
- Planning/review agents should use `model: opus`, execution agents should use `model: sonnet`
- All agents must include the `<boot>` section that reads the project config

---

## License

MIT
