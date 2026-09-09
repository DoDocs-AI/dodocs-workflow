# Tutorial: ship your first feature

By the end of this you will have installed dodocs-workflow, pointed it at one of
your own projects, and watched a team of agents take a one-line feature request
to a pull request with tests.

Budget about 15 minutes of your attention. The build itself runs longer and does
not need you.

## What you will need

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) or OpenCode, installed and working
- Git, and a project you can safely branch
- Node.js >= 20, for the pinned OpenSpec CLI that validates requirements
- `gh` authenticated, for the pull request at the end

A real project works better than an empty one. The agents read your existing
code to match its patterns, so they have more to work with in a codebase that
already does something.

## Step 1: Install

From a clone (recommended, and what you want if you plan to contribute):

```bash
git clone https://github.com/DoDocs-AI/dodocs-workflow.git
cd dodocs-workflow
bash install.sh
```

Or the one-liner, which installs the latest stable release:

```bash
curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v2.0.1/install.sh | bash
```

Everything lands in `~/.claude/`: 89 agent definitions, 27 slash commands, the
Docker runtime for container runs, and the project config template. Nothing is
written into your project yet.

Check it took:

```bash
cat ~/.claude/.dodocs-workflow-version
```

```
2.0.1
```

## Step 2: Initialize your project

Open Claude Code in the project you want to work on, then run:

```
/dodocs-workflow init
```

Three things happen, and you can see all of them:

```bash
ls .claude/scrum-team-config.md   # config template, copied in
ls openspec/                      # OpenSpec scaffolding, created
```

It also runs the doctor checks. Node.js missing is a warning rather than a stop,
so if it complains, install Node >= 20 and run `/dodocs-workflow init` again to
finish the OpenSpec half.

## Step 3: Tell the agents where things are

This is the one step that cannot be automated, and the one that determines
whether everything after it works. Open `.claude/scrum-team-config.md` and
replace every `<placeholder>` with your project's reality.

```markdown
## Tech Stack

- **Backend Framework**: Quarkus
- **Frontend Framework**: React 18 with TypeScript
- **Database**: PostgreSQL
- **Migration Tool**: Flyway

## Ports & URLs

- **Frontend Port**: 3015
- **Backend Port**: 8070
- **Dev Domain**: https://localhost:3015/

## Source Paths — Frontend

- **Pages**: src/main/webapp/src/pages/
- **Components**: src/main/webapp/src/components/
```

Fill in every section: identity, stack, ports, backend paths, frontend paths,
test paths, build and lint commands. Agents do not guess. A wrong path here
means files written into the wrong directory two hours from now.

Verify:

```
/dodocs-workflow doctor
```

It checks Node.js >= 20, that the pinned OpenSpec CLI reports `1.6.0`, and that
`openspec/` validates. A warning about a missing `## OpenSpec` section means your
config predates the current template; copy that section across.

## Step 4: Build something small

Do not start with your hardest feature. Pick something real but contained, so
you can watch the whole pipeline without waiting two hours.

```
/scrum-team add a dark mode toggle to the settings page
```

The word "toggle" plus "page" reads as a small feature, so nine agents spawn
instead of thirteen and the design phase is skipped. You will see:

1. **A branch.** `feature/add-a-dark-mode-toggle-to-the-settings-page`, created
   before anything else, after a baseline run of your existing E2E tests on main.
2. **Questions.** The product owner asks about the problem, the users, the
   acceptance criteria and the edge cases. Answer properly. These answers become
   the OpenSpec change every later agent reads.
3. **A validation gate.** The requirement is checked with
   `openspec validate --strict`. If it does not pass, the product owner is sent
   back with the validator's complaint. No input needed from you.
4. **Work.** Developers commit per task, a reviewer reads each commit, the
   tech-lead compiles and starts your app, testers drive it in a browser.

A progress block prints as agents report in:

```
─────────────────────────────────────────
  FRONTEND ██████░░░░  3/5  pending  (T04 in progress by frontend-dev-1)
  QA       ██████████  test cases ready ✅
  COMPILE  ✅ app ready
  TESTING  ⏳ US01 in progress
─────────────────────────────────────────
```

## Step 5: Read the run

While it works, open the dashboard the team keeps:

```bash
cat docs/features/add-a-dark-mode-toggle-to-the-settings-page/PROGRESS.md
```

Two tables tell you everything. **Phase Status** says where the run is.
**Phase Gates** says what is blocking it. A gate reading `FAIL` or `BLOCKED`
names its blocker in the next column.

The canonical task checklist lives with the requirement:

```bash
cat openspec/changes/<slug>/tasks.md
```

Developers tick boxes here as they commit. Phase 6 refuses to ship with any box
unticked.

## Step 6: Collect the pull request

The run ends with a PR URL. Before you read the diff, check the team's own
verdict:

```bash
gh pr view --web
```

In `PROGRESS.md`, the **Definition of Done** section should show ten passing
checks: tasks reviewed, compile clean, lint clean, manual tests passed, E2E
green, no critical bugs, acceptance criteria traced, dashboard current, no scope
creep, integration verified. The tech-lead will not open a PR until all ten
pass, so a PR that exists has already cleared them.

Merge it the way you normally merge. Archiving the requirement into your living
specs happens after the merge, on main, when you run `/ship`.

## What you built

You now have a project wired for the whole pipeline, and one feature that went
through it. Concretely, on disk:

| Path | What it holds |
|---|---|
| `.claude/scrum-team-config.md` | Where your code lives and how to build it |
| `openspec/changes/<slug>/` | The requirement, design, and task checklist |
| `openspec/specs/` | Your living specs, once `/ship` archives the change |
| `docs/features/<slug>/` | Progress dashboard, UX design, mockups, test reports |

### Where to go next

- Run it on a bigger feature. At `--size large` you get thirteen agents, an
  architecture phase, and interactive mockups at `http://localhost:3100` to
  review before any code is written.
- Try the day/night split: `/prepare-feature` while you are awake to settle
  requirements and screens, `/batch-features` overnight to build the queue. See
  [how to split preparation from building](howto-common-tasks.md#how-to-split-preparation-from-building).
- Look up anything in the [command reference](reference-commands.md), all 27 of them.
- Understand the gates in [why the pipeline is shaped this way](explanation-pipeline-design.md).

If your first run went sideways, the
[troubleshooting table](howto-common-tasks.md#troubleshooting) covers the
failures that actually happen: missing config, wrong paths, a failing compile
gate, a test that will not go green.
