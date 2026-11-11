from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
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
        for var in ("AGT_SOCKET", "AGTERM_SOCKET"):
            self.env.pop(var, None)
        saved = os.environ.get("DW_HOME")
        os.environ["DW_HOME"] = str(self.dw_home)
        self.addCleanup(self._restore_home, saved)

    @staticmethod
    def _restore_home(saved) -> None:
        if saved is None:
            os.environ.pop("DW_HOME", None)
        else:
            os.environ["DW_HOME"] = saved

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
