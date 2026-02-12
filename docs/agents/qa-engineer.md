# QA Engineer

Writes manual test cases as `.md` files covering happy paths, error paths, and edge cases. Produces test cases early so manual-tester and qa-automation can use them during incremental testing.

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
3. Writes test cases covering:
   - **Happy paths** — normal successful user workflows.
   - **Error paths** — invalid inputs, server errors, network failures.
   - **Edge cases** — boundary values, empty states, concurrent actions.
   - **Security** — unauthorized access attempts, input validation.
4. Names files descriptively (e.g., `user-settings-testcases.md`).
5. Notifies team lead when test cases are ready.

## Test Case Format

Follows existing format in the project. Each test case includes:

- **Test case ID** (e.g., TC-001)
- **Description**
- **Preconditions**
- **Steps to execute**
- **Expected results**
- **Priority** (Critical/High/Medium/Low)

## Timing

Test cases are needed by manual-tester and qa-automation during Phase 5. The QA engineer produces them as early as possible — ideally before the first developer task is code-reviewed.

## Config Sections Used

- App Identity
- Source Paths — Testing (Test Cases, Feature Docs)

## Coordination

- manual-tester reads these test cases to execute browser testing.
- qa-automation references them when writing Playwright E2E tests.
- Notifies team lead when test cases are available.

## When It Runs

- **Full workflow**: Phase 5 (early, before testing starts)
- **Retest mode**: Not spawned (uses existing test cases)
