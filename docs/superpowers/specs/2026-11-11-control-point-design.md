# Control Point — Design (part 1 of 4)

Date: 2026-11-11
Status: draft for approval

## Why

Several products are in development at the same time. Today each one needs its own
terminal session, its own command, and its own checking-in. The pipeline is also slow and
token-hungry, which gets worse with every project added.

The owner wants **one place** that controls all projects: hand out work there, and ask
there for the status of any project.

This is the first of four parts, agreed in this order:

1. **Control point** (this document)
2. **Routines** — recurring per-project activities (GTM, marketing, audits) on a schedule
3. **Leaner pipeline** — fewer agents, model tiers chosen by task difficulty
4. **One source for all harnesses** — generate Claude Code / OpenCode / Pi versions, local models

Parts 2–4 are outlined at the end so part 1 does not block them.

## What the owner decided

- One control point for all projects; status of any project can be asked there.
- It may use AGTerm (the terminal already in use) for sessions, status and dialogs.
- Work also includes non-development activity (GTM, marketing) that repeats over a
  project's life. (Scheduling is part 2; part 1 must be able to start such runs by hand.)
- Runs may ask for approval when needed.
- The four-part split and its order.

Everything below that is not in this list is the designer's call and is marked **(call)**
where it matters.

## Goals

- From one session, start a run in any registered project without opening that project.
- Ask "status of X" or "status of everything" and get: what is running, in which phase,
  what finished, what is blocked and why, what is waiting for approval.
- Runs in different projects execute in parallel, each visible as its own AGTerm session.
- Be told when a run blocks or finishes, without polling.
- Outward-facing or irreversible actions wait for explicit approval.
- Idle cost is zero: nothing consumes tokens while no one is asking and nothing is running.

## Non-goals (part 1)

- Changing any pipeline, agent, or model assignment (`/scrum-team`, `/gtm-team`,
  `/fix-the-issue` and the rest are launched exactly as they are today).
- Schedules and recurring runs (part 2).
- Launching harnesses other than Claude Code (part 4). The registry reserves the field.
- A web dashboard, multi-machine control, or team/multi-user use.
- More than one run at a time inside one project checkout.
- Commands that work outside the project checkout (`/container-team`, `--docker` runs).
  The guard is gated on the working directory and would not reach them, so part 1 refuses
  to launch them.

## Anti-goals

- The control session doing project work itself. The old `/workspace` did this: one agent
  executed every task in sequence and could not start a pipeline. The control session only
  routes, starts, watches and reports.
- A publish, send, merge, deploy or spend that happens without the owner's approval.
- A registry that silently drifts from reality (the old one has not changed since March 2026).
- Multiplying today's token cost: part 1 ships with hard concurrency limits.

## How it works

### Pieces

| Piece | What it is | Uses tokens? |
|---|---|---|
| `dw` CLI | Deterministic script: registry, starting runs, queue, status, event handling | No |
| Registry + run records | Plain JSON files under `~/.dodocs-workflow/` **(call)** — outside `~/.claude` so other harnesses can use them later | No |
| AGTerm | Hosts every run as a session; provides status glyphs, event hooks, dialogs | No |
| Guard hook | Claude Code `PreToolUse` hook, installed once globally and active only where a run is active; holds guarded actions for approval | No |
| `/control` command | The control session: a thin prompt that drives `dw` and answers in plain language | Only when the owner talks to it |

The CLI does everything that must be reliable. The control session is a conversational
front end over it; anything it can do, `dw` can do from a plain shell.

### Registry

`~/.dodocs-workflow/registry.json`. One entry per project:

- `id`, `name`, `path` (absolute)
- `group` — the AGTerm workspace the project's runs appear in. The owner already keeps one
  AGTerm workspace per client/area (Dodocs, DPL, Sous, ignashev_ai, …); runs join those
  rather than creating a parallel structure **(call)**
- `harness` — `claude` only in part 1; reserved for part 4
- `notes` — free text the control session can read (stack, ports, what the product is)

`dw project add|list|remove`. On first install, `dw project import-legacy` offers to import
the five projects from `~/.claude/workspace/registry.json`, asking for each project's
`group` (the old file's `personal`/`corporate` values are not AGTerm workspace names). The old `/workspace` command,
its agent, and its ~300 MB of event logs are left untouched; the installer prints a note
that they are superseded **(call)**.

### Runs

A run is one unit of work in one project: a command line as the owner would type it
(`/scrum-team --auto invoice sync`, `/gtm-team …`, `/fix-the-issue …`, or free text).

`dw run <project> "<command>"`:

1. Checks limits: at most **1 active run per project** and **3 active runs in total**
   **(call; both configurable)**. Over the limit, the run is queued.
2. Creates an AGTerm session in the project's group workspace, in the background (does not
   steal focus), with the harness as the session process and the command as its first
   prompt. Session name: `<project>: <short task>`; AGTerm session context: the run id.
