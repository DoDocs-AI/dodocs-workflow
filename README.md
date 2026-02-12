# dodocs-workflow

A Scrum Team workflow for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Spawns a **13-agent autonomous development team** that takes a feature from requirements gathering through architecture, implementation, code review, testing, and PR creation — with minimal human intervention.

```
/scrum-team add user billing dashboard
```

That single command launches the full team. You answer a few product questions, approve UX flows and architecture, then watch it build, review, test, and ship.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Installation](#installation)
- [Project Setup](#project-setup)
- [Usage](#usage)
- [Workflow Phases](#workflow-phases)
- [Team Roles](#team-roles)
- [Architecture](#architecture)
- [Project Config Reference](#project-config-reference)
- [Upgrade](#upgrade)
- [Uninstall](#uninstall)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## How It Works

dodocs-workflow is a set of **agent definitions** and a **slash command** for Claude Code. When you run `/scrum-team`, it orchestrates 13 specialized agents that collaborate through a shared task list, message passing, and a phased workflow:

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
           - QA Engineer writes test cases
           - Tech Lead runs compile gate + starts app
           - Manual Tester tests incrementally
           - QA Automation writes E2E tests incrementally
        |
        v
  Phase 6: Integration verification
           Full E2E suite, smoke test, final code review
        |
        v
  Phase 7: Tech Lead creates the PR
           Team lead reports summary to you
```

The key insight is **incremental parallelism** in Phase 5: testing starts as soon as the first task is code-reviewed, not after all development is done. Bugs are filed and fixed in real-time while other tasks continue.

---

## Installation

### Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and configured
- Git

### From a Local Clone (recommended)

```bash
git clone https://github.com/DoDocs-AI/dodocs-workflow.git
cd dodocs-workflow
bash install.sh
```

### One-Liner from GitHub

```bash
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/main/install.sh | bash
```

### What Gets Installed

The installer copies files to `~/.claude/` (Claude Code's global config directory):

| Destination | Files | Description |
|-------------|-------|-------------|
| `~/.claude/agents/` | 11 `.md` files | Agent role definitions |
| `~/.claude/commands/` | `scrum-team.md` | The `/scrum-team` slash command |
| `~/.claude/` | `scrum-team-config.template.md` | Config template for new projects |
| `~/.claude/` | `.dodocs-workflow-version` | Installed version tracker |

Nothing is installed into your project directories. Project-specific configuration is done separately (see below).

---

## Project Setup

Each project needs a **config file** that tells the agents about your tech stack, file paths, and commands.

### 1. Copy the Template

```bash
# From your project root
cp ~/.claude/scrum-team-config.template.md .claude/scrum-team-config.md
```

### 2. Fill In Your Project Values

Edit `.claude/scrum-team-config.md` with your project-specific settings. Every section matters — agents read this file before doing any work.

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

Open Claude Code in your project and type `/scrum-team test`. If the config is found, the workflow starts. If not, you'll get a clear error message telling you what's missing.

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

### Phase 5: Build + Incremental Test

**Agents**: ALL 13 agents in parallel

This is where the magic happens. All agents work simultaneously:

- **Developers** implement their assigned tasks and make atomic commits
- **Code reviewer** watches for completed tasks and reviews each one
- **QA engineer** writes test cases
- **Tech lead** runs compile gate, starts the app, monitors for issues
- **Manual tester** tests each feature area as soon as code-reviewer approves it
- **QA automation** writes E2E tests as each manual test scenario passes

The flow per task:
```
Developer completes task -> atomic commit
       |
       v
Code-reviewer reviews
       |
       +- Approve -> tech-lead verifies -> manual-tester tests
       |                                        |
       |                                 pass -> qa-automation writes E2E
       |                                 fail -> bug task -> developer fixes
       |
       +- Request changes -> developer fixes -> re-review
```

### Phase 6: Integration Verification

**Agents**: tech-lead, qa-automation, manual-tester, code-reviewer

After all individual tasks are complete:
- Tech lead does a full app restart and regression check
- QA automation runs the complete E2E test suite
- Manual tester does a final smoke test of the end-to-end flow
- Code reviewer does a full-diff review of all changes

### Phase 7: Ship

**Agents**: tech-lead

The tech lead creates a PR from the feature branch to main with a comprehensive description of all changes.

---

## Team Roles

The team uses 11 agent definitions that are instantiated into 13 running agents (frontend-dev and backend-dev are each used twice).

| Agent | Model | Phase | Role |
|-------|-------|-------|------|
| [product-owner](docs/agents/product-owner.md) | opus | 1 | Gathers requirements, produces Feature Brief |
| [ux-designer](docs/agents/ux-designer.md) | opus | 1-2 | Researches UI patterns, designs user flows |
| [architect](docs/agents/architect.md) | opus | 3 | Designs technical solution, produces Architecture doc |
| [scrum-master](docs/agents/scrum-master.md) | opus | 4 | Breaks architecture into tasks, assigns to team |
| [code-reviewer](docs/agents/code-reviewer.md) | opus | 5-6 | Reviews all code for quality, security, correctness |
| [tech-lead](docs/agents/tech-lead.md) | sonnet | 4-7 | Git, compile gate, app startup, bug filing, PR creation |
| [frontend-dev](docs/agents/frontend-dev.md) | sonnet | 5 | Implements frontend tasks (2 instances) |
| [backend-dev](docs/agents/backend-dev.md) | sonnet | 5 | Implements backend tasks (2 instances) |
| [qa-engineer](docs/agents/qa-engineer.md) | sonnet | 5 | Writes manual test case documents |
| [manual-tester](docs/agents/manual-tester.md) | sonnet | 5-6 | Tests features in browser via Playwright |
| [qa-automation](docs/agents/qa-automation.md) | sonnet | 5-6 | Writes Playwright E2E tests |

**Model strategy**: Planning and review roles use **opus** (higher reasoning capability). Execution roles use **sonnet** (faster, more cost-effective for code generation).

See the [docs/agents/](docs/agents/) directory for detailed documentation of each agent.

---

## Architecture

### File Layout

```
dodocs-workflow/
├── agents/                              # Agent definitions (installed to ~/.claude/agents/)
│   ├── architect.md
│   ├── backend-dev.md
│   ├── code-reviewer.md
│   ├── frontend-dev.md
│   ├── manual-tester.md
│   ├── product-owner.md
│   ├── qa-automation.md
│   ├── qa-engineer.md
│   ├── scrum-master.md
│   ├── tech-lead.md
│   └── ux-designer.md
├── commands/                            # Slash commands (installed to ~/.claude/commands/)
│   ├── scrum-team.md                    # Main /scrum-team command
│   └── dodocs-workflow.md               # Helper /dodocs-workflow command
├── docs/                                # Documentation
│   └── agents/                          # Per-agent documentation
├── templates/
│   └── scrum-team-config.template.md    # Per-project config template
├── install.sh                           # Install/upgrade script
├── uninstall.sh                         # Clean uninstall script
├── VERSION                              # Current version
└── README.md
```

### How Agents Communicate

Agents coordinate through three mechanisms:

1. **Shared Task List** — Tasks are created, assigned, blocked, and completed through Claude Code's task system. All agents see the same list.
2. **Direct Messages** — Agents send messages to specific teammates (e.g., code-reviewer notifies tech-lead after approving a task).
3. **Shared Files** — Feature Brief, UX Design, Architecture docs, and test cases are written to disk and read by downstream agents.

### Key Design Decisions

**Per-project config over convention**: Every project is different — different frameworks, different directory structures, different commands. Rather than guessing, agents read a config file that tells them exactly where things are.

**Migration ownership**: Database migrations are a common source of conflicts when multiple developers work in parallel. Only `backend-dev-1` creates migrations. `backend-dev-2` works on services and endpoints that depend on those migrations.

**Incremental testing**: Traditional workflows wait for all development to finish before testing. This workflow starts testing as soon as the first code-reviewed task is ready, catching bugs earlier and keeping developers busy with fixes while other tasks continue.

**Atomic commits**: Each completed task = one commit. This makes code review easier, git history cleaner, and rollbacks possible at the task level.

---

## Project Config Reference

The `.claude/scrum-team-config.md` file is the single source of truth that all agents read. Every section is required.

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

See the [template file](templates/scrum-team-config.template.md) for the full structure with examples.

---

## Upgrade

### From a Local Clone

```bash
cd dodocs-workflow
git pull
bash install.sh
```

The installer detects the existing installation and shows `Upgraded: v1.0.0 -> v1.1.0`.

### From GitHub

```bash
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/main/install.sh | bash
```

### Check Current Version

The installed version is stored in `~/.claude/.dodocs-workflow-version`.

---

## Uninstall

```bash
# From the repo directory
bash uninstall.sh

# Or directly
bash ~/path/to/dodocs-workflow/uninstall.sh
```

This removes:
- All 11 agent definitions from `~/.claude/agents/`
- The `/scrum-team` command from `~/.claude/commands/`
- The config template from `~/.claude/`
- The version file

Project-specific `.claude/scrum-team-config.md` files are **not** removed.

---

## Troubleshooting

### "No scrum-team config found for this project"

You need to create `.claude/scrum-team-config.md` in your project. See [Project Setup](#project-setup).

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
