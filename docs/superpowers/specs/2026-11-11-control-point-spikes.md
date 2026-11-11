# Control point: spike results

Run on 2026-11-11, macOS (Darwin 25.4.0), Claude Code 2.1.322, AGTerm 0.37.0 (85f87be1),
model `sonnet`, `--permission-mode bypassPermissions` for every spike session.

## Deviation from the task brief (agreed with the controller)

The brief says to edit `~/.claude/settings.json`. The owner has about ten other live Claude
sessions, so that file was **not touched** (no backup/restore needed). Every spike hook
lived in the throwaway repos' own project-level `.claude/settings.json`. Team members
(separate `claude` processes in tmux panes) and subagents load project settings exactly as
they load user settings, so this is a valid proxy: the evidence below shows the project-level
hook fired for all of them. The hook script exits 0 immediately unless the payload `cwd` is
inside the spikes directory and the command contains `DW_SPIKE_`.

Scratch location: `/private/tmp/claude-501/-Users-antonignasev-java-dodocs-projects-dodocs-workflow/93bc9a0c-9d31-4388-9c34-6f7180eb753b/scratchpad/spikes/`
(`repoA`, `repoB`, `repoC`, `bin/spike-hook.sh`, `logs/`).

## Summary of answers

| Name | Value |
|---|---|
| GUARD_REACHES_TEAMMATES | **yes** |
| GUARD_REACHES_SUBAGENTS | **yes** |
| ENV_MARKER_REACHES_HOOKS | **yes** (lead, teammates and subagents all saw it) |
| STATUS_ATTRIBUTION_CORRECT | **yes** (two concurrent team runs, no cross-attribution) |
| ASK_VISIBLE_FROM_OTHER_SESSION | **partly**: status glyph, unseen badge and notification are visible; the `terminal`-style ask dialog is hidden until the session is visited. Ask style: see Spike F |
| HOOK_MAX_WAIT_SECONDS | **>= 900 s** (hook entry `timeout: 3600`; probes 90, 300 and 900 s all passed, no failure seen; ceiling not found) |
| SLASH_COMMAND_AS_FIRST_PROMPT | **yes**, launch line below |
| COMPLETED_FIRES_PER_TURN | **yes**, at the end of every turn, so also early in a team run |
| SESSION_ID_FLAG | **yes**: `--session-id <uuid>` accepted, `--resume <uuid>` reopens the same conversation |

Not verified: "including in a restored session after an AGTerm restart" (design item 3).
Restarting AGTerm would have killed the owner's other live sessions. Status: `unknown`.

## Hook stdin shape (PreToolUse, matcher `Bash`)

Keys observed for the lead: `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`,
`prompt_id`, `permission_mode`, `effort`, `hook_event_name`, `tool_name`, `tool_input`,
`tool_use_id`.

- Teammate (separate process): same keys minus `prompt_id`, plus `agent_type`
  (`general-purpose`); **no** `agent_id`; its own distinct `session_id`.
- Subagent (Agent tool, in-process in the lead): lead's `session_id`, plus `agent_id` and
  `agent_type`.
- So a teammate is told apart from the lead only by its different `session_id` and by
  environment; a subagent only by `agent_id`.

Redacted example (lead):

```json
{"session_id":"a9ab494a-6257-4fef-aca0-72afbba58db8","transcript_path":"<redacted>","cwd":"<spikes>/repoA","scratchpad_dir":"<redacted>","prompt_id":"058964e1-e514-437a-ad0f-49c56ef85f8c","permission_mode":"bypassPermissions","effort":{"level":"medium"},"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo DW_SPIKE_DENY","description":"Run echo test command"},"tool_use_id":"toolu_01Cb6eV2BuGvjzBcxaBo6sZe"}
```

### Hook output that produced a deny

Exit code 0 and this JSON on stdout:

```json
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"DW_SPIKE guard: denied"}}
```

The agent saw: `PreToolUse:Bash hook error: DW_SPIKE guard: denied` (tool result
`Not run · permission denied`), and the command did not execute. Allow = exit 0 with empty
stdout. This held under `bypassPermissions`.

## Spike A: guard reach

Setup: `repoA` with project hook; session launched as
`zsh -lc 'DW_SPIKE_MARK=1 claude --model sonnet --permission-mode bypassPermissions "$(cat promptA.txt)"'`.
Prompt: create a team of two members (t1, t2) each running `echo DW_SPIKE_DENY`, one
ordinary subagent (bypassPermissions) running the same, and the lead running it too.

Hook log (`jq` of `logs/hook.log`, trimmed):

