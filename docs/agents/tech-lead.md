# Tech Lead

Creates feature branches, runs compile gates, starts the full application, monitors for build/runtime issues, files bug tasks, and creates PRs when complete.

## Spec

| Property | Value |
|----------|-------|
| **Agent file** | `agents/tech-lead.md` |
| **Model** | sonnet |
| **Active in phases** | 4 (git), 5 (compile gate + app), 6 (verification), 7 (PR) |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Outputs** | Feature branch, compile gate results, bug tasks, PR |

## Responsibilities by Phase

### Phase 4 — Git Branch Setup
- Creates `feature/<feature-name>` branch.
- Confirms branch is created and clean.

### Phase 5 — Compile Gate + App Startup
1. **Compile gate** (must pass before testing):
   - Run Compile Backend command — zero errors required.
   - Run Compile Frontend command — zero errors required.
2. **Start environment**:
   - Start DB, Start Storage, Start Backend, Start Frontend (using Commands from config).
3. **Signal "app ready"** — message to team lead unblocks manual-tester.
4. **Incremental verification** — as tasks complete, checks backend logs for exceptions, frontend console for errors.
5. **File bugs** — creates tasks with reproduction steps, error logs, assigns to responsible developer.

### Phase 6 — Integration Verification
- Full app restart.
- Regression check.
- Confirm complete feature flow works end-to-end.

### Phase 7 — Create PR
- `gh pr create` from feature branch to main.
- Includes summary of all changes.
- Signals completion to team lead.

## Bug Task Format

- Reproduction steps
- Error logs/messages
- Screenshots if applicable
- Assignment: UI issues to frontend-dev, API/DB issues to backend-dev

## Config Sections Used

- Commands (Start DB, Start Storage, Start Backend, Start Frontend, Compile Backend, Compile Frontend)
- Ports & URLs (Frontend Port, Backend Port, Dev Domain)
- Tech Stack

## When It Runs

- **Full workflow**: Phase 4 through Phase 7
- **Retest mode**: Starts environment, runs compile gate, monitors for issues
