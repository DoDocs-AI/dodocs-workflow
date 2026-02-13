# load-tester

Production-readiness load testing engineer agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `load-tester` |
| **Model** | sonnet |
| **Color** | red |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/load-tester-REPORT.md` |

## Behavior

The load tester identifies critical user paths, analyzes endpoint resource intensity, estimates system capacity, and designs load test scenarios. It focuses on finding bottlenecks before production traffic does.

### What It Checks

1. **Critical Path Identification** — Authentication flows, core business operations, list/search, file operations
2. **Endpoint Load Profile** — Expected RPS, DB queries per request, file I/O, external call dependencies
3. **Database Under Load** — Connection pool vs concurrency, lock contention, slow query potential
4. **File Operations** — MinIO throughput, large file memory usage, concurrent access
5. **Background Jobs** — Queue capacity, processing rate, backpressure handling
6. **Resource Analysis** — JVM heap config, thread pool sizing, file descriptor limits
7. **Load Test Scenarios** — Smoke, load, stress, spike, and endurance test designs
8. **Capacity Planning** — Max concurrent users estimate, first bottleneck, scaling strategy

### Report Structure

The report includes:
- Executive summary of capacity posture
- Findings table by severity
- Critical path inventory
- Endpoint load profile table
- Estimated capacity table
- Load test scenarios (ready to run)
- Scaling recommendations

## Configuration

Uses `.opencode/scrum-team-config.md` for project context. No additional configuration needed.

## Coordination

- Runs in parallel with all other auditors during Phase 1
- Findings feed into the triage in Phase 2
- Load test scenarios can be executed in Phase 3 if needed
- Re-audit in Phase 4 if Critical findings were found

## When It Runs

- Phase 1 of `/prepare-for-production` (initial audit and scenario design)
- Phase 4 of `/prepare-for-production` (re-audit if Critical/High findings were found)
