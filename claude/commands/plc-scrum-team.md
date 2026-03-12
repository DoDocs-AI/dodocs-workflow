Execute the PLC Build Pipeline — a full scrum team workflow optimized for MVP development within the Product Lifecycle framework.

The team follows a Scrum workflow and must work fully autonomously. Human only needs to provide the product slug.

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Task tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts. The ONLY exception is `plc-architect`, which uses `mode: "plan"` for architecture approval when SIZE=large and AUTO_MODE=false.

When calling the Task tool, ALWAYS include `mode: "bypassPermissions"` in the parameters. Example:
```
Task(subagent_type="plc-frontend-dev", mode="bypassPermissions", ...)
```

Spawn all agents automatically as their phase begins — do NOT ask the user for permission to spawn any agent.

<boot>
BEFORE doing anything else:

**Step 1 — Parse $ARGUMENTS:**
- Extract the product slug (required). This is the `<slug>` used in `docs/plc/<slug>/`.
- If no slug is provided, STOP immediately and tell the user: "Product slug is required. Usage: `/plc-scrum-team <slug>`"
- Extract optional flags:
  - If `--size small` is present: set SIZE=small.
  - If `--size medium` is present: set SIZE=medium.
  - If `--size large` is present: set SIZE=large.
  - If no `--size` flag: set SIZE=medium (default for PLC pipeline).
- Set AUTO_MODE=true always (PLC pipeline runs fully autonomous).

**Step 2 — Read config:**
Read `.claude/scrum-team-config.md` using the Read tool.
If the file does not exist, STOP immediately and tell the user:
"No scrum-team config found for this project. Run `dodocs-workflow init` or copy the template from `~/.claude/scrum-team-config.template.md` to `.claude/scrum-team-config.md` and fill in the values for this project."
Extract: ALL sections — you need App Identity, Tech Stack, Ports & URLs, and all paths/commands.
Also extract (optional fields, use defaults if absent):
- **Mockup Component Schema**: path to UI component schema/registry file (empty string if not set)
- **Mockup Preview Port**: port for the mockup Vite dev server (default `3100` if not set)

**Step 3 — Read MVP Scope:**
Read `docs/plc/<slug>/strategy/MVP-SCOPE.md` using the Read tool.
If the file does not exist, STOP immediately and tell the user:
"MVP-SCOPE.md not found at docs/plc/<slug>/strategy/MVP-SCOPE.md. Run the plc-mvp-scoper agent first to define the MVP scope before starting the build pipeline."

**Step 4 — Create feature branch:**
- Derive branch name: `feature/plc-<slug>-mvp`
- Run: `git checkout -b feature/plc-<slug>-mvp`
- If the branch already exists (command fails), check it out instead: `git checkout feature/plc-<slug>-mvp`
- Print: "Feature branch: feature/plc-<slug>-mvp"
</boot>

## Team Size Configuration

Based on SIZE (default: medium):

| Agent              | small | medium | large |
|--------------------|-------|--------|-------|
| plc-product-owner  | yes   | yes    | yes   |
| plc-ux-designer    | yes   | yes    | yes   |
| plc-architect      | no    | yes    | yes   |
| plc-scrum-master   | yes   | yes    | yes   |
| plc-frontend-dev-1 | yes   | yes    | yes   |
| plc-frontend-dev-2 | no    | yes    | yes   |
| plc-backend-dev-1  | no    | yes    | yes   |
| plc-backend-dev-2  | no    | no     | yes   |
| plc-code-reviewer  | yes   | yes    | yes   |
| plc-qa-engineer    | yes   | yes    | yes   |
| plc-qa-automation  | no    | yes    | yes   |
| plc-manual-tester  | yes   | yes    | yes   |
| plc-tech-lead      | yes   | yes    | yes   |

- **small** (9 agents): frontend-only change, no migrations, <5 files. Skip Phase 2 entirely (no architect). Scrum-master reads MVP-SCOPE.md directly.
- **medium** (11 agents): full-stack but no second backend dev. Architect uses `bypassPermissions` (no plan mode).
- **large** (13 agents): full team. Architect uses `bypassPermissions` (AUTO_MODE is always true).

## Team Agents

Spawn these teammates using their agent definitions from `~/.claude/agents/`. **All agents use `mode: "bypassPermissions"`.**

