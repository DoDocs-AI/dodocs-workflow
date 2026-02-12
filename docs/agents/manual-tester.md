# Manual Tester

Tests full features using the `/playwright-cli` skill for all browser interactions. Waits for all tasks to be code-reviewed and test cases to be ready, then tests the full feature story by story. Files bugs with reproduction steps and screenshots, retests fixes until all test cases pass.

## Spec

| Property | Value |
|----------|-------|
| **Agent file** | `agents/manual-tester.md` |
| **Model** | sonnet |
| **Active in phases** | 5 (feature testing), 6 (smoke test) |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Inputs** | Test case `.md` files, "app ready" signal from tech-lead |
| **Outputs** | Bug tasks, test evidence screenshots |

## Feature Testing Flow

Waits for ALL dev tasks to be code-reviewed AND qa-engineer's test cases to be ready:

1. **Wait for "app ready"** from tech-lead (compile gate passed, app running).
2. **Wait for readiness** — monitor TaskList until ALL developer tasks are completed and approved by code-reviewer, and qa-engineer's test cases are available.
3. **Test the full feature story by story** — using qa-engineer's test cases (organized by user story), test each user story completely before moving to the next.
4. **File bugs immediately** — each bug as a separate task, so developers fix while testing continues on other stories.
5. **Retest story** — after developer fixes and code-reviewer approves, retest the affected story.
6. **Loop** until all test cases pass.

## Browser Interaction

Uses `/playwright-cli` skill for all browser operations:
- Navigate to pages
- Click buttons and links
- Fill forms
- Take screenshots as evidence
- Read page snapshots to verify content

Uses the Playwright Session Name and Playwright Flags from the project config.

## Bug Report Format

Each bug task includes:
- **Test Case ID** — which test case failed (e.g., TC-012)
- **Steps to Reproduce** — exact steps taken
- **Expected Result** — what should have happened
- **Actual Result** — what actually happened
- **Screenshot** — path to screenshot evidence
- **Severity** — Critical/High/Medium/Low

Bug assignment:
- UI issues -> frontend developer who wrote the code
- API/DB issues -> backend developer who wrote the code

## Phase 6 Role

Final smoke test of the complete feature flow end-to-end after all individual tasks pass.

## Config Sections Used

- Ports & URLs (Frontend Port, Backend Port)
- Source Paths — Testing (Test Cases)
- Testing (Playwright Session Name, Playwright Flags)

## Coordination

- Waits for tech-lead "app ready" signal.
- Waits for ALL dev tasks to be code-reviewed and qa-engineer's test cases to be ready before starting.
- Notifies qa-automation when all scenarios for a user story pass (so E2E tests can be written for that story).
- Files bugs assigned to the responsible developer.
- Updates `PROGRESS.md` during testing: adds entries to the Testing section (per user story results), the Bugs section (when filing bugs), and timeline entries.

## When It Runs

- **Full workflow**: Phase 5 (feature testing) + Phase 6 (smoke test)
- **Retest mode**: Tests ALL scenarios from existing test cases, files bugs, retests fixes
