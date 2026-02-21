Create an agent team for developing new features on this project. Use delegate mode — the lead only coordinates, never writes code.

The team follows a Scrum workflow and must work fully autonomously. Human only needs to provide requirements.

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Task tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts. The ONLY exception is `architect`, which uses `mode: "plan"` for architecture approval.

When calling the Task tool, ALWAYS include `mode: "bypassPermissions"` in the parameters. Example:
```
Task(subagent_type="frontend-dev", mode="bypassPermissions", ...)
```

Spawn all agents automatically as their phase begins — do NOT ask the user for permission to spawn any agent.

<boot>
BEFORE doing anything else, read `.claude/scrum-team-config.md` using the Read tool.
If the file does not exist, STOP immediately and tell the user:
"No scrum-team config found for this project. Run `dodocs-workflow init` or copy the template from `~/.claude/scrum-team-config.template.md` to `.claude/scrum-team-config.md` and fill in the values for this project."
Extract: ALL sections — you need App Identity, Tech Stack, Ports & URLs, and all paths/commands.
</boot>

## Team Agents

Spawn these teammates using their agent definitions from `~/.claude/agents/`. **All agents use `mode: "bypassPermissions"` unless noted otherwise.**

| Name | Agent Type | Mode | Notes |
|------|-----------|------|-------|
| product-owner | `product-owner` | `bypassPermissions` | |
| ux-designer | `ux-designer` | `bypassPermissions` | |
| architect | `architect` | `plan` | Require plan approval |
| scrum-master | `scrum-master` | `bypassPermissions` | |
| code-reviewer | `code-reviewer` | `bypassPermissions` | |
| frontend-dev-1 | `frontend-dev` | `bypassPermissions` | |
| frontend-dev-2 | `frontend-dev` | `bypassPermissions` | Coordinates with frontend-dev-1 to avoid file conflicts |
| backend-dev-1 | `backend-dev` | `bypassPermissions` | Owns all database migrations |
| backend-dev-2 | `backend-dev` | `bypassPermissions` | Coordinates with backend-dev-1, never creates migrations |
| tech-lead | `tech-lead` | `bypassPermissions` | |
| qa-engineer | `qa-engineer` | `bypassPermissions` | |
| qa-automation | `qa-automation` | `bypassPermissions` | |
| manual-tester | `manual-tester` | `bypassPermissions` | |

Models are defined in each agent's `.md` file (opus for architect and security-auditor, sonnet for all other roles).

## Full Workflow

### Phase 1: Requirements + Early UX Research (PARALLEL)
**First**: Create the initial `PROGRESS.md` at `<feature-docs>/<feature-name>/PROGRESS.md` using the template from the Progress Tracking section.

Then spawn product-owner and ux-designer simultaneously (both with `mode: "bypassPermissions"`):
- **product-owner** talks to the user, gathers requirements, produces **FEATURE-BRIEF.md**
- **ux-designer** starts studying existing UI patterns, pages, and components (does NOT produce the UX doc yet — just researches)

### Phase 2: UX Design + Architecture (PARALLEL)
Spawn ux-designer and architect simultaneously once the Feature Brief is ready:
- **ux-designer** reads the Feature Brief and produces **UX-DESIGN.md** (combining research from Phase 1 with the brief) — spawned with `mode: "bypassPermissions"`
- **architect** reads the Feature Brief, researches existing code patterns, designs the technical solution, produces **ARCHITECTURE.md** — spawned with `mode: "plan"` (lead must approve the architecture plan)

Both agents work from the Feature Brief in parallel. The architect does NOT need to wait for UX Design.

- **USER CHECKPOINT**: After both UX-DESIGN.md and ARCHITECTURE.md are complete, present both to the user and ask: "Do the UX flows and architecture look right? Any changes before we proceed to development?" Wait for user approval before continuing.

### Phase 3: Task Breakdown + Git Setup
Spawn tech-lead and scrum-master with `mode: "bypassPermissions"`:
- **tech-lead** creates a feature branch: `git checkout -b feature/<feature-name>`
- **scrum-master** reads the Architecture doc and creates all tasks with these rules:
  - **Migration ownership**: Only `backend-dev-1` creates database migrations. `backend-dev-2` tasks that need migrations are blocked by `backend-dev-1`'s migration tasks
  - **No file conflicts**: No two developers edit the same file
  - **Task dependencies**: Set `blockedBy` relationships where needed
  - Assigns tasks to all devs and QA

### Phase 4: Build + Test (ALL PARALLEL)
Spawn ALL these agents simultaneously, every one with `mode: "bypassPermissions"`:
- **frontend-dev-1** + **frontend-dev-2**: work on assigned tasks, make atomic git commit per completed task
- **backend-dev-1** + **backend-dev-2**: work on assigned tasks, make atomic git commit per completed task
- **qa-engineer**: writes test case `.md` files organized by user story
- **code-reviewer**: watches for completed developer tasks, reviews each one
- **tech-lead**: runs compile gate (compile backend + frontend + lint), starts the app, monitors for build/runtime issues
- **manual-tester**: waits for ALL dev tasks to be code-reviewed AND qa-engineer's test cases to be ready, then tests the full feature story by story using the test cases
- **qa-automation**: writes E2E tests per user story — after manual-tester passes all scenarios for a user story, qa-automation writes the Playwright tests for that story

### Phase 4 Flow:
```
Developers complete tasks -> atomic commits (unchanged)
       |
       v
Code-reviewer reviews each task individually (unchanged)
       |
       v
QA-engineer writes test cases organized by user story (parallel with devs)
       |
       v
ALL tasks reviewed + test cases ready
       |
       v
Manual-tester tests the full feature using QA engineer's test cases (story by story)
       |
       +-- pass -> qa-automation writes E2E for that user story
       +-- fail -> bug task -> developer fixes -> code-reviewer reviews -> manual-tester retests
```