| Name | Agent Type | Mode | Notes |
|------|-----------|------|-------|
| plc-product-owner | `plc-product-owner` | `bypassPermissions` | |
| plc-ux-designer | `plc-ux-designer` | `bypassPermissions` | |
| plc-architect | `plc-architect` | `bypassPermissions` | Always bypassPermissions (AUTO_MODE=true) |
| plc-scrum-master | `plc-scrum-master` | `bypassPermissions` | |
| plc-code-reviewer | `plc-code-reviewer` | `bypassPermissions` | |
| plc-frontend-dev-1 | `plc-frontend-dev` | `bypassPermissions` | |
| plc-frontend-dev-2 | `plc-frontend-dev` | `bypassPermissions` | Coordinates with plc-frontend-dev-1 to avoid file conflicts |
| plc-backend-dev-1 | `plc-backend-dev` | `bypassPermissions` | Owns all database migrations |
| plc-backend-dev-2 | `plc-backend-dev` | `bypassPermissions` | Coordinates with plc-backend-dev-1, never creates migrations |
| plc-tech-lead | `plc-tech-lead` | `bypassPermissions` | |
| plc-mockup-designer | `plc-mockup-designer` | `bypassPermissions` | Skipped if SIZE=small or daytime-prep mockups already exist |
| plc-mockup-validator | `plc-mockup-validator` | `bypassPermissions` | Skipped if SIZE=small or daytime-prep mockups already exist |
| plc-qa-engineer | `plc-qa-engineer` | `bypassPermissions` | |
| plc-qa-automation | `plc-qa-automation` | `bypassPermissions` | |
| plc-manual-tester | `plc-manual-tester` | `bypassPermissions` | |

Models are defined in each agent's `.md` file (opus for architect and security-auditor, sonnet for all other roles).

## Full Workflow

### Phase 1: Requirements + Early UX Research (PARALLEL)
**First**: Create the initial `PROGRESS.md` at `docs/plc/<slug>/build/PROGRESS.md` using the template from the Progress Tracking section.

Then spawn plc-product-owner and plc-ux-designer simultaneously (both with `mode: "bypassPermissions"`):
- **plc-product-owner** derives requirements from MVP-SCOPE.md (always autonomous — AUTO_MODE=true), produces **FEATURE-BRIEF.md** at `docs/plc/<slug>/build/FEATURE-BRIEF.md`. Append `AUTO_MODE=true` and `MVP_SCOPE_PATH=docs/plc/<slug>/strategy/MVP-SCOPE.md` to the prompt.
- **plc-ux-designer** starts studying existing UI patterns, pages, and components (does NOT produce the UX doc yet — just researches)

**VALIDATE Phase 1 artifacts** before proceeding to Phase 2:
- Read `docs/plc/<slug>/build/FEATURE-BRIEF.md` using the Read tool.
- Must exist AND contain all of these non-empty sections: problem statement (or background), user stories, acceptance criteria.
- Acceptance criteria must use numbered IDs (AC-01, AC-02, ...). If ACs lack IDs, re-spawn plc-product-owner with: "Acceptance criteria need sequential IDs (AC-01, AC-02, ...) for RTM traceability."
- If the file is missing or any required section is absent/empty: re-spawn `plc-product-owner` with `bypassPermissions` and append to its prompt: "FEATURE-BRIEF.md is incomplete or missing. Regenerate it with all required sections: problem statement, user stories, acceptance criteria, and edge cases." Wait for it to complete, then re-validate before proceeding.

### Phase 2: UX Design + Architecture (PARALLEL)

**Skip Phase 2 entirely if SIZE=small** — proceed directly to Phase 3. Scrum-master reads Feature Brief directly.

Otherwise, spawn plc-ux-designer and plc-architect simultaneously once the Feature Brief is ready:

**Before spawning plc-ux-designer:** Check if `docs/plc/<slug>/build/mockups/` exists. If it exists, append the following mockup context to the plc-ux-designer's prompt:
```
Framework-native mockup components were approved by the human during daytime preparation.
Location: docs/plc/<slug>/build/mockups/  (one .tsx/.vue file per screen)
Read index.tsx for the full screen overview, then read each USxx*.tsx.
Your UX-DESIGN.md MUST align with the approved mockup structure. Do not redesign
approved screens. Enrich with: keyboard navigation, accessibility, responsive behavior,
micro-interactions, and transition details not captured in mockups.
Reference mockup filenames inline: "As shown in US01MainView.tsx, ..."
```

**Before spawning plc-architect:** Check if `docs/plc/<slug>/build/mockups/` exists. If it exists, append to the plc-architect's prompt:
```
Approved mockup components exist at docs/plc/<slug>/build/mockups/.
Read them to understand the frontend component scope and structure required.
These are the approved screens — your ARCHITECTURE.md frontend component list
should align with the mockup component structure.
```

