Fix a bug or issue by investigating the root cause, applying targeted fixes with a small focused team, verifying the fix compiles and runs, and shipping a PR.

## Usage

```
/fix-the-issue <description of the issue>
```

---

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Task tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

When calling the Task tool, ALWAYS include `mode: "bypassPermissions"` in the parameters. Example:
```
Task(subagent_type="tech-lead", mode="bypassPermissions", ...)
```

Spawn all agents automatically as their phase begins — do NOT ask the user for permission to spawn any agent.

<boot>
BEFORE doing anything else, read `.claude/scrum-team-config.md` using the Read tool.
If the file does not exist, STOP immediately and tell the user:
"No scrum-team config found for this project. Run `dodocs-workflow init` or copy the template from `~/.claude/scrum-team-config.template.md` to `.claude/scrum-team-config.md` and fill in the values for this project."
Extract: ALL sections — App Identity, Tech Stack, Ports & URLs, Source Paths, Commands.
</boot>

---

## Team

| Name | Agent Type | Mode | Role |
|------|-----------|------|------|
| tech-lead | `tech-lead` | `bypassPermissions` | Investigates issue, creates branch & tasks, verifies app, creates PR |
| frontend-dev | `frontend-dev` | `bypassPermissions` | Implements frontend fixes |
| backend-dev | `backend-dev` | `bypassPermissions` | Implements backend fixes |
| code-reviewer | `code-reviewer` | `bypassPermissions` | Reviews all changes |
| qa-automation | `qa-automation` | `bypassPermissions` | Updates test cases & E2E tests, runs Playwright suite |

Spawn only the agents needed — if the fix is backend-only, skip frontend-dev; if frontend-only, skip backend-dev.

---

## Workflow

### Phase 1: Investigation & Fix Plan

Derive a `<fix-name>` from the issue description: kebab-case, max 40 characters (e.g., `login-redirect-loop`, `invoice-total-rounding`).

Create the fix docs directory:
```bash
mkdir -p docs/fixes/<fix-name>
```

Spawn **tech-lead** (`mode: "bypassPermissions"`) with this prompt:

> Issue: `$ARGUMENTS`
>
> You are investigating a bug. Do the following:
>
> 1. Read `.claude/scrum-team-config.md` to learn the codebase structure and tech stack.
> 2. Explore the codebase — use Grep, Glob, and Read to trace the issue to its root cause. Look at relevant files, logs, error paths, and tests.
> 3. Write **`docs/fixes/<fix-name>/FIX-PLAN.md`** with:
>    - **Issue**: What is broken and how to reproduce it
>    - **Root Cause**: Where in the codebase the problem originates (file paths + line refs)
>    - **Fix Approach**: What changes to make (frontend vs backend vs both)
>    - **Files to Change**: List every file that needs modification, with a one-line description of the change
>    - **Risk**: Any side-effects or regression risk from this fix
> 4. Create the fix branch: `git checkout -b fix/<fix-name>`
> 5. Report back with the full contents of FIX-PLAN.md.

**USER CHECKPOINT**: After tech-lead returns with the FIX-PLAN.md, present it to the user and ask:
> "Here is the fix plan. Does the root cause analysis and approach look right? Any changes before we start implementing?"

Wait for explicit user approval before continuing to Phase 2.

---

### Phase 2: Task Creation & Implementation

After user approves the plan, spawn **tech-lead** to create TaskCreate entries for the developers based on FIX-PLAN.md. Each task should include:
- Which file(s) to change
- What the change is
- Which developer it is assigned to

Then spawn **frontend-dev** and **backend-dev** in parallel (both `mode: "bypassPermissions"`), each given:
- The full FIX-PLAN.md contents
- Their specific assigned tasks from the task list
- Instruction to make one atomic git commit per task with format `fix: <description>`

Both agents work simultaneously. When a developer completes all their tasks, they notify you.

---

### Phase 3: Code Review

Once all developer tasks are complete, spawn **code-reviewer** (`mode: "bypassPermissions"`) with:
- The FIX-PLAN.md (expected changes)
- Instruction to review every file modified by the developers
- Instruction to check: correctness of the fix, no regressions introduced, security, pattern adherence

If code-reviewer requests changes:
- Re-spawn the affected developer to fix them
- Re-spawn code-reviewer to re-review
- Repeat until all changes are approved

---

### Phase 4: Integration Verification

Spawn **tech-lead** (`mode: "bypassPermissions"`) to:
1. Run the **Compile Backend** command from config — must pass with zero errors
2. Run the **Compile Frontend** command from config — must pass with zero errors
3. Start the app using **Start DB**, **Start Storage**, **Start Backend**, **Start Frontend** commands from config
4. Verify the app starts and the reported issue no longer occurs (check relevant logs, endpoints, or UI behavior)
5. If compilation or runtime errors are found: create bug tasks, re-spawn the relevant developer to fix them, and repeat Phase 3–4 until clean

---

### Phase 5: QA Automation

Spawn **qa-automation** (`mode: "bypassPermissions"`) with:
- The FIX-PLAN.md (what changed and why)
- Instruction to:
  1. Scan existing `.md` test case files (in the **Test Cases** path from the project config) for scenarios that cover the fixed functionality — update any stale expected results or preconditions
  2. Scan existing Playwright spec files (in the **E2E Tests** path from the project config) for tests that exercise the fixed code paths — update selectors, assertions, or flows that no longer match
  3. Run the full Playwright test suite and confirm all tests pass
  4. Report which files were updated and the final test results

If tests fail due to the fix, work with the developer to resolve them before proceeding.

---

### Phase 6: Ship

Spawn **tech-lead** (`mode: "bypassPermissions"`) to:
1. Create a PR from `fix/<fix-name>` to `main`:
   ```bash
   gh pr create --title "fix: <fix-name>" --body "..."
   ```
   PR body should include: issue description, root cause, files changed, test results.
2. Attempt to merge the PR:
   ```bash
   gh pr merge --squash --auto
   ```
   If auto-merge is not available, merge directly:
   ```bash
   gh pr merge --squash
   ```
   If merge fails (conflicts, CI failures), report the blocker to you — do NOT force-merge.
3. After successful merge, switch back to main and pull:
   ```bash
   git checkout main && git pull
   ```
4. Report the PR URL and final status.

---

## Git Strategy

- **Fix branch**: `fix/<fix-name>` (kebab-case from issue description)
- **Commits**: One atomic commit per task — format `fix: <description>`
- **PR**: Squash-merged to main at Phase 6
- **Post-merge**: Always return to main

## Fix Docs Path

All fix documentation lives at `docs/fixes/<fix-name>/`:
- `FIX-PLAN.md` — root cause analysis and fix approach (created in Phase 1)

---

The issue to fix: $ARGUMENTS
