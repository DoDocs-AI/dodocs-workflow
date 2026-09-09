# Why the pipeline is shaped this way

This explains the design decisions behind dodocs-workflow: why there are phases
at all, why every artifact is a file on disk, why requirements go through a
validator, and what each of those choices costs you.

For what the commands do, see the [command reference](reference-commands.md).

## The problem

A single coding agent given "build a notification center" will produce something.
It will compile. It will look finished. And it will be wrong in ways you only
discover later: an acceptance criterion nobody wrote down and therefore nobody
tested, a migration that collides with another branch, a component that
reimplements one that already exists three directories away, a test suite that
was already red before the work started so nobody noticed it got redder.

None of these are model failures exactly. They are failures of *process*: nobody
wrote the requirement down in a checkable form, nobody owned the migration,
nobody knew what red looked like before the change.

Scaling the model does not fix this. Adding more agents makes it worse, because
now two of them are editing the same file.

## The approach

Six phases, each gated, with every artifact written to disk.

```
  human ask
      |
      v
  [Phase 1] requirements  -->  openspec/changes/<slug>/proposal.md + delta specs
      |                             |
      |                        GATE: openspec validate --strict
      |                             (fails -> re-spawn product-owner)
      v
  [Phase 2] design.md  ||  UX-DESIGN.md + mockups
      |                        GATE: artifacts complete + human approves
      v
  [Phase 3] tasks.md + live tasks
      |                        GATE: >=2 tasks, each tagged to a user story
      v
  [Phase 4] commits  <-->  review  <-->  test        (per story, in parallel)
      |                        GATE: compile clean, app running
      v
  [Phase 5] integration verification
      |                        GATE: security clear, all gates PASS
      v
  [Phase 6] pull request
```

Four ideas do the work.

### 1. Requirements are machine-checkable, not prose

The requirement is an OpenSpec change: `proposal.md` plus delta specs under
`openspec/changes/<slug>/specs/`, validated by a pinned CLI
(`@fission-ai/openspec@1.6.0`) with `--strict`.

This matters because a prose brief cannot fail. A validator can. When the
product-owner writes something incomplete, the gate rejects it and the agent is
re-spawned with the validator output pasted into its prompt. No human is in that
loop.

The earlier versions of this workflow used a `FEATURE-BRIEF.md`, which was
readable and completely uncheckable. That is why v2.0.0 was a breaking change.

### 2. Agents coordinate through files, not conversation

Every phase writes artifacts to a known path, and the next phase reads them.
`PROGRESS.md` holds the shared dashboard: phase status, gate table, task list,
bugs, timeline, Definition of Done.

The consequence people notice first is that a run is *inspectable*. You can open
`PROGRESS.md` mid-build and see exactly which gate is blocking. The consequence
that matters more is that a run is *resumable*, and that agents which never talk
to each other still agree on what is true.

### 3. Parallelism is bounded by ownership rules, not by hope

Phase 4 runs up to eight agents at once. Three rules keep them from colliding:

- **One migration owner.** Only `backend-dev-1` writes database migrations.
  `backend-dev-2` tasks that need one are blocked until it lands. Two agents
  writing migrations concurrently produce ordering collisions that only surface
  on a fresh database.
- **No shared files.** The scrum-master assigns tasks so that no two developers
  edit the same file. Merge conflicts inside a single run are designed out
  rather than resolved.
- **Story-level testing.** The tester starts US01 as soon as US01's tasks are
  reviewed and its test cases exist, while US02 is still being written. A bug in
  one story never stalls another.

### 4. Know what red looked like before you started

Before the feature branch is created, the E2E suite runs on `main` and the
result is recorded in `PROGRESS.md` as the regression baseline. In Phase 5, a
test that was already failing does not block the PR. Only a test that passed on
main and fails now counts as a regression.

Without this, every pre-existing failure gets attributed to the new feature, and
the team spends its time chasing them.

## Trade-offs

Every one of these choices costs something. Named honestly:

**Autonomy costs oversight.** Every agent spawns with `bypassPermissions`, which
means no permission prompts, which means the team edits your working tree
without asking. That is the point (a run takes hours and you are not watching),
but it means you should run it on a branch in a repo you trust, and it is why
`/container-team` exists: full isolation in Docker when you would rather the
agents not touch your machine directly.

**Gates cost tokens.** A failed gate re-spawns the agent that wrote the
artifact, with the failure output. That is a whole additional agent run. A large
feature is 13 agents over roughly two hours of wall clock, and the phase
timeouts (15/20/10/120/30/10 minutes) are advisory: in `--auto` they log a
warning and continue rather than aborting, because aborting a two-hour run at
minute 118 helps nobody.

**Ownership rules cost parallelism.** Serializing migrations behind one agent is
strictly slower than letting both backend devs write them. It is also the only
version that works.

**A structured pipeline costs flexibility.** The commands stop hard when
`.claude/scrum-team-config.md` or `openspec/` is missing, because an agent that
guesses your paths writes files into the wrong directories. Setup is not
optional here.

**Six phases are wrong for a one-line change.** That is what `--size small` is
for: 9 agents, Phase 2 skipped entirely. For a genuine typo, use `/fix-the-issue`
instead, or just edit the file yourself. Not everything needs a scrum team.

**More docs mean more drift.** The command definitions are the source of truth,
and the prose around them goes stale: at v2.0.1 the README still described the
v1 seven-phase flow, and the workflow map still counted 26 commands and 88
agents when there were 27 and 89. When something here disagrees with
`claude/commands/*.md`, the command file wins, and the doc is a bug.

## Alternatives considered

**One agent with a long prompt.** Cheaper and much faster. It also has no
mechanism to catch its own incomplete requirement, no second reader of its
code, and no way to test one story while writing another. The whole value here
is the gates, and gates need more than one participant.

**A human checkpoint at every phase.** Safer, and it was the original shape.
It also means the pipeline cannot run while you sleep, which removes the reason
to have it. The compromise is exactly one checkpoint, after Phase 2, where UX
flows, architecture and mockups are all on the table at once and changing your
mind is still cheap. `--auto` removes even that, and the day/night split
(`/prepare-feature` in the morning, `/batch-features` overnight) exists to put
the human decision earlier rather than delete it.

**Archiving specs on the feature branch.** Rejected. `openspec archive` folds
the change deltas into the living specs at `openspec/specs/`. Doing that on the
branch would claim the behavior exists while the code is still in review. So
`/scrum-team` never archives; `/ship` does it post-merge on main.

## Related

- [Command reference](reference-commands.md)
- [Tutorial: ship your first feature](tutorial-first-feature.md)
- [How to do the common jobs](howto-common-tasks.md)
- [The pipeline, drawn](scrum-team-pipeline.html)
