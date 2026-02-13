# devops-engineer

Production-readiness DevOps engineer agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `devops-engineer` |
| **Model** | sonnet |
| **Color** | blue |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/devops-engineer-REPORT.md` |

## Behavior

The DevOps engineer audits the infrastructure configuration for production deployment readiness. It reviews Dockerfiles, docker-compose configuration, health checks, CI/CD pipelines, environment variables, logging, and graceful shutdown handling.

### What It Checks

1. **Dockerfile** — Multi-stage build, non-root user, pinned versions, health check, .dockerignore
2. **Docker Compose** — Resource limits, restart policies, health checks, environment config
3. **Health Checks** — Liveness/readiness probes, custom health checks for dependencies
4. **Environment Config** — Env vars for secrets, no hardcoded URLs, profile separation
5. **CI/CD** — Build pipeline, test execution, deployment automation, rollback
6. **Logging** — Structured logging, appropriate levels, no sensitive data in logs
7. **Graceful Shutdown** — SIGTERM handling, in-flight request completion
8. **SSL/TLS** — TLS configuration, security headers (CSP, HSTS, X-Frame-Options)
9. **Scaling** — Stateless design, connection pooling, shared storage

### Report Structure

The report includes:
- Executive summary of infrastructure posture
- Findings table by severity
- Production readiness checklist (pass/fail per item)
- Prioritized recommendations

## Configuration

Uses `.opencode/scrum-team-config.md` for project context. No additional configuration needed.

## Coordination

- Runs in parallel with all other auditors during Phase 1
- Findings feed into the triage in Phase 2
- Also acts as a fixer in Phase 3 for infrastructure-related issues
- Critical/High findings trigger re-audit in Phase 4

## When It Runs

- Phase 1 of `/prepare-for-production` (initial audit)
- Phase 3 of `/prepare-for-production` (implements infrastructure fixes)
- Phase 4 of `/prepare-for-production` (re-audit if Critical/High findings were found)
