# api-documenter

Production-readiness API documentation agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `api-documenter` |
| **Model** | sonnet |
| **Color** | green |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/api-documenter-REPORT.md` |

## Behavior

The API documenter inventories all REST endpoints, checks for existing API documentation coverage (OpenAPI/Swagger annotations), and identifies documentation gaps. It ensures that every endpoint has clear request/response contracts.

### What It Checks

1. **Endpoint Inventory** — Every JAX-RS resource class, every annotated method, full URL paths
2. **OpenAPI Coverage** — `@Operation`, `@APIResponse`, `@Tag`, `@Parameter` annotations
3. **DTO Documentation** — `@Schema` annotations on request/response DTOs
4. **Auth Documentation** — Authentication requirements per endpoint
5. **Validation Documentation** — Bean Validation annotations and their user-facing messages
6. **Pagination** — Consistent pagination format, documented parameters
7. **Error Responses** — Common error codes and their meanings documented

### Report Structure

The report includes:
- Executive summary of API documentation posture
- Findings table by severity
- Complete endpoint inventory table
- Documentation coverage by resource class
- Missing documentation table
- Prioritized recommendations

## Configuration

Uses `.claude/scrum-team-config.md` for project context. No additional configuration needed.

## Coordination

- Runs in parallel with all other auditors during Phase 1
- Findings feed into the triage in Phase 2
- Typically produces Medium/Low findings (documentation is rarely Critical)

## When It Runs

- Phase 1 of `/prepare-for-production` (initial audit)
- Phase 4 only if Critical/High findings were found (rare for API docs)
