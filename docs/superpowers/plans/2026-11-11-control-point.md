# Control Point Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One control session from which the owner starts runs in any registered project and asks for the status of any project, with risky actions held for approval.

**Architecture:** A deterministic Python CLI (`dw`) owns the registry, run records, queue, status and event handling. AGTerm hosts each run as a background session and feeds status events back through `hooks.conf`. A global, self-gated Claude Code `PreToolUse` hook (`dw guard`) holds guarded actions. `/control` is a thin Claude Code command that drives `dw`.

**Tech Stack:** Python 3.9+ standard library only (no third-party packages; every module starts with `from __future__ import annotations`), `unittest`, bash for the installer and the validator wrapper, `agtermctl` 0.37+, Claude Code CLI.

**Spec:** `docs/superpowers/specs/2026-11-11-control-point-design.md` — read it before any task.

## Global Constraints

- State directory: `~/.dodocs-workflow/`, overridable with env `DW_HOME` (tests always set it).
- Limits: at most `1` active run per project and `3` active runs in total; both configurable in the registry. A run whose state is `blocked` with a reason starting `awaiting approval` does not count against the total.
- Stall threshold default: `30` minutes.
- Run states, exactly: `queued`, `running`, `blocked`, `done`, `failed`, `interrupted`, `cancelled`.
- Part 1 launches harness `claude` only. `dw run` on a project with another harness refuses.
- Launched sessions run with `--permission-mode bypassPermissions`.
- Pipelines, agents and existing commands are not modified.
- `dw` never edits files inside a project checkout.
- `~/.claude/settings.json` and `~/.config/agterm/hooks.conf` are edited only by `dw setup`, only after showing the change and getting a yes (or `--yes`), by merging; other entries are never rewritten.
- The old `~/.claude/workspace/` and `/workspace` command are read (import) but never modified or deleted.
- External binaries are resolved through env overrides for tests: `DW_AGTERMCTL` (default `agtermctl`), `DW_CLAUDE` (default `claude`).
- AGTerm hooks and Claude Code hooks run with a minimal PATH. The installer records the absolute path of the `python3` it verified (3.9+) as the shebang of the installed `dw`; `tests/validate-control.sh` runs the suite under `/usr/bin/python3` as well when it exists.
- Every `agtermctl` call passes `--socket` when `AGT_SOCKET` or `AGTERM_SOCKET` is set.
- A run must not be able to change its own controls: see the guard's `control` category (Task 6).
- `dw run` refuses commands that work outside the project checkout: in part 1 that is `/container-team` and any command with `--docker`. The guard is gated on the working directory and would not reach them.
- `.claude/settings.local.json` is modified and tracked in this repo: always `git add` by explicit path, never `git add -A`.
- No network access in tests. No test may touch the real `~/.dodocs-workflow`, `~/.claude` or AGTerm.
- CI on GitHub is currently broken for unrelated infrastructure reasons; run the validators locally.
- Work on branch `feature/control-point`. Commit the spec and this plan as the first commit.

## Review Focus

1. **Two `dw` processes at once** (a status hook and a CLI call, or two hooks): no lost update to the registry or a run record. → Task 2 test `test_concurrent_updates_do_not_lose_writes`.
2. **Commands with quotes, newlines, `$`, or longer than 1,024 bytes**: the launched prompt reaches the harness byte-for-byte. → Task 3 test `test_prompt_is_passed_via_file_not_argv`.
3. **Working directory is a subdirectory of the project, or reaches it through a symlink**: the guard still finds the project and its active run. → Task 6 test `test_guard_resolves_project_from_subdir_and_symlink`.
4. **AGTerm unreachable** (binary missing, socket dead): `dw run` refuses with one clear line and creates no run record; `dw status` still answers from records; the guard inside an active run denies with a reason rather than allowing. → Task 3 `test_run_refuses_without_agterm`, Task 4 `test_status_without_agterm`, Task 6 `test_guard_denies_when_agterm_unreachable_in_active_run`.
5. **A corrupt or half-written JSON file**: `dw` names the file, skips it, and keeps working with the rest; the guard allows outside active runs and holds inside one. → Task 2 `test_corrupt_run_record_is_reported_and_skipped`, Task 6 `test_guard_fail_open_outside_runs_fail_closed_inside`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `control/dw` | Executable entry point; argument parsing and dispatch only |
| `control/dwlib/paths.py` | `DW_HOME` resolution and file locations |
| `control/dwlib/store.py` | Locked, atomic JSON read/update; registry and run-record access |
| `control/dwlib/agterm.py` | Thin wrapper over `agtermctl` (create session, tree, notify, ask, close, text) |
| `control/dwlib/runs.py` | Start, queue, limits, cancel, resume, finish |
| `control/dwlib/status.py` | Merge run records, AGTerm state and project progress |
| `control/dwlib/events.py` | Handlers for AGTerm `status` and `session.closed` events |
| `control/dwlib/guard.py` | Classify a tool call; `PreToolUse` entry; approvals |
| `control/dwlib/setup.py` | `dw setup`, `dw doctor`, legacy import |
| `control/guard-rules.json` | Default guard rules |
| `claude/commands/control.md` | The `/control` command |
| `tests/control/test_*.py` | Unit tests (`unittest`) |
| `tests/control/fake-agtermctl` | Scriptable stand-in for `agtermctl` |
| `tests/validate-control.sh` | Runs the unit tests; added to CI workflow |

