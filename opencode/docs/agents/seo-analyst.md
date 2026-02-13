# seo-analyst

Production-readiness SEO analyst agent.

## Spec

| Field | Value |
|-------|-------|
| **Name** | `seo-analyst` |
| **Model** | sonnet |
| **Color** | green |
| **Tools** | Read, Bash, Grep, Glob |
| **Spawned by** | `/prepare-for-production` orchestrator |
| **Output** | `docs/production-audit/seo-analyst-REPORT.md` |

## Behavior

The SEO analyst reviews public/marketing pages for search engine optimization best practices. It checks meta tags, Open Graph data, structured data, sitemap coverage, robots.txt configuration, and technical SEO signals.

### What It Checks

1. **Meta Tags** — Title, description, viewport, canonical on every public page
2. **Open Graph** — OG title, description, image, URL, type for social sharing
3. **Sitemap** — Existence, completeness, robots.txt reference
4. **Robots.txt** — Proper allow/disallow rules, sitemap reference
5. **Structured Data** — JSON-LD for Organization, Product, FAQ, Breadcrumbs
6. **Heading Structure** — Single H1 per page, logical hierarchy
7. **Link Structure** — Descriptive anchors, external link attributes
8. **Mobile SEO** — Viewport, responsive design, touch targets

### Report Structure

The report includes:
- Executive summary of SEO posture
- Findings table by severity
- Page-by-page SEO matrix
- Technical SEO checklist
- Prioritized recommendations

## Configuration

Uses `.opencode/scrum-team-config.md` for project context. No additional configuration needed.

## Coordination

- Runs in parallel with all other auditors during Phase 1
- Findings feed into the triage in Phase 2
- Medium/Low findings are typically not re-audited in Phase 4

## When It Runs

- Phase 1 of `/prepare-for-production` (initial audit)
- Phase 4 only if Critical/High findings were found (rare for SEO)