| who | hook fired | deny honoured | `session_id` | `agent_id` / `agent_type` | hook ppid | `DW_SPIKE_MARK` | `AGTERM_SESSION_ID` in hook env |
|---|---|---|---|---|---|---|---|
| lead | yes | yes | a9ab494a | none | 76370 (lead pid) | 1 | 61707654 (the launching session) |
| teammate t1 | yes | yes | a4c115b0 (own) | none / general-purpose | 77088 | 1 | 61707654 |
| teammate t2 | yes | yes | 80f56c29 (own) | none / general-purpose | 77322 | 1 | 61707654 |
| subagent | yes | yes | a9ab494a (lead's) | ac0a2d2339e195839 / general-purpose | 76370 | 1 | 61707654 |

All four `cwd` values equal the repo root. All four agents reported the deny text
(`PreToolUse:Bash hook error: DW_SPIKE guard: denied`); none ran the command.

Mechanics worth knowing: with `teammateMode: "tmux"` each lead starts its own tmux server,
`tmux -L claude-swarm-<lead pid> new-session -d -s claude-swarm -n swarm-view ... cat`
(view with `tmux -L claude-swarm-<pid> a`). Teammates are `claude` processes inside it. The
server is created by the lead, so it inherits the lead's environment (including `AGTERM_*`
and any `DW_*` variable). Killing the lead leaves that tmux server running; the spike
cleaned its own with `tmux -L claude-swarm-<pid> kill-server`. A launcher should do the
same on run end (otherwise servers pile up; one older server from another session was
already present and was left alone).

Because teammates have their own `session_id` and no marker of which lead they belong to,
the guard must identify a run by an **environment variable** (`DW_*` marker, inherited
through tmux), not by `session_id`.

## Spike A (continued): attribution with two concurrent team runs

`repoB` and `repoC` each ran a lead plus teammates t1, t2 at the same time (sessions
`EFDEFAF3` and `12D35630`), each launched with its own `DW_SPIKE_MARK` (`B`, `C`) and a
status watcher running: `agtermctl events --json --kind status`.

Every hook invocation (lead and both teammates of each run) carried the `DW_SPIKE_MARK` and
`AGTERM_SESSION_ID` of its **own** run (B members: mark `B`, session `EFDEFAF3`; C members:
mark `C`, session `12D35630`); no member reported with the other run's values. Status events
(`logs/events.jsonl`) for the two runs touched only `spikeB`/`spikeC` rows, never each
other. The owner's existing status adapter
(`~/.config/agterm/agent-status/agterm-claude-status.sh`) uses process topology to stay
silent for a worker whose spawner is also an agent; teammates started by the per-lead tmux
server are not descendants of the lead, so they report (to the inherited, correct,
`AGTERM_SESSION_ID`). Conclusion: STATUS_ATTRIBUTION_CORRECT = yes. The AGTerm warning
(a tmux server reports to the session that started it) is satisfied here because each
tmux server is started by exactly one lead inside its own AGTerm session. It would be
wrong only if teammates were put into a shared, long-lived tmux server.

Caveat: events do not say which process set them, so per-member attribution is shown by
the hook-environment evidence, not by event payloads.

## Spike B: hook wait

Hook entry: `{"type":"command","command":"<script>","timeout":3600}`; the script sleeps N
seconds (read from a file) when the command contains `DW_SPIKE_SLEEP`, then exits 0 (allow).
One session, same conversation, three prompts, each `Run Bash exactly once: echo DW_SPIKE_SLEEP_OK...`.

| probe | hook start | hook end | outcome |
|---|---|---|---|
| 90 s | 1794387689 | 1794387779 | command ran, result returned ("done in 1m 37s") |
| 300 s | 1794387819 | 1794388119 | command ran, result returned ("5m 5s") |
| 900 s | 1794388159 | 1794389059 | command ran, result returned ("15m 4s") |

While waiting, the UI shows `running PreToolUse hooks… 1/2` and the session stays
`active`. HOOK_MAX_WAIT_SECONDS: the harness did not time out up to the tested value; the
effective ceiling is the entry's own `timeout`. Without a `timeout` field the default would
apply (not tested): always set it on the guard hook. (The UI counter read `1/2`, i.e. another
PreToolUse hook was in the chain besides ours; its source was not investigated.)

## Spike C: launch with a slash command as first prompt

Prompt file `promptCmd.txt` contains `/dodocs-workflow version`. Exact line that worked
(creates a background session; `--cwd` is the repo, the shell wrapper gives claude the
login PATH):

```bash
agtermctl session new --socket "$AGTERM_SOCKET" --no-select --workspace-name dw-spikes --create-workspace \
  --cwd <repo> --name spikeCmd \
  --command "zsh -lc 'DW_SPIKE_MARK=C claude --model sonnet --permission-mode bypassPermissions --session-id <uuid> \"\$(cat <prompt-file>)\"'"
```

Result: the slash command **executed** as a command (screen: `❯ /dodocs-workflow version`,
`Read 1 file`, `Installed dodocs-workflow version: v1.15.0`). `tree --json` `foreground`
showed `["claude","--model","sonnet","--permission-mode","bypassPermissions","--session-id","<uuid>","/dodocs-workflow version"]`.
The prompt reaches claude as one argv element, so multi-line content and quotes in the
prompt file are safe; only the quoting layers around `--command` matter (outer double
quotes for agtermctl, single quotes for `zsh -lc`, `\"\$(cat file)\"` inside).

