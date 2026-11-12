#!/usr/bin/env bash
set -euo pipefail

# Validate the installers:
#   - install.sh (local mode, into a temp HOME) actually installs every agent,
#     command, docker file, and template it claims
#   - uninstall.sh AGENTS/COMMANDS arrays are identical to install.sh's
#   - uninstall.sh removes everything install.sh installed
#   - the control point (dw) is installed with an absolute-path interpreter, never
#     runs `dw setup` by itself, and is removed again without touching registry.json
#     or runs/

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
UNINSTALL_SH="$REPO_ROOT/uninstall.sh"

ERRORS=0

fail() {
    echo "FAIL: $1"
    ERRORS=$((ERRORS + 1))
}

pass() {
    echo "PASS: $1"
}

# Extract a quoted bash array block (ARRAYNAME=( ... )) from a script
# (same line-based parsing as validate-structure.sh — portable across BSD/GNU)
extract_array() {
    local script="$1" arrayname="$2" inside=false line item
    while IFS= read -r line; do
        if [[ "$line" == "${arrayname}=("* ]]; then
            inside=true
            continue
        fi
        if $inside; then
            [[ "$line" == ")"* ]] && break
            item=$(echo "$line" | sed -n 's/.*"\([^"]*\)".*/\1/p')
            [ -n "$item" ] && echo "$item"
        fi
    done < "$script"
}

# ── 1. Array parity install.sh vs uninstall.sh ─────────────────────
echo ""
echo "=== Checking install.sh vs uninstall.sh array parity ==="
for arrayname in AGENTS COMMANDS CONTROL_FILES; do
    diff_out=$(diff <(extract_array "$INSTALL_SH" "$arrayname") <(extract_array "$UNINSTALL_SH" "$arrayname") || true)
    if [ -z "$diff_out" ]; then
        pass "$arrayname arrays are identical in install.sh and uninstall.sh"
    else
        fail "$arrayname arrays differ between install.sh and uninstall.sh:"
        echo "$diff_out"
    fi
done
echo ""

