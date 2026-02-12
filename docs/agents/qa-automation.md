# QA Automation

Writes Playwright E2E tests incrementally as manual-tester passes each scenario. Runs in parallel with testing rather than waiting for all tests to pass first.

## Spec

| Property | Value |
|----------|-------|
| **Agent file** | `agents/qa-automation.md` |
| **Model** | sonnet |
| **Active in phases** | 5 (incremental E2E writing), 6 (full suite run) |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Inputs** | Passed manual test scenarios, existing E2E test patterns |
| **Outputs** | Playwright E2E test files |

## Incremental Approach

Does NOT wait for all manual tests to pass:

1. **Start early** — studies existing E2E tests, sets up test scaffolding (describe blocks, fixtures, page objects).
2. **Watch for passed scenarios** — monitors messages from manual-tester and TaskList.
3. **Write tests incrementally** — as each scenario passes manual testing, writes the Playwright E2E test.
4. **Run and verify** — executes each new test to confirm it passes.
5. **Continue** until all scenarios are automated.

## Test Patterns

- Follows existing test structure and naming conventions.
- Uses existing fixtures for authentication (Auth Fixture from config).
- Uses page object pattern if existing tests use it.
- Tests against `localhost:<Frontend Port>`.

## Phase 6 Role

After all individual tests are written, runs the complete E2E test suite to verify no conflicts or regressions.

## Config Sections Used

- Ports & URLs (Frontend Port, Backend Port)
- Routing (Route Prefix)
- Source Paths — Testing (E2E Tests, Fixtures, Page Objects, Auth Fixture, Playwright Config)

## Coordination

- Receives notifications from manual-tester when scenarios pass.
- Monitors TaskList for test scenario status.
- Works in parallel with manual-tester — doesn't wait for all manual tests.

## When It Runs

- **Full workflow**: Phase 5 (incremental) + Phase 6 (full suite)
- **Retest mode**: Not spawned
