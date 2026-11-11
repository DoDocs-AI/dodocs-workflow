from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent
DW = REPO_ROOT / "control" / "dw"
FAKE_AGTERMCTL = TESTS_DIR / "fake-agtermctl"

# Make `import dwlib` work in unit tests.
sys.path.insert(0, str(REPO_ROOT / "control"))


class DwTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-test-")).resolve()
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.dw_home = self.tmp / "home"
        self.env = dict(os.environ)
        self.env["DW_HOME"] = str(self.dw_home)
        self.env["DW_AGTERMCTL"] = str(FAKE_AGTERMCTL)
        for var in ("AGT_SOCKET", "AGTERM_SOCKET", "DW_CLAUDE", "FAKE_AGTERM_DOWN", "DW_RUN_ID",
                    "DW_GUARD_ASK_TIMEOUT", "DW_GUARD_POLL_INTERVAL"):
            self.env.pop(var, None)
        # Workspace trust is read from this file, never from the real ~/.claude.json.
        self.claude_state = self.tmp / "claude-state.json"
        self.claude_state.write_text(json.dumps({"projects": {}}))
        self.env["DW_CLAUDE_STATE"] = str(self.claude_state)
        # The guard hook counts as installed through this file, never the real settings.
        self.claude_settings = self.tmp / "claude-settings.json"
        self.claude_settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "'%s' guard" % DW, "timeout": 900}]}]}}))
        self.env["DW_CLAUDE_SETTINGS"] = str(self.claude_settings)
        # `dw setup` and `dw doctor` never see the real terminal hooks file or tmux sockets.
        self.hooks_conf = self.tmp / "hooks.conf"
        self.env["DW_AGTERM_HOOKS_CONF"] = str(self.hooks_conf)
        self.env["DW_TMUX"] = str(self.tmp / "no-such-tmux")
        self.env["TMUX_TMPDIR"] = str(self.tmp / "tmux-tmp")
        for var, value in (("DW_HOME", str(self.dw_home)),
                           ("DW_CLAUDE_SETTINGS", str(self.claude_settings)),
                           ("DW_AGTERM_HOOKS_CONF", str(self.hooks_conf)), ("DW_RUN_ID", None)):
            self.addCleanup(self._restore_env, var, os.environ.get(var))
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    @staticmethod
    def _restore_env(var, saved) -> None:
        if saved is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = saved

    def dw(self, *args, stdin=None, env=None) -> subprocess.CompletedProcess:
        run_env = dict(self.env)
        if env:
            run_env.update(env)
        return subprocess.run(
            [sys.executable, str(DW), *args],
            input=stdin,
            env=run_env,
            capture_output=True,
            text=True,
        )

    # -- projects ---------------------------------------------------------

    def trust_project(self, path) -> None:
        """Mark a directory as already trusted in the fake Claude Code state file."""
        state = json.loads(self.claude_state.read_text())
        state["projects"][os.path.realpath(str(path))] = {"hasTrustDialogAccepted": True}
        self.claude_state.write_text(json.dumps(state))

    def add_project(self, name, group="ignashev_ai", trusted=True) -> Path:
        """Register a project with its own directory under the temp dir; returns the path."""
        path = self.tmp / "checkouts" / name
        path.mkdir(parents=True, exist_ok=True)
        r = self.dw("project", "add", "--name", name, "--path", str(path), "--group", group)
        assert r.returncode == 0, r.stderr
        if trusted:
            self.trust_project(path)
        return path

    # -- fake agtermctl ---------------------------------------------------

    @property
    def fake_agterm_dir(self) -> Path:
        return self.dw_home / "fake-agterm"

    def agterm_calls(self) -> list:
        """Every recorded agtermctl invocation, as an argv list (without the binary)."""
        path = self.fake_agterm_dir / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line)["argv"] for line in path.read_text().splitlines() if line]

    def _sessions_file(self) -> Path:
        return self.fake_agterm_dir / "sessions.json"

    def set_session_status(self, sid, status, changed_at=None) -> None:
        sessions = json.loads(self._sessions_file().read_text())
        sessions[sid]["status"] = status
        sessions[sid]["statusChangedAt"] = time.time() if changed_at is None else changed_at
        self._sessions_file().write_text(json.dumps(sessions))

    def fake_sessions(self) -> dict:
        path = self._sessions_file()
        return json.loads(path.read_text()) if path.exists() else {}

    def fake_open_asks(self) -> list:
        """Ids of questions opened with --no-block that are neither answered nor cancelled."""
        path = self.fake_agterm_dir / "asks.json"
        asks = json.loads(path.read_text()) if path.exists() else {}
        return [k for k, v in asks.items() if v.get("state") == "pending"]

    def script_ask(self, answer_id) -> None:
        self.fake_agterm_dir.mkdir(parents=True, exist_ok=True)
        (self.fake_agterm_dir / "ask-answer").write_text(answer_id)