Installed layout: `~/.dodocs-workflow/bin/dw`, `~/.dodocs-workflow/lib/dwlib/*.py`, `~/.dodocs-workflow/guard-rules.default.json`.

---

### Task 1: Spikes — verify the four mechanisms

No product code. Outcome is a results file that later tasks read. Each spike edits real user configuration temporarily; **ask the owner before starting, and restore every file afterwards.**

**Files:**
- Create: `docs/superpowers/specs/2026-11-11-control-point-spikes.md`

**Interfaces:**
- Produces: recorded answers, each with evidence:
  `GUARD_REACHES_TEAMMATES`, `GUARD_REACHES_SUBAGENTS`, `ENV_MARKER_REACHES_HOOKS`, `STATUS_ATTRIBUTION_CORRECT`, `ASK_VISIBLE_FROM_OTHER_SESSION` (and the ask style to use), `HOOK_MAX_WAIT_SECONDS`, `SLASH_COMMAND_AS_FIRST_PROMPT`, `COMPLETED_FIRES_PER_TURN`, `SESSION_ID_FLAG`.

- [ ] **Step 1: Back up** `~/.claude/settings.json` to the scratch directory.
- [ ] **Step 2: Spike A — guard reach.** Set env `DW_SPIKE_MARK=1` in the launch line. Add a `PreToolUse` hook (matcher `Bash`) to `~/.claude/settings.json` that appends its stdin JSON to a scratch log and denies any command containing `DW_SPIKE_DENY`. In a throwaway git repo, start Claude Code in an AGTerm session with `--permission-mode bypassPermissions` and have it create an agent team of two members that each run `echo DW_SPIKE_DENY`. Also have the lead spawn one ordinary subagent with `bypassPermissions` that runs the same command. Record, for the lead, each team member and the subagent: did the hook fire, was the deny honoured, what `cwd` and `session_id` the call carried, and whether `DW_SPIKE_MARK` was visible to the hook. Then run two such team sessions at once in different repos and record which AGTerm session each team member's status events are attributed to (the AGTerm docs warn that a tmux server reports to the session that started it).
- [ ] **Step 3: Spike B — hook wait.** Change the hook to `sleep 900` before answering, with `"timeout": 3600` on the hook entry. Record the longest wait the harness tolerates before it gives up, and what the agent sees when it does.
- [ ] **Step 4: Spike C — launch.** `agtermctl session new --no-select --cwd <repo> --name spike --command "zsh -lc '<claude> \"\$(cat <prompt-file>)\" --permission-mode bypassPermissions'"` with a prompt file containing `/dodocs-workflow version`. Record whether the slash command executed, and the exact command line that worked.
- [ ] **Step 5: Spike D — completion signal.** Using `agtermctl events --json --kind status`, record whether `completed` is emitted at the end of every turn of that session.
- [ ] **Step 6: Spike F — approval visibility.** From a hook in a background session, set that session `blocked`, send a notification and open an `agtermctl ask` on it while a different session is selected. Record what the owner sees without switching (badge, notification, dialog) and whether a GUI-style ask raised with `--follow` is preferable. Record what happens when a second `ask` targets the same session while one is pending.
- [ ] **Step 6b: Spike E — session id.** Record whether `claude --session-id <uuid>` is accepted and whether `claude --resume <uuid>` then reopens it. If not, record which field of hook stdin carries the lead session's id.
- [ ] **Step 7: Restore** `~/.claude/settings.json` from the backup and diff to confirm it is byte-identical. Close spike sessions.
- [ ] **Step 8: Write the results file** with the answers and evidence. If `STATUS_ATTRIBUTION_CORRECT` is `no`, record that run state must not rely on status events from team members (the result note and session close remain the signals). If `GUARD_REACHES_TEAMMATES` or `GUARD_REACHES_SUBAGENTS` is `no`, **stop and report to the owner**: the spec forbids shipping team pipelines with an unenforced guard.
- [ ] **Step 9: Commit** the spec, this plan and the results file: `docs: control point design, plan and spike results`.

---

### Task 2: Storage, registry and `dw project`

**Files:**
- Create: `control/dw`, `control/dwlib/__init__.py`, `control/dwlib/paths.py`, `control/dwlib/store.py`
- Create: `tests/control/test_store.py`, `tests/control/test_project_cli.py`, `tests/control/helpers.py`, `tests/validate-control.sh`
- Modify: `.github/workflows/validate.yml` (add a step running `bash tests/validate-control.sh`)

