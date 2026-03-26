Fix a bug with full hygiene — applies the fix via `/fix-the-issue`, then runs documentation sync, test estate maintenance, regression analysis, and optional multi-perspective validation before shipping.

## Usage

```
/fix-and-ship <description>                    # fix + full hygiene
/fix-and-ship --skip-docs <description>        # skip doc sync
/fix-and-ship --skip-tests <description>       # skip test maintenance
/fix-and-ship --skip-regression <description>  # skip regression check
/fix-and-ship --validate <description>         # force validation auditors
/fix-and-ship --no-merge <description>         # do everything but don't merge
```

Always autonomous (inherits from `/fix-the-issue`).

---

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Task tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

When calling the Task tool, ALWAYS include `mode: "bypassPermissions"` in the parameters.

Spawn all agents automatically as their phase begins — do NOT ask the user for permission to spawn any agent.

<boot>
BEFORE doing anything else, read `.claude/scrum-team-config.md` using the Read tool.
If the file does not exist, STOP immediately and tell the user:
"No scrum-team config found for this project. Run `dodocs-workflow init` or copy the template from `~/.claude/scrum-team-config.template.md` to `.claude/scrum-team-config.md` and fill in the values for this project."
Extract: ALL sections — App Identity, Tech Stack, Ports & URLs, Source Paths, Commands.
</boot>

---

## Step 0: Parse Arguments

Parse `$ARGUMENTS` for flags:
- `--skip-docs` → `SKIP_DOCS=true`
- `--skip-tests` → `SKIP_TESTS=true`
- `--skip-regression` → `SKIP_REGRESSION=true`
- `--validate` → `FORCE_VALIDATE=true`
- `--no-merge` → `NO_MERGE=true`
- Everything else after flags → `FIX_DESCRIPTION` (the issue description)

Derive `<fix-name>` from the description: kebab-case, max 40 characters.

Create the fix docs directory:
```bash
mkdir -p docs/fixes/<fix-name>
```

---

## Phase 1: Baseline Capture

**Goal:** Capture E2E test state on main before any changes.

Check if E2E tests exist in the project (look for Playwright config or test files).

If yes:
```bash
git stash  # if needed
git checkout main
npx playwright test --reporter=json 2>/dev/null || true
git checkout -
git stash pop  # if needed
```

Record results in `docs/fixes/<fix-name>/BASELINE.md`:
```markdown
# Fix Baseline — <fix-name>

## Test Results
- **Branch**: main (commit: <short-sha>)
- **Date**: <timestamp>
- **Result**: X passed, Y failed, Z skipped

## Pre-existing Failures
| Test | File | Failure |
|------|------|---------|
| ... | ... | ... |
```

If no E2E tests exist: record `No existing E2E tests — baseline skipped`.

---

## Phase 2: Fix Implementation

**Goal:** Apply the fix using the existing `/fix-the-issue` pipeline, stopping before merge.

Spawn a general-purpose agent:
```
Spawn Task:
  subagent_type = "general-purpose"
  mode          = "bypassPermissions"
  prompt        = """
    Read the file `~/.claude/commands/fix-the-issue.md` and execute the full workflow
    described in it. Set $ARGUMENTS to: `--no-merge <FIX_DESCRIPTION>`

    The --no-merge flag means: execute Phases 1-5 (Investigation, Implementation,
    Code Review, Integration Verification, QA Automation) but SKIP Phase 6 (Ship).
    Leave the fix branch active with an open PR but do NOT merge.

    When done, report back:
    - Fix branch name (fix/<fix-name>)
    - PR URL (if created)
    - List of all changed files
    - FIX-PLAN.md contents
  """
```

Wait for completion. Capture:
- `FIX_BRANCH` — the branch name
- `PR_URL` — the PR URL
- `CHANGED_FILES` — list of changed files
- `FIX_PLAN` — the fix plan contents

If Phase 2 fails → STOP and report the failure. Do not proceed to hygiene phases.

Print progress:
```
═══════════════════════════════════════════════════════
  fix-and-ship: <fix-name> — Phase 2 Complete: Fix Applied
═══════════════════════════════════════════════════════
```

---

## Phase 3: Documentation Sync

**Skip if** `SKIP_DOCS=true`.

**Goal:** Update project-level docs to reflect the fix.

