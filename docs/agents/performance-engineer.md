# performance-engineer

Production-readiness performance auditor agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `performance-engineer` |
| **Model** | opus |
| **Color** | cyan |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/performance-engineer-REPORT.md` |

## Behavior

The performance engineer analyzes the codebase for performance bottlenecks across backend, frontend, and database layers. It focuses on issues that emerge at production scale — N+1 queries, missing indexes, unbounded queries, and frontend bundle bloat.

### What It Checks

1. **N+1 Queries** — Entity relationships cross-referenced with access patterns to detect N+1 loops
2. **Missing Indexes** — Query patterns matched against existing database indexes
3. **Unbounded Queries** — List endpoints checked for pagination and LIMIT
4. **Caching Opportunities** — Repeated data lookups that could benefit from caching
5. **Frontend Bundle** — Heavy dependencies, missing lazy loading, code splitting gaps
6. **Scheduled Tasks** — Interval configuration and concurrency control

### Report Structure

The report includes:
- Executive summary of performance posture
- Findings table by severity (Critical/High/Medium/Low)
- Database index recommendations table
- N+1 query inventory
- Caching recommendations
- Frontend bundle analysis

## Configuration

Uses `.claude/scrum-team-config.md` for project context. No additional configuration needed.

## Coordination

- Runs in parallel with all other auditors during Phase 1
- Findings feed into the triage in Phase 2
- Critical/High findings trigger re-audit in Phase 4

## When It Runs

- Phase 1 of `/prepare-for-production` (initial audit)
- Phase 4 of `/prepare-for-production` (re-audit if Critical/High findings were found)
