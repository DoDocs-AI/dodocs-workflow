# db-analyst

Production-readiness database analyst agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `db-analyst` |
| **Model** | opus |
| **Color** | cyan |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/db-analyst-REPORT.md` |

## Behavior

The database analyst reviews the database schema, JPA entity mappings, Flyway migration scripts, and query patterns for production readiness. It focuses on data integrity, performance, and migration safety.

### What It Checks

1. **Schema Review** — Entity relationships, field types, column constraints (nullable, unique, length)
2. **Constraint Completeness** — Foreign key ON DELETE behavior, unique constraints, NOT NULL, check constraints
3. **Index Coverage** — Foreign key indexes, WHERE clause indexes, ORDER BY indexes, composite indexes
4. **Migration Hygiene** — Sequential numbering, atomic changes, safe column additions, locking awareness
5. **Query Optimization** — N+1 prevention, pagination, projection, batch operations
6. **Data Integrity** — Soft/hard delete consistency, cascading deletes, orphan prevention
7. **Audit Fields** — Created/updated timestamps, UTC usage, user tracking
8. **Connection Pool** — Pool sizing, timeouts, idle connection management

### Report Structure

The report includes:
- Executive summary of database posture
- Findings table by severity
- Entity relationship map
- Index coverage matrix
- Migration inventory with safety assessment
- Schema recommendations
- Prioritized recommendations

## Configuration

Uses `.claude/scrum-team-config.md` for project context. No additional configuration needed.

## Coordination

- Runs in parallel with all other auditors during Phase 1
- Findings feed into the triage in Phase 2
- Critical/High findings (missing indexes, constraint gaps) trigger re-audit in Phase 4

## When It Runs

- Phase 1 of `/prepare-for-production` (initial audit)
- Phase 4 of `/prepare-for-production` (re-audit if Critical/High findings were found)
