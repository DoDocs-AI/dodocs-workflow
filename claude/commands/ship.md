Full development lifecycle command — wraps each feature implementation with post-build hygiene (doc sync, test maintenance, regression analysis, multi-perspective validation) and feeds results back to developers for fixes before moving to the next feature.

## Usage

```
/ship                                    # auto-discover queue, implement all
/ship --features "feat-a, feat-b"        # explicit feature list
/ship --skip-validation                  # skip Phase 6 per feature
/ship --skip-docs                        # skip Phase 3 per feature
/ship --skip-regression                  # skip Phase 5 per feature
/ship --merge                            # auto-merge PRs after all pass
/ship --parallel                         # parallel features (when no conflicts)
/ship --size small|medium|large          # team size passed to scrum-team
```

Always autonomous (`--auto` implied).

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Task tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

When calling the Task tool, ALWAYS include `mode: "bypassPermissions"` in the parameters.

## Workflow

You are the **orchestrator** for the `/ship` lifecycle. Follow these phases exactly.

---

### Phase 0: Queue Discovery + Baseline

**Goal:** Find all prepared features and capture project state.

**Step 1 — Parse $ARGUMENTS:**
- Extract flags: `--features`, `--skip-validation`, `--skip-docs`, `--skip-regression`, `--merge`, `--parallel`, `--size`
- If neither `--features` nor any feature names provided → set `AUTO_DISCOVER=true`

**Step 2 — Read config:**
Read `.claude/scrum-team-config.md` using the Read tool. If the file does not exist, STOP:
"No scrum-team config found. Run `dodocs-workflow init` or copy the template."
Extract: ALL sections.
Also extract the **Feature Docs** path (default: `docs/features/`); store as `FEATURE_DOCS_PATH`.

**Step 3 — Queue discovery:**

If `AUTO_DISCOVER=true`:
- Scan `FEATURE_DOCS_PATH` for feature folders
- For each slug, read `docs/features/<slug>/STATUS`:
  - STATUS == `approved` → **include**
  - STATUS == `completed` → **skip**
  - STATUS == `in-progress` → **skip**
  - Any other value → **skip** with log: `Skipping <slug> — status is <status> (not approved)`
  - STATUS file missing → skip

If `--features` provided:
- Parse comma-separated list, trim whitespace
- Derive kebab-case slug for each

**Step 4 — Generate run ID:**
```bash
RUN_ID=$(date +%Y%m%d-%H%M%S)
mkdir -p docs/ship/$RUN_ID
```

**Step 5 — Baseline capture:**
- Check if E2E tests exist in the project
- If yes, run them on `main` branch (before any feature branches):
  ```bash
  git stash  # if needed
  git checkout main
  npx playwright test --reporter=json 2>/dev/null || true
  git checkout -  # return to previous branch
  git stash pop  # if needed
  ```
- Record results in `docs/ship/$RUN_ID/BASELINE.md`:
  ```markdown
  # Ship Baseline — <run-id>

  ## Test Results
  - **Branch**: main (commit: <short-sha>)
  - **Date**: <timestamp>
  - **Result**: X passed, Y failed, Z skipped

  ## Pre-existing Failures
  | Test | File | Failure |
  |------|------|---------|
  | ... | ... | ... |

  ## Doc Inventory
  | File | Last Modified |
  |------|--------------|
  | README.md | <date> |
  | ... | ... |
  ```
- If no E2E tests exist: record `No existing E2E tests — baseline skipped`

**Gate:** At least 1 approved feature found. Baseline captured.

---

### Phase 1: Dependency Analysis + Ordering

**Goal:** Determine safe execution order.

**Parse dependencies:**
- For each feature in the queue, read `docs/features/<slug>/FEATURE-BRIEF.md`
- Look for `[depends-on: ...]` annotations
- Build adjacency list: `{ feature → [dependencies] }`

**Cross-feature conflict analysis** (if `--parallel`):
- For each feature, read `docs/features/<slug>/ARCHITECTURE.md` (if exists)
- Extract file inventories
- Build shared-file map: `file_path → [feature-slugs]`
- If conflicts found, add synthetic dependencies

