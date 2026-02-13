# QA Automation

Writes Playwright E2E tests per user story after manual-tester passes all scenarios for that story. Works alongside testing at the story level.

## Spec

| Property | Value |
|----------|-------|
| **Agent file** | `agents/qa-automation.md` |
| **Model** | sonnet |
| **Active in phases** | 5 (story-level E2E writing), 6 (full suite run) |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Inputs** | Passed manual test scenarios, existing E2E test patterns |
| **Outputs** | Playwright E2E test files |

## Story-Based Approach

Writes E2E tests per user story after manual-tester passes all scenarios for that story:

1. **Start early** — studies existing E2E tests, sets up test scaffolding (describe blocks, fixtures, page objects).
2. **Watch for passed user stories** — monitors messages from manual-tester for user stories where all scenarios pass.
3. **Write tests per user story** — when a user story passes manual testing, writes the Playwright E2E tests covering all scenarios for that story.
4. **Run and verify** — executes the tests for that story to confirm they pass.
5. **Continue** until all user stories are automated.

## Test Patterns

- Follows existing test structure and naming conventions.
- Uses existing fixtures for authentication (Auth Fixture from config).
- Uses page object pattern if existing tests use it.
- Tests against `localhost:<Frontend Port>`.

## Phase 6 Role

After all user stories are automated, runs the complete E2E test suite to verify no conflicts or regressions.

## Config Sections Used

- Ports & URLs (Frontend Port, Backend Port)
- Routing (Route Prefix)
- Source Paths — Testing (E2E Tests, Fixtures, Page Objects, Auth Fixture, Playwright Config)

## Coordination

- Receives notifications from manual-tester when all scenarios for a user story pass.
- Monitors TaskList for user story testing status.
- Works alongside manual-tester at the story level — writes E2E tests per user story as each story passes.
- After writing E2E tests for each user story, updates the E2E Automation section of `PROGRESS.md` and adds a timeline entry.

## When It Runs

- **Full workflow**: Phase 5 (story-level) + Phase 6 (full suite)
- **Retest mode**: Not spawned
