# The control point

One place to hand out work to all your projects and to ask how they are going. This page
says what it is, how to set it up, how approvals work, and, in plain words, what its guard
does not protect against. For the command syntax see the
[command reference](reference-commands.md#control-point).

## What it is, and is not

The control point is two things:

- **`dw`**, a command-line tool. It keeps a registry of your projects, starts a run in a
  project as a background session in the AGTerm terminal, reports status, and handles
  approvals. It does everything that has to be reliable, and it uses no tokens.
- **`/control`**, a Claude Code command. It is a thin conversational layer over `dw`: you
  say "fix the login bug in slotme" or "what is going on?", and it runs the right `dw`
  command and answers in plain language.

A **run** is one unit of work in one project: a command exactly as you would type it
(`/scrum-team --auto invoice sync`, `/fix-the-issue ...`, `/gtm-team ...`, or free text).
It gets its own AGTerm session in the workspace you chose for that project, and runs with
permissions bypassed, as the pipelines already require.

It is **not**:

- a place where work gets done. The control session only routes, starts, watches and
  reports. It never edits a project.
- a sandbox. See [What the guard does not protect against](#what-the-guard-does-not-protect-against).
- a change to any pipeline. `/scrum-team`, `/gtm-team` and the rest run exactly as before.
- a scheduler. Recurring runs are a later part.

## First-time setup

1. **Install.** `bash install.sh` copies `dw` to `~/.dodocs-workflow/bin/dw` and the `/control`
   command to `~/.claude/commands/`. If `~/.local/bin` exists, `dw` is linked there. The
   installer needs a `python3` 3.9 or newer; without one, the control point is skipped with a
   warning and the rest installs. It never edits your Claude Code settings or terminal hooks.
   The installer installs the whole workflow, agents and commands included, at the version of
   the repository you run it from, which may be newer than what you have installed. To install
   only the control point, run this from a checkout of the repository, then copy
   `claude/commands/control.md` to `~/.claude/commands/` yourself:

   ```
   DW_INSTALL_HOME="$HOME/.dodocs-workflow" HOME="$(mktemp -d)" bash install.sh
   ```

   `DW_INSTALL_HOME` keeps `dw` in your real `~/.dodocs-workflow`; the throwaway `HOME` takes
   the agents and commands. It also means no `dw` link is made in `~/.local/bin`: use
   `~/.dodocs-workflow/bin/dw` or link it yourself.
2. **`dw setup`.** Shows the change it will make and asks before making it: one guard entry in
   `~/.claude/settings.json` and two lines in AGTerm's `hooks.conf`. It merges and never
   rewrites other entries. **Runs cannot start until this has been run**, and `dw run` and
   `dw resume` test the guard entry once before each launch: the entry must exist, cover
   every tool (matcher `*`, empty or absent) and actually execute, or the run is refused.
   Running `dw setup` again repairs an entry whose program is missing or not executable, or
   whose matcher does not cover all tools, and leaves exactly one guard entry. It does
   **not** repair an entry whose program exists but fails: fix that one by hand. `dw doctor` checks the result;
   `dw setup --remove` takes it all out again.
3. **Register projects.** `dw project add --name <name> --path <path> --group <AGTerm workspace>`, or
   `dw project import-legacy` to import the projects from the old `/workspace` registry
   (it asks for each project's workspace; the old command and its files are left untouched).
4. **Trust each project in Claude Code once.** Open Claude Code in the directory and accept
   the trust dialog. `dw run` refuses projects that are not trusted yet.
5. **Open `/control`** in a Claude Code session and talk to it. It is meant to live in one
   long-running session, but holds no state: closing it loses nothing. Open it in a directory
   outside your registered projects: inside a project with an active run, the guard holds the
   control session's own `dw` commands like that run's.

Uninstalling (`uninstall.sh`) first runs `dw setup --remove`, then removes the program. Your
registry, run records and log in `~/.dodocs-workflow/` are kept.

## Limits

- **One active run per project, three in total.** Further runs wait in a queue and start when
  there is room. A run that is only waiting for approval does not count against the total.
- **AGTerm is required** to start runs. Without it, the registry and `dw status` still work and
  `dw run` refuses.
- **Claude Code only** for now. Other harnesses are a later part; `dw run` refuses them.
- **Nothing outside the checkout.** `/container-team` and any `--docker` command are refused,
  because the guard only reaches commands that work in the project directory.
- **A run that finishes as done has its session closed.** After the state change and the
  notification, `dw` closes the run's AGTerm session. **Closing a session ends anything still
  running in it**, such as a preview server a pipeline started, so start a run whose output you
  want to browse in its session with `dw run --keep-open <project> "<command>"` (kept across
  `dw resume`), or turn closing off for every run with `"close_done_sessions": false` at the top
  level of `~/.dodocs-workflow/registry.json` (`--keep-open` wins either way). Sessions of runs
  that failed, blocked or were interrupted stay open for you to look at; `dw dismiss <run-id>`
  closes a finished run's session that is still open, and `dw status` marks such a run
  `session still open`. A failed close is only logged in `dw.log`.
- A run that is interrupted (AGTerm restarted, session lost) is never re-run automatically.
  `dw resume <run-id>` reopens its Claude conversation and tells the agent to continue the
  task and finish it, with the same instructions for the result note. A finished note left
  over from before the interruption is set aside first, so it cannot end the resumed run at once.
- **Shell.** Claude Code on macOS runs commands in zsh. The guard looks through the zsh
  words that go in front of a command (`repeat N`, `noglob`, `nocorrect`, `builtin`, `exec`,
  `-`) and judges the command behind them.

## How approvals work

While a run is active in a project, a guard checks every tool call made in that directory and
holds the risky ones: merging or pushing to the default branch, deploying, publishing or
sending anything outward, spending money, destructive data commands, and anything that would
change the control point's own settings. Everything it does not recognise is allowed.

- **The dialog.** A held action opens a native AGTerm question on that run's session, marks
  the run `blocked` with the reason `awaiting approval`, and sends a notification. You can
  answer *approve once*, *approve this action for the rest of the run*, or *deny*. "For this
  run" means the rule that held it, in that run only, until it ends.
- **What the question shows.** One line. The guarded action comes first and is never cut. After
  it, when the action runs in another directory than the session's, comes `(in <directory>)`
  (a very long directory is shortened in the middle). Then the surrounding command, with each
  line break shown as `⏎`. If the command is too long it is trimmed at the end with a visible
  `… (+N chars; full command in dw.log)`; the full text is in `dw.log`. The text is the
  agent's own command, cleaned of control and invisible formatting characters, but not
  otherwise interpreted. Do not take it as a description of what the command does.
- **What one approval covers.** The guarded part of the command, in the directory it runs in,
  and not the whole command line. If a run's first try is "commit, then push" and you approve
  it, a later plain `git push origin main` in the same directory is the same action and goes
  through once. This holds only for plain command sequences (commands joined with `;`, `&&`
  or `||`). A command with a loop or `if`, a pipe, a wrapper (`xargs`, `sudo`, `timeout`,
  `env` ...), a subshell or group, a background job, or inline code (`bash -c`,
  `python -c` ...) is approved as a whole, by its exact text. Repeats count: `X && X` is not `X`. The same
  action in another directory is a different action. File writes and other tools are approved
  by their exact input.
- **The 15-minute wait.** The guard waits up to about fifteen minutes for an answer. If none
  comes, it refuses for now, tells the agent to carry on with other work and retry, and the
  approval stays pending.
- **From `/control`.** `dw approve <run-id>` lets the pending action through once;
  `dw deny <run-id>` refuses it. Both work while the question is waiting (the waiting call is
  let through or refused at once) and afterwards (the agent's retry is let through once, or
  refused). `/control` runs these only when you say so in that conversation.
- **Holds that cannot be approved from `dw`.** A run must not be able to change its own
  controls. A `dw` command that changes state, or a write to the control point's state
  directory, `~/.claude/settings.json` or AGTerm's hooks file, is held in a separate
  `control` category. It can be approved once, from the dialog only, never for the rest of
  the run and never with `dw approve`.
- **Commands the guard cannot read.** For the programs it guards (git, gh, kubectl, the
  shells, interpreters, wrappers ...), a command whose deciding words are only known at run
  time, or whose syntax the guard cannot follow, is held as "command cannot be read", in its
  own `unreadable` category. It can be approved once, with `dw approve`, or for the rest of
  the run with the dialog's *Approve unreadable commands for this run* button. **Approving
  unreadable commands for a run turns off the guard's fail-closed reading for that run:**
  every later command it cannot read in that run goes through without a question, whatever
  it does. When the same command also matches another category (a push, a deploy, a change
  to the control point), that category decides the question, and an approval of unreadable
  commands never lets it through. Answering such a question *for this run* remembers only the
  other rule, not the unreadable class.
  The run-wide approval does **not** cover four kinds of unreadable command, which stay in
  the `control` category ("command cannot be read and may change the control point"; approve
  once from the dialog or deny, never with `dw approve`):
  1. a command whose text mentions the control point or a file or variable that protects it
     (`dw`, `.dodocs-workflow`, `DW_HOME`, `.claude/settings`, `settings.local.json`,
     `hooks.conf`, `agtermctl`, `.git/config`, `.git/hooks`, `.git/info/attributes`,
     `GIT_DIR`, `core.hooksPath`, `BASH_ENV`, `LD_PRELOAD` and the other loader variables), in
     any case and through quotes or backslashes;
  2. a command where what cannot be read is where it writes (a loop variable over words only
     known at run time, or too many words, used as a write target; an arithmetic subscript),
     or a git configuration or environment override (`git -c core.sshCommand=...`,
     `GIT_DIR=...`, `git config $KEY ...`);
  3. anything where what runs is itself computed, after the same-command variables and
     functions are read (see [What the guard reads in full](#what-the-guard-reads-in-full)):
     a program word (`$CMD`, `"$TOOL" get x`, `$(echo git) status`, and any run-time word
     after a wrapper, which the guard cannot tell from the program: `timeout 5 ls $DIR`,
     `sudo -u x make "$T"`), a code loader (`node -r "$X"`, `python3 -m "$MOD"`, `perl -M$X`),
     a script operand (`python3 "$SCRIPT"`, `bash $S`), inline code given as a value
     (`python3 -c "$CODE"`, `eval "$X"`), or a call of a function the command defines but the
     guard could not read. Plain "command cannot be read" means only a known program with a
     run-time argument (`kubectl $VERB pods`, `git push origin "$B"`; `python3 scripts/x.py "$f"`
     is not held at all);
  4. shell or interpreter code that could not be scanned at all: a shell or interpreter fed
     from a pipe (`curl ... | sh`), an interactive shell (`su`, `sudo -s`), `bash -c "$CMD"`,
     `python3 -c "$CODE"`, `eval "$(...)"`, `source <(...)`, `bash <(...)`, or a `-c` string
     or here-document the guard cannot parse.
- **Automatic approvals, per project.** An action you would approve every time can be let
  through without a question in one project. After a run asks for it, say so to `/control`
  ("always allow that in this project"), or run
  `dw project auto-approve <project> --from-run <run-id> --action <id>`, with the short action
  id `dw status` shows next to the pending approval (or a finished run's last held action). It
  names that action exactly, its rule, its full command segment and its directory, and prints
  the entry. If the run has since been held on something else, the id no longer matches and
  nothing is added; without `--action`, `dw` shows the action and asks first in a terminal, and
  refuses anywhere else. It does not approve the pending action
  itself; answer that as usual. From then on the guard lets that exact action through in that
  project and writes `auto-approved run <id> rule <rule>: <segment>` to `dw.log`. An entry is
  exact by default; to widen one deliberately, write it yourself:
  `dw project auto-approve <project> --rule <rule-id> --match '<regex>' [--in <dir>] [--note <text>]`
  (the regex must match the whole segment; `--in` limits it to a directory and below).
  `dw project auto-approve <project> --list` shows the entries, numbered;
  `--remove N` takes one out. A call is let through only when every guarded part of it is
  covered. **Never auto-approved:** anything in the `control` category (changes to the control
  point, and the unreadable commands that may make them), and anything in a session whose run
  has ended. An entry for "command cannot be read" must name something specific: an empty
  pattern, `.*`, `.+` and any pattern that matches the empty string or everything are refused,
  by `dw` and again by the guard. Entries the guard cannot use (a bad regex, a nested
  quantifier such as `(a+)+`, wrong types) are ignored and reported by `dw doctor`. Automatic
  approvals cover shell commands only. `dw status` shows the rule id and action id of a pending
  approval, so you can see what an entry would name.
- **`dw` itself refuses inside a run.** Called with `DW_RUN_ID` in its environment (the run's
  session and everything it starts), every `dw` subcommand that changes something (`approve`,
  `deny`, `run`, `resume`, `cancel`, `dismiss`, `setup`, `project add`/`remove`/`import-legacy`,
  adding or removing automatic approvals) exits with "dw cannot change the control point from
  inside a run", whatever the guard decided. Reading (`status`, `queue`, `tail`, `doctor`,
  `project list`) still works.
- While a run is active in a project, your own Claude sessions in that project see the same
  questions. That is accepted.
- **After the run ends.** A session that belongs to a run that has finished, failed, been
  interrupted or cancelled (or not started yet) keeps working until it is closed, but every
  action the guard would hold is refused outright, with no dialog. Do such an action by hand,
  or start a new run for it.
- **The result note.** `dw` creates the run's note, `~/.dodocs-workflow/runs/<run-id>.result.md`,
  as an empty file when the run is requested, and the launch instructions tell the agent to fill it
  in when the work is finished or cannot go on. The agent may write it with its file-writing
  tool, or with a plain redirect: `echo`, `printf` or `cat ... > note` (a here-document is
  fine), or `tee`. Other ways of writing it (`cp` or `mv` onto it, a link, any other program) are
  held like any other write into the state directory. An empty note means "not finished".
  `dw` reads the note when the session reports it has finished or is closed. The first word of
  its first line is the outcome: `DONE`, `BLOCKED` or `FAILED`. A leading `#`, `*`, `-`, `>`
  or backquote is ignored, and the word may be followed by the end of the line or by `:`,
  `-`, `.`, an en dash or an em dash, so `BLOCKED: need a key` and `- BLOCKED — need a key`
  both count; `Failed to reproduce, all good` does not. A note that does not start with one
  of the three words counts as `DONE`. A `BLOCKED` note blocks the run and is then set
  aside, so the agent can write a new one.
- **State directory.** Run records, the registry and the log live in `~/.dodocs-workflow/`.
  `DW_HOME` overrides that for tests only: launched sessions and the terminal hooks always use
  the default directory.

## What the guard reads in full

Three everyday forms are read as if they had been written out, and the result is judged by the
same rules. Anything not positively simple and static stays "command cannot be read".

The first two are read only when nothing in the command could change what a name means: no
`eval`, `source` (or `.` as a command), `declare`, `typeset`, `local`, `readonly`, `export`,
`unset`, `read`, `mapfile`, `readarray`, `getopts`, `let`, `set`, `setopt`, `unsetopt`, `shopt`,
`emulate`, `alias`, `unalias`, `trap`, `enable` or `builtin` anywhere in it, no `printf -v`, and
no `IFS` at all; and the name itself appears (quotes removed) only where it is assigned or
defined and where it is used or called.

- **A variable that stands for a command or a path, set in the same command.**
  `K="kubectl -n app"; $K get pods` is read as `kubectl -n app get pods` (also `${K}`, also
  inside `$( ... )`, loops and pipelines of that command); `D=.git; echo x > $D/config` is a
  write to `.git/config`. Only when the value is one literal (quotes allowed; letters, digits,
  `_./:@%+,=-` and single spaces only; used as the program, its first word must be a plain
  program name), assigned once at the top level of the command (not in a
  subshell, a pipeline, the background, under `&&`/`||`, an `if` or a loop, and not with
  `export`, `local` or as a prefix of another command) before it is used, and the name is never
  reassigned, unset, `read`, appended to or used in any other way (`${!K}`, `${K[@]}`,
  `${K:-x}`). It is not carried into a shell the command starts (`bash -c '$K ...'`). The
  guard splits an unquoted value into words as bash does; zsh does not split it, so there such a
  command would run nothing.
- **A small function used as an alias, defined in the same command.**
  `k(){ kubectl -n app "$@"; }; k get pods` is read as `kubectl -n app get pods`, through the
  body and not through the name: a function takes precedence over a program of the same name,
  so `git(){ echo "$@"; }; git push origin main` is an `echo`, and `ok(){ git push origin main; }; ok`
  is a push. Only when it is defined once, at the top level, as `name(){ ...; }`,
  `name() { ...; }` or `function name { ...; }`, its body is one simple command using only
  `"$@"`, `$@`, `"$1"`...`$9` (no pipe, redirect, substitution or other variable, and no call of
  another function the command defines), and every mention of its name is the definition or a
  plain call later in the command (not `time k`, `xargs k`, `bash -c k` ...). Any other
  function's body is read where it is defined, and each plain call of it is held as `control`
  (what it runs was not read).
- **An inline script on standard input with arguments.** `python3 - "$F" <<'PY' ... PY` (and
  `node -`, `ruby -`, `perl -`, `bash -s -- ...`): the here-document is the code and is scanned
  like other inline code; the words after `-` are data for it, so a run-time value there does
  not make the command unreadable. Without a here-document the code is unseen and the command
  stays unreadable; fed from a pipe it is `control`.

## What the guard does not protect against

**The guard is not a sandbox.** It reads the commands and tool calls a cooperative agent
makes and holds the risky ones. It does not stop an agent, or a script or tool the agent
starts, from doing something it has no pattern for. **A script the agent writes and then
runs is not inspected.** Do not treat an unanswered dialog as the only thing between a run
and your production systems.

**For anything that must not happen, rely on protected branches and separate deploy
credentials.** Protect `main` on the remote so it cannot be pushed to or merged without
review, and keep deploy, payment and publishing credentials out of the environment the runs
use, so the guard being wrong is not enough to cause harm.

### Known ways around the guard

Both lists below describe the guard as of this release and are expected to shrink. The
lists are the authority: do not infer from the examples that a similar form is caught or
held.

Things that pass although you might expect them to be held.

**Code it cannot see**
- Script files and build steps (`bash deploy.sh`, `python script.py`, `make release`,
  `npm run deploy`), git hooks, and anything a `Makefile` or `package.json` script does.
- Inline code is scanned for markers only; commands or URLs built from pieces pass.
- Content read from files: `psql -f drop.sql`, `expect -f`, `source ./x.sh`, `sed -f`, `awk -f`.
- Shell aliases, and functions defined outside the command (in a profile or an earlier
  command), including one named like a read-only program; `tmux send-keys`, `screen -X stuff`.
  (A small function defined in the same command is read: see
  [What the guard reads in full](#what-the-guard-reads-in-full).)
- An alias defined and then used inside one command (`alias gp='git push origin main'; gp`)
  is not read.
- A file named only inside program text: `sed -n 'w .git/hooks/pre-push' x`,
  `awk '{print > ".git/hooks/pre-push"}' x`, and paths built inside `python -c` or `node -e`.

**Paths and names only known at run time**
- A path with no protected name in its fixed text: `echo x > $D/settings.json`, `echo x > $F`,
  `echo x > $GIT_DIR/$X`, and a variable assigned earlier on the same line in a form the guard
  does not read (`x=$(echo .git); echo x > $x/config`,
  `cd "$(git rev-parse --git-dir)" && echo x > config`; a static one is read, see
  [What the guard reads in full](#what-the-guard-reads-in-full)).
- A substitution that prints a protected name: `echo x > $(echo .git)/config`,
  `echo x > $(basename .git)/config`.
- A subscript that reaches arithmetic evaluation at run time. In `[[ ... ]]` with a numeric
  operator (`[[ "$x" -eq 0 ]]`) and in any `-v` test (`[ -v "$x" ]`), bash evaluates the
  operand's value as arithmetic, so a value that arrives at run time (a variable, or the output
  of a command substitution such as `[[ $(cat staged.txt) -eq 0 ]]`) and contains a subscript
  like `a[$(cmd)]` runs `cmd` unseen. Plain `[` and `test` with `-eq` and the like do not
  evaluate arithmetic. The same class: `let 'a[$(cmd)]'`, and arithmetic expansion such as
  `$((x))` of a variable holding a subscript.
- Words that are run-time values outside a deciding position, such as the body of
  `curl -d "$DATA"` to a local host.
- Names produced by an earlier command and piped into a writer are not checked:
  `find . -name x | xargs chmod +x`, `ls | xargs touch`, `git ls-files | xargs sed -i ...`.
- Names that reach a writer without being on the command line: `xargs chmod +x < list.txt`,
  `while read f; do cp x "$f"; done < list.txt`, `sort list.txt | xargs touch`, a bare `read`,
  here-strings, here-documents and process substitution; a compound substitution body that
  starts with `cat`.
- A directory as the destination of `cp` or `mv`, where the file name comes from the source:
  `cp /tmp/config .git/`, `cp /tmp/settings.json .claude/`.
- A symlink to a protected directory made earlier in the same command line.
- Directory tracking that follows a `cd` which does not run, or guesses its target: after
  `cd ~/.claude && command -v cd /tmp; echo x > settings.json` the guard believes the shell is
  in `/tmp` (`command -v cd ...` only prints), and a `repeat` with a count that is not a plain
  number is read by guess. The relative write is then judged in the wrong directory.
- A relative write to a bare protected file name after a `cd` the guard cannot resolve: after
  `cd $VAR`, `cd -` or `popd`, `echo x > settings.json` is not held.
- A redirect whose target is known only at run time: `echo x > "$X"` is not held, whatever
  `X` holds at run time, including a protected path (the guard never judges the value of a
  variable). The result-note exemption is never applied to such a target.
- Arithmetic `$((...))` that is also read as a command substitution whose body starts with a
  subshell: if that second reading cannot be parsed and names no guarded program, only the
  arithmetic reading counts, so a program hidden behind a variable passes
  (`x=git; echo $(($x push origin main); true)`, `echo $(("$G" push origin main); true)`).

**Protected directories named as a whole**
- `rm -rf .claude`, `rm -rf .git`, `mv .claude c`, `cp -r /tmp/x .claude`,
  `rsync -a /tmp/x/.claude/ .claude/`, `rsync -a --delete /tmp/x/ ./`, `tar -xzf o.tgz -C .claude`, `unzip x.zip -d .claude`,
  `chmod -R 755 .claude`, `git checkout HEAD .claude/`, `git stash -- .claude`.
- `git clean -fd[x]`, `git reset --hard`, `git checkout -f`, `git stash -u`, which can delete
  untracked or revert tracked settings files.

**`find`** (the weakest part; it is a heuristic over find's expression language)
- A find that writes what it finds, started in an existing directory that shows no `.git`,
  `.claude` or `agterm` directly inside (a monorepo subfolder), and `find -exec sh -c '...' _ {} \;`.

**Environment and hooks**
- Loader and tool variables the guard does not list or read: `PYTHONPATH`, `NODE_PATH`,
  `GEM_HOME`, `PERL5LIB`, `PATH` prefixes, `JAVA_TOOL_OPTIONS`, `LD_LIBRARY_PATH`,
  `DYLD_LIBRARY_PATH`, `GIT_EXTERNAL_DIFF`, `GIT_PAGER`, `PAGER`, `EDITOR`, `PROMPT_COMMAND`;
  a static `NODE_OPTIONS=--require ./x.js`; `ENV=file` with the shell started by another
  program; variables given to a non-wrapper such as `docker run -e LD_PRELOAD=...`;
  python `-m` inside a longer option cluster (`python3 -um$MOD`).
- `less +'!cmd' file` and `less -k`.
- Hook-like files and tools: `.husky/pre-push`, `.githooks/pre-push`, `.claude/hooks/x.sh`,
  `.git/info/exclude`, `.git/HEAD`; `git lfs install`, `pre-commit install`, `npx husky install`,
  `git init`, `git apply`, `git am`, `git cherry-pick`, `git config user.name x`.
- An external diff or textconv driver configured in `.gitattributes` or git config runs unseen.

**Outward actions by other means**
- Python `requests` or `node fetch` without a recognisable marker, `ftp`, SDK command-line
  tools that are not in the rules, `openssl s_client`, containers that call out.
  `gh issue comment` and `gh pr comment` are allowed on purpose.
- A tag pushed by plain name (`git push origin v1.0`).
- Deletion other than `rm` or `find`: moving out of the project and deleting in `/tmp`,
  overwriting with `>` or `cp` outside the project, `rsync --delete`, `truncate`, `dd`,
  `git clean` in another repository. Writes to `~/.zshrc` or `~/.ssh/authorized_keys` are not
  guarded. (Deletions with `rm` outside the project are held, except under `/tmp` and
  `/private/tmp`.)

**Outside the hook**
- `launchd` or `cron` jobs that run later; hooks disabled through managed settings or
  `CLAUDE_*` variables in a nested process.
- Killing the hook process (`pkill -f "dw guard"`) lets the call it was deciding through.
- A result note that says `DONE`, written early, ends the run early. The session keeps
  working; from then on the guard refuses every action it would hold, but everything else
  goes ahead.
- In-process teammates, built-in tools that act outward, MCP servers whose write tools have
  read-only names, a browser `navigate` to a GET URL with side effects.
- Your own sessions are guarded only while a run is active in that project.
- Run records and the registry are plain files owned by the same user; only the `control`
  category protects them.
- The text of the approval question is the agent's own command. It is cleaned of control
  and invisible formatting characters and trimmed, but not otherwise interpreted, so it can
  be misleading about what the command does. The held action shown first is the guard's own
  description.
- Reads are not held at all: a run can read `~/.claude/settings.json`, the registry and run
  records.

### Known over-holds

Things that are held although they are harmless. They are held as `control`, so they cannot
be approved for the run, unless noted. Those held as "command cannot be read" are in the
`unreadable` category and can be approved for the run (see
[How approvals work](#how-approvals-work)).

- **Reading a protected file** (`.git`, `.claude/settings.json`) in a way the guard cannot
  prove is a read: a read-only program
  called by path or with an unlisted option (`/bin/cat`, `grep --no-color`, `sed -n '/a/,/b/{p}'`,
  `awk '$3 > 100'`), `rg --debug`, anything under a wrapper or inside a shell string
  (`sudo cat .git/config`, `bash -c 'cat .claude/settings.json'`), an assignment whose value
  is a protected path (`CFG=.git/config; cat $CFG`), and a substitution or pipeline naming
  such a file that feeds a non-read-only program (`... | xargs prettier --check`).
- **Ordinary git work on settings files**: `git commit <path>`, `git reset <path>`,
  `git rm --cached`, `git update-index`, `git stash push -- <path>`,
  `git checkout -- .claude/settings.json`, `git restore .claude/settings.json`, and
  `cp settings.json settings.json.bak`, `zip -x '.git/*'`. A `git rev-parse --git-path` hook
  path, `$GIT_DIR/hooks...` and `$GIT_DIR/config*` are held for any purpose.
- **Writes with a run-time part**: under `.claude/` or `agterm/` whose last segment ends in a
  run-time word (`mkdir -p .claude/worktrees/$N`, `echo x > .claude/logs/out-$DATE`; but
  `.claude/agents/$NAME.md` passes); any wildcard below a literal `.git/`
  (`rm .git/refs/heads/$B`); a segment that may be a protected name with something after it
  (`.*/x`, `a*/x`); `..` after a run-time segment in a path that also names a protected
  directory; a run-time word written directly in your home directory (`echo x > ~/$F`).
- **Run-time programs and wrappers**, all held as `control`: `cd $DW_HOME`,
  `python3 -m $MOD`, `tsx $SCRIPT`, a wrapper with a run-time or glob argument
  (`timeout 5 ls $DIR`, `npx tsx x.ts "$PORT"`: the word may be the program), a loop over more than 64
  literal words, or over words only known at run time (`for f in $(ls)`), whose body writes
  the loop variable.
- **Environment**: `ENV=value` on a line that also runs a shell (`ENV=prod npm ci && bash build.sh`),
  `BASH_ENV=value` always, `NODE_OPTIONS` with run-time text, loader variables under a wrapper
  even when they belong to the wrapped program (`sudo make LD_PRELOAD=x`).
- **`find` that writes what it finds** at a project root without ruling protected files out
  (`find . -type f -empty -delete`, `find . -name '*.json' -exec prettier --write {} +`); a find
  whose start directory does not exist yet; a `-name` equal to a git hook or protected file
  name (`find . -name config -delete`); a prune in an unusual shape; excluding `.git` and
  `.claude` but not `agterm`. Adding
  `-not -path '*/.git/*' -not -path '*/.claude/*' -not -path '*agterm/*'` makes it pass.

- **The state directory and the result note**: `mkdir -p ~/.dodocs-workflow/runs`, or the
  same with `$DW_HOME` (only the plain, existing path is spared); writing the note with
  `cp`, `mv` or `git log > note` or any other program than `echo`, `printf`, `cat`, `tee` and
  the file-writing tool.
  Also held: a grouped command writing the note (`{ echo a; echo b; } > note`,
  `(echo a; echo b) > note`), `cd <state dir>/runs; echo x > <run-id>.result.md`, and any note
  write whose command line contains an arithmetic expansion (`echo $((1+2)) > note`,
  `echo "$((1+2))" > note`, a here-document body with `$((...))` written to the note), though
  the same arithmetic written elsewhere passes.
- **Inline code that runs a guarded program in a form the scanner has no pattern for**
  (`python3 -c 'os.system("kubectl rollout status deploy/a")'`) is held as `unreadable`.
- **An approval question for the same words in another directory**: an approval covers one
  directory, so `git push origin main` after `cd /tmp/other` asks again (an ordinary question,
  not a `control` hold).

If a hold is wrong for your work, deny it, or approve it once from the dialog where that is
allowed, and ask the agent for a different form of the command.
