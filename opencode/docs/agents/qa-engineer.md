# QA Engineer

Writes manual test cases as `.md` files organized by user story, covering happy paths, error paths, and edge cases. Produces test cases early — manual-tester cannot begin testing until test cases are ready.

## Spec

| Property | Value |
|----------|-------|
| **Agent file** | `agents/qa-engineer.md` |
| **Model** | sonnet |
| **Active in phases** | 5 (early) |
| **Tools** | Read, Write, Grep, Glob, Bash |
| **Outputs** | Test case `.md` files in the Test Cases path |

## Behavior

1. Reads existing test case files to match format exactly.
2. Reads the Feature Brief, UX Design, and Architecture docs.
3. **Organizes test cases by user story** — each test case file maps to a user story so manual-tester can execute story by story and qa-automation can write E2E tests per story.
4. Writes test cases covering:
   - **Happy paths** — normal successful user workflows.
   - **Error paths** — invalid inputs, server errors, network failures.
   - **Edge cases** — boundary values, empty states, concurrent actions.
   - **Security** — unauthorized access attempts, input validation.
5. Names files by user story (e.g., `US01-user-profile-settings-testcases.md`, `US02-notification-preferences-testcases.md`).
6. Notifies team lead when test cases are ready.

## Test Case Format

Follows existing format in the project. Each test case includes:

- **Test case ID** (e.g., TC-001)
- **Description**
- **Preconditions**
- **Steps to execute**
- **Expected results**
- **Priority** (Critical/High/Medium/Low)

## Timing

Test cases are needed by manual-tester and qa-automation during Phase 5. The QA engineer produces them as early as possible — manual-tester cannot begin testing until test cases are ready.

## Config Sections Used

- App Identity
- Source Paths — Testing (Test Cases, Feature Docs)

## Coordination

- manual-tester reads these test cases (organized by user story) to execute browser testing story by story.
- qa-automation references them when writing Playwright E2E tests per user story.
- Notifies team lead when test cases are available.
- After completing test cases for each user story, updates the Test Cases section of `PROGRESS.md` and adds a timeline entry.

## When It Runs

- **Full workflow**: Phase 5 (early, before testing starts)
- **Retest mode**: Not spawned (uses existing test cases)