**Launcher must handle a first-run dialog.** The first time `claude` runs in a directory it
shows "Quick safety check: Is this a project you created or one you trust?" with `No, exit`
preselected. It appeared for each of `repoA`, `repoB`, `repoC` (and does not reappear for a
path already accepted; `repoC` did not ask a second time). Answered with
`agtermctl session type --target <id> $'\e[B'` (Down) then `agtermctl session type --target <id> $'\r'`
(Enter). Passing `--permission-mode bypassPermissions` does not skip it. The launcher
should pre-accept trust for the project (or detect the prompt via `session text` and
answer it) before reporting the run as started.

Not verified: a restored session after an AGTerm restart (see Summary).

## Spike D: completion signal

Using `agtermctl events --json --kind status` filtered to the spike session
`0691E6A0` (the Spike C session: slash command turn, then two typed prompts):

```
[seq 2319] active (prev idle, blink)   <- turn 1 (slash command)
[seq 2321] completed (prev active)
[seq 2324] idle (prev completed)
[seq 2325] active   <- turn 2
[seq 2327] completed
[seq 2328] idle
[seq 2329] active   <- turn 3
[seq 2330] completed
[seq 2333] idle
```

`completed` fired at the end of **every** turn (3 turns, 3 completions). In the team runs
the lead's turns end while teammates are still working (lead spawns the team, ends the turn,
teammates report, new lead turn), so the session went `completed` early, then `active`
again, then `completed` again: in run B the sequence was active, completed (before the team
finished), active, completed, then `idle` later. So `completed` is **not** a reliable
end-of-pipeline signal for team pipelines. Take completion from the result note / session
close, and treat `completed` only as "the lead is waiting".

`idle` follows `completed` automatically after a delay or when anything is typed (status
reset), so a watcher must not read `idle` as "never completed".

## Spike E: session id

- `claude --session-id <uuid>` is accepted. Hook stdin `session_id` for the lead equals
  that uuid (checked: `3726c469-a533-4849-8e21-944486602487` in the hook log for
  `echo DW_SPIKE_OK_turn2`/`turn3`).
- After closing the AGTerm session, `claude --resume <uuid>` (same `--cwd`) reopened the
  same conversation with the full earlier history visible (slash-command turn and both
  typed turns). It continues the same id (not a fork).
- Transcripts live under `~/.claude/projects/<cwd with / and . replaced by ->/<uuid>.jsonl`,
  so resume needs the same working directory.
- Teammates get their own `session_id` (Spike A), so only the lead's id equals the one the
  launcher passed. Never match a teammate by `session_id`.

## Spike F: approval visibility

Simulated hook actions from a shell against a background session `spikeF` (`--no-select`)
while the owner's own session was selected:

```
agtermctl session status blocked --target F --blink     -> ok
agtermctl notify "Approval needed" --title "dw spike" --target F   -> ok
agtermctl ask "Approve spike action?" --message ... --button yes=Yes --button no=No --target F --no-block --json
   -> {"id":"D4834226-..."}
tree --json node F: {"status":"blocked","unseen":1,"ask":{"id":"D4834226-..."},"active":false}
tree top level:     {"askPending":null,"pickPending":null}
```

What the owner sees without switching: the blocked status glyph (blinking), the unseen badge
(`unseen: 1`) and a desktop notification attributed to the session. The default
`--style terminal` ask is attached to the session and **stays hidden and pending** until the
session is visited ("An explicit unselected session is accepted and keeps its ask hidden"),
so it is not itself a prompt the owner can see; the glyph, badge and notification are the
signals. A `--style gui` ask uses the window's shared modal slot (shared with `pick`),
centred over the terminal area and raised with `--follow`; it is visible from any session
but interrupts whatever the owner is doing and blocks other picks. **Not run live**: it would
have put a modal over the owner's working window. Recommendation: use the terminal-style ask
plus `blocked` glyph and notification by default (no focus theft); offer GUI+`--follow` only
as an explicit opt-in for runs the owner wants to be pulled to.

Ask lifecycle observed:

- A blocking `agtermctl ask ... --target F` (no `--no-block`) waits; `ask cancel <id>` makes
  it exit 2 with `{"result":"cancelled"}`; `ask result <id>` returns `{"result":"pending"}`
  (exit 1) while unanswered and `cancelled` (exit 2) after.
- Second `ask` to the same session while one is pending: refused immediately,
  `{"ok":false,"error":"ask already pending"}`. A guard must serialize its asks per session
  (queue them) or reuse/cancel the pending one.
- Use `agtermctl session seen --target F` and `session status idle` to clear the badge and
  glyph afterwards.
- Typing into the session clears the `blocked` glyph (per Settings status reset).

## Consequences for later tasks

- GUARD_REACHES_TEAMMATES = yes and GUARD_REACHES_SUBAGENTS = yes: team pipelines may ship
  behind the guard, provided the guard is a hook (project- or user-level) that keys on an
  environment marker, not on `session_id`, and denies via the JSON above.
- Hook may block for at least 900 s with `timeout: 3600` on the entry (see Spike B).
- Run state must not rely on `completed` as the end of a pipeline; use the result note and
  session close.
- Launcher: pre-accept or answer the workspace-trust dialog; kill the per-lead tmux server
  on run end; pass `--session-id`; use `--resume <id>` with the same cwd to reopen.
