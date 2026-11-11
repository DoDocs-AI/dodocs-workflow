from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import DW, FAKE_AGTERMCTL, DwTestCase

MARK_START = "# >>> dodocs-workflow control"
MARK_END = "# <<< dodocs-workflow control"

ORIGINAL_SETTINGS = {
    "model": "opus",
    "hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/local/bin/other-hook"}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "afplay done.aiff"}]}],
    },
    "permissions": {"allow": ["Bash(ls:*)"]},
    "teammateMode": "tmux",
}
ORIGINAL_HOOKS_CONF = "# my hooks\non notify say hi\n"


class SetupBase(DwTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.settings = self.tmp / "work" / "settings.json"
        self.settings.parent.mkdir()
        self.conf = self.tmp / "work" / "hooks.conf"
        self.env["DW_CLAUDE_SETTINGS"] = str(self.settings)
        self.env["DW_AGTERM_HOOKS_CONF"] = str(self.conf)
        os.environ["DW_CLAUDE_SETTINGS"] = str(self.settings)
        os.environ["DW_AGTERM_HOOKS_CONF"] = str(self.conf)

    def write_fixtures(self, settings=ORIGINAL_SETTINGS, conf=ORIGINAL_HOOKS_CONF) -> None:
        self.settings.write_text(json.dumps(settings, indent=2) + "\n")
        self.conf.write_text(conf)

    def backups(self, path):
        return sorted(path.parent.glob(path.name + ".dw-backup-*"))

    def reload_calls(self):
        return [c for c in self.agterm_calls() if c[:2] == ["hooks", "reload"]]


class SetupTests(SetupBase):
    def test_setup_adds_guard_entry_and_preserves_other_hooks(self):
        self.write_fixtures()
        r = self.dw("setup", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = json.loads(self.settings.read_text())
        pre = after["hooks"]["PreToolUse"]
        self.assertEqual(pre[0], ORIGINAL_SETTINGS["hooks"]["PreToolUse"][0])
        self.assertEqual(len(pre), 2)
        self.assertEqual(pre[1], {"matcher": "*", "hooks": [
            {"type": "command", "command": "'%s' guard" % DW, "timeout": 3600}]})
        for key in ("model", "permissions", "teammateMode"):
            self.assertEqual(after[key], ORIGINAL_SETTINGS[key])
        self.assertEqual(after["hooks"]["Stop"], ORIGINAL_SETTINGS["hooks"]["Stop"])
        self.assertEqual(list(after), list(ORIGINAL_SETTINGS))

    def test_setup_is_idempotent(self):
        self.write_fixtures()
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)
        settings_bytes, conf_bytes = self.settings.read_bytes(), self.conf.read_bytes()
        backups = (self.backups(self.settings), self.backups(self.conf))
        r = self.dw("setup", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing to do", r.stdout.lower())
        self.assertEqual((self.settings.read_bytes(), self.conf.read_bytes()),
                         (settings_bytes, conf_bytes))
        self.assertEqual((self.backups(self.settings), self.backups(self.conf)), backups)

    def test_setup_without_yes_and_answer_no_changes_nothing(self):
        self.write_fixtures()
        before = (self.settings.read_bytes(), self.conf.read_bytes())
        r = self.dw("setup", stdin="y\n")  # stdin is not a terminal: counts as "no"
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual((self.settings.read_bytes(), self.conf.read_bytes()), before)
        self.assertEqual(self.backups(self.settings) + self.backups(self.conf), [])
        self.assertEqual(self.reload_calls(), [])
        self.assertIn("PreToolUse", r.stdout)  # the pending change was shown

    def test_setup_creates_missing_files(self):
        r = self.dw("setup", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(self.settings.read_text())
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 1)
        self.assertIn("on status '%s' hook status" % DW, self.conf.read_text())
        self.assertEqual(self.backups(self.settings) + self.backups(self.conf), [])

    def test_remove_restores_original_bytes(self):
        self.write_fixtures()
        before = (self.settings.read_bytes(), self.conf.read_bytes())
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)
        self.assertNotEqual(self.settings.read_bytes(), before[0])
        r = self.dw("setup", "--remove", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.settings.read_bytes(), self.conf.read_bytes()), before)

    def test_remove_restores_bytes_when_hooks_section_was_absent(self):
        self.write_fixtures({"model": "opus"}, "")
        before = (self.settings.read_bytes(), self.conf.read_bytes())
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)
        self.assertEqual(self.dw("setup", "--remove", "--yes").returncode, 0)
        self.assertEqual((self.settings.read_bytes(), self.conf.read_bytes()), before)

    def test_remove_keeps_a_foreign_hook_sharing_the_group(self):
        group = {"matcher": "*", "hooks": [
            {"type": "command", "command": "other"},
            {"type": "command", "command": "'%s' guard" % DW, "timeout": 3600}]}
        self.write_fixtures({"hooks": {"PreToolUse": [group]}})
        self.assertEqual(self.dw("setup", "--remove", "--yes").returncode, 0)
        after = json.loads(self.settings.read_text())
        self.assertEqual(after["hooks"]["PreToolUse"],
                         [{"matcher": "*", "hooks": [{"type": "command", "command": "other"}]}])

    def test_remove_without_yes_and_non_terminal_changes_nothing(self):
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)
        before = (self.settings.read_bytes(), self.conf.read_bytes())
        r = self.dw("setup", "--remove", stdin="y\n")
        self.assertEqual(r.returncode, 1)
        self.assertEqual((self.settings.read_bytes(), self.conf.read_bytes()), before)

    def test_remove_when_nothing_installed_is_a_no_op(self):
        self.write_fixtures()
        before = (self.settings.read_bytes(), self.conf.read_bytes())
        r = self.dw("setup", "--remove", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.settings.read_bytes(), self.conf.read_bytes()), before)

    def test_written_entry_is_recognised_by_guard_entry_present_and_removal_clears_it(self):
        from dwlib import guard, setup
        self.write_fixtures()
        self.assertFalse(guard.guard_entry_present(self.settings))
        for item in setup.plan_setup(self.settings, self.conf, str(DW)):
            item["apply"]()
        self.assertTrue(guard.guard_entry_present(self.settings))
        self.assertEqual(setup.plan_setup(self.settings, self.conf, str(DW)), [])
        descriptions = setup.remove_setup(self.settings, self.conf)
        self.assertEqual(len(descriptions), 2)
        self.assertFalse(guard.guard_entry_present(self.settings))
        self.assertEqual(setup.remove_setup(self.settings, self.conf), [])

    def test_hooks_conf_block_between_markers_and_reload_called(self):
        self.write_fixtures()
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)
        text = self.conf.read_text()
        self.assertTrue(text.startswith(ORIGINAL_HOOKS_CONF))
        lines = text.splitlines()
        start, end = lines.index(MARK_START), lines.index(MARK_END)
        self.assertEqual(lines[start + 1:end], [
            "on status '%s' hook status" % DW,
            "on session.closed '%s' hook session-closed" % DW])
        self.assertEqual(len(self.reload_calls()), 1)

    def test_setup_updates_a_stale_block_in_place(self):
        stale = ORIGINAL_HOOKS_CONF + "%s\non status '/old/dw' hook status\n%s\non notify later\n" % (
            MARK_START, MARK_END)
        self.write_fixtures(conf=stale)
        r = self.dw("setup", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.conf.read_text()
        self.assertNotIn("/old/dw", text)
        self.assertTrue(text.endswith("on notify later\n"))
        self.assertEqual(text.count(MARK_START), 1)
        self.assertIn("on session.closed '%s' hook session-closed" % DW, text)

    def test_backup_is_saved_before_first_modification_and_announced(self):
        self.write_fixtures()
        before = (self.settings.read_bytes(), self.conf.read_bytes())
        r = self.dw("setup", "--yes")
        for path, original in ((self.settings, before[0]), (self.conf, before[1])):
            found = self.backups(path)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].read_bytes(), original)
            self.assertRegex(found[0].name, r"\.dw-backup-\d+$")
            self.assertIn(str(found[0]), r.stdout)

    def test_invalid_settings_json_is_refused_and_nothing_changes(self):
        self.write_fixtures()
        self.settings.write_text("{ not json")
        before = (self.settings.read_bytes(), self.conf.read_bytes())
        r = self.dw("setup", "--yes")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertEqual((self.settings.read_bytes(), self.conf.read_bytes()), before)
        self.assertEqual(self.backups(self.settings) + self.backups(self.conf), [])

    def test_unbalanced_markers_are_refused(self):
        self.write_fixtures(conf="%s\non status x\n" % MARK_START)
        before = self.conf.read_bytes()
        r = self.dw("setup", "--yes")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertEqual(self.conf.read_bytes(), before)

    def test_single_line_settings_style_is_preserved(self):
        self.settings.write_text(json.dumps({"model": "x"}))
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)
        text = self.settings.read_text()
        self.assertEqual(len(text.splitlines()), 1)
        self.assertFalse(text.endswith("\n"))
        self.assertEqual(self.dw("setup", "--remove", "--yes").returncode, 0)
        self.assertEqual(self.settings.read_text(), json.dumps({"model": "x"}))

    def test_setup_through_a_symlink_records_the_resolved_path(self):
        link = self.tmp / "local-bin" / "dw"
        link.parent.mkdir()
        link.symlink_to(DW)
        r = subprocess.run([sys.executable, str(link), "setup", "--yes"], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        settings, conf = self.settings.read_text(), self.conf.read_text()
        self.assertEqual(json.loads(settings)["hooks"]["PreToolUse"][0]["hooks"][0]["command"],
                         "'%s' guard" % os.path.realpath(str(DW)))
        self.assertIn("on status '%s' hook status" % os.path.realpath(str(DW)), conf)
        self.assertNotIn(str(link), settings + conf)

    def test_setup_replaces_a_stale_guard_entry_and_leaves_other_hooks(self):
        gone = self.tmp / "gone" / "old" / "bin" / "dw"
        settings = json.loads(json.dumps(ORIGINAL_SETTINGS))
        settings["hooks"]["PreToolUse"].append({"matcher": "*", "hooks": [
            {"type": "command", "command": "'%s' guard" % gone, "timeout": 3600}]})
        self.write_fixtures(settings)
        r = self.dw("setup", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = json.loads(self.settings.read_text())
        expected = json.loads(json.dumps(settings))
        expected["hooks"]["PreToolUse"][1]["hooks"][0]["command"] = "'%s' guard" % DW
        self.assertEqual(after, expected)
        r = self.dw("setup", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing to do", r.stdout.lower())

    def test_plan_setup_refreshes_a_block_whose_path_is_gone(self):
        from dwlib import setup
        gone = self.tmp / "gone" / "dw"
        self.write_fixtures(conf="%s\non status '%s' hook status\non session.closed '%s' hook "
                                 "session-closed\n%s\n" % (MARK_START, gone, gone, MARK_END))
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)
        self.assertNotIn(str(gone), self.conf.read_text())
        self.assertEqual(setup.plan_setup(self.settings, self.conf, str(DW)), [])

    def test_symlinked_settings_file_stays_a_symlink(self):
        real = self.tmp / "dotfiles-settings.json"
        real.write_text(json.dumps({"model": "x"}, indent=2) + "\n")
        self.settings.symlink_to(real)
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)
        self.assertTrue(self.settings.is_symlink())
        self.assertIn("PreToolUse", real.read_text())


class DoctorTests(SetupBase):
    def line(self, out, check):
        found = [l for l in out.splitlines() if l.split(None, 1)[-1].startswith(check + ":")]
        self.assertEqual(len(found), 1, "%s in:\n%s" % (check, out))
        return found[0]

    def installed(self):
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)

    def test_doctor_all_ok_after_setup(self):
        self.installed()
        r = self.dw("doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for l in r.stdout.splitlines():
            self.assertRegex(l, r"^(OK|WARN|FAIL)  \S")
        self.assertNotIn("FAIL", r.stdout)

    def test_doctor_fails_when_guard_entry_and_hooks_are_missing(self):
        self.write_fixtures()
        r = self.dw("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.line(r.stdout, "guard entry").startswith("FAIL"))
        self.assertTrue(self.line(r.stdout, "hooks.conf").startswith("FAIL"))

    def test_doctor_fails_when_agterm_is_unreachable(self):
        self.installed()
        r = self.dw("doctor", env={"FAKE_AGTERM_DOWN": "1"})
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.line(r.stdout, "agtermctl").startswith("FAIL"))

    def test_doctor_fails_on_a_project_path_that_is_gone(self):
        self.installed()
        path = self.add_project("alpha")
        path.rmdir()
        r = self.dw("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.line(r.stdout, "projects").startswith("FAIL"))
        self.assertIn("alpha", self.line(r.stdout, "projects"))

    def test_doctor_fails_on_corrupt_files(self):
        self.installed()
        self.dw_home.mkdir(parents=True, exist_ok=True)
        (self.dw_home / "registry.json").write_text("{ nope")
        r = self.dw("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.line(r.stdout, "files").startswith("FAIL"))

    def test_doctor_fails_on_invalid_settings_json(self):
        self.installed()
        self.settings.write_text("{ nope")
        r = self.dw("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.line(r.stdout, "files").startswith("FAIL"))

    def test_doctor_marks_orphaned_running_run_interrupted(self):
        self.installed()
        self.add_project("alpha")
        rid = self.dw("run", "alpha", "/scrum-team x").stdout.split()[0]
        from dwlib import store
        sid = store.load_run(rid)["agterm_session"]
        sessions = self.fake_sessions()
        del sessions[sid]
        (self.fake_agterm_dir / "sessions.json").write_text(json.dumps(sessions))
        r = self.dw("doctor")
        record = store.load_run(rid)
        self.assertEqual(record["state"], "interrupted")
        self.assertIn(rid, r.stdout)
        self.assertTrue(self.line(r.stdout, "runs").startswith("WARN"))
        self.assertEqual(r.returncode, 0)

    def test_doctor_repairs_nothing_when_a_window_is_closed(self):
        self.installed()
        self.add_project("alpha")
        rid = self.dw("run", "alpha", "/scrum-team x").stdout.split()[0]
        from dwlib import store
        sid = store.load_run(rid)["agterm_session"]
        sessions = self.fake_sessions()
        del sessions[sid]
        (self.fake_agterm_dir / "sessions.json").write_text(json.dumps(sessions))
        (self.fake_agterm_dir / "closed-window").write_text("")
        r = self.dw("doctor")
        self.assertEqual(store.load_run(rid)["state"], "running")
        line = self.line(r.stdout, "runs")
        self.assertTrue(line.startswith("WARN"), line)
        self.assertIn("%s not visible \u2014 a terminal window is closed; cannot tell" % rid, line)
        self.assertEqual(r.returncode, 0)

    def test_doctor_leaves_running_run_with_live_session_alone(self):
        self.installed()
        self.add_project("alpha")
        rid = self.dw("run", "alpha", "/scrum-team x").stdout.split()[0]
        r = self.dw("doctor")
        from dwlib import store
        self.assertEqual(store.load_run(rid)["state"], "running")
        self.assertTrue(self.line(r.stdout, "runs").startswith("OK"))

    def test_doctor_does_not_touch_runs_when_agterm_is_unreachable(self):
        self.installed()
        self.add_project("alpha")
        rid = self.dw("run", "alpha", "/scrum-team x").stdout.split()[0]
        self.dw("doctor", env={"FAKE_AGTERM_DOWN": "1"})
        from dwlib import store
        self.assertEqual(store.load_run(rid)["state"], "running")

    def test_doctor_warns_when_teammate_mode_is_not_tmux(self):
        self.write_fixtures({k: v for k, v in ORIGINAL_SETTINGS.items() if k != "teammateMode"})
        self.dw("setup", "--yes")
        r = self.dw("doctor")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(self.line(r.stdout, "teammateMode").startswith("WARN"))

    def test_doctor_teammate_mode_tmux_is_ok(self):
        self.write_fixtures()
        self.dw("setup", "--yes")
        self.assertTrue(self.line(self.dw("doctor").stdout, "teammateMode").startswith("OK"))

    def _tmux_env(self):
        fake = self.tmp / "fake-tmux"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        sockets = self.tmp / "tmux-tmp" / ("tmux-%d" % os.getuid())
        sockets.mkdir(parents=True)
        return {"DW_TMUX": str(fake)}, sockets

    def test_doctor_reports_leftover_claude_swarm_tmux_servers_without_killing(self):
        self.installed()
        env, sockets = self._tmux_env()
        done = subprocess.Popen([sys.executable, "-c", "pass"])
        done.wait()
        dead = sockets / ("claude-swarm-%d" % done.pid)
        dead.write_text("")
        alive = sockets / ("claude-swarm-%d" % os.getpid())
        alive.write_text("")
        other = sockets / "default"
        other.write_text("")
        r = self.dw("doctor", env=env)
        line = self.line(r.stdout, "tmux")
        self.assertTrue(line.startswith("WARN"), line)
        self.assertIn("claude-swarm-%d" % done.pid, line)
        self.assertNotIn("claude-swarm-%d" % os.getpid(), line)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(dead.exists() and alive.exists() and other.exists())

    def test_doctor_tmux_without_leftovers_is_ok(self):
        self.installed()
        env, sockets = self._tmux_env()
        (sockets / ("claude-swarm-%d" % os.getpid())).write_text("")
        self.assertTrue(self.line(self.dw("doctor", env=env).stdout, "tmux").startswith("OK"))

    def test_doctor_skips_tmux_check_silently_when_tmux_is_not_installed(self):
        self.installed()
        r = self.dw("doctor")  # DW_TMUX points at a file that does not exist
        self.assertNotRegex(r.stdout, r"(?m)^\w+  tmux:")

    def test_doctor_fails_when_the_installed_dw_path_is_gone(self):
        gone = self.tmp / "gone" / "dw"
        self.write_fixtures({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "'%s' guard" % gone, "timeout": 3600}]}]}},
            "%s\non status '%s' hook status\non session.closed '%s' hook session-closed\n%s\n"
            % (MARK_START, gone, gone, MARK_END))
        r = self.dw("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.line(r.stdout, "dw path").startswith("FAIL"))
        self.assertIn(str(gone), self.line(r.stdout, "dw path"))
        self.assertIn("run `dw setup` again", self.line(r.stdout, "dw path"))
        self.assertEqual(self.dw("setup", "--yes").returncode, 0)  # the remedy it names works
        r = self.dw("doctor")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(self.line(r.stdout, "dw path").startswith("OK"))
        self.assertTrue(self.line(r.stdout, "guard entry").startswith("OK"))

    def test_doctor_fails_when_hooks_conf_has_only_one_line(self):
        self.installed()
        text = self.conf.read_text().replace(
            "on session.closed '%s' hook session-closed\n" % DW, "")
        self.conf.write_text(text)
        r = self.dw("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.line(r.stdout, "hooks.conf").startswith("FAIL"))

    def test_doctor_function_returns_check_ok_detail_triples(self):
        from dwlib import setup
        self.write_fixtures()
        results = setup.doctor()
        self.assertTrue(all(len(t) == 3 and isinstance(t[1], bool) for t in results))
        self.assertIn(False, [ok for _, ok, _ in results])


class IsolationTests(DwTestCase):
    def test_in_process_code_sees_only_fake_binaries_and_temp_paths(self):
        import shutil
        from dwlib import agterm
        self.assertEqual(agterm._binary(), str(FAKE_AGTERMCTL))
        tmux = shutil.which(os.environ.get("DW_TMUX") or "tmux")
        self.assertIsNone(tmux)  # the fixture points at a tmux that does not exist
        self.assertTrue(os.environ["TMUX_TMPDIR"].startswith(str(self.tmp)))
        for var in ("DW_HOME", "DW_CLAUDE_SETTINGS", "DW_AGTERM_HOOKS_CONF", "DW_CLAUDE_STATE"):
            self.assertTrue(os.environ[var].startswith(str(self.tmp)), var)
        for key, value in self.env.items():
            if key.startswith("DW_"):
                self.assertEqual(os.environ.get(key), value, key)


LEGACY = {
    "version": "1.0",
    "workspaces": ["personal", "corporate"],
    "projects": [
        {"id": "proj-001", "name": "Match Point", "workspace": "corporate", "type": "software",
         "phase": "in_progress", "path": "@A", "description": "Doc extraction. Quarkus + React.",
         "status": "active", "created_at": "2026-03-04T12:28:41Z", "tasks": []},
        {"id": "proj-002", "name": "Gone Project", "workspace": "corporate", "path": "@MISSING",
         "description": "x"},
        {"id": "proj-003", "name": "Side Thing", "workspace": "personal", "path": "@B",
         "description": ""},
    ],
}


class ImportLegacyTests(DwTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.a, self.b = self.tmp / "a", self.tmp / "b"
        self.a.mkdir()
        self.b.mkdir()
        legacy = json.loads(json.dumps(LEGACY))
        for p in legacy["projects"]:
            p["path"] = {"@A": str(self.a), "@B": str(self.b),
                         "@MISSING": str(self.tmp / "missing")}[p["path"]]
        self.legacy = self.tmp / "legacy-registry.json"
        self.legacy.write_text(json.dumps(legacy, indent=2))

    def test_import_legacy_maps_fields_and_skips_missing_paths(self):
        from dwlib import setup, store
        added = setup.import_legacy(self.legacy, lambda p: "Dodocs" if p["workspace"] == "corporate" else None)
        self.assertEqual([p["id"] for p in added], ["match-point"])
        project = store.load_registry()["projects"][0]
        self.assertEqual(project, {
            "id": "match-point", "name": "Match Point", "path": str(self.a), "group": "Dodocs",
            "harness": "claude", "notes": "Doc extraction. Quarkus + React.", "guard_rules": []})

    def test_import_legacy_skips_none_group_and_existing_ids(self):
        from dwlib import setup, store
        self.add_project("Match Point", group="Keep")
        asked = []

        def group_for(p):
            asked.append(p["name"])
            return "G"

        added = setup.import_legacy(self.legacy, group_for)
        self.assertEqual([p["id"] for p in added], ["side-thing"])
        self.assertEqual(asked, ["Side Thing"])  # no question about a project that exists or is gone
        by_id = {p["id"]: p for p in store.load_registry()["projects"]}
        self.assertEqual(by_id["match-point"]["group"], "Keep")

    def test_import_legacy_never_writes_to_legacy_file(self):
        from dwlib import setup
        os.utime(str(self.legacy), (1000000000, 1000000000))
        before = (self.legacy.read_bytes(), self.legacy.stat().st_mtime)
        setup.import_legacy(self.legacy, lambda p: "G")
        self.assertEqual((self.legacy.read_bytes(), self.legacy.stat().st_mtime), before)

    def test_import_legacy_cli_with_group_imports_all_valid(self):
        r = self.dw("project", "import-legacy", "--from", str(self.legacy), "--group", "Dodocs")
        self.assertEqual(r.returncode, 0, r.stderr)
        projects = json.loads(self.dw("project", "list", "--json").stdout)
        self.assertEqual({p["id"] for p in projects}, {"match-point", "side-thing"})
        self.assertEqual({p["group"] for p in projects}, {"Dodocs"})
        self.assertIn("match-point", r.stdout)
        self.assertIn("Gone Project", r.stdout)  # the skipped one is reported

    def test_import_legacy_cli_non_terminal_without_group_imports_nothing(self):
        r = self.dw("project", "import-legacy", "--from", str(self.legacy), stdin="Dodocs\nDodocs\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.dw("project", "list", "--json").stdout), [])
        self.assertIn("--group", r.stdout)

    def test_import_legacy_cli_missing_source_is_one_line_error(self):
        r = self.dw("project", "import-legacy", "--from", str(self.tmp / "nope.json"), "--group", "G")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_import_legacy_default_source_is_home_claude_workspace(self):
        home = self.tmp / "fakehome"
        (home / ".claude" / "workspace").mkdir(parents=True)
        (home / ".claude" / "workspace" / "registry.json").write_text(self.legacy.read_text())
        r = self.dw("project", "import-legacy", "--group", "G", env={"HOME": str(home)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("match-point", r.stdout)


if __name__ == "__main__":
    unittest.main()
