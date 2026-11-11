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
2. **`dw setup`.** Shows the change it will make and asks before making it: one guard entry in
   `~/.claude/settings.json` and two lines in AGTerm's `hooks.conf`. It merges and never
   rewrites other entries. **Runs cannot start until this has been run**, and `dw run` and
   `dw resume` test the guard entry once before each launch: an entry whose program is gone
   or fails, or whose matcher does not cover all tools, refuses the run. Running `dw setup`
   again repairs an entry whose program is missing or not executable, or whose matcher does
   not cover all tools, and leaves exactly one guard entry. It does **not** repair an entry
   whose program exists but fails: fix that one by hand. `dw doctor` checks the result;
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
- A run that is interrupted (AGTerm restarted, session lost) is never re-run automatically.
  `dw resume <run-id>` reopens its Claude conversation for you to continue.

## How approvals work

While a run is active in a project, a guard checks every tool call made in that directory and
holds the risky ones: merging or pushing to the default branch, deploying, publishing or
sending anything outward, spending money, destructive data commands, and anything that would
change the control point's own settings. Everything it does not recognise is allowed.

- **The dialog.** A held action opens a native AGTerm question on that run's session, marks
  the run `blocked` with the reason `awaiting approval`, and sends a notification. You can
  answer *approve once*, *approve this action for the rest of the run*, or *deny*. "For this
  run" means the same action pattern, in that run only, until it ends.
- **The 15-minute wait.** The guard waits up to about fifteen minutes for an answer. If none
  comes, it refuses for now, tells the agent to carry on with other work and retry, and the
  approval stays pending.
- **From `/control`.** `dw approve <run-id>` lets the pending action through once, on the
  retry; `dw deny <run-id>` refuses it. `/control` runs these only when you say so in that
  conversation.
- **Holds that cannot be approved from `dw`.** A run must not be able to change its own
  controls. A `dw` command that changes state, or a write to the control point's state
  directory, `~/.claude/settings.json` or AGTerm's hooks file, is held in a separate
  `control` category. It can be approved once, from the dialog only, never for the rest of
  the run and never with `dw approve`.
- While a run is active in a project, your own Claude sessions in that project see the same
  questions. That is accepted.
- **After the run ends.** A session that belongs to a run that has finished, failed, been
  interrupted or cancelled (or not started yet) keeps working until it is closed, but every
  action the guard would hold is refused outright, with no dialog. Do such an action by hand,
  or start a new run for it.
- **State directory.** Run records, the registry and the log live in `~/.dodocs-workflow/`.
  `DW_HOME` overrides that for tests only: launched sessions and the terminal hooks always use
  the default directory.

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
- Shell aliases and functions, including one named like a read-only program; `tmux send-keys`,
  `screen -X stuff`.
- A file named only inside program text: `sed -n 'w .git/hooks/pre-push' x`,
  `awk '{print > ".git/hooks/pre-push"}' x`, and paths built inside `python -c` or `node -e`.

**Paths and names only known at run time**
- A path with no protected name in its fixed text: `echo x > $D/settings.json`, `echo x > $F`,
  `echo x > $GIT_DIR/$X`, and a variable assigned earlier on the same line
  (`x=.git; echo x > $x/config`, `cd "$(git rev-parse --git-dir)" && echo x > config`).
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
- Reads are not held at all: a run can read `~/.claude/settings.json`, the registry and run
  records.

### Known over-holds

Things that are held although they are harmless. They are held as `control`, so they cannot
be approved for the run, unless noted.

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
- **Run-time programs and wrappers**: `cd $DW_HOME`, `python3 -m $MOD`, `tsx $SCRIPT`, a wrapper
  with a run-time or glob argument (`timeout 5 ls $DIR`, `npx tsx x.ts "$PORT"`), and a loop
  over more than 64 literal words whose body writes the loop variable.
- **Environment**: `ENV=value` on a line that also runs a shell (`ENV=prod npm ci && bash build.sh`),
  `BASH_ENV=value` always, `NODE_OPTIONS` with run-time text, loader variables under a wrapper
  even when they belong to the wrapped program (`sudo make LD_PRELOAD=x`).
- **`find` that writes what it finds** at a project root without ruling protected files out
  (`find . -type f -empty -delete`, `find . -name '*.json' -exec prettier --write {} +`); a find
  whose start directory does not exist yet; a `-name` equal to a git hook or protected file
  name (`find . -name config -delete`); a prune in an unusual shape; excluding `.git` and
  `.claude` but not `agterm`. Adding
  `-not -path '*/.git/*' -not -path '*/.claude/*' -not -path '*agterm/*'` makes it pass.

If a hold is wrong for your work, deny it, or approve it once from the dialog where that is
allowed, and ask the agent for a different form of the command.
