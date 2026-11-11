from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from helpers import DwTestCase, FAKE_AGTERMCTL

SUFFIX_RE = re.compile(
    r"When this work is finished, or you cannot continue, write a short result note to "
    r"(\S+)\. First line: exactly DONE, BLOCKED or FAILED\. Then: what was done, the pull "
    r"request URL if any, and what is left\. Write this file even if the work failed\.\Z")


def opt(argv, name):
    return argv[argv.index(name) + 1]


class RunTestBase(DwTestCase):
    def new_session_calls(self):
        return [c for c in self.agterm_calls() if c[:2] == ["session", "new"]]

    def run_cmd(self, project, *command, env=None):
        return self.dw("run", project, *command, env=env)

    def run_id(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.split()[0]

    def record(self, run_id):
        from dwlib import store
        return store.load_run(run_id)

    def set_record(self, run_id, **fields):
        from dwlib import store
        store.update_run(run_id, lambda r: {**r, **fields})

    def run_records(self):
        from dwlib import store
        return store.list_runs()[0]


class RunStartTests(RunTestBase):
    def test_run_starts_session_in_group_workspace(self):
        path = self.add_project("slotme", group="ignashev_ai")
        r = self.run_cmd("slotme", "/scrum-team", "build", "it")
        rid = self.run_id(r)
        self.assertRegex(rid, r"^r-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(r.stdout.split()[1:], ["started"])
        calls = self.new_session_calls()
        self.assertEqual(len(calls), 1)
        argv = calls[0]
        self.assertIn("--no-select", argv)
        self.assertIn("--create-workspace", argv)
        self.assertEqual(opt(argv, "--workspace-name"), "ignashev_ai")
        self.assertEqual(opt(argv, "--cwd"), str(path.resolve()))
        self.assertEqual(opt(argv, "--name"), "slotme: /scrum-team build it")
        rec = self.record(rid)
        self.assertEqual(rec["state"], "running")
        self.assertEqual(rec["project_id"], "slotme")
        self.assertEqual(rec["command"], "/scrum-team build it")
        self.assertIn(rec["agterm_session"], self.fake_sessions())
        self.assertIsNone(rec["reason"])
        self.assertIsInstance(rec["started_at"], float)
        for key in ("approvals", "grants"):
            self.assertEqual(rec[key], [])
        self.assertIsNone(rec["pending_approval"])
        # restore pinned to nothing and the run id set as session context
        session = self.fake_sessions()[rec["agterm_session"]]
        self.assertEqual(session["restore"], "")
        self.assertEqual(session["context"], rid)

    def test_session_name_uses_first_40_chars_of_command(self):
        self.add_project("slotme")
        self.run_id(self.run_cmd("slotme", "x" * 100))
        name = opt(self.new_session_calls()[0], "--name")
        self.assertEqual(name, "slotme: " + "x" * 40)

    def test_prompt_is_passed_via_file_not_argv(self):
        from dwlib import paths
        self.add_project("slotme")
        command = "do \"this\" and 'that' $HOME `id`\nsecond line " + "z" * 3000
        command = command[:3000]
        self.assertEqual(len(command.encode()), 3000)
        rid = self.run_id(self.run_cmd("slotme", command))
        data = paths.prompt_path(rid).read_bytes()
        self.assertTrue(data.startswith(command.encode()))
        tail = data[len(command.encode()):].decode()
        self.assertTrue(tail.startswith("\n\n"))
        m = SUFFIX_RE.match(tail[2:])
        self.assertIsNotNone(m, tail)
        self.assertEqual(m.group(1), str(paths.result_note_path(rid)))
        self.assertTrue(os.path.isabs(m.group(1)))
        cmd_arg = opt(self.new_session_calls()[0], "--command")
        self.assertNotIn("this", cmd_arg)
        self.assertNotIn("second line", cmd_arg)
        self.assertIn(str(paths.prompt_path(rid)), cmd_arg)
        self.assertIn("$(cat ", cmd_arg)

    def test_session_command_shape_and_run_id_env(self):
        rid = self.run_id((self.add_project("slotme"), self.run_cmd("slotme", "go"))[1])
        cmd_arg = opt(self.new_session_calls()[0], "--command")
        self.assertTrue(cmd_arg.startswith("zsh -lc '"), cmd_arg)
        self.assertIn("DW_RUN_ID=%s " % rid, cmd_arg)
        self.assertIn("--permission-mode bypassPermissions", cmd_arg)
        self.assertNotIn("--model", cmd_arg)
        self.assertIn(" claude ", cmd_arg)

    def test_claude_binary_comes_from_dw_claude(self):
        self.add_project("slotme")
        self.run_id(self.run_cmd("slotme", "go", env={"DW_CLAUDE": "/opt/x/claude-fake"}))
        self.assertIn("/opt/x/claude-fake --permission-mode",
                      opt(self.new_session_calls()[0], "--command"))

    def test_harness_session_id_recorded_and_passed_at_launch(self):
        self.add_project("slotme")
        rid = self.run_id(self.run_cmd("slotme", "go"))
        sid = self.record(rid)["harness_session"]
        self.assertRegex(sid, r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
        self.assertIn("--session-id %s" % sid, opt(self.new_session_calls()[0], "--command"))

    def test_socket_flag_passed_on_every_call_when_env_set(self):
        self.add_project("slotme")
        self.run_id(self.run_cmd("slotme", "go", env={"AGTERM_SOCKET": "/tmp/x.sock"}))
        calls = self.agterm_calls()
        self.assertGreaterEqual(len(calls), 3)
        for argv in calls:
            self.assertEqual(opt(argv, "--socket"), "/tmp/x.sock", argv)
            # options go after the subcommand
            self.assertNotEqual(argv[0], "--socket")

    def test_agt_socket_also_honoured(self):
        self.add_project("slotme")
        self.run_id(self.run_cmd("slotme", "go", env={"AGT_SOCKET": "/tmp/y.sock"}))
        self.assertTrue(all(opt(a, "--socket") == "/tmp/y.sock" for a in self.agterm_calls()))


class RunLimitTests(RunTestBase):
    def test_second_run_same_project_is_queued(self):
        self.add_project("slotme")
        self.run_id(self.run_cmd("slotme", "one"))
        r = self.run_cmd("slotme", "two")
        rid = self.run_id(r)
        self.assertEqual(r.stdout.strip(), "%s queued (project busy)" % rid)
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["reason"]), ("queued", "project busy"))
        self.assertEqual(len(self.new_session_calls()), 1)

    def _three_running(self):
        ids = []
        for name in ("a", "b", "c"):
            self.add_project(name)
            ids.append(self.run_id(self.run_cmd(name, "go")))
        return ids

    def test_fourth_run_across_projects_is_queued(self):
        self._three_running()
        self.add_project("d")
        r = self.run_cmd("d", "go")
        rid = self.run_id(r)
        self.assertEqual(r.stdout.strip(), "%s queued (total limit 3)" % rid)
        self.assertEqual(self.record(rid)["state"], "queued")

    def test_awaiting_approval_run_frees_a_total_slot(self):
        a, _b, _c = self._three_running()
        self.set_record(a, state="blocked", reason="awaiting approval: x")
        self.add_project("d")
        r = self.run_cmd("d", "go")
        self.assertTrue(r.stdout.strip().endswith("started"), r.stdout)

    def test_blocked_for_other_reason_still_counts(self):
        a, _b, _c = self._three_running()
        self.set_record(a, state="blocked", reason="stalled")
        self.add_project("d")
        self.assertIn("queued", self.run_cmd("d", "go").stdout)

    def test_blocked_awaiting_approval_still_occupies_its_project(self):
        a = self.run_id((self.add_project("a"), self.run_cmd("a", "go"))[1])
        self.set_record(a, state="blocked", reason="awaiting approval: x")
        self.assertIn("queued (project busy)", self.run_cmd("a", "again").stdout)

    def test_limits_come_from_registry(self):
        self.add_project("a")
        self.add_project("b")
        reg = json.loads((self.dw_home / "registry.json").read_text())
        reg["limits"]["total"] = 1
        (self.dw_home / "registry.json").write_text(json.dumps(reg))
        self.run_id(self.run_cmd("a", "go"))
        r = self.run_cmd("b", "go")
        self.assertIn("queued (total limit 1)", r.stdout)

    def test_counts_against_total(self):
        from dwlib import runs
        self.assertTrue(runs.counts_against_total({"state": "running", "reason": None}))
        self.assertTrue(runs.counts_against_total({"state": "blocked", "reason": "stalled"}))
        self.assertTrue(runs.counts_against_total({"state": "blocked", "reason": None}))
        self.assertFalse(runs.counts_against_total(
            {"state": "blocked", "reason": "awaiting approval: rm -rf"}))
        for state in ("queued", "done", "failed", "interrupted", "cancelled"):
            self.assertFalse(runs.counts_against_total({"state": state, "reason": None}))

    def test_queued_run_starts_oldest_first_when_a_slot_frees(self):
        a = self.run_id((self.add_project("a"), self.run_cmd("a", "go"))[1])
        q1 = self.run_id(self.run_cmd("a", "second"))
        q2 = self.run_id(self.run_cmd("a", "third"))
        self.assertEqual(self.dw("cancel", a).returncode, 0)
        self.assertEqual(self.record(q1)["state"], "running")
        self.assertEqual(self.record(q2)["state"], "queued")

    def test_queued_run_for_other_project_is_not_blocked_by_busy_one(self):
        from dwlib import runs
        self.add_project("a")
        self.add_project("b")
        self.run_id(self.run_cmd("a", "go"))
        self.run_id(self.run_cmd("a", "waiting"))
        self.run_id(self.run_cmd("b", "go"))
        self.assertEqual(sorted(r["state"] for r in self.run_records()),
                         ["queued", "running", "running"])
        self.assertEqual(runs.start_eligible(), [])


class RunRefusalTests(RunTestBase):
    def test_run_refuses_without_agterm(self):
        self.add_project("slotme")
        r = self.run_cmd("slotme", "go", env={"FAKE_AGTERM_DOWN": "1"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("AGTerm", r.stderr)
        self.assertEqual(self.run_records(), [])
        self.assertFalse((self.dw_home / "runs").exists() and
                         list((self.dw_home / "runs").glob("*.prompt")))

    def test_run_refuses_when_agtermctl_binary_missing(self):
        self.add_project("slotme")
        r = self.run_cmd("slotme", "go", env={"DW_AGTERMCTL": "/nonexistent/agtermctl"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("AGTerm", r.stderr)
        self.assertEqual(self.run_records(), [])

    def test_run_refuses_non_claude_harness(self):
        self.add_project("slotme")
        reg = json.loads((self.dw_home / "registry.json").read_text())
        reg["projects"][0]["harness"] = "codex"
        (self.dw_home / "registry.json").write_text(json.dumps(reg))
        r = self.run_cmd("slotme", "go")
        self.assertEqual(r.returncode, 2)
        self.assertIn("codex", r.stderr)
        self.assertEqual(self.run_records(), [])

    def test_run_refuses_out_of_checkout_commands(self):
        self.add_project("slotme")
        r = self.run_cmd("slotme", "/container-team", "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("/container-team", r.stderr)
        self.assertIn("outside the project checkout", r.stderr)
        r = self.run_cmd("slotme", "/scrum-team", "--docker", "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--docker", r.stderr)
        self.assertIn("outside the project checkout", r.stderr)
        self.assertEqual(self.run_records(), [])
        self.assertEqual(self.new_session_calls(), [])

    def test_run_refuses_unknown_and_ambiguous_project(self):
        self.add_project("slotme-a")
        self.add_project("slotme-b")
        r = self.run_cmd("nope", "go")
        self.assertEqual(r.returncode, 2)
        self.assertIn("nope", r.stderr)
        r = self.run_cmd("slotme", "go")
        self.assertEqual(r.returncode, 2)
        self.assertIn("slotme-a", r.stderr)

    def test_run_refuses_untrusted_workspace(self):
        path = self.add_project("slotme", trusted=False)
        r = self.run_cmd("slotme", "go")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertIn("open Claude Code once", r.stderr)
        self.assertIn(str(path), r.stderr)
        self.assertEqual(self.run_records(), [])
        self.assertEqual(self.new_session_calls(), [])
        # dw never writes the state file
        self.assertEqual(json.loads(self.claude_state.read_text()), {"projects": {}})

    def test_trust_requires_accepted_flag_for_exact_path(self):
        path = self.add_project("slotme", trusted=False)
        self.claude_state.write_text(json.dumps({"projects": {
            str(path.resolve()): {"hasTrustDialogAccepted": False},
            str(path.parent): {"hasTrustDialogAccepted": True},
        }}))
        self.assertEqual(self.run_cmd("slotme", "go").returncode, 2)

    def test_missing_or_corrupt_claude_state_means_untrusted(self):
        self.add_project("slotme")
        self.claude_state.write_text("{")
        self.assertEqual(self.run_cmd("slotme", "go").returncode, 2)
        self.claude_state.unlink()
        self.assertEqual(self.run_cmd("slotme", "go").returncode, 2)

    def test_run_without_command_is_a_usage_error(self):
        self.add_project("slotme")
        self.assertEqual(self.dw("run", "slotme").returncode, 2)


class CancelAndQueueTests(RunTestBase):
    def test_cancel_closes_session_and_marks_cancelled(self):
        self.add_project("slotme")
        rid = self.run_id(self.run_cmd("slotme", "go"))
        sid = self.record(rid)["agterm_session"]
        r = self.dw("cancel", rid)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record(rid)
        self.assertEqual(rec["state"], "cancelled")
        self.assertIsInstance(rec["ended_at"], float)
        self.assertNotIn(sid, self.fake_sessions())
        closes = [c for c in self.agterm_calls() if c[:2] == ["session", "close"]]
        self.assertEqual([opt(c, "--target") for c in closes], [sid])

    def test_cancel_queued_run_never_started(self):
        self.add_project("slotme")
        self.run_id(self.run_cmd("slotme", "one"))
        rid = self.run_id(self.run_cmd("slotme", "two"))
        before = len(self.new_session_calls())
        r = self.dw("cancel", rid)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record(rid)
        self.assertEqual(rec["state"], "cancelled")
        self.assertIsNone(rec["agterm_session"])
        self.assertIsNone(rec["started_at"])
        self.assertEqual(len(self.new_session_calls()), before)
        self.assertEqual([c for c in self.agterm_calls() if c[:2] == ["session", "close"]], [])

    def test_cancel_unknown_run_exits_2(self):
        r = self.dw("cancel", "r-nope")
        self.assertEqual(r.returncode, 2)
        self.assertIn("r-nope", r.stderr)

    def test_cancel_finished_run_exits_2(self):
        self.add_project("slotme")
        rid = self.run_id(self.run_cmd("slotme", "go"))
        self.set_record(rid, state="done")
        r = self.dw("cancel", rid)
        self.assertEqual(r.returncode, 2)
        self.assertIn("done", r.stderr)

    def test_cancel_running_run_when_agterm_down_leaves_it_running(self):
        self.add_project("slotme")
        rid = self.run_id(self.run_cmd("slotme", "go"))
        r = self.dw("cancel", rid, env={"FAKE_AGTERM_DOWN": "1"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("AGTerm", r.stderr)
        self.assertEqual(self.record(rid)["state"], "running")

    def test_queue_lists_queued_runs_only(self):
        self.add_project("slotme")
        self.run_id(self.run_cmd("slotme", "one"))
        q = self.run_id(self.run_cmd("slotme", "two"))
        r = self.dw("queue")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1)
        self.assertIn(q, r.stdout)
        self.assertIn("project busy", r.stdout)
        data = json.loads(self.dw("queue", "--json").stdout)
        self.assertEqual([d["id"] for d in data], [q])
        self.assertEqual(data[0]["state"], "queued")

    def test_queue_empty(self):
        r = self.dw("queue", "--json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout), [])


class StateGuardTests(RunTestBase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {
            "DW_AGTERMCTL": str(FAKE_AGTERMCTL), "DW_HOME": str(self.dw_home)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _project(self, name="slotme"):
        self.add_project(name)
        from dwlib import store
        return store.find_project(store.load_registry(), name)

    def _queued_record(self, project, state="queued"):
        from dwlib import runs, store
        rec = {"id": runs.new_run_id(), "project_id": project["id"], "command": "go",
               "state": state, "reason": None, "agterm_session": None,
               "harness_session": None, "created_at": 1.0, "started_at": None,
               "ended_at": None, "approvals": [], "pending_approval": None, "grants": []}
        store.create_run(rec)
        return rec

    def test_start_refuses_record_that_is_no_longer_queued(self):
        from dwlib import runs
        project = self._project()
        rec = self._queued_record(project, state="cancelled")
        with self.assertRaises(runs.RunError):
            runs._start(rec, project)
        self.assertEqual(self.record(rec["id"])["state"], "cancelled")
        self.assertEqual(self.new_session_calls(), [])

    def test_cancelled_while_launching_is_not_resurrected_and_session_closed(self):
        from dwlib import agterm, runs
        project = self._project()
        rec = self._queued_record(project)

        def cancel_during_launch(**kwargs):
            self.set_record(rec["id"], state="cancelled")
            return "SID-1"

        with mock.patch.object(agterm, "new_session", side_effect=cancel_during_launch), \
                mock.patch.object(agterm, "close_session") as close:
            with self.assertRaises(runs.RunError):
                runs._start(rec, project)
        close.assert_called_once_with("SID-1")
        self.assertEqual(self.record(rec["id"])["state"], "cancelled")

    def test_run_cancelled_while_queued_is_not_started_later(self):
        from dwlib import runs
        self.add_project("slotme")
        first = self.run_id(self.run_cmd("slotme", "one"))
        queued = self.run_id(self.run_cmd("slotme", "two"))
        self.assertEqual(self.dw("cancel", queued).returncode, 0)
        self.set_record(first, state="done")
        self.assertEqual(runs.start_eligible(), [])
        self.assertEqual(self.record(queued)["state"], "cancelled")
        self.assertEqual(len(self.new_session_calls()), 1)

    def test_cancel_does_not_overwrite_done(self):
        self.add_project("slotme")
        rid = self.run_id(self.run_cmd("slotme", "go"))
        self.set_record(rid, state="done")
        self.assertEqual(self.dw("cancel", rid).returncode, 2)
        self.assertEqual(self.record(rid)["state"], "done")

    def test_cancel_finishing_underneath_leaves_done(self):
        from dwlib import runs
        self.add_project("slotme")
        rid = self.run_id(self.run_cmd("slotme", "go"))
        from dwlib import agterm

        def finish(_sid):
            self.set_record(rid, state="done")

        with mock.patch.object(agterm, "close_session", side_effect=finish):
            with self.assertRaises(runs.RunError):
                runs.cancel_run(rid)
        self.assertEqual(self.record(rid)["state"], "done")


class LaunchFailureTests(RunTestBase):
    def test_launch_error_marks_run_failed_and_next_queued_run_starts(self):
        for name in ("a", "b", "c"):
            self.add_project(name)
        reg = json.loads((self.dw_home / "registry.json").read_text())
        reg["limits"]["total"] = 1
        (self.dw_home / "registry.json").write_text(json.dumps(reg))
        first = self.run_id(self.run_cmd("a", "go"))
        bad = self.run_id(self.run_cmd("b", "go"))
        good = self.run_id(self.run_cmd("c", "go"))
        self.assertEqual(self.record(bad)["state"], "queued")
        self.fake_agterm_dir.joinpath("fail-next").write_text("session new")
        self.assertEqual(self.dw("cancel", first).returncode, 0)
        failed = self.record(bad)
        self.assertEqual(failed["state"], "failed")
        self.assertIn("scripted failure", failed["reason"])
        self.assertIsInstance(failed["ended_at"], float)
        self.assertEqual(self.record(good)["state"], "running")

    def test_run_with_launch_error_exits_2_with_one_line(self):
        self.add_project("slotme")
        self.fake_agterm_dir.mkdir(parents=True, exist_ok=True)
        (self.fake_agterm_dir / "fail-next").write_text("session new")
        r = self.run_cmd("slotme", "go")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual([x["state"] for x in self.run_records()], ["failed"])

    def test_adapter_timeout_is_unreachable_not_a_traceback(self):
        self.add_project("slotme")
        r = self.run_cmd("slotme", "go", env={
            "FAKE_AGTERM_SLEEP": "5", "DW_AGTERMCTL_TIMEOUT": "1"})
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        self.assertIn("AGTerm", r.stderr)
        rec = self.run_records()[0]
        self.assertEqual((rec["state"], rec["reason"]), ("queued", "AGTerm unavailable"))


class AgtermAdapterTests(RunTestBase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {
            "DW_AGTERMCTL": str(FAKE_AGTERMCTL), "DW_HOME": str(self.dw_home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for var in ("AGT_SOCKET", "AGTERM_SOCKET", "FAKE_AGTERM_DOWN"):
            os.environ.pop(var, None)

    def test_available_true_and_false(self):
        from dwlib import agterm
        self.assertTrue(agterm.available())
        with mock.patch.dict(os.environ, {"FAKE_AGTERM_DOWN": "1"}):
            self.assertFalse(agterm.available())
        with mock.patch.dict(os.environ, {"DW_AGTERMCTL": "/nonexistent/agtermctl"}):
            self.assertFalse(agterm.available())

    def test_functions_raise_unavailable_when_down(self):
        from dwlib import agterm
        with mock.patch.dict(os.environ, {"FAKE_AGTERM_DOWN": "1"}):
            for call in (
                lambda: agterm.new_session("/", "w", "n", "c", "ctx"),
                agterm.session_states,
                lambda: agterm.notify("S", "t", "b"),
                lambda: agterm.ask("S", "t", "m", [("y", "Yes")], 1),
                lambda: agterm.close_session("S"),
                lambda: agterm.session_tail("S", 5),
            ):
                with self.assertRaises(agterm.AgtermUnavailable):
                    call()

    def test_session_states_and_close(self):
        from dwlib import agterm
        sid = agterm.new_session(str(self.tmp), "grp", "my name", "echo hi", "ctx-1")
        states = agterm.session_states()
        self.assertEqual(states[sid]["name"], "my name")
        self.assertIsNone(states[sid]["status"])
        self.assertIsNone(states[sid]["status_changed_at"])
        self.set_session_status(sid, "blocked", changed_at=1234.5)
        states = agterm.session_states()
        self.assertEqual(states[sid]["status"], "blocked")
        self.assertEqual(states[sid]["status_changed_at"], 1234.5)
        agterm.close_session(sid)
        self.assertNotIn(sid, agterm.session_states())

    def test_ask_returns_button_id_or_none_on_timeout(self):
        from dwlib import agterm
        sid = agterm.new_session(str(self.tmp), "grp", "n", "c", "x")
        self.assertIsNone(agterm.ask(sid, "t", "m", [("yes", "Yes"), ("no", "No")], 5))
        self.script_ask("no")
        self.assertEqual(agterm.ask(sid, "t", "m", [("yes", "Yes"), ("no", "No")], 5), "no")
        call = [c for c in self.agterm_calls() if c[0] == "ask"][-1]
        self.assertIn("yes=Yes", call)
        self.assertIn("no=No", call)

    def test_notify_and_session_tail(self):
        from dwlib import agterm
        sid = agterm.new_session(str(self.tmp), "grp", "n", "c", "x")
        agterm.notify(sid, "Title", "Body")
        notify = [c for c in self.agterm_calls() if c[0] == "notify"][0]
        self.assertEqual(notify[1], "Body")
        self.assertEqual(opt(notify, "--title"), "Title")
        self.assertEqual(agterm.session_tail(sid, 3).strip(), "")
        tail = [c for c in self.agterm_calls() if c[:2] == ["session", "text"]][0]
        self.assertEqual(opt(tail, "--lines"), "3")


if __name__ == "__main__":
    unittest.main()