- **plc-ux-designer** reads the Feature Brief and produces **UX-DESIGN.md** at `docs/plc/<slug>/build/UX-DESIGN.md` (combining research from Phase 1 with the brief) — spawned with `mode: "bypassPermissions"`
- **plc-architect** reads the Feature Brief, researches existing code patterns, designs the technical solution, produces **ARCHITECTURE.md** at `docs/plc/<slug>/build/ARCHITECTURE.md` — spawned with `mode: "bypassPermissions"` (always, since AUTO_MODE=true)

Both agents work from the Feature Brief in parallel. The architect does NOT need to wait for UX Design.

**Mockup generation (after plc-ux-designer + plc-architect complete):**

Check if `docs/plc/<slug>/build/mockups/` already exists (created by daytime preparation):

- **If it DOES exist (daytime-prep mockups)**: Skip plc-mockup-designer and plc-mockup-validator.
  The existing mockups count as already approved. Proceed directly to validation below.

- **If it does NOT exist**: spawn the mockup pipeline sequentially:
  1. Spawn **plc-mockup-designer** with `mode: "bypassPermissions"`. Pass the slug and
     a note: "Generate framework-native mockup components from FEATURE-BRIEF.md and UX-DESIGN.md.
     Read existing UI components and patterns from the codebase before creating any file.
     Output directory: docs/plc/<slug>/build/mockups/ (all files go here).
     Mockup preview port: <MOCKUP_PORT from config, default 3100>.
     Mockup Component Schema: <MOCKUP_SCHEMA_PATH from config — if non-empty, read this file first and use it as the authoritative component reference>."
     Wait for completion.
  2. Spawn **plc-mockup-validator** with `mode: "bypassPermissions"`. Pass the slug.
     Wait for completion.
  3. If plc-mockup-validator reports FAILED:
     - Re-spawn plc-mockup-designer with the note: "MOCKUP-VALIDATION.md reported failures.
       Fix the identified issues and regenerate the mockup components." Wait for completion.
     - Re-spawn plc-mockup-validator. Wait for completion.
     - If still FAILED after retry: log the failures and proceed (do not block the workflow).

**VALIDATE Phase 2 artifacts** before proceeding:
- Read `docs/plc/<slug>/build/ARCHITECTURE.md` — must exist and contain at minimum
  one of: backend endpoints section OR frontend components section, AND a file inventory section.
- Read `docs/plc/<slug>/build/UX-DESIGN.md` — must exist and contain at least one user flow.
- If ARCHITECTURE.md is missing or incomplete: re-spawn `plc-architect` with `bypassPermissions`
  with the note: "ARCHITECTURE.md is missing or incomplete. Please regenerate it covering:
  backend endpoints, database entities, frontend components, and file inventory."
  Wait for completion, re-validate.
- If UX-DESIGN.md is missing: re-spawn `plc-ux-designer` with `bypassPermissions` with the note:
  "UX-DESIGN.md is missing. Please produce it from the Feature Brief and your Phase 1 research."
  Wait for completion.

**AUTO_MODE checkpoint**: Log "AUTO_MODE: Architecture, UX Design and Mockups auto-approved." and proceed immediately to Phase 3.

### Phase 3: Task Breakdown
Spawn plc-scrum-master with `mode: "bypassPermissions"`:
- **plc-scrum-master** reads the Architecture doc and creates all tasks with these rules:
  - **Migration ownership**: Only `plc-backend-dev-1` creates database migrations. `plc-backend-dev-2` tasks that need migrations are blocked by `plc-backend-dev-1`'s migration tasks
  - **No file conflicts**: No two developers edit the same file
  - **Task dependencies**: Set `blockedBy` relationships where needed
  - Assigns tasks to all devs and QA

**VALIDATE Phase 3 task breakdown** before proceeding to Phase 4:
- Call TaskList and count tasks assigned to developers (plc-frontend-dev-*, plc-backend-dev-*).
- Must have at least 2 developer tasks AND all developer tasks must have a user story prefix (`[US01]`, `[US02]`, etc.) in their subject.
- If fewer than 2 developer tasks exist OR tasks are missing user story prefixes: re-spawn `plc-scrum-master` with `bypassPermissions` and append: "Task breakdown is incomplete. Re-read ARCHITECTURE.md and create ALL developer tasks. Every task subject must start with a user story prefix like [US01]. Ensure file conflict and migration ownership rules are applied." Wait for completion, re-validate.

