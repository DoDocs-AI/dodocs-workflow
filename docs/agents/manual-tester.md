# Manual Tester

Tests features incrementally using the `/playwright-cli` skill for all browser interactions. Starts testing each area as soon as code-reviewer approves it. Files bugs with reproduction steps and screenshots, retests fixes until all test cases pass.

## Spec

| Property | Value |
|----------|-------|
| **Agent file** | `agents/manual-tester.md` |
| **Model** | sonnet |
| **Active in phases** | 5 (incremental testing), 6 (smoke test) |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Inputs** | Test case `.md` files, "app ready" signal from tech-lead |
| **Outputs** | Bug tasks, test evidence screenshots |

## Incremental Testing Flow

Does NOT wait for all development to finish:

1. **Wait for "app ready"** from tech-lead (compile gate passed, app running).
2. **Monitor TaskList** for tasks that are completed by a developer AND approved by code-reviewer.
3. **Test incrementally** — begins testing each feature area as soon as approved code exists.
4. **File bugs immediately** — each bug as a separate task, so developers fix while testing continues.
5. **Retest fixes** — after developer fixes and code-reviewer approves, re-run the exact failing scenario.
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
- Watches code-reviewer approvals to know when to test.
- Notifies qa-automation when test scenarios pass (so E2E tests can be written).
- Files bugs assigned to the responsible developer.

## When It Runs

- **Full workflow**: Phase 5 (incremental) + Phase 6 (smoke test)
- **Retest mode**: Tests ALL scenarios from existing test cases, files bugs, retests fixes
