# security-auditor

Production-readiness security auditor agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `security-auditor` |
| **Model** | opus |
| **Color** | red |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/security-auditor-REPORT.md` |

## Behavior

The security auditor performs a comprehensive OWASP top 10 review of the entire codebase. It systematically checks every REST endpoint for authentication annotations, scans for hardcoded secrets, reviews dependency versions for known CVEs, and evaluates frontend security practices.

### What It Checks

1. **OWASP Top 10** — All 10 categories systematically reviewed against the codebase
2. **Auth Coverage** — Every JAX-RS endpoint cross-referenced with auth annotations
3. **Hardcoded Secrets** — Source code scanned for API keys, tokens, passwords, private keys
4. **Dependency CVEs** — Maven and npm dependency versions checked against known vulnerabilities
5. **Frontend Security** — CSP headers, token storage, XSS prevention, cookie flags

### Report Structure

The report includes:
- Executive summary of security posture
- Findings table by severity (Critical/High/Medium/Low)
- Dependency CVE summary table
- Auth coverage matrix (every endpoint with auth status)
- Prioritized recommendations

## Configuration

Uses `.opencode/scrum-team-config.md` for project context. No additional configuration needed.

## Coordination

- Runs in parallel with all other auditors during Phase 1
- Findings feed into the triage in Phase 2
- Critical/High findings trigger re-audit in Phase 4

## When It Runs

- Phase 1 of `/prepare-for-production` (initial audit)
- Phase 4 of `/prepare-for-production` (re-audit if Critical/High findings were found)
