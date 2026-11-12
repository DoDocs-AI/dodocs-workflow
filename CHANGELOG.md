# Changelog

All notable changes to dodocs-workflow will be documented in this file.

## [Unreleased]

feat(control): guard usability

- "Command cannot be read" is its own approval category, `unreadable` (rule id
  `control-unreadable` unchanged), no longer `control`: it can be approved once, with
  `dw approve`, or for the rest of the run ("Approve unreadable commands for this run"), which
  turns the guard's fail-closed reading off for that run. When the same command also matches
  another category, that category decides the question, and an unreadable approval never lets
  it through.

## [v2.1.0] - 2026-11-12

feat(control): control point — `/control` and the `dw` command

- `/control` command: one session that starts runs in all registered projects as
  background AGTerm sessions, reports status, and passes approvals; it never does a
  project's work.
- `dw` CLI (`control/`): project registry, runs with limits (1 per project, 3 in total),
  status, approvals, `dw setup`, `dw doctor`, `dw project import-legacy`.
- Approval guard: a global Claude Code `PreToolUse` entry, active only where a run is
  active. It is not a sandbox; see docs/explanation-control-point.md for what it does not
  protect against.
- Manual acceptance run on a real terminal changed how the guard and the runs behave: the
  approval question now opens (one line, the guarded action first, long commands trimmed with
  a visible marker); one approval covers the guarded part of a plain command sequence in its
  directory, so "commit, then push" and a later plain push are the same action; `dw` creates
  the run's result note up front and the guard spares only plain writes to it; `dw resume`
  tells the agent to continue; zsh command words (`repeat`, `noglob`, ...) are looked through;
  `dw run` refuses a guard entry that does not cover every tool or does not execute. Remaining
  limits are listed in docs/explanation-control-point.md.
- `install.sh` installs `dw` to `~/.dodocs-workflow/` with an absolute python3 (3.9+)
  shebang and never runs `dw setup`; `uninstall.sh` runs `dw setup --remove --yes` first
  and keeps `registry.json`, `runs/` and `dw.log`.

## [v2.0.1] - 2026-09-09

chore: MIT LICENSE + scrum team pipeline diagram

The repository now carries the MIT license text it has always declared in the
README, so the terms are actually granted and GitHub can detect the license.

- LICENSE: standard MIT text, Copyright (c) 2026 DoDocs-AI
- README: License section links the file
- docs/scrum-team-pipeline.html: a single-page scheme of the /scrum-team
  workflow — artifact-chain flow diagram, the six phase bands with their
  agents and gates, the Phase 4 story loop, size matrix, the ten Definition
  of Done checks, and retest mode

No agent, command, or install behavior changes.

## [v2.0.0] - 2026-07-27

feat!: spec-driven requirements — the pipeline is now built on OpenSpec (BREAKING)

The requirements layer is restructured around OpenSpec (@fission-ai/openspec, pinned
1.6.0). Every feature is now an OpenSpec change — openspec/changes/<slug>/ with
proposal.md, validated delta specs, design.md, and tasks.md — and shipping archives
the deltas into living per-capability specs at openspec/specs/, giving every project
a canonical, always-current description of system behavior.

### Breaking
- product-owner writes proposal.md + delta specs (strict CLI validation) instead of
  FEATURE-BRIEF.md; architect writes design.md instead of ARCHITECTURE.md;
  scrum-master writes tasks.md as the canonical checklist
- /change-request captures requests as delta changes against the living specs;
  the per-feature CHANGELOG.md is retired (the change archive is the audit trail)
- /scrum-team, /prepare-feature(s), /batch-features, /change-request, /ship STOP on
  projects without openspec/ and point to the migration path
- Requires Node.js >= 20 (for the pinned openspec CLI via npx)

### Migration
- Existing projects: run /spec-bootstrap once — it derives openspec/specs/ from your
  legacy FEATURE-BRIEFs (kept untouched as read-only history) and seeds change
  proposals for in-flight features
- New projects: dodocs-workflow init now scaffolds openspec/ automatically
- Staying on v1: curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v1.17.0/install.sh | bash

### Added
- Post-merge archiving in /ship and /merge-features (never on feature branches)
- /brainstorm FRD handoff into /prepare-feature; /wiki ingests openspec/specs and
  changes; doc-sync-agent treats openspec/specs/ as behavioral truth
- OpenCode mirror fully ported; FEATURE-BRIEF containment lint in CI
- Requirements quality loop (UX + business critics + enricher) now scores OpenSpec
  changes directly, with openspec validate --strict as a mechanical gate

### Deferred
- PLC and GTM pipelines stay on the legacy artifact model for now

## [v1.17.0] - 2026-07-27

feat: OpenSpec foundations — Phase 0 of the spec-driven requirements migration (inert, no pipeline behavior change)