3. Writes a run record `~/.dodocs-workflow/runs/<run-id>.json`: project, command, AGTerm
   session id, harness session id, state, timestamps, branch if known.

Run states: `queued → running → (blocked ⇄ running) → done | failed | interrupted | cancelled`.

The launched session runs with permissions bypassed **(call)**. Runs are unattended and
the pipelines already require it; an ordinary permission prompt on every file write would
make `blocked` meaningless across parallel runs. The guard (below) is therefore the only
barrier, and is built on that assumption.

**Interrupted runs.** If AGTerm restarts or the session dies mid-run, the run is marked
`interrupted` and is never re-run automatically: repeating `/scrum-team --auto …` on a
half-finished branch is worse than stopping. The launch pins the session's restore command
to nothing, and `dw resume <run-id>` reopens the stored harness session for the owner to
continue **(call)**.

The first prompt is the owner's command plus a short fixed suffix asking the run to write a
result note (`runs/<run-id>.result.md`: outcome, PR link if any, what is left) when it
finishes or cannot continue. This is the only addition to the pipelines **(call)**.

`dw cancel <run-id>` closes the session and marks the record. `dw queue` lists waiting runs.

**After a run finishes** it reports and stops. The next run in that project starts
automatically only if the owner queued one **(call)**.

### Status

`dw status [project] [--json]` merges three sources, none of which interrupts a running agent:

1. The run record (state, timestamps, command).
2. AGTerm's live session state — `active` / `blocked` / `completed` and when it last
   changed. The agent-status hooks that set these glyphs are already installed on this
   machine for Claude Code, Pi, OpenCode and Codex.
3. Project-side progress, when the pipeline writes one: `docs/features/<slug>/PROGRESS.md`
   for `/scrum-team` (phase, gates, task counts), the result note otherwise.

For "what is it doing right now", the control session may read the tail of the run's
terminal buffer through AGTerm. That is read-only.

A run whose session is `active` but whose state has not changed for a long time is reported
as possibly stalled (threshold configurable, default 30 min **(call)**); part 1 only
reports it, it does not restart anything.

### Events

Two lines in AGTerm's `hooks.conf` call `dw` (installed by `dw setup`, which shows the
lines and asks before editing that file):

- on `status`: `blocked` → record it and notify the owner; `completed` → if the result note
  exists, mark the run done, notify, and start the next queued run if limits allow.
  The installed status hook sets `completed` at the end of every turn, so the result note,
  not the glyph, is the completion signal.
- on `session.closed`: mark a still-running run as ended (`failed` unless a result note
  says otherwise).

Notification is an AGTerm desktop notification attributed to the run's session, so one
click jumps to it **(call)**.

### Approvals

Guarded actions **(call — the list)**:

- merging or pushing to the default branch, `gh pr merge`
- deploying (kubectl apply/rollout, helm, vercel/cloud deploys, docker push)
- publishing or posting to any external channel; sending email or outreach messages
- anything that spends money (ads, paid API purchases, payment-provider writes)
- deleting data outside the project checkout; destructive database commands

Mechanism: `/scrum-team` spawns its agents with permissions bypassed, so wording in a
prompt cannot be relied on. Launched runs therefore carry a `PreToolUse` guard hook that
matches guarded actions by tool and command pattern. On a match it opens a native AGTerm
question ("slotme: merge PR #41 to main — approve?") and waits; the answer allows or
denies the tool call. While waiting, the run is `blocked` with reason
`awaiting approval`, which is what status reports.

**How the guard is attached (owner's decision): one global hook, self-gated.**
`/scrum-team` creates an agent team, and on this machine teammates run as separate Claude
Code processes in tmux panes, so settings passed only to the launched session would not
reach them. The guard is therefore one `PreToolUse` entry in `~/.claude/settings.json`,
the file where AGTerm's status hooks already live. (Per-project, per-run attachment was
considered and rejected by the owner.)

Requirements that follow from that choice **(calls)**:

- The hook exits immediately, allowing the call, unless the working directory is inside a
  registered project that has an active run. The check is a local file lookup and must add
  no noticeable delay to ordinary sessions.
- `dw setup` adds the entry: it shows the exact change, asks before editing, merges into
  the existing file and never rewrites other entries. `uninstall.sh` removes exactly that
  entry.
- If the hook itself fails (missing file, bad registry), it allows the call outside active
  runs and holds it inside one.
- While a run is active in a project, the owner's own Claude sessions in that project see
  the same approval questions. That is accepted.
- Nothing is written into project repositories for the guard.

Patterns live in one file (`guard-rules.json`), with per-project additions in the registry.

