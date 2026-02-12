# error-handler

Production-readiness error handling auditor agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `error-handler` |
| **Model** | sonnet |
| **Color** | yellow |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/error-handler-REPORT.md` |

## Behavior

The error handler auditor reviews the codebase for consistent error handling patterns, proper error responses, frontend error boundaries, and logging coverage. It ensures that production errors are caught, logged, and communicated to users appropriately.

### What It Checks

1. **Backend Error Responses** — Consistent error DTO structure, exception mappers, correct HTTP status codes
2. **Exception Handling** — No swallowed exceptions, no generic catch-alls hiding errors, no stack traces in responses
3. **Validation Errors** — Field-level error messages, 400 status with structured body
4. **Frontend Error Boundaries** — React Error Boundaries at page and component levels
5. **API Error Handling** — All fetch calls have error handling, 401/403 trigger auth flow
6. **User-Facing Messages** — User-friendly (not technical), suggest corrective action
7. **Logging Coverage** — All catch blocks log, appropriate log levels, no sensitive data

### Report Structure

The report includes:
- Executive summary of error handling posture
- Findings table by severity
- Backend error response inventory
- Frontend error boundary coverage matrix
- Logging gap analysis
- Prioritized recommendations

## Configuration

Uses `.claude/scrum-team-config.md` for project context. No additional configuration needed.

## Coordination

- Runs in parallel with all other auditors during Phase 1
- Findings feed into the triage in Phase 2
- Critical/High findings trigger re-audit in Phase 4

## When It Runs

- Phase 1 of `/prepare-for-production` (initial audit)
- Phase 4 of `/prepare-for-production` (re-audit if Critical/High findings were found)