dodocs-workflow is migrating its requirements layer to OpenSpec (@fission-ai/openspec,
pinned 1.6.0): living per-capability specs in openspec/specs/ and validated change
proposals in openspec/changes/. This release ships the tooling ahead of the v2 cutover
so projects can migrate at their own pace — the FEATURE-BRIEF pipeline is unchanged.

### Added
- claude/templates/openspec-conventions.md — single source of truth for agents:
  directory split rule, artifact formats, pinned CLI usage, validation gates
  (installed to ~/.claude/openspec-conventions.md)
- /spec-bootstrap command + spec-bootstrapper agent — one-time migration that derives
  openspec/specs/ living specs from existing FEATURE-BRIEFs and the codebase, and
  seeds openspec/changes/ proposals for in-flight features
- scrum-team config template: new "OpenSpec" section (CLI pin, root, spec domains)
- dodocs-workflow init: doctor checks (Node >= 20, pinned CLI) + non-interactive
  "openspec init --tools none" scaffolding; new "doctor" subcommand
- docker/agent-env.Dockerfile pre-installs @fission-ai/openspec@1.6.0
- tests/validate-openspec.sh — pin consistency + fixture validate/archive loop
  against the real pinned CLI (hard-required in CI, warn-only offline)
- tests/validate-install.sh — temp-HOME install/uninstall smoke test + array parity

### Fixed
- uninstall.sh was missing 62 agents and 22 commands vs install.sh — now fully synced
- tests/validate-docs.sh count-drift grep matched incidental prose and never caught
  real drift — now anchored to "N agent definitions" / "N slash commands"
- release.sh: BSD awk multiline -v failure and blank-line-terminated stdin made
  multi-paragraph changelog entries impossible to pipe

## [v1.16.0] - 2026-07-14

feat: /change-request now updates the existing feature in place, with a product decision gate

`/change-request <area-slug>` previously created a brand-new sibling folder
(`docs/features/<area-slug>-<change>/`) with a fresh delta FEATURE-BRIEF.md and treated the
original feature docs as read-only. It now updates the **existing** feature's docs, code, and
tests in place, and asks product to decide first whether the request is a change or a new feature.

### Added
- **Product decision gate (Phase 4)** — `product-owner` runs in CLASSIFICATION MODE to judge
  the request as `CHANGE` vs `NEW_FEATURE` and returns a verdict + reasoning. The user confirms;
  if it's really a new feature, `/change-request` hands off to `/scrum-team` and leaves the
  existing feature untouched.
- **CHANGELOG.md per feature** — each change appends a dated entry to
  `docs/features/<area-slug>/CHANGELOG.md` as the audit trail.

### Changed
- `product-owner` CHANGE-UPDATE MODE edits `FEATURE-BRIEF.md` in place (targeted edits, no rewrite)
  instead of writing a separate delta brief.
- Phase 7 runs the scrum-team against the existing `docs/features/<area-slug>/` folder with
  overrides so `architect`/`ux-designer` edit `ARCHITECTURE.md`/`UX-DESIGN.md` in place and the
  devs/QA modify the existing feature's code and tests. Branch is `feature/<area-slug>-<change-slug>`.
- Removed the old `<CR_SLUG>` sibling-folder / `CHANGE-REQUEST.md` / delta-docs model.
- Mirrored the rework to the OpenCode copy; updated `docs/FEATURES.md` Change Request section.

## [v1.15.0] - 2026-06-25

feat: add requirements quality agentic loop (UX + business critics)

Adds a critic + auto-refine loop over requirements docs, modeled on the existing
mockup-validator pattern.

### Added
- **`ux-requirements-critic`** (Opus) — scores a FEATURE-BRIEF.md/FRD.md on 6 UX-requirement
  dimensions and writes `REQ-UX-REVIEW.md` with a 1–5 matrix, weighted average, and PASS/FAIL.
- **`business-requirements-critic`** (Opus) — scores the same doc on 6 business dimensions and
  writes `REQ-BUSINESS-REVIEW.md`.
- **`requirements-enricher`** (Opus) — non-interactive rewrite that resolves every Critical and
  High finding from both critics, recording inferred decisions under an `## Assumptions` section.

### Changed
- `/prepare-feature` gains **Phase D1.5**, running before any mockup work.
- `/brainstorm` runs the loop over the FRD after it is produced.
- Loop shape in both: score (both critics in parallel) → gate → enrich, max 3×, then a human gate.
  Writes `REQUIREMENTS-VALIDATION.md` with before→after scores.
- `install.sh` agent count updated to 88.

## [v1.14.1] - 2026-04-08

fix: extend /wiki ingest to support any docs/ path, not just features/