**Interfaces:**
- Produces (`paths.py`): `home() -> Path`; `registry_path() -> Path`; `runs_dir() -> Path`; `run_path(run_id: str) -> Path`; `result_note_path(run_id: str) -> Path` (`runs/<id>.result.md`); `prompt_path(run_id: str) -> Path` (`runs/<id>.prompt`).
- Produces (`store.py`):
  - `update_json(path: Path, fn: Callable[[dict], dict], default: dict) -> dict` — exclusive `fcntl.flock` on `<path>.lock`, read, apply `fn`, write to a temp file in the same directory, `os.replace`. Returns the written value.
  - `read_json(path: Path, default: dict) -> dict` — raises `CorruptFile(path)` on invalid JSON.
  - `load_registry() -> dict`; `find_project(registry: dict, query: str) -> dict` — match on id, then case-insensitive name, then unique substring; raises `ProjectNotFound` or `AmbiguousProject(candidates)`.
  - `list_runs() -> tuple[list[dict], list[Path]]` — records, plus paths of corrupt files skipped.
  - `load_run(run_id: str) -> dict`; `update_run(run_id: str, fn) -> dict`.
- Registry shape: `{"version": 1, "limits": {"per_project": 1, "total": 3}, "stall_minutes": 30, "projects": [{"id", "name", "path", "group", "harness": "claude", "notes": "", "guard_rules": []}]}`. Project `id` is the name lowercased with non-alphanumerics collapsed to `-`.
- Produces (`tests/control/helpers.py`): `class DwTestCase(unittest.TestCase)` — `setUp` creates a temp `DW_HOME`, puts `tests/control/fake-agtermctl` in `DW_AGTERMCTL`; `self.dw(*args, stdin=None, env=None) -> subprocess.CompletedProcess` runs `control/dw`.
- CLI: `dw project add --name N --path P --group G [--notes T]`; `dw project list [--json]`; `dw project remove ID`. Exit code `0` on success, `2` on user error with a one-line message on stderr.

- [ ] **Step 1: Write failing tests** in `test_store.py`:
  - `test_update_json_creates_file_with_default`
  - `test_concurrent_updates_do_not_lose_writes` — 8 processes each increment a counter 25 times through `update_json`; final value is `200`.
  - `test_corrupt_run_record_is_reported_and_skipped` — one valid and one truncated record; `list_runs()` returns 1 record and 1 corrupt path.
  - `test_find_project_by_id_name_and_unique_substring`, `test_find_project_ambiguous_raises_with_candidates`
- [ ] **Step 2: Write failing tests** in `test_project_cli.py`:
  - `test_add_then_list_json` — add name `SlotMe App`, path = a temp dir, group `ignashev_ai`; list shows id `slotme-app`, harness `claude`.
  - `test_add_rejects_missing_path` (exit 2), `test_add_rejects_duplicate_id` (exit 2), `test_remove_unknown_exits_2`
  - `test_path_is_stored_resolved` — a symlinked path is stored as its `realpath`.
- [ ] **Step 3: Run** `python3 -m unittest discover -s tests/control -v` — expect failures (modules missing).
- [ ] **Step 4: Implement** `paths.py`, `store.py`, the `dw` entry point with the `project` subcommands, and `helpers.py`.
- [ ] **Step 5: Create `tests/validate-control.sh`** in the style of the other validators (`PASS:`/`FAIL:` lines, non-zero exit on failure): runs the unittest discovery above and checks `control/dw` is executable.
- [ ] **Step 6: Run** `bash tests/validate-control.sh` — expect all PASS.
- [ ] **Step 7: Commit** `feat(control): registry storage and dw project commands`.

---

### Task 3: AGTerm adapter, `dw run`, limits, queue, cancel

**Files:**
- Create: `control/dwlib/agterm.py`, `control/dwlib/runs.py`, `tests/control/fake-agtermctl`, `tests/control/test_runs.py`
- Modify: `control/dw`

**Interfaces:**
- Consumes: Task 2 store API; Task 1 answers `SLASH_COMMAND_AS_FIRST_PROMPT` (the exact launch line) and `SESSION_ID_FLAG`.
- Produces (`agterm.py`); every function raises `AgtermUnavailable` when the binary is missing or the call fails to connect:
  - `available() -> bool`
  - `new_session(cwd: str, workspace_name: str, name: str, command: str, context: str) -> str` — background session (`--no-select --create-workspace`), restore pinned to nothing; returns the session id.
  - `session_states() -> dict[str, dict]` — session id → `{"status": str|None, "status_changed_at": float|None, "name": str}` from `tree --json` across all windows.
  - `notify(session_id: str, title: str, body: str) -> None`
  - `ask(session_id: str, title: str, message: str, buttons: list[tuple[str, str]], timeout: int) -> str|None` — returns the chosen button id, or `None` on escape, cancel or timeout.
  - `close_session(session_id: str) -> None`; `session_tail(session_id: str, lines: int) -> str`
- Produces (`runs.py`):
  - `new_run_id() -> str` — `r-YYYYMMDD-HHMMSS-<4 hex>`.
  - `request_run(project: dict, command: str) -> dict` — creates the record as `queued`, then calls `start_eligible()`; returns the record.
  - `start_eligible() -> list[dict]` — starts queued runs oldest-first while limits allow; returns the runs started.
  - `counts_against_total(run: dict) -> bool`
  - `cancel_run(run_id: str) -> dict`