Default posture **(call)**: the guard is a list of things to hold, and anything it does not
match is allowed. The owner asked for approvals "if needed", and a pipeline of many agents
cannot stop on every unrecognised command. To keep the list from being trivially bypassed,
the categories are matched broadly rather than by exact command:

- any MCP tool that sends, posts, publishes, shares or writes to an outside service
  (mail, chat, CRM, calendar, payments, ads) — matched by server and verb, default guarded
  for servers not on a known read-only list
- network writes from the shell to non-local hosts (`curl`/`wget`/`http` with a write
  method or body), and `gh`/cloud CLIs with mutating subcommands
- the git, deploy and destructive-data patterns listed above

The question offers three answers: approve once, approve this action for the rest of the
run, deny. The run's session is also marked blocked and a notification is sent, because a
question on a session the owner is not looking at may not be visible.

An approval stays pending until the owner answers **(call)**. A hook cannot hold a tool
call open forever, so if no answer comes within the hook's limit the action is refused for
now, the agent is told to continue other work and retry later, and the approval remains
pending. The owner can then answer from the control session (`dw approve` / `dw deny`),
which lets the retry through once. A run that is only awaiting approval does not count
against the total-run limit, so it cannot starve other projects **(call)**.

**A run cannot change its own controls (call).** Launched runs have permissions bypassed
and could otherwise approve themselves. Inside an active run the guard also holds any
`dw` command that changes state, and any write to the control point's state directory
(other than the run's own result note), to `~/.claude/settings.json`, or to AGTerm's
hooks file. These can only be approved once, never for the rest of the run.

### The control session

`/control` (Claude Code command, installed by `install.sh`). Its prompt is short:

- Use `dw` for every registry, run, queue and status operation.
- Never edit files in a project and never do a project's work; start a run instead.
- Resolve project names loosely ("slotme", "the booking app").
- When asked to start work, pick the pipeline command, state which one and why in one line,
  then start it. Ask first only when the request is genuinely ambiguous.
- Status answers lead with what needs the owner, then what is running, then what finished.

It is meant to live in one long-running AGTerm session, but holds no state of its own:
closing and reopening it loses nothing.

### Without AGTerm

Part 1 requires AGTerm to start runs. Without it, `dw status` and the registry still work
and `dw run` refuses with a clear message. A headless fallback is deferred **(call —
this narrows what was said in conversation, where a fallback mode was suggested)**.

## Where it lives

- `control/` in this repo: the `dw` CLI, guard hook, default guard rules **(call)**
- `claude/commands/control.md`
- `install.sh` installs them; `uninstall.sh` removes them (never the registry or run records)
- `tests/validate-control.sh`, in the style of the existing validators, running `dw`
  against a fake `agtermctl` so it needs neither AGTerm nor network

## To verify early (spikes before the plan is fixed)

1. The guard fires for tool calls made by team members running as separate processes
   with permissions bypassed, and its deny is honoured.
2. A hook can block on an AGTerm question for minutes without the harness timing it out;
   if not, the hook denies with "approval requested" and the run retries after approval.
3. Starting Claude Code as an AGTerm session process with a slash command as the first
   prompt runs that command (including in a restored session after an AGTerm restart).
5. Status events from team members running in tmux panes are attributed to the right
   AGTerm session when two runs are active; and an approval question on a background
   session is actually visible to the owner.
4. The `completed` status fires once at the true end of a long pipeline, not at each
   intermediate turn; if it fires early, completion is taken from the result note instead.

If 1 fails, part 1 does not ship team pipelines as launchable
until it passes; an unenforced guard is not acceptable.

## Left to the builder

- Implementation language of `dw` (the repo is bash; Python 3 is available and acceptable).
- Exact JSON shapes, id format, file locking for the registry and run records.
- Guard pattern syntax and the initial pattern list for each guarded category.
- Wording of the `/control` prompt and of status output.

## Outline of later parts

**Part 2 — Routines.** Registry gains per-project routines: a command plus a schedule.
A system scheduler calls `dw tick`, which starts due routines through the same run
mechanism, under the same limits and guard. Routine output that would go public always
stops at the guard.

**Part 3 — Leaner pipeline.** Replace the standing 9–13-role team with a fresh agent per
small task, a review after each, and one final review. Choose the model by task difficulty,
escalating only after repeated failed fixes. Size a feature from its written spec instead
of keywords in its name. Agents declare a tier (`critical` / `standard` / `routine`), not
a model name.

**Part 4 — One source for all harnesses.** A single harness-neutral definition generates
the Claude Code, OpenCode and Pi versions, replacing the hand-maintained `opencode/` copy.
A per-harness mapping turns tiers into models, including local ones. Pi has no built-in
subagents (optional `pi-subagents` package), so there the pipeline needs that package or
runs tasks sequentially. An existing Pi `scrum-team` extension on this machine is prior
material. The registry's `harness` field then selects per project.