The `/wiki ingest` command now accepts any documentation path under `docs/`, not just
`docs/features/<slug>/`. This enables ingesting PLC phase outputs, architecture docs,
API references, or any other structured documentation directory.

### Changed
- `/wiki ingest <doc-path>` — `<doc-path>` is now relative to `docs/` (e.g. `plc/my-project`, `api`, `features/my-feature`)
- Backward compatible: bare slug with no `/` still falls back to `docs/features/<slug>/`
- Entry slug derived from full path with `/` → `-` (e.g. `plc/my-project` → `docs/wiki/plc-my-project.md`)
- `/wiki coverage` now scans all `docs/` subdirectories (not just `docs/features/`) for undocumented content
- `wiki-maintainer` agent updated: flexible discovery adapts to any doc structure (feature, PLC, README-only, etc.)
- Wiki entry frontmatter uses generic `slug:` field (backward-compat: `feature:` still accepted by lint)
- Sections in wiki entries are now optional — only included when relevant content exists in source

## [v1.14.0] - 2026-04-07

feat: add /wiki command and wiki-maintainer agent — compiled knowledge layer at docs/wiki/

Adds `/wiki` command with four sub-commands:
- `init` — bootstraps `docs/wiki/` with README.md, COVERAGE.md, and _template.md
- `ingest <slug>` — synthesizes a feature's docs into a concise wiki entry at `docs/wiki/<slug>.md`
- `coverage` — reports which features have/haven't been ingested (runs bash directly, no agent)
- `lint` — validates all wiki entries for consistency and completeness, writes LINT-REPORT.md

Companion `wiki-maintainer` agent handles all three write tasks (init/ingest/lint) with
full Read/Write/Edit/Bash/Grep/Glob access. Non-destructive: never modifies `docs/features/`
or `docs/e2e-testcases/`.

## [v1.13.1] - 2026-04-05

feat: add OpenHands handoff message to prepare-feature; add SKIP_PREP artifact detection to scrum-team

## [v1.5.20] - 2026-02-27

feat: /change-request command — targeted changes to existing feature areas

Adds /change-request <area-slug> command to both Claude Code and OpenCode installs.
The command reads an existing feature area's docs as immutable baseline, captures
a change description from the user, derives a CR slug, spawns product-owner in
change mode to produce CHANGE-REQUEST.md and a delta FEATURE-BRIEF.md, then
optionally launches the full scrum-team with per-phase overrides that inject
baseline context so architects and UX designers produce delta docs, not full redesigns.

## [v1.5.16] - 2026-02-25

- feat: create feature branch at boot (Step 3) before any agent spawns — all docs land on feature branch from the start
- feat: add Mockup Component Schema and Mockup Preview Port fields to scrum-team-config template
- feat: mockup-designer reads component schema from config as authoritative reference for available UI components
- feat: scrum-team starts Vite mockup preview server before user checkpoint and shows preview URL
- feat: Phase 4 orchestrator prints periodic progress bar report after each agent idle notification
- fix: Phase 3 no longer spawns tech-lead — only scrum-master needed for task breakdown

## [v1.5.15] - 2026-02-25

- feat: add AppIntegrationView to mockup pipeline — full app shell with feature wired into navigation, shown as default screen in mockup hub

## [v1.5.14] - 2026-02-25

- feat: expand frontend-dev agent with full mockup-driven implementation workflow (5-step process, mockup→production translation table, state machine patterns)

## [v1.5.13] - 2026-02-25

- feat: move mockups to docs/features/<slug>/mockups/ and add standalone Vite dev server per feature (no router integration)

## [v1.5.10] - 2026-02-23