# CONTROL_FILES must list exactly what is in control/ (dw, guard-rules.json and every
# dwlib module), so a new module cannot be forgotten
echo "=== Checking CONTROL_FILES against control/ ==="
expected_control=$( { echo "dw"; echo "guard-rules.json"; (cd "$REPO_ROOT/control" && ls dwlib/*.py); } | sort)
actual_control=$(extract_array "$INSTALL_SH" CONTROL_FILES | sort)
if [ "$expected_control" = "$actual_control" ]; then
    pass "CONTROL_FILES matches control/ on disk"
else
    fail "CONTROL_FILES differs from control/ on disk:"
    diff <(echo "$expected_control") <(echo "$actual_control") || true
fi
echo ""

# ── 2. Fresh install into a temp HOME ──────────────────────────────
echo "=== Running install.sh into a temp HOME (local mode) ==="
FAKE_HOME=$(mktemp -d)
trap 'rm -rf "$FAKE_HOME"' EXIT

# Settings files the control point may edit are pointed at temp files; the installer
# must not create or touch them
export DW_CLAUDE_SETTINGS="$FAKE_HOME/settings.json"
export DW_AGTERM_HOOKS_CONF="$FAKE_HOME/hooks.conf"
# The terminal and tmux binaries are pointed at paths that do not exist, so no step
# (the uninstall's `dw setup --remove` reloads the terminal hooks) reaches the real ones
export DW_AGTERMCTL="$FAKE_HOME/no-such-agtermctl"
export DW_TMUX="$FAKE_HOME/no-such-tmux"
mkdir -p "$FAKE_HOME/.local/bin"

if HOME="$FAKE_HOME" bash "$INSTALL_SH" >"$FAKE_HOME/install.out" 2>&1; then
    pass "install.sh completed"
else
    fail "install.sh exited non-zero"
fi

expected_agents=$(extract_array "$INSTALL_SH" AGENTS | wc -l | tr -d ' ')
installed_agents=$(find "$FAKE_HOME/.claude/agents" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
if [ "$installed_agents" = "$expected_agents" ]; then
    pass "installed $installed_agents agent files (matches AGENTS array)"
else
    fail "installed $installed_agents agent files, AGENTS array lists $expected_agents"
fi

expected_cmds=$(extract_array "$INSTALL_SH" COMMANDS | wc -l | tr -d ' ')
installed_cmds=$(find "$FAKE_HOME/.claude/commands" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
if [ "$installed_cmds" = "$expected_cmds" ]; then
    pass "installed $installed_cmds command files (matches COMMANDS array)"
else
    fail "installed $installed_cmds command files, COMMANDS array lists $expected_cmds"
fi

for f in \
    ".claude/docker/agent-env.Dockerfile" \
    ".claude/docker/agent-entrypoint.sh" \
    ".claude/skills/gtm-api-config.template.md" \
    ".claude/statusline-dodocs-workflow.sh" \
    ".claude/scrum-team-config.template.md" \
    ".claude/openspec-conventions.md" \
    ".claude/.dodocs-workflow-version"
do
    if [ -f "$FAKE_HOME/$f" ]; then
        pass "installed $f"
    else
        fail "missing after install: $f"
    fi
done

installed_version=$(cat "$FAKE_HOME/.claude/.dodocs-workflow-version" 2>/dev/null || echo "MISSING")
repo_version=$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")
if [ "$installed_version" = "$repo_version" ]; then
    pass "version file matches VERSION ($repo_version)"
else
    fail "version file is '$installed_version', VERSION is '$repo_version'"
fi
echo ""

# ── 2b. The control point ──────────────────────────────────────────
echo "=== Checking the control point install ==="
DWH="$FAKE_HOME/.dodocs-workflow"
if [ -x "$DWH/bin/dw" ]; then
    pass "installed bin/dw (executable)"
else
    fail "bin/dw missing or not executable"
fi

shebang=$(head -n 1 "$DWH/bin/dw" 2>/dev/null || true)
interp="${shebang#\#!}"
if [[ "$shebang" == '#!/'* && "$interp" != *' '* && -x "$interp" ]] \
   && "$interp" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    pass "bin/dw shebang is an absolute python3 >= 3.9 ($interp)"
else
    fail "bin/dw shebang is not an absolute python3 >= 3.9: $shebang"
fi
if [ "$(head -n 1 "$REPO_ROOT/control/dw")" = "#!/usr/bin/env python3" ]; then
    pass "repo control/dw keeps #!/usr/bin/env python3"
else
    fail "repo control/dw shebang changed"
fi

while IFS= read -r item; do
    case "$item" in
        dw) target="$DWH/bin/dw" ;;
        guard-rules.json) target="$DWH/guard-rules.default.json" ;;
        *) target="$DWH/lib/$item" ;;
    esac
    [ -f "$target" ] || fail "control file missing after install: $target"
done < <(extract_array "$INSTALL_SH" CONTROL_FILES)
if [ -f "$DWH/lib/dwlib/guard_shell.py" ] && [ -f "$DWH/lib/dwlib/setup.py" ] && [ -f "$DWH/guard-rules.default.json" ]; then
    pass "library modules and default guard rules installed"
else
    fail "library modules or guard-rules.default.json missing"
fi

# Minimal PATH, as hooks run
if [ "$(env -i HOME="$FAKE_HOME" DW_HOME="$DWH" DW_AGTERMCTL="$DW_AGTERMCTL" DW_TMUX="$DW_TMUX" PATH=/usr/bin:/bin "$DWH/bin/dw" project list --json 2>/dev/null)" = "[]" ]; then
    pass "installed dw runs with a minimal PATH and 'project list --json' prints []"
else
    fail "installed dw did not print [] for 'project list --json'"
fi

if [ -L "$FAKE_HOME/.local/bin/dw" ] && [ "$(readlink "$FAKE_HOME/.local/bin/dw")" = "$DWH/bin/dw" ]; then
    pass "~/.local/bin/dw symlink points at the install"
else
    fail "~/.local/bin/dw symlink missing or wrong"
fi

if [ -f "$FAKE_HOME/.claude/commands/control.md" ]; then
    pass "installed ~/.claude/commands/control.md"
else
    fail "missing after install: ~/.claude/commands/control.md"
fi

if [ ! -e "$DW_CLAUDE_SETTINGS" ] && [ ! -e "$DW_AGTERM_HOOKS_CONF" ] && [ ! -e "$FAKE_HOME/.claude/settings.json" ]; then
    pass "install.sh did not run dw setup (no settings or hooks files touched)"
else
    fail "install.sh created or edited a settings/hooks file"
fi
if grep -q "Run 'dw setup' to enable approvals and status events." "$FAKE_HOME/install.out"; then
    pass "install.sh tells the owner to run 'dw setup'"
else
    fail "install.sh does not print the 'dw setup' next step"
fi

# State that must survive an uninstall; a settings entry that uninstall must remove
mkdir -p "$DWH/runs"
echo '{"projects": []}' > "$DWH/registry.json"
echo '{}' > "$DWH/runs/r1.json"
echo "x" > "$DWH/dw.log"
echo '{"hooks": {"UserPromptSubmit": []}}' > "$DW_CLAUDE_SETTINGS"
if env -i HOME="$FAKE_HOME" DW_HOME="$DWH" DW_CLAUDE_SETTINGS="$DW_CLAUDE_SETTINGS" \
        DW_AGTERM_HOOKS_CONF="$DW_AGTERM_HOOKS_CONF" DW_AGTERMCTL="$DW_AGTERMCTL" DW_TMUX="$DW_TMUX" \
        PATH=/usr/bin:/bin "$DWH/bin/dw" setup --yes >/dev/null 2>&1 \
   && grep -q "guard" "$DW_CLAUDE_SETTINGS"; then
    pass "dw setup (temp files) adds the guard entry, for the uninstall check below"
else
    fail "dw setup into temp files did not add the guard entry"
fi
echo ""

# ── 2c. No usable python3: the control point is skipped, the rest installs ──
echo "=== Running install.sh with no usable python3 ==="
NOPY_HOME=$(mktemp -d)
if HOME="$NOPY_HOME" DW_INSTALL_PYTHON=/nonexistent/python3 bash "$INSTALL_SH" >"$NOPY_HOME/install.out" 2>&1; then
    pass "install.sh completes without python3"
else
    fail "install.sh failed without python3"
fi
if [ ! -e "$NOPY_HOME/.dodocs-workflow/bin/dw" ] && [ -f "$NOPY_HOME/.claude/commands/scrum-team.md" ] \
   && grep -qi "python" "$NOPY_HOME/install.out"; then
    pass "control point skipped with a warning; the rest of the install went ahead"
else
    fail "expected the control point skipped with a warning and the rest installed"
fi
rm -rf "$NOPY_HOME"
echo ""

# ── 3. Uninstall removes everything ────────────────────────────────
echo "=== Running uninstall.sh against the temp HOME ==="
if HOME="$FAKE_HOME" bash "$UNINSTALL_SH" >/dev/null 2>&1; then
    pass "uninstall.sh completed"
else
    fail "uninstall.sh exited non-zero"
fi

if [ ! -e "$DWH/bin/dw" ] && [ ! -e "$DWH/lib" ] && [ ! -e "$DWH/guard-rules.default.json" ] \
   && [ ! -e "$FAKE_HOME/.local/bin/dw" ] && [ ! -L "$FAKE_HOME/.local/bin/dw" ]; then
    pass "uninstall removed bin/, lib/, guard-rules.default.json and the dw symlink"
else
    fail "control point files left after uninstall"
fi
if [ -f "$DWH/registry.json" ] && [ -f "$DWH/runs/r1.json" ] && [ -f "$DWH/dw.log" ]; then
    pass "uninstall left registry.json, runs/ and dw.log in place"
else
    fail "uninstall removed registry.json, runs/ or dw.log"
fi
if ! grep -q "guard" "$DW_CLAUDE_SETTINGS" 2>/dev/null; then
    pass "uninstall ran 'dw setup --remove' (guard entry gone from the settings file)"
else
    fail "guard entry still in the settings file after uninstall"
fi

# A symlink that points somewhere else is not ours and must survive
echo ""
echo "=== Uninstall leaves a foreign ~/.local/bin/dw alone ==="
HOME="$FAKE_HOME" bash "$INSTALL_SH" >/dev/null 2>&1 || true
rm -f "$FAKE_HOME/.local/bin/dw"
ln -s /usr/bin/true "$FAKE_HOME/.local/bin/dw"
HOME="$FAKE_HOME" bash "$UNINSTALL_SH" >/dev/null 2>&1 || true
if [ -L "$FAKE_HOME/.local/bin/dw" ] && [ "$(readlink "$FAKE_HOME/.local/bin/dw")" = "/usr/bin/true" ]; then
    pass "foreign dw symlink untouched"
else
    fail "uninstall removed a dw symlink that is not ours"
fi
rm -f "$FAKE_HOME/.local/bin/dw"
echo ""

leftovers=$(find "$FAKE_HOME/.claude" -type f 2>/dev/null || true)
if [ -z "$leftovers" ]; then
    pass "no dodocs-workflow files left after uninstall"
else
    fail "files left after uninstall:"
    echo "$leftovers"
fi
echo ""

# ── Summary ─────────────────────────────────────────────────────────
if [ "$ERRORS" -gt 0 ]; then
    echo "FAILED: $ERRORS error(s) found."
    exit 1
else
    echo "ALL CHECKS PASSED."
    exit 0
fi
