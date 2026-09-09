# Command Reference

Every slash command dodocs-workflow installs, what it takes, and what it writes.
27 commands for Claude Code; OpenCode ships a 5-command subset (marked **OC** below).

All commands run from your project root and read `.claude/scrum-team-config.md`
unless noted otherwise. Commands that build features also require `openspec/` in
the project root (see [Setup and maintenance](#setup-and-maintenance)).

- New here? Start with the [first-feature tutorial](tutorial-first-feature.md).
- Trying to get a specific job done? See [common tasks](howto-common-tasks.md).
- Wondering why the pipeline is shaped this way? See [design notes](explanation-pipeline-design.md).

## Table of Contents

- [Setup and maintenance](#setup-and-maintenance)
- [Building features](#building-features)
- [Fixing and landing](#fixing-and-landing)
- [Requirements and discovery](#requirements-and-discovery)
- [Production readiness](#production-readiness)
- [Product and GTM pipelines](#product-and-gtm-pipelines)
- [Design](#design)
- [Knowledge and operations](#knowledge-and-operations)
- [Data connectors](#data-connectors)
- [Flags that appear across commands](#flags-that-appear-across-commands)

---

## Setup and maintenance

### `/dodocs-workflow` **OC**

Manage the installation in the current project.

| Subcommand | Effect |
|---|---|
| `init` (or no argument) | Copies the config template to `.claude/scrum-team-config.md`, runs the doctor checks, scaffolds `openspec/` with the pinned CLI, smoke-checks it with `validate --all` |
| `version` | Prints the installed version from `~/.claude/.dodocs-workflow-version` |
| `upgrade` | Pulls and installs the latest release |
| `doctor` | Verifies the OpenSpec toolchain: Node.js >= 20, the pinned CLI reports `1.6.0`, `openspec/` validates with `--strict` if present, and the config carries an `## OpenSpec` section |

`init` is safe to re-run. If Node.js >= 20 is missing it warns and continues, so
you can install Node and re-run to finish the OpenSpec half.

### `/dw-upgrade`

Upgrade dodocs-workflow to the latest GitHub release. Queries
`repos/DoDocs-AI/dodocs-workflow/releases/latest` with `gh`, shows your current
version, then runs the install script from that tag.

Requires: `gh` authenticated.

### `/spec-bootstrap`

One-time migration for projects that predate the OpenSpec pipeline. Derives
`openspec/specs/<domain>/spec.md` from existing feature docs and the codebase,
and seeds change proposals for features still in flight.

| Argument | Effect |
|---|---|
| *(none)* | Full bootstrap, with interactive approval of the derived domain list |
| `--dry-run` | Propose the domain list and per-feature mapping, write nothing |

Your legacy `FEATURE-BRIEF.md` files are left untouched as read-only history.

---

## Building features

### `/scrum-team <feature>` **OC**

The core pipeline. Runs a 13-agent scrum team through six phases: requirements,
UX plus architecture, task breakdown, build plus test, integration verification,
ship. Produces a pull request.

| Argument | Effect |
|---|---|
| `<feature name>` | Required. Becomes the branch slug (`feature/<slug>`) |
| `--auto` | Skip the human checkpoint after Phase 2; derive requirements without interviewing you |
| `--size small\|medium\|large` | Team size. Without it, size is guessed from the feature name |
| `--retest <feature>` | Skip Phases 1 to 3 and re-run testing against existing test cases with 5 agents |
| `--skip-regression` | Skip the pre-branch E2E baseline run on main |

Team size controls how many agents spawn and which phases run:

| Size | Agents | Notes |
|---|---|---|
| `small` | 9 | Frontend only, no migrations, under 5 files. Skips Phase 2 entirely (no architect, no mockups) |
| `medium` | 11 | Full stack, one backend dev, architect runs without plan mode |
| `large` | 13 | Default. Full team, architect uses plan mode unless `--auto` |

Auto-detection when `--size` is absent: names containing `button`, `color`,
`style`, `layout`, `UI`, `page`, `component`, `display` read as small; `API`,
`endpoint`, `schema`, `database`, `query` read as medium; anything else large.

Writes: `openspec/changes/<slug>/` (proposal, delta specs, design.md, tasks.md),
`docs/features/<slug>/` (PROGRESS.md, UX-DESIGN.md, mockups, test reports).

Full walkthrough: [the pipeline diagram](scrum-team-pipeline.html).

### `/prepare-feature <feature>`

Daytime half of the day/night split. Interactive requirements, then
framework-native mockups built from your real components, then validation, then
your approval. Stops before any production code is written.

| Argument | Effect |
|---|---|
| `<feature name>` | Required |
| `--auto` | Run without the interactive requirements interview |
| `--port <n>` | Mockup preview server port (default 3100) |

Writes `docs/features/<slug>/` including `STATUS`. When `STATUS` is `approved`,
a later `/scrum-team` run on the same slug skips its own requirements phase and
reuses the approved mockups.

### `/prepare-features`

Same preparation pipeline across several features in sequence.

| Argument | Effect |
|---|---|
| *(none)* | Auto-discover pending features under `docs/features/` |
| `--features "a, b, c"` | Explicit comma-separated list |
| `--file <path>` | Read the list from a file, for example `docs/backlog.md` |

### `/batch-features`

Night half of the split. Runs `/scrum-team --auto` over a list of features, one
after another or in parallel.

| Argument | Effect |
|---|---|
| *(none)* | Auto-discover from `docs/features/` |
| `--features "a, b, c"` | Explicit list |
| `--file <path>` | Read the list from a file |
| `--parallel` | Run features concurrently instead of sequentially |
| `--size small\|medium\|large` | Passed through to each `/scrum-team` run |

Always runs in `--auto` mode. There is no human checkpoint.

### `/ship`

Wraps feature implementation with post-build hygiene. Per feature it runs
implementation, documentation sync, test estate maintenance, a full regression
suite, and multi-perspective validation, feeding failures back to the developers
before moving on. Eight phases including queue discovery and dependency ordering.

| Argument | Effect |
|---|---|
| *(none)* | Auto-discover the queue and implement everything in it |
| `--features "a, b"` | Explicit list |
| `--size small\|medium\|large` | Team size passed to `/scrum-team` |
| `--parallel` | Run features concurrently when they do not conflict |
| `--merge` | Auto-merge the PRs once every feature passes |
| `--skip-docs` | Skip the per-feature documentation sync |
| `--skip-regression` | Skip the per-feature regression suite |
| `--skip-validation` | Skip the per-feature validation phase |

`/ship` owns `openspec archive`, which runs post-merge on main. `/scrum-team`
deliberately does not archive on the feature branch.

### `/container-team <feature>`

Runs the whole `/scrum-team` pipeline inside an isolated Docker container so
your main Claude Code session stays free. The container runs non-interactively
while you watch logs and PROGRESS.md.

| Argument | Effect |
|---|---|
| `<feature name>` | Launch a container team for this feature |
| `<feature> --detach` | Launch and exit immediately, no monitoring loop |
| `<feature> --k8s` | Use a Kubernetes Job instead of Docker |
| `--attach <container-id>` | Re-enter the monitoring loop for a running container |
| `--status` | List all running container teams |

Requires Docker running, or a configured cluster with `--k8s`.

### `/change-request <area>`

For changing a feature area that already exists. Product assesses the scope
first, then the request is captured as an OpenSpec change with
MODIFIED/ADDED/REMOVED deltas against the living specs in `openspec/specs/`,
validated by the pinned CLI, and implemented in place by the scrum team.

Takes an area slug or domain name. Use this rather than `/scrum-team` when the
behavior already exists and you are amending it.

---

## Fixing and landing

### `/fix-the-issue <description>`

Root-cause a bug and ship the fix with a small focused team. Six phases:
investigation and fix plan, task creation and implementation, code review,
integration verification, QA automation, ship.

| Argument | Effect |
|---|---|
| `<description>` | Required. What is broken |
| `--no-merge` | Run Phases 1 to 5 and stop before shipping |

### `/fix-and-ship <description>`

`/fix-the-issue` plus full hygiene. Eight phases: baseline capture, fix,
documentation sync, test estate maintenance, regression check, optional
validation, ship, final report.

| Argument | Effect |
|---|---|
| `<description>` | Required |
| `--skip-docs` | Skip documentation sync |
| `--skip-tests` | Skip test estate maintenance |
| `--skip-regression` | Skip the regression check |
| `--validate` | Force the validation auditors to run |
| `--no-merge` | Do everything except merge |

### `/rebase`

Rebase the current feature or fix branch onto `main`, then check every migration
for correct naming and sequential order, renaming any that landed out of order.
Reports what it checked and what it fixed. Takes no arguments.

### `/merge-features`

Merge all open `feature/*` pull requests into main in creation order, with CI
gating, auto-rebase on conflicts, and a summary report.

| Argument | Effect |
|---|---|
| *(none)* | Merge every open `feature/*` PR |
| `--dry-run` | Print the status table and exit without merging |
| `--only <n,m,...>` | Merge only these PR numbers |
| `--skip-ci` | Merge even when checks are pending or failing |

Requires `gh` authenticated.

---

## Requirements and discovery

### `/brainstorm <idea>`

Stress-test a feature idea before committing to it. Researches the market, then
pushes back on the idea through adversarial questioning across five or more
areas, and produces a Feature Requirements Document.

Writes `docs/brainstorm/<feature-name>/FRD.md`. Needs no scrum-team config, so
it works in any repo.

---

## Production readiness

### `/prepare-for-production`

Ten specialist auditors sweep the codebase, then findings are triaged, fixed,
and the fixes verified. Four phases.

| Argument | Effect |
|---|---|
| *(none)* | Run all ten auditors |
| `--only <list>` | Run a comma-separated subset |

Valid `--only` values and the agent behind each:

| Value | Agent | Covers |
|---|---|---|
| `security` | security-auditor | OWASP top 10, auth coverage, hardcoded secrets, dependency CVEs |
| `performance` | performance-engineer | N+1 queries, missing indexes, bundle size, caching |
| `accessibility` | accessibility-auditor | WCAG 2.1 AA, keyboard nav, ARIA, contrast |
| `seo` | seo-analyst | Meta tags, Open Graph, sitemap, robots.txt, structured data |
| `devops` | devops-engineer | Dockerfile, compose config, health checks, CI/CD, env config |
| `error-handler` | error-handler | Error response consistency, error boundaries, logging coverage |
| `dependency` | dependency-auditor | npm and Maven vulnerabilities, outdated packages, licenses |
| `api-docs` | api-documenter | OpenAPI spec generation, API reference coverage |
| `db` | db-analyst | Schema review, missing indexes and constraints, migration hygiene |
| `load-test` | load-tester | Breaking points and bottlenecks on key endpoints |

Writes `docs/production-audit/<agent-name>-REPORT.md` per auditor.

---

## Product and GTM pipelines

These are larger orchestrations that wrap the feature pipeline. Each keeps its
own state file so a long run can be resumed or inspected.

### `/product-lifecycle <product>`

20+ agents across six phases: Discover, Strategy, Build, Launch, Grow, Evolve.
The Build phase delegates to `/plc-scrum-team`.

| Argument | Effect |
|---|---|
| `--auto` | Run without decision gates |
| `--resume` | Continue from the existing `PLC-STATE.md` instead of starting fresh |
| `--skip-discover` | Skip the discovery phase |
| `--skip-build` | Skip the build phase |
| `--skip-test` | Skip the test phase |

Writes `docs/plc/<slug>/` with a subdirectory per phase and `PLC-STATE.md`.

### `/product-launch <product>`

15+ agents across ten phases taking an idea to first revenue: idea, build, test,
production, iterate.

| Argument | Effect |
|---|---|
| `--auto` | Run without decision gates |
| `--prod-url <url>` | Target URL for the production smoke test |
| `--features "a, b"` | Explicit feature list for the build phase |
| `--size small\|medium\|large` | Team size for the build phase |
| `--skip-build` / `--skip-test` / `--skip-smoke` / `--skip-iterate` | Skip that phase |

Writes `docs/launch/<slug>/` and `LAUNCH-PROGRESS.md`.

### `/plc-scrum-team <slug>`

The Build pipeline used inside `/product-lifecycle`. A full scrum team tuned for
MVP scope, always autonomous.

| Argument | Effect |
|---|---|
| `<slug>` | Required. The `docs/plc/<slug>/` product slug |
| `--size small\|medium\|large` | Team size, default `medium` |

This pipeline intentionally still uses the legacy artifact model
(`docs/plc/<slug>/build/FEATURE-BRIEF.md`, `ARCHITECTURE.md`) rather than
OpenSpec changes.

### `/gtm-team <product>`

16 agents across six phases producing a Go-To-Market strategy and execution
plan: ICP profiles, competitive analysis, positioning, content, outbound,
paid, CRM design, metrics.

`--auto` runs it without decision gates. Writes `docs/gtm/<slug>/` and
`GTM-PROGRESS.md`.

---

## Design

### `/web-design <site-name>`

Generates an award-caliber Next.js site with Tailwind, then screenshots and
scores it with a design validator, iterating until it passes the quality
threshold or runs out of iterations.

| Argument | Effect |
|---|---|
| `<site-name>` | Required |
| `--pages <n>` | Page count (default 3) |
| `--port <n>` | Dev server port (default 3200) |
| `--theme "<direction>"` | Creative direction, for example `"brutalist dark"` |
| `--max-iterations <n>` | Iteration cycles (default 3) |

Writes `docs/designs/`.

---

## Knowledge and operations

### `/wiki`

Maintains a compiled knowledge layer at `docs/wiki/`. Non-destructive: it never
modifies the source doc directories it reads.

| Subcommand | Effect |
|---|---|
| `init` | Bootstrap the `docs/wiki/` structure |
| `ingest <doc-path>` | Compile any docs path into a wiki entry |
| `coverage` | Report which doc directories have no wiki entry |
| `lint` | Validate all entries for consistency |

### `/supervisor`

Hourly health check and auto-fix across every active PLC project and
`feature/*` branch. Scans state, writes a dashboard, and spawns agents to
unblock stalled work.

| Argument | Effect |
|---|---|
| `--report-only` | Produce the dashboard, change nothing |
| `--fix-only <slug>` | Only act on one project |
| `--stall-threshold <hours>` | How long before work counts as stalled (default 2) |
| `--verbose` | Detailed output |

Writes `docs/supervisor/DASHBOARD.md`. Pairs with `/loop 1h /supervisor` for
continuous monitoring.

---

## Data connectors

Four API wrappers that feed the GTM and discovery agents. Each looks for its key
in the environment or your config at boot and tells you what to set if it is
missing.

| Command | Service | Typical use |
|---|---|---|
| `/apollo` | Apollo.io | Find and enrich people and companies for prospecting |
| `/linkedin` | Proxycurl | Profiles, companies, employees, job postings for ICP work |
| `/pipedrive` | Pipedrive | Create and search deals, contacts, organizations, activities |
| `/semrush` | Semrush | Keyword research, domain analysis, backlink audits |

Most accept `--limit <n>` and `--save` to persist results into the GTM docs.
`/apollo` adds filters such as `--titles`, `--seniority`, `--industry`,
`--company-size` and `--location`; `/linkedin` adds `--company`, `--role`,
`--title`, `--country`; `/pipedrive` addresses deals, people and organizations
with `--deal`, `--person`, `--org`, `--stage`, `--value`, `--due`;
`/semrush` takes `--db <country-db>`.

---

## Flags that appear across commands

| Flag | Meaning wherever it appears |
|---|---|
| `--auto` | No human checkpoints. Requirements get derived rather than interviewed, and approvals are logged instead of asked |
| `--size small\|medium\|large` | How many agents to spawn for the build |
| `--features "a, b"` | Explicit feature list instead of auto-discovery |
| `--file <path>` | Read the feature list from a file |
| `--parallel` | Run independent units concurrently |
| `--no-merge` | Do the work, stop before merging |
| `--dry-run` | Report what would happen, write nothing |
| `--skip-*` | Drop that phase from the run |

---

## Related

- [Tutorial: ship your first feature](tutorial-first-feature.md)
- [How to do the common jobs](howto-common-tasks.md)
- [Why the pipeline is shaped this way](explanation-pipeline-design.md)
- [Feature catalog](FEATURES.md)