- fix: batch-features and feature-manager now correctly run the full scrum-team workflow by reading ~/.claude/commands/scrum-team.md directly (sub-agents spawned via Task tool do not inherit the parent session's skill system, so /scrum-team shorthand was never executed)
- fix: add bypassPermissions mode to sub-agent spawns in batch-features and feature-manager

## [v1.5.9] - 2026-02-23

- feat: add research phase to product-owner and architect agents (read SPECIFICATION.md, related briefs/arch docs, and sample source files before producing output)
- feat: feature-manager auto-discover mode (Phase 0 builds FEATURES array from docs/features/ when no explicit list provided)
- feat: batch-features no-args support triggers auto-discover mode

## [v1.5.8] - 2026-02-23

- feat: feature-manager agent for parallel batch execution with DAG scheduling, retry logic, stall detection, and completeness verification
- feat: batch-features parallel mode delegates to feature-manager agent; sequential mode properly invokes /scrum-team --auto via Task
- feat: add brainstorm command and brainstorm-facilitator agent

## [v1.5.6] - 2026-02-21

- fix: include /rebase command in install.sh

## [v1.5.5] - 2026-02-21

- tech-lead now rebases on main and validates migrations (naming convention + sequential order) before creating a PR
- Add /rebase command: manual rebase on main with full migration check and auto-fix

## [v1.5.4] - 2026-02-21

- Add /fix-the-issue command: lightweight bug-fix workflow with tech-lead investigation, parallel frontend/backend implementation, code review, compile gate, QA automation test updates, and PR creation with squash-merge

## [v1.5.3] - 2026-02-21

- Support modifying existing test cases and E2E tests: qa-engineer now scans for stale .md test case files and updates them in-place before creating new ones; qa-automation now scans for existing Playwright spec files covering changed functionality and updates them before writing new tests

## [v1.5.1] - 2026-02-18

- Remove --headed flag from manual-tester: playwright-cli now runs headless by default, no Playwright Flags config field needed
- Remove Playwright Flags field from scrum-team-config template (both claude and opencode)

## [v1.5.0] - 2026-02-18

- Switch Docker isolation to no-host-port architecture: only the frontend gets one host port (for manual-tester playwright-cli), all other services (backend, postgres, redis, minio) stay fully internal to the Docker network
- Startup health poll now runs inside Docker via curlimages/curl container (no host-side curl needed)
- qa-automation gets a new docker_test_runner section: runs Playwright inside a container on the same Docker network using internal URLs (BASE_URL, API_URL env vars), with fallback to host Playwright when Playwright Service is blank
- TEST-ENV.md now includes both external Test Frontend URL (for manual-tester) and internal Docker network URLs (for qa-automation)
- Replace App Services field in scrum-team-config template with explicit fields: Frontend Service Name, Frontend Internal Port, Backend Service Name, Backend Internal Port, Playwright Service
- Add Test Environment (Docker Isolation) section to opencode template (was missing)

## [v1.4.0] - 2026-02-18

- Add remote dev environment testing support: manual-tester and qa-automation now register a fresh tenant before testing, use it throughout, and delete it after all tests complete
- Add Remote Testing section to scrum-team-config template (Remote Dev URL, Tenant Registration URL, Tenant Admin URL)

## [v1.3.9] - 2026-02-18

- Enforce headless mode for all Playwright E2E tests in qa-automation agent (never use --headed flag)

## [v1.3.8] - 2026-02-18

- Track PROGRESS.md in git: tech-lead now commits and pushes PROGRESS.md to the feature branch after PR creation
- Add Session Cost section to PROGRESS.md template to record total spend per feature session

## [v1.3.7] - 2026-02-18

- feat: add /dw-upgrade command for one-step upgrade
- feat: show installed version in statusline (dw v1.3.x) with ⬆️ indicator when update available

## [v1.3.3] - 2026-02-16

- Product-owner agent upgraded from sonnet to opus model for better reasoning
- Added comprehensive environment-specific questions (environments, config, dependencies, behaviors, test data, security)
- Enhanced Feature Brief format with Environment Configuration section
- Added AskUserQuestion tool to OpenCode product-owner

## [v1.3.2] - 2026-02-16

- Add WebSearch tool to architect agent for documentation lookup

## [v1.3.1] - 2026-02-16

- Product-owner agent now uses AskUserQuestion for structured questions with selectable answer variants instead of plain text lists

## [v1.3.0] - 2026-02-15

- Parallelized UX Design and Architecture phases (formerly sequential Phase 2 + Phase 3, now single parallel Phase 2)
- Architect now reads Feature Brief as primary input, no longer waits for UX Design
- User checkpoint covers both UX and architecture approval together
- Reduced workflow from 7 phases to 6 phases

## [v1.2.2] - 2026-02-14

- Added autonomous execution block to manual-tester agent for approval-free command execution
- Switched planning/review roles (code-reviewer, product-owner, scrum-master, ux-designer, db-analyst, performance-engineer) from opus to sonnet model

## [v1.2.1] - 2026-02-14

- Fixed agents prompting for permissions despite bypassPermissions flag
- Moved bypassPermissions instruction to top-level mandatory section in scrum-team command
- Added explicit Mode column to all agent tables (scrum-team and retest)
- Added missing bypassPermissions to prepare-for-production auditor agents
- Reinforced mode at every phase spawn point for reliability

## [v1.2.0] - 2025-02-13

- manual-tester switched to haiku model for cost optimization
- Screenshots only captured on test failure (reduced token usage)
- Fixed VERSION file path in install.sh

## [v1.1.0] - 2025-02-12

- Added OpenCode workflow distribution (install-opencode.sh, opencode/ directory)
- OpenCode agents and commands mirror Claude Code workflow

## [v1.0.0] - 2025-02-11

- Initial release of dodocs-workflow
- 13-agent scrum team workflow for Claude Code
- 10-agent production readiness audit
- /scrum-team and /prepare-for-production slash commands
- Project config template system
