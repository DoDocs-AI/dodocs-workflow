# How to do the common jobs

Task-oriented recipes. Each one assumes dodocs-workflow is installed and the
project is set up (if not, start with the
[first-feature tutorial](tutorial-first-feature.md)).

Pick the job you have:

| You want to | Go to |
|---|---|
| Build something new | [Build a feature end to end](#how-to-build-a-feature-end-to-end) |
| Decide requirements now, build tonight | [Split preparation from building](#how-to-split-preparation-from-building) |
| Change behavior that already exists | [Change an existing feature](#how-to-change-an-existing-feature) |
| Fix something broken | [Fix a bug](#how-to-fix-a-bug) |
| Re-run testing on finished work | [Retest a feature](#how-to-retest-a-feature) |
| Keep your session free while it builds | [Run the team in a container](#how-to-run-the-team-in-a-container) |
| Land a pile of finished branches | [Merge every open feature branch](#how-to-merge-every-open-feature-branch) |
| Check readiness before launch | [Audit for production](#how-to-audit-for-production) |
| Adopt this in an existing codebase | [Adopt the workflow in an existing project](#how-to-adopt-the-workflow-in-an-existing-project) |
| Stop long runs from stalling silently | [Keep long runs unstuck](#how-to-keep-long-runs-unstuck) |

---

## How to build a feature end to end

Takes a feature description and gives you a reviewed, tested pull request.

### Prerequisites

- `.claude/scrum-team-config.md` filled in with your real paths, ports and commands
- `openspec/` in the project root
- A clean working tree (the command creates a branch)

### Steps

1. Describe the feature in one line.

   ```
   /scrum-team add organization member invitation flow
   ```

   Be specific about the user-visible outcome. "Add invitations" produces vaguer
   requirements than "let an org admin invite a member by email and see pending
   invites".

2. Answer the product owner's questions.

   It asks about the problem, the users, acceptance criteria and edge cases.
   These answers become the OpenSpec change that everything downstream reads, so
   this is the cheapest place to be precise.

3. Review at the single checkpoint.

   After Phase 2 you get UX flows, the architecture, and interactive mockups
   running at `http://localhost:3100`. Open the mockups. This is the last point
   where changing your mind is cheap.

4. Wait.

   Phase 4 is the long one, up to two hours for a large feature. A status block
   prints after each agent reports:

   ```
   ─────────────────────────────────────────
     BACKEND  ██████████  6/6  done ✅
     FRONTEND ░░░░░░░░░░  0/5  pending  (T16 in progress by frontend-dev-1)
     QA       ██████████  test cases ready ✅
     COMPILE  🔨 tech-lead running now
     TESTING  ⏳ waiting for compile gate
   ─────────────────────────────────────────
   ```

### Verification

The run ends with a PR URL. Confirm the work actually passed rather than
timed out:

```bash
cat docs/features/<slug>/PROGRESS.md
```

The **Phase Gates** table should read `PASS` on every row, and **Definition of
Done** should show ten passing checks. `openspec/changes/<slug>/tasks.md` should
have every box ticked.

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "No scrum-team config found for this project" | Run `/dodocs-workflow init`, then fill in the generated `.claude/scrum-team-config.md` |
| "This project is not initialized for the OpenSpec pipeline" | Run `/dodocs-workflow init` for a new project, `/spec-bootstrap` for one with existing features |
| Agents write files to the wrong place | Config paths do not match your tree. Check the Source Paths sections against your actual directories |
| Compile gate keeps failing | A developer introduced a build error; the tech-lead files a bug task and assigns it back. If it repeats on the same file, the compile command in your config may be wrong |
| Manual tests keep failing the same case | After two failed retests the tester escalates to the tech-lead for root cause instead of filing a third fix task. Read the bug entries in PROGRESS.md |
| The architecture is wrong | Reject it at the checkpoint with specific feedback. The architect revises and resubmits |

---

## How to split preparation from building

Decide requirements while you are awake, build while you are not. This is the
highest-value pattern in the workflow.

### Prerequisites

Same as above, plus a rough list of what you want built.

### Steps

1. During the day, prepare each feature interactively.

   ```
   /prepare-feature organization invitations
   ```

   You answer requirements questions and approve mockups. It stops before any
   production code is written and marks `docs/features/<slug>/STATUS` as
   `approved`.

   For several at once:

   ```
   /prepare-features --features "org-invitations, billing-dashboard, dark-mode"
   ```

2. At the end of the day, hand the approved queue to the build.

   ```
   /batch-features --features "org-invitations, billing-dashboard, dark-mode"
   ```

   Or let it discover everything approved:

   ```
   /batch-features
   ```

   Add `--parallel` when the features do not touch the same files.

### Verification

`/batch-features` always runs in `--auto` mode, so nothing waits for you
overnight. In the morning:

```bash
gh pr list --state open --json number,title,headRefName
```

One PR per feature. Any feature that stalled shows up in its own
`docs/features/<slug>/PROGRESS.md` with the blocking gate named.

### Troubleshooting

A feature whose `STATUS` is not `approved` gets its requirements re-derived from
scratch by the overnight run instead of reusing your morning decisions. Check
`STATUS` before you go home.

---

## How to change an existing feature

Use this when the behavior already exists and you are amending it. Do not use
`/scrum-team`, which is shaped for new capabilities.

### Prerequisites

`openspec/specs/` populated (from shipping features, or from `/spec-bootstrap`).

### Steps

1. Name the area, not the change.

   ```
   /change-request billing
   ```

2. Describe what should be different when asked.

Product assesses the scope first, then the request is captured as an OpenSpec
change with MODIFIED, ADDED or REMOVED deltas against the living specs, and the
scrum team edits the existing code and tests in place.

### Verification

```bash
npx -y @fission-ai/openspec@1.6.0 validate <change-slug> --strict
```

Exit code 0. The deltas should reference the capability that already exists in
`openspec/specs/` rather than declaring a new one.

---

## How to fix a bug

Two commands, different amounts of ceremony.

### Steps

For a straightforward fix:

```
/fix-the-issue org invite emails send twice when the form is double-submitted
```

Six phases: investigation, implementation, code review, integration
verification, QA automation, ship.

When the fix touches documented behavior or shared test surface:

```
/fix-and-ship org invite emails send twice when the form is double-submitted
```

Eight phases: the above plus baseline capture, documentation sync, test estate
maintenance, and a regression check before shipping.

To inspect the work before it lands, add `--no-merge` to either.

### Verification

Both end with a PR. `/fix-and-ship` also writes a regression comparison, so
check that no test which passed at baseline is failing now.

### Troubleshooting

If the root cause is not where you expected, that is the point of Phase 1: read
the fix plan it produced before letting the implementation proceed.

---

## How to retest a feature

Re-run the full test pass on work that is already built, without the
requirements, design and breakdown phases.

### Steps

```
/scrum-team --retest organization-invitations
```

Five agents spawn at once: tech-lead brings the app up and runs the compile
gate, the manual tester works every scenario in the existing test cases, and a
frontend and backend developer stand by to take bug tasks immediately.

### Verification

The loop ends when the tester confirms every test case passes with no open
bugs. No branch is created and no PR is opened; this mode only tests and fixes.

---

## How to run the team in a container

Frees your Claude Code session while the pipeline runs.

### Prerequisites

Docker running, or a configured Kubernetes cluster.

### Steps

1. Launch it.

   ```
   /container-team organization invitations
   ```

   Add `--detach` to launch and exit immediately. Add `--k8s` to run it as a
   Kubernetes Job instead.

2. Check on it later.

   ```
   /container-team --status
   /container-team --attach <container-id>
   ```

### Verification

`docs/features/<slug>/PROGRESS.md` updates from inside the container exactly as
it would locally.

### Troubleshooting

"container-team requires Docker or Kubernetes" means Docker is not running and
`--k8s` was not passed. Start Docker Desktop or point at a cluster.

---

## How to merge every open feature branch

After a batch run you have several PRs. This lands them in creation order with
CI gating and auto-rebase.

### Steps

1. Look before you leap.

   ```
   /merge-features --dry-run
   ```

   Prints the status table and exits without merging.

2. Merge.

   ```
   /merge-features
   /merge-features --only 42,43        # just these PRs
   ```

### Verification

The command finishes with a summary report naming what merged, what was rebased
and what was skipped.

### Troubleshooting

CI failures block a merge by design. `--skip-ci` overrides that. Before reaching
for it, check whether CI is broken for infrastructure reasons rather than code
reasons: a job that fails in seconds with no steps executed never ran your tests
at all.

---

## How to audit for production

Ten specialists sweep the codebase, then findings are triaged, fixed and
verified.

### Steps

Everything:

```
/prepare-for-production
```

Or a subset, when you know where the risk is:

```
/prepare-for-production --only security,db,performance
```

Valid values: `security`, `performance`, `accessibility`, `seo`, `devops`,
`error-handler`, `dependency`, `api-docs`, `db`, `load-test`.

### Verification

```bash
ls docs/production-audit/
```

One `<agent-name>-REPORT.md` per auditor that ran.

---

## How to adopt the workflow in an existing project

The pipeline needs living specs. A project with history does not have them yet.

### Steps

1. Install and initialize.

   ```
   /dodocs-workflow init
   ```

2. Fill in `.claude/scrum-team-config.md`. Every path, port and command must
   match reality; agents do not guess.

3. Derive specs from what already exists.

   ```
   /spec-bootstrap --dry-run
   ```

   Read the proposed domain list and per-feature mapping. When it looks right:

   ```
   /spec-bootstrap
   ```

   Existing `FEATURE-BRIEF.md` files are left untouched as read-only history.

### Verification

```
/dodocs-workflow doctor
```

Doctor checks Node.js >= 20, that the pinned CLI reports `1.6.0`, and runs
`openspec validate --all --strict` when `openspec/` exists. All three should pass
before you build anything.

---

## How to keep long runs unstuck

Batch and lifecycle runs go for hours. The supervisor watches them.

### Steps

One pass:

```
/supervisor --report-only
```

Continuous:

```
/loop 1h /supervisor
```

Tune how patient it is with `--stall-threshold <hours>` (default 2), or point it
at one project with `--fix-only <slug>`.

### Verification

```bash
cat docs/supervisor/DASHBOARD.md
```

Without `--report-only` it also spawns agents to unblock what it found stalled.

---

## Related

- [Command reference](reference-commands.md)
- [Tutorial: ship your first feature](tutorial-first-feature.md)
- [Why the pipeline is shaped this way](explanation-pipeline-design.md)
