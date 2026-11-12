from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from helpers import DwTestCase


class ProjectCliTests(DwTestCase):
    def _add(self, name="SlotMe App", path=None, group="ignashev_ai", *extra):
        path = path or str(self.tmp)
        return self.dw("project", "add", "--name", name, "--path", path,
                       "--group", group, *extra)

    def test_add_then_list_json(self):
        r = self._add(path=str(self.tmp), *())
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.dw("project", "list", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        projects = json.loads(r.stdout)
        self.assertEqual(len(projects), 1)
        p = projects[0]
        self.assertEqual(p["id"], "slotme-app")
        self.assertEqual(p["harness"], "claude")
        self.assertEqual(p["group"], "ignashev_ai")
        self.assertEqual(p["notes"], "")
        self.assertEqual(p["guard_rules"], [])

    def test_add_stores_notes_and_list_plain(self):
        self._add(path=str(self.tmp))
        r = self.dw("project", "add", "--name", "Other", "--path", str(self.tmp),
                    "--group", "g", "--notes", "hi")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.dw("project", "list").stdout
        self.assertIn("slotme-app", out)
        self.assertIn("other", out)

    def test_add_rejects_missing_path(self):
        r = self._add(path=str(self.tmp / "nope"))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_add_rejects_duplicate_id(self):
        self.assertEqual(self._add(path=str(self.tmp)).returncode, 0)
        r = self._add(name="slotme  app", path=str(self.tmp))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_remove(self):
        self._add(path=str(self.tmp))
        r = self.dw("project", "remove", "slotme-app")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.dw("project", "list", "--json").stdout), [])

    def test_remove_unknown_exits_2(self):
        r = self.dw("project", "remove", "ghost")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_path_is_stored_resolved(self):
        real = self.tmp / "real"
        real.mkdir()
        link = self.tmp / "link"
        os.symlink(str(real), str(link))
        self.assertEqual(self._add(path=str(link)).returncode, 0)
        p = json.loads(self.dw("project", "list", "--json").stdout)[0]
        self.assertEqual(p["path"], os.path.realpath(str(link)))

    def test_corrupt_registry_exits_2(self):
        self.dw_home.mkdir(parents=True)
        (self.dw_home / "registry.json").write_text("{")
        r = self.dw("project", "list")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()


class InsideRunRefusalTests(DwTestCase):
    """`dw` refuses every state-changing subcommand when its environment names a run
    (DW_RUN_ID), whatever the guard decided; read-only subcommands, `dw hook` and `dw guard`
    are unaffected."""

    REFUSAL = "dw cannot change the control point from inside a run"

    def snapshot(self):
        files = {}
        for root in (self.dw_home, self.claude_settings.parent):
            for p in sorted(Path(root).rglob("*")):
                if p.is_file() and ".lock" not in p.name and p.name != "dw.log":
                    files[str(p)] = p.read_bytes()
        return files

    def test_state_changing_subcommands_refuse_with_dw_run_id(self):
        path = self.add_project("alpha")
        other = self.tmp / "checkouts" / "beta"
        other.mkdir(parents=True)
        legacy = self.tmp / "legacy.json"
        legacy.write_text(json.dumps({"projects": []}))
        commands = [["approve", "r-1"], ["deny", "r-1"], ["run", "alpha", "/scrum-team", "x"],
                    ["resume", "r-1"], ["cancel", "r-1"], ["dismiss", "r-1"], ["setup", "--yes"],
                    ["setup", "--remove", "--yes"],
                    ["project", "add", "--name", "beta", "--path", str(other), "--group", "g"],
                    ["project", "remove", "alpha"],
                    ["project", "import-legacy", "--from", str(legacy), "--group", "g"]]
        before = self.snapshot()
        for argv in commands:
            with self.subTest(argv=argv):
                r = self.dw(*argv, env={"DW_RUN_ID": "r-1"})
                self.assertEqual(r.returncode, 2)
                self.assertEqual(r.stderr.strip(), "dw: " + self.REFUSAL)
                self.assertEqual(r.stdout, "")
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(path.is_dir())

    def test_without_dw_run_id_they_are_not_refused(self):
        self.add_project("alpha")
        other = self.tmp / "checkouts" / "beta"
        other.mkdir(parents=True)
        for argv in (["project", "add", "--name", "beta", "--path", str(other), "--group", "g"],
                     ["project", "remove", "beta"], ["approve", "r-1"], ["dismiss", "r-1"]):
            with self.subTest(argv=argv):
                r = self.dw(*argv)
                self.assertNotIn(self.REFUSAL, r.stderr)
        self.assertEqual(self.dw("project", "list").stdout.split()[0], "alpha")

    def test_read_only_subcommands_work_inside_a_run(self):
        self.add_project("alpha")
        for argv in (["status"], ["status", "--json"], ["queue"], ["project", "list"],
                     ["doctor"], ["tail", "r-1"]):
            with self.subTest(argv=argv):
                r = self.dw(*argv, env={"DW_RUN_ID": "r-1"})
                self.assertNotIn(self.REFUSAL, r.stderr)
                if argv[0] in ("status", "queue", "project"):
                    self.assertEqual(r.returncode, 0, r.stderr)
        r = self.dw("guard", stdin="{}", env={"DW_RUN_ID": "r-1"})
        self.assertNotIn(self.REFUSAL, r.stdout + r.stderr)
        r = self.dw("hook", "status", env={"DW_RUN_ID": "r-1"})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))