Spawn `doc-sync-agent`:
```
Spawn Task:
  subagent_type = "doc-sync-agent"
  mode          = "bypassPermissions"
  prompt        = """
    Fix: <fix-name>
    Branch: fix/<fix-name>
    Changed files: <CHANGED_FILES>
    Fix description: <FIX_DESCRIPTION>

    Sync project documentation for this fix.
    Write your report to: docs/fixes/<fix-name>/DOC-SYNC-REPORT.md
  """
```

Wait for completion. Read the report.

**On failure:** Create fix task → spawn developer (`frontend-dev` or `backend-dev`) → `code-reviewer` reviews → re-check. Max 1 iteration.

Print progress:
```
═══════════════════════════════════════════════════════
  fix-and-ship: <fix-name> — Phase 3 Complete: Docs Synced
═══════════════════════════════════════════════════════
```

---

## Phase 4: Test Estate Maintenance

**Skip if** `SKIP_TESTS=true`.

**Goal:** Update existing tests project-wide that reference changed areas.

Spawn `test-estate-maintainer`:
```
Spawn Task:
  subagent_type = "test-estate-maintainer"
  mode          = "bypassPermissions"
  prompt        = """
    Fix: <fix-name>
    Branch: fix/<fix-name>
    Changed files: <CHANGED_FILES>
    Fix description: <FIX_DESCRIPTION>

    Update all existing tests project-wide that are affected by this fix's changes.
    Write your report to: docs/fixes/<fix-name>/TEST-MAINTENANCE-REPORT.md
  """
```

Wait for completion. Read the report.

**On failure:** Create fix task → spawn developer → `code-reviewer` reviews → re-check. Max 1 iteration.

Print progress:
```
═══════════════════════════════════════════════════════
  fix-and-ship: <fix-name> — Phase 4 Complete: Test Estate Updated
═══════════════════════════════════════════════════════
```

---

## Phase 5: Regression Check

**Skip if** `SKIP_REGRESSION=true`.

**Goal:** Run full E2E suite on the fix branch, compare against baseline, fix regressions.

**Step 1 — Start the app:**
```
Spawn Task:
  subagent_type = "tech-lead"
  mode          = "bypassPermissions"
  prompt        = "Start the full application on the current fix branch. Verify it compiles and runs."
```

**Step 2 — Run full E2E suite:**
```bash
npx playwright test --reporter=json 2>&1
```

**Step 3 — Analyze results:**
```
Spawn Task:
  subagent_type = "regression-analyst"
  mode          = "bypassPermissions"
  prompt        = """
    Fix: <fix-name>
    Baseline: docs/fixes/<fix-name>/BASELINE.md
    Test results: <paste JSON results or path>

    Classify all failures and produce:
    docs/fixes/<fix-name>/REGRESSION-REPORT.md
  """
```

Wait for completion. Read the regression report.

**Step 4 — Fix loop (max 2 iterations):**

If new regressions found:
1. For each fix task from regression-analyst:
   - Determine if frontend or backend fix needed
   - Spawn appropriate developer (`frontend-dev` or `backend-dev`) with `mode: "bypassPermissions"`
   - Developer fixes → spawn `code-reviewer` to review
2. Re-run failing tests only
3. Spawn regression-analyst again to re-classify
4. If still failing after 2 iterations → log as unresolved, continue

Print progress:
```
═══════════════════════════════════════════════════════
  fix-and-ship: <fix-name> — Phase 5 Complete: Regression Check Done
═══════════════════════════════════════════════════════
```

---

## Phase 6: Validation (Smart-Trigger, Optional)

**Only runs if** `FORCE_VALIDATE=true` OR the fix touches security/auth files.

**Smart trigger detection:**
```bash
git diff --name-only origin/main...HEAD > /tmp/fix-changed-files.txt
```

Check changed files against trigger patterns:

| Trigger Pattern | Auditor(s) to Spawn |
|----------------|---------------------|
| `**/auth/**`, `**/security*`, `**/session*`, `**/token*` | `security-auditor` |
| `*.tsx`, `*.vue`, `*.jsx`, `*.css`, `*.scss`, `*.html` | `ux-reviewer` + `accessibility-auditor` |
| `**/controller*`, `**/route*`, `**/entity*`, `**/migration*`, `*.sql` | `performance-engineer` |