**Topological sort (Kahn's algorithm):**
1. Compute in-degree for each feature
2. Enqueue all features with in-degree 0
3. While queue non-empty: dequeue, append to sorted order, decrement dependents
4. If sorted list < total features → cycle detected → STOP with error

**Output:** `docs/ship/$RUN_ID/EXECUTION-PLAN.md`

```markdown
# Execution Plan — <run-id>

## Features: <count>
## Mode: sequential | parallel

| Order | Feature | Dependencies | Status |
|-------|---------|-------------|--------|
| 1 | user-auth | (none) | Pending |
| 2 | billing-dashboard | user-auth | Pending |
| 3 | dark-mode | user-auth, billing-dashboard | Pending |
```

**Gate:** Valid order. No cycles.

---

### Per-Feature Loop (Phases 2-6)

For each feature in topologically sorted order, execute Phases 2 through 6. After each feature completes all phases, update the baseline before starting the next feature.

Print progress:
```
═══════════════════════════════════════════════════════
  Feature 1/3: notification-center — Phase 2: Implementation
═══════════════════════════════════════════════════════
```

---

### Phase 2: Feature Implementation (per feature)

**Goal:** Build the feature using the existing scrum-team pipeline.

1. Set STATUS to `in-progress`: write `in-progress` to `docs/features/<slug>/STATUS`
2. Delegate to scrum-team:
   ```
   Spawn Task:
     subagent_type = "general-purpose"
     mode          = "bypassPermissions"
     prompt        = """
       Read the file `~/.claude/commands/scrum-team.md` and execute the full workflow
       described in it. Set $ARGUMENTS to: `--auto [--size <SIZE>] <feature-name>`
       (omit --size if SIZE was not provided)
     """
   ```
   Wait for completion.
3. Capture result: PR URL, branch name, pass/fail
4. If scrum-team fails → set STATUS=`failed`, log reason in `docs/ship/$RUN_ID/<slug>/IMPLEMENTATION.md`, skip to next feature

**Gate:** Feature PR created. Feature branch active.

**IMPORTANT:** After scrum-team completes, do NOT merge. Keep the feature branch active for hygiene phases.

---

### Phase 3: Documentation Sync (per feature)

**Skip if** `--skip-docs` flag is set.

**Goal:** Update project-level docs to reflect this feature.

Create output directory:
```bash
mkdir -p docs/ship/$RUN_ID/<slug>
```

**Spawn doc-sync-agent:**
```
Spawn Task:
  subagent_type = "doc-sync-agent"
  mode          = "bypassPermissions"
  prompt        = """
    Feature: <feature-slug>
    Branch: feature/<slug>

    Sync project documentation for this feature.
    Write your report to: docs/ship/<run-id>/<slug>/DOC-SYNC-REPORT.md
  """
```

**In parallel, if feature added new API endpoints** (check `git diff --name-only origin/main...HEAD` for controller/route files):
```
Spawn Task:
  subagent_type = "api-documenter"
  mode          = "bypassPermissions"
  prompt        = """
    Scope: only new/changed endpoints from feature/<slug>.
    Run git diff origin/main...HEAD to see changes.
    Write report to docs/ship/<run-id>/<slug>/API-DOCS-REPORT.md
  """
```

Wait for all agents to complete.

**Gate:** Docs compile/render clean. No broken references.

**On failure:** Create fix task → spawn developer → code-reviewer reviews → re-check.

---

### Phase 4: Test Estate Maintenance (per feature)

**Skip if** `--skip-regression` flag is set (test maintenance is part of regression pipeline).

**Goal:** Update existing tests broken by this feature.

**Spawn test-estate-maintainer:**
```
Spawn Task:
  subagent_type = "test-estate-maintainer"
  mode          = "bypassPermissions"
  prompt        = """
    Feature: <feature-slug>
    Branch: feature/<slug>

    Update all existing tests project-wide that are affected by this feature's changes.
    Write your report to: docs/ship/<run-id>/<slug>/TEST-MAINTENANCE-REPORT.md
  """
```

Wait for completion.

**Gate:** All updated test files parse/compile without errors.

**On failure:** Create fix task → spawn developer → fix → re-check.

---

### Phase 5: Full Regression Suite (per feature)

**Skip if** `--skip-regression` flag is set.

**Goal:** Run ALL E2E tests, compare against baseline, fix regressions.

**Step 1 — Start the app:**
```
Spawn Task:
  subagent_type = "tech-lead"
  mode          = "bypassPermissions"
  prompt        = "Start the full application on the current feature branch. Verify it compiles and runs."
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
    Feature: <feature-slug>
    Baseline: docs/ship/<run-id>/BASELINE.md
    Test results: <paste JSON results or path>

    Classify all failures and produce:
    docs/ship/<run-id>/<slug>/REGRESSION-REPORT.md
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

If test maintenance issues found:
- Re-spawn `test-estate-maintainer` with specific file list
- Re-run affected tests

**Gate:** Zero new regressions (or all resolved). Pre-existing failures don't block.

**Update baseline:** After this feature's regressions are resolved, update the running BASELINE.md with current test results for the next feature.

---

### Phase 6: Multi-Perspective Validation (per feature)

**Skip if** `--skip-validation` flag is set.

**Goal:** Audit the feature from relevant quality perspectives.

**Smart trigger detection:**
```bash
git diff --name-only origin/main...HEAD > /tmp/ship-changed-files.txt
```

Check changed files against trigger patterns:

| Trigger Pattern | Auditor(s) to Spawn |
|----------------|---------------------|
| `*.tsx`, `*.vue`, `*.jsx`, `*.css`, `*.scss`, `*.html` | `ux-reviewer` + `accessibility-auditor` |
| `**/auth/**`, `**/security*`, `**/migration*`, `**/session*`, `**/token*` | `security-auditor` |
| `**/controller*`, `**/route*`, `**/entity*`, `**/migration*`, `*.sql` | `performance-engineer` |
| Always | `quality-metrics-collector` |

**Spawn triggered auditors in parallel** (all with `mode: "bypassPermissions"`):

Each auditor writes its report to `docs/ship/$RUN_ID/<slug>/`:
- `UX-REVIEW.md`
- `ACCESSIBILITY-REPORT.md`
- `SECURITY-REPORT.md`
- `PERFORMANCE-REPORT.md`
- `QUALITY-METRICS.md`

Wait for all auditors to complete.

**Produce VALIDATION-SUMMARY.md:**
```markdown
# Validation Summary: <feature-slug>

## Auditors Triggered
| Auditor | Trigger | Result |
|---------|---------|--------|
| quality-metrics-collector | always | PASS |
| ux-reviewer | UI files changed | PASS |
| accessibility-auditor | UI files changed | WARN (2 High) |
| security-auditor | auth files changed | PASS |

## Findings by Severity
- Critical: 0
- High: 2
- Medium: 5
- Low: 8

## Critical Findings (MUST FIX)
(none — or list)

## Verdict: PASS / PASS WITH WARNINGS / FAIL
```

**Fix loop for Critical findings (max 2 iterations):**
1. Create fix tasks from Critical findings → spawn developers
2. Developers fix → code-reviewer reviews
3. Re-run the auditor that found Critical issues
4. Proceed when zero Critical

**Gate:** Zero Critical findings. High findings logged as warnings.

---

### Phase 7: Final Ship Report

**Goal:** Produce comprehensive report across all features.

Runs ONCE after all features complete their per-feature loops.

**Produce `docs/ship/$RUN_ID/SHIP-REPORT.md`:**

```markdown
# Ship Report — <run-id>

**Date**: <timestamp>
**Features**: <count> shipped, <count> failed, <count> skipped

## Per-Feature Results

| Feature | PR | Docs Synced | Tests Updated | Regressions | Validation | Status |
|---------|-----|------------|---------------|-------------|------------|--------|
| user-auth | #42 | 3 files | 2 tests | 0 new | PASS | DONE |
| billing | #43 | 1 file | 5 tests | 1 (fixed) | PASS | DONE |
| dark-mode | — | — | — | — | — | FAILED |

## Project Health: Before vs After
- E2E pass rate: <baseline>% → <final>%
- Doc coverage: <before> → <after>
- Total test cases: <before> → <after>

## Unresolved Issues
| Feature | Phase | Issue | Severity |
|---------|-------|-------|----------|
| (none, or list) |

## Overall: PASS / PASS WITH WARNINGS / FAIL

**PASS**: All features shipped, zero unresolved Critical/High findings
**PASS WITH WARNINGS**: All features shipped, some High findings logged
**FAIL**: One or more features failed or unresolved Critical findings
```

**Update STATUS files:**
- For each successfully completed feature: write `completed` to `docs/features/<slug>/STATUS`
- For failed features: STATUS already set to `failed` in Phase 2

**Auto-merge** (if `--merge` flag):
```
Spawn Task:
  subagent_type = "general-purpose"
  mode          = "bypassPermissions"
  prompt        = """
    Read the file `~/.claude/commands/merge-features.md` and execute the workflow.
    Set $ARGUMENTS to: (empty — merge all feature/* PRs)
    Only merge PRs for features that passed in SHIP-REPORT.md.
  """
```

Print final summary:
```
═══════════════════════════════════════════════════════
Ship Complete: <run-id>
═══════════════════════════════════════════════════════
Features:  3 shipped, 0 failed
Overall:   PASS
Report:    docs/ship/<run-id>/SHIP-REPORT.md
═══════════════════════════════════════════════════════
```

The feature list to process: $ARGUMENTS
