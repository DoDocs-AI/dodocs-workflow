# dodocs-workflow Features

> v1.7.0 | Autonomous Scrum Team + Product Lifecycle Framework for Claude Code & OpenCode

dodocs-workflow turns a one-line feature description into a production-ready pull request. It orchestrates up to 13 specialized AI agents that follow a real scrum process — requirements, UX design, architecture, implementation, code review, manual testing, E2E automation, and PR creation. The Product Lifecycle (PLC) framework extends this with 20+ agents across 6 phases taking any product from concept to profitable business.

---

## Table of Contents

- [Core Workflows](#core-workflows)
  - [Scrum Team](#1-scrum-team)
  - [Container Team](#2-container-team)
  - [Prepare for Production](#3-prepare-for-production)
  - [Batch Features](#4-batch-features)
  - [Change Request](#5-change-request)
  - [Fix the Issue](#6-fix-the-issue)
  - [Brainstorm](#7-brainstorm)
  - [Prepare Feature](#8-prepare-feature)
  - [Merge Features](#9-merge-features)
  - [Rebase](#10-rebase)
  - [Product Lifecycle](#11-product-lifecycle)
  - [Product Launch](#12-product-launch)
  - [GTM Team](#13-gtm-team)
- [Agent Roster](#agent-roster)
  - [Scrum Team Agents](#scrum-team-agents-13)
  - [PLC Scrum Team Agents](#plc-scrum-team-agents-13)
  - [PLC Strategy & Discovery Agents](#plc-strategy--discovery-agents-19)
  - [Production Audit Agents](#production-audit-agents-10)
  - [GTM Agents](#gtm-agents-16)
  - [Specialized Agents](#specialized-agents)
- [Workflow Phases](#workflow-phases)
- [Architecture Highlights](#architecture-highlights)
- [Per-Project Configuration](#per-project-configuration)
- [Installation & Upgrade](#installation--upgrade)

---

## Core Workflows

### 1. Scrum Team

**Command**: `/scrum-team <feature-description>`

The flagship workflow. A single command spawns a 13-agent development team that builds, reviews, tests, and ships an entire feature.

**What it does**:
- Product Owner interviews you about the feature and writes a Feature Brief
- UX Designer researches existing UI patterns and produces user flow designs
- Architect designs the technical solution (endpoints, entities, components, API contracts)
- Scrum Master breaks the architecture into tasks with dependencies
- 4 Developers implement in parallel with atomic commits per task
- Code Reviewer reviews every task for quality, security, and correctness
- QA Engineer writes manual test cases organized by user story
- Tech Lead manages the git branch, runs compile gates, starts the app
- Manual Tester tests each user story in the browser via Playwright
- QA Automation writes E2E Playwright tests per passing user story
- Tech Lead creates the final PR

**Flags**:
| Flag | Effect |
|------|--------|
| `--auto` | Autonomous mode — skips human approval checkpoints |
| `--size small` | Fewer agents for simple features (button, color change) |
| `--size medium` | Standard team for API/endpoint work |
| `--size large` | Full 13-agent team (default for complex features) |
| `--retest <name>` | Skip requirements/design, jump to testing with 5 agents |

**Human checkpoints** (skipped in `--auto` mode):
1. Approve UX flows after Phase 2
2. Approve architecture after Phase 3

**Output**: Feature branch with atomic commits, all docs in `docs/features/<feature>/`, and an open PR.

---

### 2. Container Team

**Command**: `/container-team <feature-description>`

Runs the full scrum-team workflow inside an isolated Docker container, freeing your main Claude Code session for other work.

**What it does**:
- Builds a Docker image with Node.js, git, gh CLI, and Claude Code CLI
- Mounts your project directory into the container
- Launches the 13-agent scrum team inside the container
- Displays a live monitoring dashboard with phase progress and recent logs
- Agents write code directly to your mounted project directory

**Flags**:
| Flag | Effect |
|------|--------|
| `--detach` | Launch in background without the monitoring loop |
| `--attach <id>` | Re-attach to a running container |
| `--status` | List all running container teams |
| `--k8s` | Run on Kubernetes instead of Docker |

**Use case**: Run multiple features in parallel, each in its own container, while you continue using Claude Code for other tasks.

---

### 3. Prepare for Production

**Command**: `/prepare-for-production`

Audits the entire codebase for production readiness across 10 dimensions using 10 specialized agents running in parallel.

**What it does**:
- **Phase 1 — Audit**: 10 auditors run simultaneously, each producing a report
- **Phase 2 — Triage**: Consolidates findings, deduplicates, classifies by severity
- **Phase 3 — Fix**: Developers fix Critical/High issues, code-reviewer reviews
- **Phase 4 — Re-audit**: Re-runs failed auditors, produces final SUMMARY.md

**Audit dimensions**:
| Auditor | Checks |
|---------|--------|
| Security | OWASP top 10, auth coverage, hardcoded secrets, dependency CVEs |
| Performance | N+1 queries, missing indexes, bundle size, caching |
| Accessibility | WCAG 2.1 AA, keyboard nav, ARIA, color contrast |
| SEO | Meta tags, Open Graph, sitemap, robots.txt, structured data |
| DevOps | Dockerfile, docker-compose, health checks, CI/CD |
| Error Handling | Error responses, error boundaries, logging coverage |
| Dependencies | npm audit, Maven checks, outdated packages, licenses |
| API Docs | OpenAPI spec, endpoint inventory, API reference |
| Database | Schema, indexes, constraints, migration hygiene |
| Load Testing | Load test scenarios, capacity estimates, breaking points |

**Selective mode**: `/prepare-for-production --only security,performance,db`

**Pass criteria**: Zero Critical, zero High findings remaining.

---

### 4. Batch Features

**Command**: `/batch-features --features "feat-a, feat-b, feat-c"`

Processes multiple features autonomously, one after another or in parallel.

**What it does**:
- Accepts a comma-separated feature list or a backlog file (`--file docs/backlog.md`)
- Supports dependency annotations: `feature-name[depends-on: dep-a, dep-b]`
- DAG-aware scheduling — respects dependency order
- Runs full scrum-team per feature
- Reports progress across the batch

**Flags**:
| Flag | Effect |
|------|--------|
| `--features "a, b, c"` | Inline feature list |
| `--file <path>` | Read features from a markdown file |
| `--parallel` | DAG-aware parallel execution |
| `--size small\|medium\|large` | Team size for all features |

---

### 5. Change Request

**Command**: `/change-request <area-slug>`

Makes targeted changes to an existing feature area without rebuilding everything from scratch.

**What it does**:
- Reads existing baseline docs (FEATURE-BRIEF.md, ARCHITECTURE.md, UX-DESIGN.md) as immutable context
- Captures your change description through interactive questioning
- Produces a CHANGE-REQUEST.md and delta architecture/UX docs
- Spawns the full team with per-phase overrides scoped to the change

**Use case**: "Add a filter dropdown to the existing invoices page" — the team understands the existing feature and only builds the delta.

---

### 6. Fix the Issue

**Command**: `/fix-the-issue <description>`

Lightweight 5-agent workflow for bug fixes and small issues.

**What it does**:
- Tech Lead investigates the root cause, creates FIX-PLAN.md
- Frontend and backend developers implement the fix in parallel
- Code Reviewer reviews the changes
- Manual Tester verifies the fix in the browser
- Creates a `fix/<name>` branch and ships a PR via squash-merge

**Agents**: tech-lead, code-reviewer, manual-tester, frontend-dev, backend-dev

**Use case**: Bug reports, regressions, and small improvements that don't need full scrum ceremony.

---

### 7. Brainstorm

**Command**: `/brainstorm <feature-idea>`

AI-driven feature idea stress-testing — research the market, challenge the idea through adversarial questioning, and produce a Feature Requirements Document.

**What it does**:
- Performs 5-6 web searches to research the competitive landscape
- Asks you tough questions across 5+ areas (user need, technical feasibility, scope, edge cases, alternatives)
- Produces a structured FRD.md with validated requirements

**Output**: `docs/brainstorm/<feature-name>/FRD.md`

**No project config required** — works as a standalone discovery tool.

---

### 8. Prepare Feature

**Command**: `/prepare-feature <feature-name>`

Daytime preparation pipeline: interactive requirements gathering, framework-native mockups, and validation — without building anything.

**What it does**:
- Product Owner gathers requirements and writes FEATURE-BRIEF.md
- Mockup Designer creates framework-native UI components using your real design system
- Mockup Validator cross-checks mockups against the Feature Brief
- You approve the outputs

**Output**: FEATURE-BRIEF.md, mockup components in `docs/features/<feature>/mockups/`, MOCKUP-VALIDATION.md

**Use case**: Prepare features during the day (interactive), then batch-run `/scrum-team` overnight in `--auto` mode.

---

### 9. Merge Features

**Command**: `/merge-features`

Merges all open `feature/*` pull requests into main in creation order, with CI gating and automatic conflict resolution.

**What it does**:
- Lists all open `feature/*` PRs targeting main
- Checks CI status for each PR
- Squash-merges PRs that pass CI
- Auto-rebases PRs with conflicts (spawns a tech-lead agent for complex rebases)
- Re-checks remaining PRs after each merge (since main advanced)
- Produces a summary report

**Flags**:
| Flag | Effect |
|------|--------|
| `--dry-run` | Show what would happen without merging |
| `--only 42,38` | Merge only specific PR numbers |
| `--skip-ci` | Merge even if CI is pending or failing |

---

### 10. Rebase

**Command**: `/rebase`

Rebases the current feature/fix branch on top of `main` with migration ordering validation.

**What it does**:
- Fetches latest main
- Rebases current branch onto main
- Validates that database migrations remain properly ordered after rebase
- Reports any conflicts for manual resolution

---

### 11. Product Lifecycle

**Command**: `/product-lifecycle <product-name>`

Full-cycle product lifecycle pipeline — 20+ agents across 6 phases taking a product from raw concept to profitable, self-evolving business.

**Phases**:
| Phase | What Happens | Key Agents |
|-------|-------------|------------|
| Discover | Market research, ICP profiling, demand validation | plc-market-scout, plc-icp-profiler, plc-validation-agent |
| Strategy | Product strategy, roadmap, pricing, MVP scoping | plc-product-strategist, plc-roadmap-planner, plc-pricing-architect, plc-mvp-scoper |
| Build | Full development via plc-scrum-team (13-agent pipeline) | plc-product-owner, plc-architect, plc-scrum-master, plc-frontend-dev, plc-backend-dev, plc-code-reviewer, plc-tech-lead, plc-qa-engineer, plc-manual-tester, plc-qa-automation, plc-ux-designer, plc-mockup-designer, plc-mockup-validator |
| Launch | Analytics setup, copywriting, distribution, monetization | plc-analytics-agent, plc-copy-agent, plc-distribution-agent, plc-revenue-agent |
| Grow | Growth experiments, retention, SEO content | plc-growth-hacker, plc-retention-engineer, plc-seo-content-agent |
| Evolve | Feature invention, competitive intel, customer feedback | plc-feature-inventor, plc-competitive-intel, plc-customer-voice |

**Phase gates**: Enforced between each phase — criteria must be met and logged before advancing. Gate check reports written to `docs/plc/<slug>/gates/`.

**Flags**:
| Flag | Effect |
|------|--------|
| `--auto` | Skip human approval gates |
| `--skip-discover` | Jump past discovery phase |
| `--skip-build` | Skip build phase |
| `--resume` | Resume from existing PLC-STATE.md |

---

### 12. Product Launch

**Command**: `/product-launch <product-name>`

15+ agents across 10 phases — from idea validation through MVP build to launch.

---

### 13. GTM Team

**Command**: `/gtm-team <product-name>`

16 agents across 6 phases producing a complete Go-To-Market strategy.

---

## Agent Roster

### Scrum Team Agents (13)

| Agent | Model | Role |
|-------|-------|------|
| Product Owner | Opus | Requirements gathering, Feature Brief |
| UX Designer | Sonnet | UI pattern research, user flow design |
| Architect | Opus | Technical solution design |
| Scrum Master | Opus | Task breakdown, dependency mapping, assignment |
| Tech Lead | Sonnet | Git, compile gates, app startup, bug filing, PR creation |
| Code Reviewer | Opus | Quality, security, correctness review |
| Frontend Dev x2 | Sonnet | Frontend implementation, atomic commits |
| Backend Dev x2 | Sonnet | Backend implementation, migrations (dev-1 only) |
| QA Engineer | Sonnet | Manual test case documentation |
| Manual Tester | Haiku | Browser-based testing via Playwright |
| QA Automation | Sonnet | E2E Playwright test generation |

### Production Audit Agents (10)

| Agent | Model | Domain |
|-------|-------|--------|
| Security Auditor | Opus | OWASP, auth, secrets, CVEs |
| Performance Engineer | Opus | N+1, indexes, bundle size, caching |
| Accessibility Auditor | Sonnet | WCAG 2.1 AA, keyboard, ARIA, contrast |
| SEO Analyst | Sonnet | Meta tags, OG, sitemap, structured data |
| DevOps Engineer | Sonnet | Docker, CI/CD, health checks, env config |
| Error Handler | Sonnet | Error responses, boundaries, logging |
| Dependency Auditor | Sonnet | npm audit, Maven, outdated packages, licenses |
| API Documenter | Sonnet | OpenAPI spec, endpoint inventory |
| DB Analyst | Opus | Schema, indexes, constraints, migrations |
| Load Tester | Sonnet | Load scenarios, capacity, breaking points |

### Specialized Agents

| Agent | Model | Used By |
|-------|-------|---------|
| Mockup Designer | Sonnet | `/prepare-feature` — creates framework-native UI mockups |
| Mockup Validator | Sonnet | `/prepare-feature` — validates mockups against requirements |
| Brainstorm Facilitator | Opus | `/brainstorm` — adversarial feature idea testing |
| Feature Manager | Sonnet | `/batch-features` — DAG-aware batch scheduling |

### PLC Scrum Team Agents (13)

MVP-focused copies of the scrum team agents, optimized for PLC Build phase. Always autonomous, core-flow only.

| Agent | Model | PLC Differences |
|-------|-------|----------------|
| PLC Product Owner | Opus | Auto-mode only, reads MVP-SCOPE.md |
| PLC UX Designer | Sonnet | Simplified MVP UX, core flow only |
| PLC Architect | Opus | Reads PLC strategy docs, MVP-minimal |
| PLC Scrum Master | Sonnet | Smaller task breakdown for Must-Have items |
| PLC Frontend Dev | Sonnet | MVP-focused, skip non-essential polish |
| PLC Backend Dev | Sonnet | MVP-focused, minimal endpoints |
| PLC Code Reviewer | Sonnet | Lighter review, correctness only |
| PLC Tech Lead | Sonnet | Writes BUILD-SUMMARY.md on completion |
| PLC QA Engineer | Sonnet | Core flow test cases only |
| PLC QA Automation | Sonnet | E2E for core flow only |
| PLC Manual Tester | Haiku | Tests "Mom Test" scenario |
| PLC Mockup Designer | Sonnet | Simplified MVP mockups |
| PLC Mockup Validator | Sonnet | Validates against MVP-SCOPE.md |

### PLC Strategy & Discovery Agents (19)

| Agent | Model | Phase | Role |
|-------|-------|-------|------|
| PLC Orchestrator | Opus | All | Meta-orchestrator coordinating all PLC agents |
| PLC Market Scout | Sonnet | Discover | Competitive landscape and opportunity scanning |
| PLC ICP Profiler | Sonnet | Discover | Ideal customer profile definition |
| PLC Validation Agent | Sonnet | Discover | Demand testing with real prospects |
| PLC Product Strategist | Opus | Strategy | Strategy brief creation |
| PLC Roadmap Planner | Sonnet | Strategy | NOW/NEXT/LATER roadmap |
| PLC Pricing Architect | Opus | Strategy | Pricing model design |
| PLC MVP Scoper | Opus | Strategy | MoSCoW classification, core flow, "Mom Test" |
| PLC Architect Agent | Opus | Build | Stack selection, data models, API contracts |
| PLC Dev Agent | Sonnet | Build | Standalone development (manual use) |
| PLC QA Agent | Sonnet | Build | Standalone QA (manual use) |
| PLC Analytics Agent | Sonnet | Launch | Analytics tool setup, event tracking, funnels |
| PLC Copy Agent | Sonnet | Launch | Landing page copywriting |
| PLC Distribution Agent | Sonnet | Launch | Channel distribution strategy |
| PLC Revenue Agent | Sonnet | Launch | Monetization setup |
| PLC Growth Hacker | Sonnet | Grow | Growth experiments and optimization |
| PLC Retention Engineer | Sonnet | Grow | Churn reduction, engagement loops |
| PLC SEO Content Agent | Sonnet | Grow | SEO content strategy |
| PLC Feature Inventor | Sonnet | Evolve | Feature discovery from feedback |
| PLC Competitive Intel | Sonnet | Evolve | Competitive monitoring |
| PLC Customer Voice | Sonnet | Evolve | Customer feedback analysis |

### GTM Agents (16)

| Agent | Model | Role |
|-------|-------|------|
| GTM Community | Sonnet | Community engagement strategies |
| GTM Copywriter | Sonnet | B2B SaaS copywriting |
| GTM CRM | Sonnet | CRM pipeline design |
| GTM Experiment | Sonnet | A/B test design and optimization |
| GTM ICP Discovery | Sonnet | Prospect profiling and scoring |
| GTM Lead Scoring | Sonnet | Lead scoring models |
| GTM Localization | Sonnet | Market-specific content adaptation |
| GTM Market Research | Sonnet | Competitive intelligence |
| GTM Metrics | Sonnet | KPI dashboards and analytics |
| GTM Outbound | Sonnet | Outbound sales sequences |
| GTM Paid Ads | Sonnet | Paid advertising campaigns |
| GTM Proposal | Sonnet | Sales proposal templates |
| GTM Reporting | Sonnet | GTM performance reporting |
| GTM SEO Content | Sonnet | SEO keyword research and content |
| GTM Trend Monitor | Sonnet | Industry trend monitoring |
| GTM Strategist | Opus | GTM strategy orchestration |

---

## Workflow Phases

The full `/scrum-team` workflow runs through 7 phases:

```
Phase 1: Requirements + UX Research          [parallel]
  Product Owner writes FEATURE-BRIEF.md
  UX Designer researches existing UI patterns

Phase 2: UX Design + Mockups                 [parallel]
  UX Designer produces UX-DESIGN.md
  Architect designs ARCHITECTURE.md
  Mockup Designer creates components
  Mockup Validator validates against brief
  >>> HUMAN CHECKPOINT: approve UX + architecture

Phase 3: Task Breakdown
  Scrum Master creates tasks with dependencies
  Tech Lead creates feature branch

Phase 4: Build + Test                        [all parallel]
  4 Developers implement tasks (atomic commits)
  Code Reviewer reviews each completed task
  QA Engineer writes test cases per user story
  Tech Lead runs compile gate + starts app
  Manual Tester tests story by story (after review + test cases ready)
  QA Automation writes E2E per passing story
  Bugs: filed -> fixed -> reviewed -> retested (loop)

Phase 5: Integration Verification
  Full app restart + regression check
  Complete E2E suite run
  Final smoke test
  Full-diff code review

Phase 6: Ship
  Tech Lead creates PR to main
  Team lead reports summary
```

---

## Architecture Highlights

**Project-agnostic**: Works with any tech stack — Quarkus+React, Spring Boot+Vue, Express+Angular, Django+Next.js, etc. All project specifics come from a single config file.

**Migration ownership**: Only `backend-dev-1` creates database migrations. `backend-dev-2` tasks that depend on migrations are blocked until dev-1 completes. This prevents migration conflicts.

**Story-level testing**: Manual testing starts per user story as soon as that story's tasks are reviewed and test cases are ready — not after all development is done. Development and testing run in parallel at story granularity.

**Atomic commits**: One commit per completed task. Cleaner history, easier reviews, task-level rollbacks.

**Model strategy**: Planning and review roles (Product Owner, Architect, Code Reviewer, Scrum Master) use Opus for higher reasoning capability. Execution roles (developers, tech lead, QA) use Sonnet for speed and cost efficiency. Manual Tester uses Haiku for frequent browser interactions.

**Communication**: Agents coordinate via shared task lists, direct messages, shared files on disk (Feature Brief, Architecture, test cases), and a real-time PROGRESS.md dashboard.

**Docker isolation**: `/container-team` runs the entire team in a Docker container with the project directory mounted, letting you use Claude Code for other work while the team builds.

---

## Per-Project Configuration

Each project needs a `.claude/scrum-team-config.md` file (or `.opencode/scrum-team-config.md` for OpenCode) that tells agents about:

| Section | What agents learn |
|---------|-------------------|
| App Identity | App name and description |
| Tech Stack | Backend/frontend frameworks, DB, migration tool, auth, build tool, API pattern |
| Ports & URLs | Frontend port, backend port, dev domain |
| Source Paths — Backend | Controllers, entities, services, DTOs, migrations, tests |
| Source Paths — Frontend | Pages, components, services, types, router, mockup schema |
| Source Paths — Testing | Test cases, feature docs, E2E tests, fixtures, page objects, Playwright config |
| Commands | How to start DB, storage, backend, frontend; how to compile |
| Routing | Route prefix (e.g., `/workspace`) |
| Testing | Playwright session name, flags |
| Test Environment | Docker Compose file, service names, ports, Dockerfiles (for Docker Isolation) |
| Remote Testing | Remote dev URL, tenant registration/admin URLs (optional) |

A template is provided at install: `~/.claude/scrum-team-config.template.md`

---

## Installation & Upgrade

**Install** (Claude Code):
```bash
git clone https://github.com/DoDocs-AI/dodocs-workflow.git
cd dodocs-workflow && bash install.sh
```

**Install** (OpenCode):
```bash
git clone https://github.com/DoDocs-AI/dodocs-workflow.git
cd dodocs-workflow && bash install-opencode.sh
```

**Upgrade**: `/dodocs-workflow upgrade`

**Check version**: `/dodocs-workflow version`

**What gets installed** (to `~/.claude/` or `~/.opencode/`):
- 76 agent definitions in `agents/` (Claude Code) / 21 in `agents/` (OpenCode)
- 21 slash commands in `commands/` (Claude Code) / 5 in `commands/` (OpenCode)
- Docker runtime files in `docker/`
- Config template
- Status line script with auto-update notifications