If `FORCE_VALIDATE=true`, spawn ALL auditors regardless of trigger patterns.

**Spawn triggered auditors in parallel** (all with `mode: "bypassPermissions"`).

Each auditor writes its report to `docs/fixes/<fix-name>/`:
- `SECURITY-REPORT.md`
- `UX-REVIEW.md`
- `ACCESSIBILITY-REPORT.md`
- `PERFORMANCE-REPORT.md`

Wait for all auditors to complete.

**Fix loop for Critical findings (max 2 iterations):**
1. Create fix tasks from Critical findings → spawn developers
2. Developers fix → code-reviewer reviews
3. Re-run the auditor that found Critical issues
4. Proceed when zero Critical

Print progress:
```
═══════════════════════════════════════════════════════
  fix-and-ship: <fix-name> — Phase 6 Complete: Validation Done
═══════════════════════════════════════════════════════
```

---

## Phase 7: Ship

**Skip if** `NO_MERGE=true`. Instead, print the PR URL and report path.

Spawn **tech-lead** (`mode: "bypassPermissions"`) to:
1. If a PR does not already exist, create one:
   ```bash
   gh pr create --title "fix: <fix-name>" --body "..."
   ```
   PR body should include: issue description, root cause, files changed, hygiene results.
2. Squash-merge the PR:
   ```bash
   gh pr merge --squash --auto
   ```
   If auto-merge is not available:
   ```bash
   gh pr merge --squash
   ```
   If merge fails (conflicts, CI failures), report the blocker — do NOT force-merge.
3. After successful merge, switch back to main and pull:
   ```bash
   git checkout main && git pull
   ```

---

## Phase 8: Final Report

Produce `docs/fixes/<fix-name>/FIX-SHIP-REPORT.md`:

```markdown
# Fix Ship Report — <fix-name>

**Date**: <timestamp>
**Branch**: fix/<fix-name>
**PR**: <PR_URL>

## Fix Summary
- **Issue**: <description>
- **Root Cause**: <from FIX-PLAN.md>
- **Files Changed**: <count>

## Hygiene Results

| Phase | Status | Details |
|-------|--------|---------|
| Fix Implementation | PASS | <files changed count> files modified |
| Documentation Sync | PASS / SKIPPED | <files updated or "skipped"> |
| Test Maintenance | PASS / SKIPPED | <tests updated or "skipped"> |
| Regression Check | PASS / SKIPPED | <new regressions: 0 or count> |
| Validation | PASS / SKIPPED / N/A | <auditors triggered or "not triggered"> |
| Ship | MERGED / SKIPPED | <PR URL or "no-merge flag"> |

## Changed Files
| File | Change Type |
|------|------------|
| ... | ... |

## Overall: PASS / PASS WITH WARNINGS / FAIL
```

Print final summary:
```
═══════════════════════════════════════════════════════
  Fix & Ship Complete: <fix-name>
═══════════════════════════════════════════════════════
  Issue:      <description>
  Branch:     fix/<fix-name>
  PR:         <PR_URL>
  Status:     PASS
  Report:     docs/fixes/<fix-name>/FIX-SHIP-REPORT.md
═══════════════════════════════════════════════════════
```

---

## Git Strategy

- **Fix branch**: `fix/<fix-name>` (created by `/fix-the-issue`)
- **Commits**: One atomic commit per task — format `fix: <description>`
- **Hygiene commits**: Format `chore: update docs for <fix-name>` / `chore: update tests for <fix-name>`
- **PR**: Squash-merged to main at Phase 7

## Fix Docs Path

All fix documentation lives at `docs/fixes/<fix-name>/`:
- `FIX-PLAN.md` — root cause analysis and fix approach (from Phase 2)
- `BASELINE.md` — E2E test baseline before fix (from Phase 1)
- `DOC-SYNC-REPORT.md` — documentation sync results (from Phase 3)
- `TEST-MAINTENANCE-REPORT.md` — test estate maintenance results (from Phase 4)
- `REGRESSION-REPORT.md` — regression analysis results (from Phase 5)
- `SECURITY-REPORT.md` / `UX-REVIEW.md` / etc. — validation reports (from Phase 6)
- `FIX-SHIP-REPORT.md` — final summary (from Phase 8)

---

The issue to fix: $ARGUMENTS
