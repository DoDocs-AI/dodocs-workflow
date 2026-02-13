# accessibility-auditor

Production-readiness accessibility auditor agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `accessibility-auditor` |
| **Model** | sonnet |
| **Color** | magenta |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/accessibility-auditor-REPORT.md` |

## Behavior

The accessibility auditor reviews the React frontend for WCAG 2.1 Level AA compliance. It systematically checks semantic HTML usage, ARIA attributes, keyboard navigation, form accessibility, color contrast patterns, and focus management.

### What It Checks

1. **Semantic HTML** — Proper use of landmarks, headings, buttons vs clickable divs
2. **ARIA Attributes** — Modals, live regions, custom components have proper ARIA
3. **Keyboard Navigation** — All interactive elements reachable via keyboard, no traps
4. **Images/Media** — Alt text on images, accessible SVG icons, icon-only button labels
5. **Forms** — Label associations, error message linking, required field indicators
6. **Color/Contrast** — Contrast ratios, information not conveyed by color alone
7. **Focus Management** — Modal focus traps, route change focus, visible focus indicators

### Report Structure

The report includes:
- Executive summary of accessibility posture
- Findings table with WCAG criterion references
- Component accessibility matrix
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