### Phase 4: Build + Test (ALL PARALLEL)
Spawn agents simultaneously according to the SIZE configuration (see Team Size Configuration table), every one with `mode: "bypassPermissions"`:
- **plc-frontend-dev-1** (all sizes) + **plc-frontend-dev-2** (medium/large only): work on assigned tasks, make atomic git commit per completed task
- **plc-backend-dev-1** (medium/large only) + **plc-backend-dev-2** (large only): work on assigned tasks, make atomic git commit per completed task
- **plc-qa-engineer**: creates RTM.md (Requirements Traceability Matrix mapping Feature Brief ACs → Architecture → Tasks → Test Cases), validates architecture coverage, then writes test case .md files for ALL Must-Have ACs
- **plc-code-reviewer**: watches for completed developer tasks, reviews each one
- **plc-tech-lead**: runs compile gate (compile backend + frontend + lint), starts the app, monitors for build/runtime issues
- **plc-manual-tester**: waits for "app ready" signal, then begins testing each user story as soon as all tasks for THAT story are code-reviewed AND plc-qa-engineer's test cases for that story are ready — does NOT wait for all stories to complete
- **plc-qa-automation** (medium/large only): writes E2E tests per user story — after plc-manual-tester passes all scenarios for a user story, plc-qa-automation writes the Playwright tests for that story

**Periodic progress report** — print after every agent message received during Phase 4:

Call TaskList and output a compact status block in this exact format:
```
─────────────────────────────────────────
  BACKEND  ██████████  6/6  done ✅
  FRONTEND ░░░░░░░░░░  0/5  pending  (T16 in progress by plc-frontend-dev-1)
  QA       ██████████  test cases ready ✅
  COMPILE  🔨 plc-tech-lead running now
  TESTING  ⏳ waiting for compile gate
─────────────────────────────────────────
```
Rules for the report:
- **BACKEND / FRONTEND**: count tasks assigned to plc-backend-dev-* / plc-frontend-dev-*. Fill bar: `█` for each completed, `░` for each pending (scale to 10 chars). Show `done ✅` when all complete, otherwise show the in-progress task ID and owner.
- **QA**: `test cases ready ✅` when plc-qa-engineer is done, otherwise `⏳ writing test cases`.
- **COMPILE**: `✅ app ready` after plc-tech-lead signals compile gate passed; `🔨 running now` while active; `⏳ waiting` before started.
- **TESTING**: `✅ all stories pass` when plc-manual-tester is done; show current story being tested otherwise.
- Omit rows that don't apply to the current SIZE (e.g., no BACKEND row for small).
- Print the report **after each agent idle notification** — do not wait for all agents to finish.

### Phase 4 Flow:
```
Developers complete tasks -> atomic commits (per story)
       |
       v
plc-code-reviewer reviews each task individually
       |
       v  (per story — no waiting for other stories)
ALL tasks for US01 reviewed + US01 test cases ready
       |
       v
plc-manual-tester tests US01 immediately
       |
       +-- pass -> plc-qa-automation writes E2E for US01
       +-- fail -> bug task -> developer fixes -> plc-code-reviewer reviews -> plc-manual-tester retests
            (if same test case fails 2+ times -> escalate to plc-tech-lead)

Meanwhile: US02 development continues in parallel -> reviewed -> plc-manual-tester tests US02 -> ...
```

### Phase 5: Integration Verification
After all tasks are complete, reviewed, and tested:
- **plc-tech-lead**: full app restart, regression check
- **plc-qa-automation**: runs the full E2E test suite
- **plc-manual-tester**: final smoke test of the complete feature flow end-to-end
- **plc-code-reviewer**: reviews the full feature diff (all changes from feature branch)
- **plc-tech-lead**: Acceptance Verification — reads RTM.md and verifies every Must-Have AC has architecture, implementation, test cases, and passing test results

### Phase 6: Ship
- **plc-tech-lead**: creates a PR from the feature branch to main
- Produce **BUILD-SUMMARY.md** at `docs/plc/<slug>/build/BUILD-SUMMARY.md` with:
  - MVP scope delivered (from MVP-SCOPE.md Must-Haves)
  - User stories implemented
  - Architecture decisions made
  - Acceptance Verification summary from RTM.md
  - Test coverage summary
  - Known limitations / deferred items
  - PR link
- Team lead reports completion to the user with a summary

## Parallel Execution Rules

- From Phase 4 onward, plc-tech-lead, plc-code-reviewer, plc-manual-tester, plc-qa-automation, and all developers MUST run in parallel
- **Story-level testing**: plc-manual-tester begins testing each user story as soon as ALL dev tasks for that story are code-reviewed AND plc-qa-engineer's test cases for that story are ready. Does NOT wait for other stories — testing and development run in parallel across stories.
- **Story-level E2E**: plc-qa-automation writes E2E tests per user story — after plc-manual-tester passes all scenarios for a story, plc-qa-automation writes the E2E tests for that story
- When plc-manual-tester or plc-tech-lead files a bug, the assigned developer picks it up and fixes it immediately — no waiting
- After a developer fixes a bug, plc-code-reviewer reviews the fix, then plc-manual-tester retests that story
- **Bug fix cycle detection**: if plc-manual-tester retests the same test case 2+ times and it still fails, escalate to plc-tech-lead for root cause analysis instead of creating another fix task
- This review-test-fix-retest loop continues until all test cases pass

