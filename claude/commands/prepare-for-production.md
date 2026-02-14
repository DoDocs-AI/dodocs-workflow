# /prepare-for-production

Run a comprehensive production-readiness audit of the codebase using 10 specialized auditor agents, then triage findings, fix issues, and verify fixes.

## Usage

```
/prepare-for-production
/prepare-for-production --only security,performance
/prepare-for-production --only security,performance,db
```

## Arguments

- `--only <auditors>` — Comma-separated list of specific auditors to run. Valid values: `security`, `performance`, `accessibility`, `seo`, `devops`, `error-handler`, `dependency`, `api-docs`, `db`, `load-test`. If omitted, all 10 auditors run.

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Task tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts. This applies to ALL auditor agents and ALL developer agents in every phase.

When calling the Task tool, ALWAYS include `mode: "bypassPermissions"` in the parameters.

## Workflow

You are the **orchestrator** for the production-readiness audit. Follow these 4 phases exactly.

---

### Phase 1: Parallel Audit

**Goal:** Run all auditor agents in parallel. Each produces a report.

First, read `.claude/scrum-team-config.md` for project context.

Create the output directory:
```bash
mkdir -p docs/production-audit
```

Parse the `--only` argument if provided. Map short names to agent names:
- `security` → `security-auditor`
- `performance` → `performance-engineer`
- `accessibility` → `accessibility-auditor`
- `seo` → `seo-analyst`
- `devops` → `devops-engineer`
- `error-handler` → `error-handler`
- `dependency` → `dependency-auditor`
- `api-docs` → `api-documenter`
- `db` → `db-analyst`
- `load-test` → `load-tester`

If `--only` is provided, only spawn those agents. Otherwise spawn all 10.

**Spawn each auditor using the Task tool** with these settings:
- `subagent_type`: Use the agent name (e.g., `security-auditor`)
- `mode`: `"bypassPermissions"` — REQUIRED for all agents
- `prompt`: "Read `.claude/scrum-team-config.md` for project context. Perform your full audit checklist against the codebase. Write your report to `docs/production-audit/<agent-name>-REPORT.md`. Be thorough — check every file, every endpoint, every pattern."
- `model`: Use the model specified in the agent definition (opus for security, performance, db; sonnet for others)
- `run_in_background`: true (so all 10 run in parallel)

**IMPORTANT:** Launch ALL auditors in a SINGLE message so they run concurrently.

Wait for all auditors to complete. Check each output file:
```bash
ls -la docs/production-audit/*-REPORT.md
```

---

### Phase 2: Triage + Task Creation

**Goal:** Read all reports, consolidate findings by severity, create fix tasks.

Read every report in `docs/production-audit/`:
```bash
ls docs/production-audit/*-REPORT.md
```

Read each report file. For each finding across all reports:

1. **Deduplicate** — Same issue found by multiple auditors counts once
2. **Classify severity:**
   - **Critical** — Security vulnerabilities, data exposure, broken auth, data corruption risks
   - **High** — Performance bottlenecks (N+1, missing indexes), missing error handling, accessibility blockers
   - **Medium** — SEO gaps, missing docs, infra improvements, outdated dependencies
   - **Low** — Nice-to-haves, minor optimizations, style improvements

3. **Create a consolidated triage document** at `docs/production-audit/TRIAGE.md`:

```markdown
# Production Audit Triage

**Date:** [date]
**Reports Reviewed:** [count]
**Total Findings:** [count]

## Summary by Severity

| Severity | Count | Fix Required Before Production |
|----------|-------|-------------------------------|
| Critical | X | YES |
| High | X | YES |
| Medium | X | Recommended |
| Low | X | Optional |

## Critical Findings (Must Fix)

| # | Finding | Source Report | Assigned To | Task ID |
|---|---------|-------------|-------------|---------|

## High Findings (Should Fix)

[Same table]

## Medium Findings (Recommended)

[Same table]

## Low Findings (Optional)

[Same table]
```

4. **Create fix tasks** using TaskCreate for Critical and High findings. Assign to:
   - `backend-dev-1` — Backend security fixes, DB indexes, error handling, API docs
   - `frontend-dev-1` — Frontend performance, accessibility fixes, SEO tags, error boundaries
   - `devops-engineer` — Infrastructure fixes (Dockerfile, health checks, CI/CD)

Group related fixes into single tasks where appropriate (e.g., "Add missing auth annotations to 5 endpoints" is one task, not five).

---

### Phase 3: Fix + Review

**Goal:** Fix Critical and High issues, review each fix.

For each fix task:

1. **Spawn the appropriate developer agent** (use `general-purpose` subagent_type with `mode: "bypassPermissions"`):
   - Give it the specific task details from the triage
   - Tell it to make atomic commits per fix
   - Tell it to run relevant compile/build checks after each fix

2. **After each fix, verify:**
   - Backend compiles: `./mvnw compile`
   - Frontend compiles: `cd src/main/webapp && npx tsc --noEmit`
   - The specific fix addresses the finding

3. **Review pattern:** After fixes are complete, review the changes:
   - Check that fixes are correct and complete
   - Check that fixes don't introduce new issues
   - Check that the app still compiles and runs

---

### Phase 4: Re-audit + Sign-off

**Goal:** Verify fixes by re-running auditors that found Critical/High issues.

1. Identify which auditors found Critical or High findings
2. Re-run ONLY those auditors (use `--only` equivalent)
3. Compare new reports against the triage
4. Produce a final summary

Create `docs/production-audit/SUMMARY.md`:

```markdown
# Production Readiness Summary

**Date:** [date]
**Audit Duration:** [time from start to finish]

## Overall Status: [PASS / PASS WITH WARNINGS / FAIL]

## Audit Results

| Area | Auditor | Critical | High | Medium | Low | Status |
|------|---------|----------|------|--------|-----|--------|
| Security | security-auditor | 0 | 0 | X | X | PASS |
| Performance | performance-engineer | 0 | 0 | X | X | PASS |
| Accessibility | accessibility-auditor | 0 | 0 | X | X | PASS |
| SEO | seo-analyst | 0 | 0 | X | X | PASS |
| DevOps | devops-engineer | 0 | 0 | X | X | PASS |
| Error Handling | error-handler | 0 | 0 | X | X | PASS |
| Dependencies | dependency-auditor | 0 | 0 | X | X | PASS |
| API Docs | api-documenter | 0 | 0 | X | X | PASS |
| Database | db-analyst | 0 | 0 | X | X | PASS |
| Load Testing | load-tester | 0 | 0 | X | X | PASS |

## Fixes Applied

| # | Finding | Fix Description | Commit | Verified |
|---|---------|----------------|--------|----------|

## Remaining Items (Medium/Low)

| # | Finding | Severity | Recommendation |
|---|---------|----------|---------------|

## Sign-off

- [ ] All Critical findings resolved
- [ ] All High findings resolved
- [ ] Application compiles (backend + frontend)
- [ ] No new issues introduced by fixes
- [ ] Production deployment checklist reviewed
```

**Pass criteria:**
- PASS: Zero Critical, zero High findings remaining
- PASS WITH WARNINGS: Zero Critical, some High with documented justification
- FAIL: Any Critical findings remaining

---

## Notes

- All reports are written to `docs/production-audit/`
- The orchestrator (you) acts as the triage lead in Phase 2
- Existing agents (`backend-dev-1`, `frontend-dev-1`, `code-reviewer`) are reused for Phase 3
- The `scrum-team-config.md` provides all project context needed by auditors