### Phase 5: Integration Verification
After all tasks are complete, reviewed, and tested:
- **tech-lead**: full app restart, regression check
- **qa-automation**: runs the full E2E test suite
- **manual-tester**: final smoke test of the complete feature flow end-to-end
- **code-reviewer**: reviews the full feature diff (all changes from feature branch)

### Phase 6: Ship
- **tech-lead**: creates a PR from the feature branch to main
- Team lead reports completion to the user with a summary

## Parallel Execution Rules

- From Phase 4 onward, tech-lead, code-reviewer, manual-tester, qa-automation, and all developers MUST run in parallel
- **Feature-level testing**: manual-tester waits for ALL dev tasks to be code-reviewed AND qa-engineer's test cases to be ready before beginning testing. Then tests the full feature story by story.
- **Story-level E2E**: qa-automation writes E2E tests per user story — after manual-tester passes all scenarios for a story, qa-automation writes the E2E tests for that story
- When manual-tester or tech-lead files a bug, the assigned developer picks it up and fixes it immediately — no waiting
- After a developer fixes a bug, code-reviewer reviews the fix, then manual-tester retests that story
- This review-test-fix-retest loop continues until all test cases pass

## Compile Gate

Before manual-tester begins testing, tech-lead MUST confirm:
1. Backend compiles without errors
2. Frontend compiles without errors
3. No lint errors
4. App starts and is accessible
Only then does tech-lead signal "app ready" for testing to begin.

## Git Strategy

- **Feature branch**: `feature/<feature-name>` created at Phase 3
- **Atomic commits**: Each completed task = one commit with descriptive message
- **Commit format**: `<scope>: <description>` (e.g., `backend: add User entity and migration`)
- **PR**: Created at Phase 6 by tech-lead after all verification passes

## Progress Tracking

The team maintains a shared **PROGRESS.md** file at `<feature-docs>/<feature-name>/PROGRESS.md` that provides a single-file view of overall workflow status. All agents update this file at key milestones.

- **Created by**: Team lead at the start of Phase 1
- **Updated by**: Every agent at their key milestones (artifact completion, task creation, reviews, testing, etc.)
- **Purpose**: Human-readable progress dashboard — useful for both the team lead and the human user

The team lead creates the initial PROGRESS.md using this template:

```markdown
# Progress: <feature-name>

## Current Phase
Phase 1 — Requirements + UX Research

## Phase Status

| Phase | Status | Agent(s) |
|-------|--------|----------|
| Phase 1: Requirements + UX Research | In Progress | product-owner, ux-designer |
| Phase 2: UX Design + Architecture | Pending | ux-designer, architect |
| Phase 3: Task Breakdown + Git | Pending | scrum-master, tech-lead |
| Phase 4: Build + Test | Pending | all |
| Phase 5: Integration Verification | Pending | — |
| Phase 6: Ship | Pending | — |

## Artifacts

| Document | Status | Author |
|----------|--------|--------|
| FEATURE-BRIEF.md | Pending | product-owner |
| UX-DESIGN.md | Pending | ux-designer |
| ARCHITECTURE.md | Pending | architect |

## Development Tasks
<!-- scrum-master populates this after Phase 4 -->

## Code Reviews
<!-- code-reviewer updates this -->

## Test Cases
<!-- qa-engineer updates this -->

## Testing
<!-- manual-tester updates this -->

## E2E Automation
<!-- qa-automation updates this -->

## Bugs
<!-- manual-tester / tech-lead add bugs here -->

## Timeline
<!-- all agents append entries -->

## Session Cost

| Item | Value |
|------|-------|
| Total Cost (USD) | $0.00 — update from statusline before merging |
| Feature Branch | feature/<feature-name> |
| PR URL | — |
| Completed | <!-- tech-lead: fill with completion date --> |
```

## Retest Mode

If `$ARGUMENTS` starts with `--retest`, enter retest mode instead of the full workflow:

1. **Parse arguments**: Extract the feature name (e.g., `--retest user-settings`)
2. **Skip Phases 1-3 entirely** — do NOT spawn product-owner, ux-designer, architect, scrum-master, frontend-dev-2, backend-dev-2, qa-engineer, or qa-automation
3. **Read existing context**:
   - Test cases from the **Test Cases** path in the project config relevant to the feature
   - Feature docs from the **Feature Docs** path in the project config for `<feature-name>/`
4. **Spawn ALL these agents in parallel** (all with `mode: "bypassPermissions"`):

| Name | Agent Type | Mode | Retest Role |
|------|-----------|------|-------------|
| tech-lead | `tech-lead` | `bypassPermissions` | Starts full environment, compile gate, verifies app runs |
| code-reviewer | `code-reviewer` | `bypassPermissions` | Reviews any fixes made during retest |
| manual-tester | `manual-tester` | `bypassPermissions` | Tests ALL scenarios from existing test cases |
| frontend-dev-1 | `frontend-dev` | `bypassPermissions` | Ready to pick up and fix UI bugs immediately |
| backend-dev-1 | `backend-dev` | `bypassPermissions` | Ready to pick up and fix API/DB bugs immediately |

### Retest Phases

- **Phase R1**: All 5 agents spawn in parallel. Tech-lead starts the app and runs compile gate
- **Phase R2**: manual-tester tests ALL scenarios from existing test cases. Developers stand by for bug tasks
- **Phase R3** (continuous loop): manual-tester files bugs -> developers fix -> code-reviewer reviews fix -> manual-tester retests -> repeat until all test cases pass
- **Done**: when manual-tester confirms all test cases pass with no remaining bugs

The feature to implement/retest: $ARGUMENTS