## Compile Gate

Before plc-manual-tester begins testing, plc-tech-lead MUST confirm:
1. Backend compiles without errors
2. Frontend compiles without errors
3. No lint errors
4. App starts and is accessible
Only then does plc-tech-lead signal "app ready" for testing to begin.

## Git Strategy

- **Feature branch**: `feature/plc-<slug>-mvp` created at boot (before Phase 1)
- **Atomic commits**: Each completed task = one commit with descriptive message
- **Commit format**: `<scope>: <description>` (e.g., `backend: add User entity and migration`)
- **PR**: Created at Phase 6 by plc-tech-lead after all verification passes

## Progress Tracking

The team maintains a shared **PROGRESS.md** file at `docs/plc/<slug>/build/PROGRESS.md` that provides a single-file view of overall workflow status. All agents update this file at key milestones.

- **Created by**: Team lead at the start of Phase 1
- **Updated by**: Every agent at their key milestones (artifact completion, task creation, reviews, testing, etc.)
- **Purpose**: Human-readable progress dashboard — useful for both the team lead and the human user

The team lead creates the initial PROGRESS.md using this template:

```markdown
# Progress: PLC Build — <slug>

## Current Phase
Phase 1 — Requirements + UX Research

## Phase Status

| Phase | Status | Agent(s) |
|-------|--------|----------|
| Phase 1: Requirements + UX Research | In Progress | plc-product-owner, plc-ux-designer |
| Phase 2: UX Design + Architecture | Pending | plc-ux-designer, plc-architect |
| Phase 3: Task Breakdown | Pending | plc-scrum-master |
| Phase 4: Build + Test | Pending | all |
| Phase 5: Integration Verification | Pending | — |
| Phase 6: Ship | Pending | — |

## MVP Scope Reference
- MVP-SCOPE.md: docs/plc/<slug>/strategy/MVP-SCOPE.md
- Must-Have count: <!-- fill from MVP-SCOPE.md -->
- Core Flow steps: <!-- fill from MVP-SCOPE.md -->

## Artifacts

| Document | Status | Author | Path |
|----------|--------|--------|------|
| MVP-SCOPE.md | Done (pre-existing) | plc-mvp-scoper | docs/plc/<slug>/strategy/MVP-SCOPE.md |
| FEATURE-BRIEF.md | Pending | plc-product-owner | docs/plc/<slug>/build/FEATURE-BRIEF.md |
| UX-DESIGN.md | Pending | plc-ux-designer | docs/plc/<slug>/build/UX-DESIGN.md |
| ARCHITECTURE.md | Pending | plc-architect | docs/plc/<slug>/build/ARCHITECTURE.md |
| mockups/ | Pending | plc-mockup-designer | docs/plc/<slug>/build/mockups/ |
| MOCKUP-VALIDATION.md | Pending | plc-mockup-validator | docs/plc/<slug>/build/ |
| RTM.md | Pending | plc-qa-engineer | docs/plc/<slug>/build/RTM.md |
| BUILD-SUMMARY.md | Pending | plc-tech-lead | docs/plc/<slug>/build/BUILD-SUMMARY.md |

## Development Tasks
<!-- plc-scrum-master populates this after Phase 3 -->

## Code Reviews
<!-- plc-code-reviewer updates this -->

## Test Cases
<!-- plc-qa-engineer updates this -->

## Testing
<!-- plc-manual-tester updates this -->

## E2E Automation
<!-- plc-qa-automation updates this -->

## Bugs
<!-- plc-manual-tester / plc-tech-lead add bugs here -->

## Timeline
<!-- all agents append entries -->

## Session Cost

| Item | Value |
|------|-------|
| Total Cost (USD) | $0.00 — update from statusline before merging |
| Feature Branch | feature/plc-<slug>-mvp |
| PR URL | — |
| Completed | <!-- plc-tech-lead: fill with completion date --> |
```

> **Note on mockup rows**: When creating PROGRESS.md, if `docs/plc/<slug>/build/mockups/` already
> exists (daytime prep was done), pre-fill both mockup rows as `Done` instead of `Pending`.
> Otherwise leave them as `Pending` — the mockup agents will update them during Phase 2.

The product to build: $ARGUMENTS