- Run record shape: `{"id", "project_id", "command", "state", "reason": None, "agterm_session": None, "harness_session": None, "created_at", "started_at": None, "ended_at": None, "approvals": [], "pending_approval": None, "grants": []}`. Timestamps are epoch seconds (float).
- `harness_session`: when Task 1 recorded `SESSION_ID_FLAG` = yes, `dw` generates a UUID, passes it with that flag at launch and stores it; otherwise it stays `None` here and Task 5 fills it by the method Task 1 recorded.
- Launch: the full first prompt (owner's command, blank line, the fixed suffix below) is written to `prompt_path(run_id)` and passed to the harness by reading that file in the session command, never inline. Session name: `<project name>: <first 40 chars of command>`. Session context: the run id.
- Fixed suffix, verbatim:
  ```
  When this work is finished, or you cannot continue, write a short result note to <ABSOLUTE result_note_path>. First line: exactly DONE, BLOCKED or FAILED. Then: what was done, the pull request URL if any, and what is left. Write this file even if the work failed.
  ```
- `fake-agtermctl`: a Python script. Records each invocation as a JSON line in `$DW_HOME/fake-agterm/calls.jsonl`. `session new` prints a fresh id and stores the session; `tree --json` renders stored sessions with any status set by the test through `$DW_HOME/fake-agterm/sessions.json`; `ask` prints the answer scripted in `$DW_HOME/fake-agterm/ask-answer` (missing file = timeout, exit 124); `FAKE_AGTERM_DOWN=1` makes every call exit 1 with a connection error. Helper methods on `DwTestCase`: `agterm_calls()`, `set_session_status(sid, status)`, `script_ask(answer_id)`.
- CLI: `dw run PROJECT COMMAND...` prints `<run-id> started` or `<run-id> queued (<reason>)`; `dw queue [--json]`; `dw cancel RUN_ID`.

- [ ] **Step 1: Write `fake-agtermctl`** and the `DwTestCase` helpers.
- [ ] **Step 2: Write failing tests** in `test_runs.py`:
  - `test_run_starts_session_in_group_workspace` — one `session new` call with `--no-select`, `--workspace-name ignashev_ai`, `--create-workspace`, `--cwd <project path>`; record state `running`, `agterm_session` set.
  - `test_prompt_is_passed_via_file_not_argv` — command = 3,000 bytes containing `"`, `'`, `$HOME`, backticks and a newline; the prompt file's content starts with those exact bytes and ends with the suffix; the `--command` argument does not contain the command text.
  - `test_second_run_same_project_is_queued` — reason `project busy`.
  - `test_fourth_run_across_projects_is_queued` — reason `total limit 3`.
  - `test_awaiting_approval_run_frees_a_total_slot` — three running, one set to `blocked`/`awaiting approval: x`; a run in a fourth project starts.
  - `test_limits_come_from_registry` — `total: 1` queues the second project.
  - `test_run_refuses_without_agterm` — `FAKE_AGTERM_DOWN=1`: exit 2, stderr contains `AGTerm`, and no run record exists.
  - `test_run_refuses_non_claude_harness` — exit 2.
  - `test_run_refuses_out_of_checkout_commands` — `/container-team x` and `/scrum-team --docker x` exit 2 with a message naming the reason.
  - `test_harness_session_id_recorded_and_passed_at_launch` (skipped with a reason when `SESSION_ID_FLAG` is no)
  - `test_cancel_closes_session_and_marks_cancelled`, `test_cancel_queued_run_never_started`
- [ ] **Step 3: Run the tests** — expect failures.
- [ ] **Step 4: Implement** `agterm.py`, `runs.py`, and the `run`, `queue`, `cancel` subcommands.
- [ ] **Step 5: Run** `bash tests/validate-control.sh` — expect all PASS.
- [ ] **Step 6: Commit** `feat(control): start, queue and cancel runs in AGTerm sessions`.

---

### Task 4: `dw status`

**Files:**
- Create: `control/dwlib/status.py`, `tests/control/test_status.py`
- Modify: `control/dw`

**Interfaces:**
- Consumes: `store.list_runs`, `agterm.session_states`, `paths.result_note_path`.
- Produces (`status.py`):
  - `project_status(project: dict, runs: list[dict], sessions: dict[str, dict]|None, now: float) -> dict` — `{"project", "active": [RunView], "queued": [RunView], "recent": [RunView]}`; `recent` is the last 5 ended runs.
  - `RunView` keys: `id`, `command`, `state`, `reason`, `since` (seconds in current state), `live` (AGTerm status or `None`), `stalled` (bool), `progress` (str or `None`), `result` (first 20 lines of the result note or `None`).
  - `find_progress(project_path: str, run: dict) -> str|None` — for a command starting with `/scrum-team`, the newest `docs/features/*/PROGRESS.md` modified after `started_at`; returns its `## Current Phase` section and `## Phase Status` table. Otherwise `None`.
  - `overall_status(now: float) -> dict` — `{"needs_owner": [...], "projects": [...], "corrupt_files": [...]}`; `needs_owner` lists runs that are `blocked`, `failed`, or `interrupted`.
- `stalled` is true when state is `running`, AGTerm reports `active`, and `now - status_changed_at` exceeds `stall_minutes`.
- CLI: `dw tail RUN_ID [--lines N]` (default 40) prints the run's terminal tail through `agterm.session_tail`; exit 2 if the run has no live session.
- CLI: `dw status [PROJECT] [--json]`. Text output order: needs owner, running, queued, recently finished. With AGTerm unreachable, `live` is `None` everywhere and the text output ends with `AGTerm not reachable: live state unavailable`.

- [ ] **Step 1: Write failing tests** in `test_status.py`:
  - `test_blocked_run_listed_under_needs_owner_with_reason`
  - `test_stalled_flag_after_threshold` — status `active` unchanged for 31 minutes → `stalled` true; 29 minutes → false.
  - `test_scrum_progress_extracted` — fixture `PROGRESS.md` with `## Current Phase\nPhase 4: Build + Test`; `progress` contains `Phase 4: Build + Test`.
  - `test_progress_ignores_files_older_than_run`
  - `test_result_note_shown_for_finished_run`
  - `test_status_without_agterm` — `FAKE_AGTERM_DOWN=1`: exit 0, runs listed, trailing notice present.
  - `test_status_reports_corrupt_files` — the corrupt file's path appears in the output and the other runs are still listed.
  - `test_project_filter_loose_match` — `dw status slot` resolves `slotme-app`.
  - `test_tail_prints_session_text_and_fails_for_ended_run`
- [ ] **Step 2: Run the tests** — expect failures.
- [ ] **Step 3: Implement** `status.py` and the `status` subcommand.
- [ ] **Step 4: Run** `bash tests/validate-control.sh` — expect all PASS.
- [ ] **Step 5: Commit** `feat(control): merged status across projects`.

---

### Task 5: Events — completion, blocking, interruption, resume

**Files:**
- Create: `control/dwlib/events.py`, `tests/control/test_events.py`
- Modify: `control/dwlib/runs.py`, `control/dw`

**Interfaces:**
- Consumes: Task 1 answers `COMPLETED_FIRES_PER_TURN`, `SESSION_ID_FLAG`; `agterm.notify`; `runs.start_eligible`.
- Produces (`events.py`):
  - `on_status(session_id: str, status: str) -> None`
  - `on_session_closed(session_id: str) -> None`
  - `read_result_note(run_id: str) -> tuple[str, str]|None` — (`DONE`|`BLOCKED`|`FAILED`, body); a first line that is none of the three counts as `DONE` when the file is non-empty.
- Produces (`runs.py`): `finish_run(run_id: str, state: str, reason: str|None) -> dict`; `resume_run(run_id: str) -> dict`.
- Behaviour:
  - `on_status(..., "blocked")`: run → `blocked` with reason `waiting for input` unless a `pending_approval` is set (then the reason is left as is); notify.
  - `on_status(..., "active")`: a `blocked` run with no `pending_approval` → `running`.
  - `on_status(..., "completed")`: if a result note exists → finish as `done` (note `DONE`), `blocked` (`BLOCKED`; run stays open, notify) or `failed` (`FAILED`); notify; `start_eligible()`. With no result note, nothing changes.
  - `on_session_closed`: run still `running` or `blocked` → `done`/`failed` per the result note if one exists, else `interrupted`; then `start_eligible()`. Ended runs are untouched.
  - Events for sessions that belong to no run are ignored silently and exit 0.
- `resume_run`: only for `interrupted`; opens a new AGTerm session in the project that resumes the stored harness session (form recorded in Task 1); state → `running`; subject to the same limits (refuses with a message if over).
- CLI: `dw hook status` and `dw hook session-closed` read `AGT_SESSION_ID` and `AGT_EVENT_STATUS` from the environment; always exit 0 and never print to stdout. `dw resume RUN_ID`.

- [ ] **Step 1: Write failing tests** in `test_events.py`:
  - `test_completed_without_note_changes_nothing`
  - `test_completed_with_done_note_finishes_and_starts_next_queued` — the queued run's `session new` call appears after the event.
  - `test_completed_with_failed_note_marks_failed_and_notifies`
  - `test_blocked_then_active_round_trip`
  - `test_blocked_does_not_overwrite_pending_approval_reason`
  - `test_session_closed_without_note_marks_interrupted`
  - `test_session_closed_with_done_note_marks_done`
  - `test_unknown_session_event_is_ignored` — exit 0, no files changed.
  - `test_hook_never_fails` — corrupt registry: exit 0, error appended to `$DW_HOME/dw.log`.
  - `test_resume_only_for_interrupted`, `test_resume_respects_limits`
- [ ] **Step 2: Run the tests** — expect failures.
- [ ] **Step 3: Implement** `events.py`, `finish_run`, `resume_run`, and the `hook` and `resume` subcommands.
- [ ] **Step 4: Run** `bash tests/validate-control.sh` — expect all PASS.
- [ ] **Step 5: Commit** `feat(control): run lifecycle from AGTerm events`.

---

### Task 6: Guard

**Files:**
- Create: `control/dwlib/guard.py`, `control/guard-rules.json`, `tests/control/test_guard_classify.py`, `tests/control/test_guard_hook.py`
- Modify: `control/dw`

**Interfaces:**
- Consumes: Task 1 answer `HOOK_MAX_WAIT_SECONDS`; `agterm.ask`; store API.
- Produces (`guard.py`):
  - `load_rules(project: dict) -> list[dict]` — defaults from `guard-rules.default.json` in `DW_HOME` (falling back to the repo file) plus the project's `guard_rules`.
  - `classify(tool_name: str, tool_input: dict, cwd: str, project_path: str, rules: list[dict]) -> dict|None` — the matching rule (`{"id", "category", "describe"}`) or `None`.
  - `active_run_for_cwd(cwd: str) -> tuple[dict, dict]|None` — (project, run) when `realpath(cwd)` is inside a registered project that has a run in state `running` or `blocked`.
  - `decide(payload: dict) -> dict` — the `PreToolUse` hook output object.
- Rule categories, exactly: `merge`, `deploy`, `publish`, `send`, `spend`, `destroy`, `control`.
- `control` protects the control point from the runs it launches. Inside an active run it holds: any `dw` invocation other than `dw status`, `dw queue`, `dw tail` and `dw project list`; and any Bash, Write or Edit that targets `DW_HOME` (except that run's own result note), `~/.claude/settings.json`, or AGTerm's `hooks.conf`. `control` actions are never approvable "for this run": the dialog offers only `once` and `deny`, and `dw approve` refuses them.
- Decision flow in `decide`:
  1. No active run for `cwd` → allow.
  2. `classify` returns `None` → allow.
  3. Rule id in `run["approvals"]` → allow. A matching one-shot entry in `run["grants"]` → consume it and allow.
  4. Otherwise, if the run already has a `pending_approval` for a different action, deny at once with the step 6 reason (one question per run at a time). Else set `pending_approval = {"rule", "describe", "tool", "since"}`, state `blocked`, reason `awaiting approval: <describe>`; set the AGTerm session status to `blocked` and send a notification naming the project and action; then ask, in the style Task 1 recorded as visible, with buttons `once` = "Approve once", `run` = "Approve for this run", `deny` = "Deny", timeout `min(HOOK_MAX_WAIT_SECONDS - 30, 3000)`.
  5. `once` → allow. `run` → add the rule id to `approvals`, allow. `deny` → deny with reason `Denied by the owner. Do not attempt this action another way.` In all three, clear `pending_approval` and return the run to `running`.
  6. No answer → deny with reason `Approval is pending with the owner. Do not work around it. Continue other work, then retry this exact action later.`; `pending_approval` stays set.
- Hook output: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"|"deny", "permissionDecisionReason": str}}`. For an allow in steps 1–2 the hook prints nothing and exits 0.
- Failure posture: any exception → outside an active run, exit 0 silently; inside one (or when that cannot be determined because the registry is unreadable but the `cwd` matches a path mentioned in a readable run record), deny with reason `Guard error: <message>`. Errors are appended to `$DW_HOME/dw.log`.
- CLI: `dw guard` (stdin: hook payload). `dw approve RUN_ID` adds a one-shot grant for the pending rule and clears the pending approval; `dw deny RUN_ID` clears it without a grant. Both exit 2 when nothing is pending.
- Default rules must make the classification table below pass. Rule syntax is the implementer's choice.

Classification table (`project_path=/p`, `cwd=/p` unless stated):

| Tool call | Result |
|---|---|
| Bash `git push origin main` | `merge` |
| Bash `git push` while HEAD is the default branch | `merge` |
| Bash `git push origin feature/x` | allow |
| Bash `git merge feature/x` while HEAD is the default branch | `merge` |
| Bash `gh pr merge 41 --squash` | `merge` |
| Bash `gh pr create --title t` | allow |
| Bash `kubectl apply -f k8s/` | `deploy` |
| Bash `kubectl get pods` | allow |
| Bash `helm upgrade api ./chart` | `deploy` |
| Bash `vercel deploy --prod` | `deploy` |
| Bash `docker push ghcr.io/x/y:1` | `deploy` |
| Bash `docker build -t y .` | allow |
| Bash `curl -X POST https://api.example.com/v1/posts -d @b.json` | `publish` |
| Bash `curl -X POST http://localhost:8000/api/items -d '{}'` | allow |
| Bash `curl https://example.com/docs` | allow |
| Bash `psql -c "DROP TABLE users"` | `destroy` |
| Bash `rm -rf /Users/me/other` | `destroy` |
| Bash `rm -rf ./build` | allow |
| Bash `cd /tmp && git push origin main` | `merge` |
| `mcp__claude_ai_Gmail__send_message` | `send` |
| `mcp__claude_ai_Gmail__search_threads` | allow |
| `mcp__claude_ai_Slack__post_message` (unknown server, write verb) | `publish` |
| `mcp__linear__save_issue` | allow (issue trackers are on the read/work allowlist) |
| `mcp__plugin_stripe_stripe__stripe_api_write` | `spend` |
| `mcp__plugin_stripe_stripe__stripe_api_read` | allow |
| `mcp__some_new_server__get_items` | allow |
| `mcp__some_new_server__publish_page` | `publish` |
| Write `/p/src/a.py` | allow |
| Bash `dw approve r-1` | `control` |
| Bash `~/.dodocs-workflow/bin/dw setup --remove --yes` | `control` |
| Bash `dw status --json` | allow |
| Write `<DW_HOME>/runs/<this run>.result.md` | allow |
| Write `<DW_HOME>/runs/<this run>.json` | `control` |
| Edit `~/.claude/settings.json` | `control` |
| Bash `echo x >> ~/.dodocs-workflow/registry.json` | `control` |

- [ ] **Step 1: Write failing tests** in `test_guard_classify.py`: one subtest per table row, named `test_classification_table`. The two "HEAD is the default branch" rows use a real temp git repo.
- [ ] **Step 2: Write failing tests** in `test_guard_hook.py`:
  - `test_no_active_run_allows_silently` — empty stdout, exit 0.
  - `test_guard_resolves_project_from_subdir_and_symlink` — `cwd` = `<project>/src/deep`, and separately a symlink to the project; both hold `git push origin main`.
  - `test_approve_once_allows_and_asks_again_next_time`
  - `test_approve_for_run_is_remembered`
  - `test_deny_returns_owner_denied_reason`
  - `test_no_answer_denies_and_leaves_pending` — run is `blocked`, reason starts `awaiting approval`.
  - `test_dw_approve_grants_exactly_one_retry`
  - `test_dw_deny_clears_pending`
  - `test_control_actions_offer_no_run_wide_approval_and_dw_approve_refuses`
  - `test_second_guarded_call_while_one_pending_is_denied_without_second_dialog`
  - `test_pending_approval_sets_session_blocked_and_notifies`
  - `test_guard_denies_when_agterm_unreachable_in_active_run`
  - `test_guard_fail_open_outside_runs_fail_closed_inside` — corrupt registry: `cwd` unrelated → allow; `cwd` matching a run record's project path → deny with `Guard error`.
  - `test_guard_latency_outside_runs` — 20 invocations with a 50-project registry average under 150 ms each.
- [ ] **Step 3: Run the tests** — expect failures.
- [ ] **Step 4: Implement** `guard.py`, `guard-rules.json`, and the `guard`, `approve`, `deny` subcommands.
- [ ] **Step 5: Run** `bash tests/validate-control.sh` — expect all PASS.
- [ ] **Step 6: Commit** `feat(control): approval guard for runs`.

---

### Task 7: `dw setup`, `dw doctor`, legacy import

**Files:**
- Create: `control/dwlib/setup.py`, `tests/control/test_setup.py`
- Modify: `control/dw`

**Interfaces:**
- Produces (`setup.py`):
  - `plan_setup(settings_path: Path, hooks_conf_path: Path, dw_bin: str) -> list[dict]` — pending changes, each `{"file", "description", "apply": Callable}`; empty when already set up.
  - `remove_setup(settings_path: Path, hooks_conf_path: Path) -> list[str]` — removes exactly what `plan_setup` adds; returns descriptions.
  - `import_legacy(legacy_path: Path, group_for: Callable[[dict], str|None]) -> list[dict]` — projects added; a project whose `group_for` returns `None`, whose path does not exist, or whose id already exists is skipped.
  - `doctor() -> list[tuple[str, bool, str]]` — (check, ok, detail).
- Settings entry: a `PreToolUse` hook group with matcher `*`, command `'<dw_bin>' guard`, and `timeout` = the Task 1 `HOOK_MAX_WAIT_SECONDS`. It is identified for idempotence and removal by its command string.
- `hooks.conf` lines, exactly, between marker comments `# >>> dodocs-workflow control` and `# <<< dodocs-workflow control`:
  ```
  on status '<dw_bin>' hook status
  on session.closed '<dw_bin>' hook session-closed
  ```
  After writing, `agtermctl hooks reload` is called.
- Paths are overridable for tests with env `DW_CLAUDE_SETTINGS` and `DW_AGTERM_HOOKS_CONF`.
- `doctor` checks: `agtermctl` reachable; guard entry present; both `hooks.conf` lines present; every project path exists; no run is `running` whose AGTerm session is gone (reported, and such runs are marked `interrupted`); no corrupt files.
- CLI: `dw setup [--yes] [--remove]` prints each pending change and asks `Apply? [y/N]` unless `--yes`; `dw doctor` exits 1 if any check fails; `dw project import-legacy [--from PATH]` prompts for each project's group (empty answer skips).

- [ ] **Step 1: Write failing tests** in `test_setup.py`:
  - `test_setup_adds_guard_entry_and_preserves_other_hooks` — fixture settings with existing `PreToolUse`, `Stop` and unrelated keys; after setup every original entry is still present and unchanged, plus one new entry.
  - `test_setup_is_idempotent` — second run reports nothing to do; files byte-identical.
  - `test_setup_without_yes_and_answer_no_changes_nothing`
  - `test_setup_creates_missing_files`
  - `test_remove_restores_original_bytes` — setup then `--remove` leaves both fixture files byte-identical to the originals.
  - `test_hooks_conf_block_between_markers_and_reload_called`
  - `test_import_legacy_maps_fields_and_skips_missing_paths` — fixture copied from the shape of `~/.claude/workspace/registry.json` (`id`, `name`, `workspace`, `path`, `description`); `description` becomes `notes`.
  - `test_import_legacy_never_writes_to_legacy_file` — mtime and bytes unchanged.
  - `test_doctor_marks_orphaned_running_run_interrupted`
- [ ] **Step 2: Run the tests** — expect failures.
- [ ] **Step 3: Implement** `setup.py` and the `setup`, `doctor`, `project import-legacy` subcommands.
- [ ] **Step 4: Run** `bash tests/validate-control.sh` — expect all PASS.
- [ ] **Step 5: Commit** `feat(control): setup, doctor and legacy import`.

---

### Task 8: `/control` command, installer, docs

**Files:**
- Create: `claude/commands/control.md`
- Modify: `install.sh`, `uninstall.sh`, `tests/validate-install.sh`, `docs/reference-commands.md`, `docs/FEATURES.md`, `README.md`, `CHANGELOG.md`

**Interfaces:**
- Consumes: every `dw` subcommand from Tasks 2–7.
- `install.sh`: add `control` to the `COMMANDS` array; add a `CONTROL_FILES` array listing `dw`, each `dwlib/*.py` and `guard-rules.json`, installed (local copy or `curl` from `$REPO_URL/control/...`, matching the existing pattern) to `~/.dodocs-workflow/bin/dw` (mode 755), `~/.dodocs-workflow/lib/dwlib/`, `~/.dodocs-workflow/guard-rules.default.json`. If `~/.local/bin` exists, symlink `dw` there. Finish by printing: `Run 'dw setup' to enable approvals and status events.` The installer itself never runs `dw setup`.
- `uninstall.sh`: same arrays; runs `dw setup --remove --yes` if `dw` is present, then removes `bin/`, `lib/`, `guard-rules.default.json` and the symlink. It must leave `registry.json` and `runs/` in place.
- `control/dw` must find `dwlib` both in the repo (`control/dwlib`) and installed (`../lib/dwlib`).
- `claude/commands/control.md` content requirements (wording is the implementer's):
  - Runs `dw doctor` first; if the guard or hooks are missing, says so and offers `dw setup`.
  - Uses only `dw` for registry, run, queue, status, approve and deny operations.
  - Never edits files in a registered project and never does a project's work; it starts a run.
  - When asked for work: picks the command (`/scrum-team`, `/fix-the-issue`, `/change-request`, `/gtm-team`, or free text), states the choice and reason in one line, then runs `dw run`.
  - Status answers: what needs the owner first, then running, then finished. Uses `dw status --json`; for "what is it doing right now" reads the session tail.
  - Approvals: describes the pending action from `dw status`, and runs `dw approve` or `dw deny` only on the owner's explicit word in that conversation.
- Docs: add `/control` and the `dw` subcommands to `docs/reference-commands.md`; update the "N slash commands" count in `docs/FEATURES.md` (`tests/validate-docs.sh` checks it against `claude/commands/`); one short section in `README.md`; a `CHANGELOG.md` entry under Unreleased. Do not bump `VERSION` (releases go through `release.sh`).

- [ ] **Step 1: Extend `tests/validate-install.sh`** with checks that fail now: after a local install into a temp `HOME`, `~/.dodocs-workflow/bin/dw` exists and `dw project list --json` prints `[]`; `~/.claude/commands/control.md` exists; after uninstall the binary and library are gone, and a `registry.json` created in between still exists.
- [ ] **Step 2: Run** `bash tests/validate-install.sh` — expect the new checks to FAIL.
- [ ] **Step 3: Write `claude/commands/control.md`** and update `install.sh` and `uninstall.sh`.
- [ ] **Step 4: Update the docs** listed above.
- [ ] **Step 5: Run every validator**: `for t in tests/validate-*.sh; do bash "$t" || echo "FAILED: $t"; done` — expect no `FAILED` line.
- [ ] **Step 6: Manual acceptance on the owner's machine** (ask before running; it starts real sessions and edits `~/.claude/settings.json` through `dw setup`):
  1. Local install, `dw setup`, `dw project import-legacy`.
  2. From a `/control` session: start a small `/fix-the-issue` run in one project and a free-text run in another; confirm both appear as background sessions in the right AGTerm workspaces.
  3. Ask for status of one project and of everything; confirm the answers match the sessions.
  4. In a throwaway repo registered as a project, have a run attempt `git push origin main`; confirm the dialog appears, deny works, and "approve for this run" is remembered.
  5. Close one run's session by hand; confirm it shows as `interrupted` and `dw resume` reopens it.
  Record the outcome of each in the pull request description.
- [ ] **Step 7: Commit** `feat(control): /control command, installer and docs`.