class AutoApproveCliTests(DwTestCase):
    def entries(self):
        return json.loads(self.dw("project", "list", "--json").stdout)[0].get("auto_approve", [])

    def test_explicit_list_and_remove(self):
        path = self.add_project("alpha")
        r = self.dw("project", "auto-approve", "alpha", "--rule", "kubectl-change",
                    "--match", r"kubectl -n app rollout restart deploy/\w+", "--in", str(path),
                    "--note", "restarts are fine")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["in"], os.path.realpath(str(path)))
        r = self.dw("project", "auto-approve", "alpha", "--rule", "git-push-default",
                    "--match", "git push origin main")
        self.assertEqual(r.returncode, 0, r.stderr)
        listing = self.dw("project", "auto-approve", "alpha", "--list")
        self.assertEqual(listing.returncode, 0)
        lines = listing.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("1") and "kubectl-change" in lines[0])
        self.assertEqual(self.dw("project", "auto-approve", "alpha", "--remove", "1").returncode, 0)
        self.assertEqual([e["rule"] for e in self.entries()], ["git-push-default"])
        self.assertEqual(self.dw("project", "auto-approve", "alpha", "--remove", "5").returncode, 2)

    def test_refusals(self):
        self.add_project("alpha")
        for argv in (["--rule", "control-state", "--match", "x"],
                     ["--rule", "control-dw", "--match", "dw run x"],
                     ["--rule", "control-unreadable", "--match", ".*"],
                     ["--rule", "control-unreadable", "--match", ".+"],
                     ["--rule", "control-unreadable", "--match", "a*"],
                     ["--rule", "git-push-default", "--match", "git push ("],
                     ["--rule", "git-push-default", "--match", "(a+)+"],
                     ["--rule", "git-push-default"],
                     ["--rule", "git-push-default", "--match", "git push origin main\x1b[2K"],
                     ["--rule", "git-push-default", "--match", "git push\u202e origin main"],
                     ["--rule", "git-push-default", "--match", "git push\norigin main"],
                     ["--from-run", "r-nope"], ["--from-run", "r-nope", "--action", "abcd1234"]):
            with self.subTest(argv=argv):
                r = self.dw("project", "auto-approve", "alpha", *argv)
                self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.entries(), [])

    def test_inside_a_run_only_the_list_works(self):
        self.add_project("alpha")
        env = {"DW_RUN_ID": "r-1"}
        r = self.dw("project", "auto-approve", "alpha", "--rule", "git-push-default",
                    "--match", "git push origin main", env=env)
        self.assertEqual((r.returncode, r.stderr.strip()),
                         (2, "dw: dw cannot change the control point from inside a run"))
        self.assertEqual(self.dw("project", "auto-approve", "alpha", "--remove", "1",
                                 env=env).returncode, 2)
        self.assertEqual(self.dw("project", "auto-approve", "alpha", "--list", env=env).returncode, 0)

    def test_doctor_reports_bad_entries(self):
        from dwlib import paths, store
        self.add_project("alpha")

        def fn(reg):
            reg["projects"][0]["auto_approve"] = [{"rule": "x", "match": "("},
                                                  {"rule": "control-unreadable", "match": ".*"}]
            return reg
        store.update_json(paths.registry_path(), fn, store.default_registry())
        r = self.dw("doctor")
        line = [l for l in r.stdout.splitlines() if "auto-approve" in l][0]
        self.assertTrue(line.startswith("WARN"), line)
        self.assertIn("entry 1", line)
        self.assertIn("entry 2", line)
