# dependency-auditor

Production-readiness dependency auditor agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `dependency-auditor` |
| **Model** | sonnet |
| **Color** | white |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/dependency-auditor-REPORT.md` |

## Behavior

The dependency auditor reviews all Maven and npm dependencies for security vulnerabilities, outdated versions, license compliance, and unnecessary packages. It treats every dependency as a potential attack surface.

### What It Checks

1. **Maven Vulnerabilities** — Dependency tree analysis, known CVEs in direct and transitive deps
2. **npm Vulnerabilities** — Package audit, known vulnerabilities in the dependency graph
3. **Outdated Versions** — Current vs latest stable for critical dependencies
4. **Unused Dependencies** — Packages declared but never imported
5. **License Compliance** — Copyleft license detection, missing license fields
6. **Bundle Impact** — Heavy dependencies with lighter alternatives
7. **Supply Chain** — Lock file integrity, version pinning, update automation

### Report Structure

The report includes:
- Executive summary of dependency health
- Findings table by severity
- Maven dependency health table
- npm dependency health table
- License summary
- Prioritized recommendations

## Configuration

Uses `.opencode/scrum-team-config.md` for project context. No additional configuration needed.

## Coordination

- Runs in parallel with all other auditors during Phase 1
- Findings feed into the triage in Phase 2
- Critical findings (CVEs) trigger re-audit in Phase 4

## When It Runs

- Phase 1 of `/prepare-for-production` (initial audit)
- Phase 4 of `/prepare-for-production` (re-audit if Critical/High findings were found)
