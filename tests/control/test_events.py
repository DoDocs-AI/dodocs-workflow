from __future__ import annotations

import json
import os
import shlex

from helpers import DwTestCase


class EventBase(DwTestCase):
    def start(self, project, command="/scrum-team x"):
        r = self.dw("run", project, command)
        self.assertEqual(r.returncode, 0, r.stderr)
        rid = r.stdout.split()[0]
        return rid, self.record(rid)["agterm_session"]

    def record(self, rid):
        from dwlib import store
        return store.load_run(rid)

    def set_record(self, rid, **fields):
        from dwlib import store
        store.update_run(rid, lambda r: {**r, **fields})

    def note(self, rid, text):
        from dwlib import paths
        p = paths.result_note_path(rid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def status_event(self, sid, status):
        return self.dw("hook", "status", env={"AGT_SESSION_ID": sid, "AGT_EVENT_STATUS": status})

    def closed_event(self, sid):
        return self.dw("hook", "session-closed", env={"AGT_SESSION_ID": sid})

    def notify_calls(self):
        return [c for c in self.agterm_calls() if c[:1] == ["notify"]]

    def new_session_calls(self):
        return [c for c in self.agterm_calls() if c[:2] == ["session", "new"]]


class StatusEventTests(EventBase):
    def test_completed_without_note_changes_nothing(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        before = self.record(rid)
        r = self.status_event(sid, "completed")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.record(rid), before)
        self.assertEqual(self.notify_calls(), [])

    def test_completed_with_done_note_finishes_and_starts_next_queued(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        rid2, _ = self.start("alpha", "/other")
        self.assertEqual(self.record(rid2)["state"], "queued")
        self.assertEqual(len(self.new_session_calls()), 1)
        self.note(rid, "DONE\nall merged\n")
        r = self.status_event(sid, "completed")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        rec = self.record(rid)
        self.assertEqual(rec["state"], "done")
        self.assertIsNotNone(rec["ended_at"])
        self.assertIsNotNone(rec["state_changed_at"])
        self.assertEqual(self.record(rid2)["state"], "running")
        self.assertEqual(len(self.new_session_calls()), 2)
        self.assertEqual(len(self.notify_calls()), 1)

    def test_completed_with_failed_note_marks_failed_and_notifies(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "FAILED\ntests would not pass\n")
        self.assertEqual(self.status_event(sid, "completed").returncode, 0)
        rec = self.record(rid)
        self.assertEqual(rec["state"], "failed")
        self.assertIn("tests would not pass", rec["reason"])
        notes = self.notify_calls()
        self.assertEqual(len(notes), 1)
        self.assertIn(sid, notes[0])

    def test_completed_with_blocked_note_blocks_and_keeps_run_open(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "BLOCKED\nneed the API key\n")
        self.status_event(sid, "completed")
        rec = self.record(rid)
        self.assertEqual(rec["state"], "blocked")
        self.assertIn("need the API key", rec["reason"])
        self.assertIsNone(rec["ended_at"])
        self.assertEqual(len(self.notify_calls()), 1)
        self.status_event(sid, "completed")  # next turn end: no second notification
        self.assertEqual(len(self.notify_calls()), 1)

    def test_run_pre_creates_an_empty_private_note(self):
        import stat
        from dwlib import paths
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        note = paths.result_note_path(rid)
        info = os.lstat(str(note))
        self.assertTrue(stat.S_ISREG(info.st_mode))
        self.assertEqual((info.st_size, stat.S_IMODE(info.st_mode), info.st_nlink), (0, 0o600, 1))

    def test_an_empty_or_blank_note_counts_as_no_note(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        for text in ("", "  \n\t\n"):
            with self.subTest(text=text):
                self.note(rid, text)
                self.status_event(sid, "completed")
                self.assertEqual(self.record(rid)["state"], "running")
        self.closed_event(sid)
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["reason"]),
                         ("interrupted", "session closed before the work finished"))

    def test_blocked_note_is_handled_once(self):
        from dwlib import paths
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "BLOCKED\nneed the API key\n")
        self.status_event(sid, "completed")
        self.assertEqual(self.record(rid)["state"], "blocked")
        self.assertEqual(paths.result_note_path(rid).read_text(), "")  # an empty note again
        moved = list(paths.runs_dir().glob(rid + ".result.blocked-*.md"))
        self.assertEqual(len(moved), 1)
        self.assertIn("need the API key", moved[0].read_text())
        self.status_event(sid, "active")
        self.assertEqual(self.record(rid)["state"], "running")
        self.status_event(sid, "completed")  # no new note: nothing changes
        self.assertEqual(self.record(rid)["state"], "running")
        self.note(rid, "DONE\nfinished after all\n")
        self.status_event(sid, "completed")
        self.assertEqual(self.record(rid)["state"], "done")
        self.assertTrue(paths.result_note_path(rid).exists())

    def test_blocked_note_at_session_close_is_moved_aside(self):
        from dwlib import paths
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "BLOCKED\nwhy\n")
        self.closed_event(sid)
        self.assertEqual(self.record(rid)["state"], "interrupted")
        self.assertEqual(paths.result_note_path(rid).read_text(), "")  # an empty note again
        self.assertEqual(len(list(paths.runs_dir().glob(rid + ".result.blocked-*.md"))), 1)

    def test_failed_move_is_logged_and_state_change_stands(self):
        from unittest import mock
        from dwlib import events, paths
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "BLOCKED\nwhy\n")
        with mock.patch.dict(os.environ, {"DW_AGTERMCTL": self.env["DW_AGTERMCTL"]}), \
                mock.patch.object(events.os, "rename", side_effect=OSError("disk says no")):
            events.on_status(sid, "completed")  # must not raise
        self.assertEqual(self.record(rid)["state"], "blocked")
        self.assertTrue(paths.result_note_path(rid).exists())  # the move really failed
        log = (self.dw_home / "dw.log").read_text()
        self.assertIn("move note", log)
        self.assertIn("disk says no", log)

    def test_note_without_marker_counts_as_done(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "I did the thing\n")
        self.status_event(sid, "completed")
        self.assertEqual(self.record(rid)["state"], "done")

    def test_empty_note_is_no_note(self):
        from dwlib import events
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "  \n")
        self.assertIsNone(events.read_result_note(rid))
        self.status_event(sid, "completed")
        self.assertEqual(self.record(rid)["state"], "running")

    def test_read_result_note(self):
        from dwlib import events
        self.assertIsNone(events.read_result_note("r-none"))
        self.note("r-a", "BLOCKED\nwhy\nmore")
        self.assertEqual(events.read_result_note("r-a"), ("BLOCKED", "why\nmore"))
        self.note("r-b", "failed\nx")
        self.assertEqual(events.read_result_note("r-b")[0], "FAILED")
        self.note("r-c", "whatever\nx")
        self.assertEqual(events.read_result_note("r-c")[0], "DONE")

    def test_read_result_note_marker_with_text_on_its_line(self):
        from dwlib import events
        for text, expected in (
                ("BLOCKED: need a token\nmore", ("BLOCKED", "need a token\nmore")),
                ("BLOCKED: need a token", ("BLOCKED", "need a token")),
                ("\n\n  blocked:need a token\n", ("BLOCKED", "need a token")),
                ("FAILED - tests red\nlog", ("FAILED", "tests red\nlog")),
                ("# DONE\nmerged", ("DONE", "merged")),
                ("**Blocked.** waiting\n", ("BLOCKED", "waiting")),
                ("All finished\nok", ("DONE", "All finished\nok")),
                ("BLOCKEDX need\n", ("DONE", "BLOCKEDX need"))):
            with self.subTest(text=text):
                self.note("r-m", text)
                self.assertEqual(events.read_result_note("r-m"), expected)

    def test_read_result_note_marker_after_list_quote_or_code_and_before_a_dash(self):
        from dwlib import events
        for text, expected in (
                ("- BLOCKED: x", ("BLOCKED", "x")),
                ("> BLOCKED: x", ("BLOCKED", "x")),
                ("`BLOCKED`: x", ("BLOCKED", "x")),
                ("BLOCKED — need x", ("BLOCKED", "need x")),
                ("BLOCKED – need x\nmore", ("BLOCKED", "need x\nmore")),
                ("BLOCKED  \nwhy", ("BLOCKED", "why")),
                ("BLOCKED\r\nwhy", ("BLOCKED", "why")),
                ("Failed to reproduce, all good", ("DONE", "Failed to reproduce, all good")),
                ("Done with the refactor\nok", ("DONE", "Done with the refactor\nok")),
                ("Blocked waiting\nx", ("DONE", "Blocked waiting\nx"))):
            with self.subTest(text=text):
                self.note("r-m", text)
                self.assertEqual(events.read_result_note("r-m"), expected)

    def test_completed_with_marker_and_text_on_one_line_stays_blocked(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "BLOCKED: x\n")
        self.status_event(sid, "completed")
        rec = self.record(rid)
        self.assertEqual(rec["state"], "blocked")
        self.assertIn("x", rec["reason"])
        self.assertIsNone(rec["ended_at"])

    def test_blocked_then_active_round_trip(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.status_event(sid, "blocked")
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["reason"]), ("blocked", "waiting for input"))
        self.assertIsNotNone(rec["state_changed_at"])
        self.assertEqual(len(self.notify_calls()), 1)
        self.status_event(sid, "active")
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["reason"]), ("running", None))

    def test_blocked_does_not_overwrite_pending_approval_reason(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.set_record(rid, reason="awaiting approval: git push",
                        pending_approval={"action": "git push"})
        self.status_event(sid, "blocked")
        rec = self.record(rid)
        self.assertEqual(rec["state"], "blocked")
        self.assertEqual(rec["reason"], "awaiting approval: git push")
        self.status_event(sid, "active")  # an approval is pending: stay blocked
        self.assertEqual(self.record(rid)["state"], "blocked")

    def test_finished_run_is_never_moved_by_events(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.set_record(rid, state="cancelled", ended_at=1.0)
        self.note(rid, "DONE\nx")
        for st in ("blocked", "active", "completed"):
            self.status_event(sid, st)
        self.closed_event(sid)
        self.assertEqual(self.record(rid)["state"], "cancelled")

    def test_unknown_session_event_is_ignored(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        snapshot = {p.name: p.read_bytes() for p in (self.dw_home / "runs").iterdir()}
        for args in (("status", "completed"), ("status", "blocked")):
            r = self.dw("hook", *args, env={"AGT_SESSION_ID": "NOPE", "AGT_EVENT_STATUS": args[1]})
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        r = self.closed_event("NOPE")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        after = {p.name: p.read_bytes() for p in (self.dw_home / "runs").iterdir()}
        self.assertEqual(after, snapshot)
        self.assertFalse((self.dw_home / "dw.log").exists())


class SessionClosedTests(EventBase):
    def test_session_closed_without_note_marks_interrupted(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        rid2, _ = self.start("alpha", "/other")
        r = self.closed_event(sid)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        rec = self.record(rid)
        self.assertEqual(rec["state"], "interrupted")
        self.assertIsNotNone(rec["ended_at"])
        self.assertIsNotNone(rec["state_changed_at"])
        self.assertEqual(self.record(rid2)["state"], "running")

    def test_session_closed_with_done_note_marks_done(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "DONE\nok")
        self.closed_event(sid)
        self.assertEqual(self.record(rid)["state"], "done")

    def test_session_closed_with_failed_note_marks_failed(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "FAILED\nboom")
        self.closed_event(sid)
        self.assertEqual(self.record(rid)["state"], "failed")

    def test_session_closed_on_blocked_run_without_note_interrupts(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.status_event(sid, "blocked")
        self.closed_event(sid)
        self.assertEqual(self.record(rid)["state"], "interrupted")

    def test_session_closed_after_done_leaves_run_alone(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "DONE\nok")
        self.status_event(sid, "completed")
        ended = self.record(rid)
        self.closed_event(sid)
        self.assertEqual(self.record(rid), ended)


class HookRobustnessTests(EventBase):
    def test_hook_never_fails(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "DONE\nok")
        (self.dw_home / "registry.json").write_text("{not json")
        r = self.status_event(sid, "completed")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.record(rid)["state"], "done")  # the change survived
        log = (self.dw_home / "dw.log").read_text()
        self.assertIn("completed", log)
        self.assertIn("registry.json", log)

    def test_hook_with_corrupt_run_record_logs_and_exits_zero(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        (self.dw_home / "runs" / (rid + ".json")).write_text("{broken")
        r = self.closed_event(sid)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        log = (self.dw_home / "dw.log").read_text()
        self.assertIn(rid + ".json", log)
        self.assertIn(sid, log)

    def test_hook_with_missing_environment_exits_zero_silently(self):
        for args in (("status",), ("session-closed",), ("bogus",), ()):
            r = self.dw("hook", *args)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), args)

    def test_notification_failure_does_not_undo_state_change(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "FAILED\nboom")
        (self.fake_agterm_dir / "fail-next").write_text("notify")
        r = self.status_event(sid, "completed")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.record(rid)["state"], "failed")
        self.assertIn("notify", (self.dw_home / "dw.log").read_text())

    def test_agterm_down_does_not_prevent_state_change(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        rid2, _ = self.start("alpha", "/other")
        self.note(rid, "DONE\nok")
        r = self.dw("hook", "status", env={"AGT_SESSION_ID": sid, "AGT_EVENT_STATUS": "completed",
                                           "FAKE_AGTERM_DOWN": "1"})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.record(rid)["state"], "done")
        self.assertEqual(self.record(rid2)["state"], "queued")  # could not start: AGTerm down


class ResumeTests(EventBase):
    def interrupted(self, project="alpha"):
        rid, sid = self.start(project)
        self.closed_event(sid)
        self.assertEqual(self.record(rid)["state"], "interrupted")
        return rid

    def test_resume_launches_resume_form_and_marks_running(self):
        path = self.add_project("alpha")
        rid, sid = self.start("alpha")
        hs = self.record(rid)["harness_session"]
        self.closed_event(sid)
        r = self.dw("resume", rid)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record(rid)
        self.assertEqual(rec["state"], "running")
        self.assertIsNone(rec["ended_at"])
        self.assertNotEqual(rec["agterm_session"], sid)
        self.assertIsNotNone(rec["state_changed_at"])
        argv = self.new_session_calls()[-1]
        self.assertEqual(argv[argv.index("--cwd") + 1], str(path.resolve()))
        command = argv[argv.index("--command") + 1]
        inner = shlex.split(command)[-1]
        self.assertIn("DW_RUN_ID=%s" % rid, inner)
        self.assertIn("--resume %s" % hs, inner)
        self.assertIn("--permission-mode bypassPermissions", inner)
        self.assertNotIn("--session-id", inner)

    def test_resume_gives_the_conversation_a_first_prompt_through_a_file(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        hs = self.record(rid)["harness_session"]
        self.closed_event(sid)
        self.assertEqual(self.dw("resume", rid).returncode, 0)
        argv = self.new_session_calls()[-1]
        inner = shlex.split(argv[argv.index("--command") + 1])[-1]
        from dwlib import paths
        prompt_file = os.path.abspath(str(paths.resume_prompt_path(rid)))
        self.assertIn("--resume %s \"$(cat %s)\"" % (hs, shlex.quote(prompt_file)), inner)
        self.assertIn("DW_RUN_ID=%s" % rid, inner)
        self.assertIn("--permission-mode bypassPermissions", inner)
        text = open(prompt_file, encoding="utf-8").read()
        note = os.path.abspath(str(paths.result_note_path(rid)))
        self.assertTrue(text.startswith(
            "You were interrupted. Continue the task from where it stopped and finish it.\n\n"), text)
        self.assertIn("write a short result note to %s." % note, text)
        self.assertIn("the file already exists.", text)
        self.assertNotIn("You were interrupted", inner)
        self.assertNotIn("result note", inner)

    def test_resume_sets_aside_a_leftover_note_and_starts_with_an_empty_one(self):
        from dwlib import paths
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.closed_event(sid)
        self.assertEqual(self.record(rid)["state"], "interrupted")
        self.note(rid, "DONE\nwritten after the session closed\n")
        self.assertEqual(self.dw("resume", rid).returncode, 0)
        self.assertEqual(paths.result_note_path(rid).read_text(), "")
        moved = list(paths.runs_dir().glob(rid + ".result.blocked-*.md"))
        self.assertEqual(len(moved), 1)
        self.assertIn("written after the session closed", moved[0].read_text())
        self.status_event(self.record(rid)["agterm_session"], "completed")
        self.assertEqual(self.record(rid)["state"], "running")

    def test_resume_only_for_interrupted(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        for state in ("running", "done", "failed", "cancelled", "blocked", "queued"):
            self.set_record(rid, state=state)
            r = self.dw("resume", rid)
            self.assertEqual(r.returncode, 2, state)
            self.assertIn("interrupted", r.stderr)
            self.assertEqual(self.record(rid)["state"], state)
        r = self.dw("resume", "r-nope")
        self.assertEqual(r.returncode, 2)

    def test_resume_respects_limits(self):
        self.add_project("alpha")
        rid = self.interrupted()
        other, _ = self.start("alpha", "/other")  # takes the only slot of the project
        before = len(self.new_session_calls())
        r = self.dw("resume", rid)
        self.assertEqual(r.returncode, 2)
        self.assertIn("busy", r.stderr)
        self.assertEqual(self.record(rid)["state"], "interrupted")
        self.assertEqual(len(self.new_session_calls()), before)

    def test_resume_respects_total_limit(self):
        for n in ("a", "b", "c", "d"):
            self.add_project(n)
        rid = self.interrupted("a")
        for n in ("b", "c", "d"):
            self.start(n)
        r = self.dw("resume", rid)
        self.assertEqual(r.returncode, 2)
        self.assertIn("limit", r.stderr)
        self.assertEqual(self.record(rid)["state"], "interrupted")

    def test_resume_refuses_untrusted_project(self):
        path = self.add_project("alpha")
        rid = self.interrupted()
        self.claude_state.write_text(json.dumps({"projects": {}}))
        r = self.dw("resume", rid)
        self.assertEqual(r.returncode, 2)
        self.assertIn("trust", r.stderr)

    def test_resume_refuses_when_agterm_down(self):
        self.add_project("alpha")
        rid = self.interrupted()
        r = self.dw("resume", rid, env={"FAKE_AGTERM_DOWN": "1"})
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.record(rid)["state"], "interrupted")

    def test_resume_without_harness_session_refuses(self):
        self.add_project("alpha")
        rid = self.interrupted()
        self.set_record(rid, harness_session=None)
        r = self.dw("resume", rid)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.record(rid)["state"], "interrupted")


class StaleApprovalTests(EventBase):
    def test_interrupt_and_resume_clear_pending_approval_and_grants(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.set_record(rid, state="blocked", reason="awaiting approval: git push",
                        pending_approval={"action": "git push"}, grants=[{"g": 1}],
                        approvals=[{"action": "ls"}])
        self.closed_event(sid)
        rec = self.record(rid)
        self.assertEqual(rec["state"], "interrupted")
        self.assertIsNone(rec["pending_approval"])
        self.assertEqual(rec["grants"], [])
        self.assertEqual(rec["approvals"], [{"action": "ls"}])
        self.set_record(rid, pending_approval={"action": "stale"}, grants=[{"g": 2}])
        self.assertEqual(self.dw("resume", rid).returncode, 0)
        rec = self.record(rid)
        self.assertIsNone(rec["pending_approval"])
        self.assertEqual(rec["grants"], [])
        self.assertEqual(rec["approvals"], [{"action": "ls"}])
        sid2 = rec["agterm_session"]
        self.status_event(sid2, "blocked")
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["reason"]), ("blocked", "waiting for input"))
        self.status_event(sid2, "active")
        self.assertEqual(self.record(rid)["state"], "running")

    def test_cancel_clears_pending_approval(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.set_record(rid, pending_approval={"action": "x"}, grants=[{"g": 1}])
        self.assertEqual(self.dw("cancel", rid).returncode, 0)
        rec = self.record(rid)
        self.assertEqual((rec["pending_approval"], rec["grants"]), (None, []))


class DismissTests(EventBase):
    def test_dismiss_finished_run_sets_acknowledged(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.closed_event(sid)
        r = self.dw("dismiss", rid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.record(rid)["acknowledged"])

    def test_dismiss_refuses_unfinished_and_unknown(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        r = self.dw("dismiss", rid)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("acknowledged", self.record(rid))
        self.assertEqual(self.dw("dismiss", "r-nope").returncode, 2)

    def test_dismissed_run_leaves_needs_owner_but_stays_in_recent(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.closed_event(sid)
        data = json.loads(self.dw("status", "--json").stdout)
        self.assertEqual([v["id"] for v in data["needs_owner"]], [rid])
        self.dw("dismiss", rid)
        data = json.loads(self.dw("status", "--json").stdout)
        self.assertEqual(data["needs_owner"], [])
        self.assertEqual([v["id"] for p in data["projects"] for v in p["recent"]], [rid])


class StateChangedAtTests(EventBase):
    def test_every_transition_records_state_changed_at(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.assertIsNotNone(self.record(rid)["state_changed_at"])
        rid2, _ = self.start("alpha", "/other")  # queued, then cancelled
        self.assertEqual(self.dw("cancel", rid2).returncode, 0)
        self.assertIsNotNone(self.record(rid2)["state_changed_at"])

    def test_since_uses_state_changed_at_and_falls_back(self):
        import time
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        now = time.time()
        self.set_record(rid, state_changed_at=now - 500, started_at=now - 5000)
        data = json.loads(self.dw("status", "--json").stdout)
        view = [v for p in data["projects"] for v in p["active"] if v["id"] == rid][0]
        self.assertAlmostEqual(view["since"], 500, delta=30)
        from dwlib import store
        store.update_run(rid, lambda r: {k: v for k, v in r.items() if k != "state_changed_at"})
        data = json.loads(self.dw("status", "--json").stdout)
        view = [v for p in data["projects"] for v in p["active"] if v["id"] == rid][0]
        self.assertAlmostEqual(view["since"], 5000, delta=30)


class AcknowledgementTests(EventBase):
    def needs_owner(self):
        return [v["id"] for v in json.loads(self.dw("status", "--json").stdout)["needs_owner"]]

    def test_dismissed_run_not_resumed_stays_out(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.closed_event(sid)
        self.dw("dismiss", rid)
        self.assertIn("acknowledged_at", self.record(rid))
        self.assertEqual(self.needs_owner(), [])

    def test_dismiss_resume_interrupt_again_returns_to_needs_owner(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.closed_event(sid)
        self.dw("dismiss", rid)
        self.assertEqual(self.dw("resume", rid).returncode, 0)
        self.assertNotIn("acknowledged", self.record(rid))
        sid2 = self.record(rid)["agterm_session"]
        self.closed_event(sid2)
        self.assertEqual(self.record(rid)["state"], "interrupted")
        self.assertEqual(self.needs_owner(), [rid])

    def test_stale_acknowledgement_is_ignored_by_status(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.closed_event(sid)
        rec = self.record(rid)
        self.set_record(rid, acknowledged=True, acknowledged_at=rec["state_changed_at"] - 10)
        self.assertEqual(self.needs_owner(), [rid])


class DoneSessionCloseTests(EventBase):
    """A run that finishes as done has its session closed (unless switched off); other
    endings keep the session for the owner to look at."""

    def close_calls(self, sid):
        return [c for c in self.agterm_calls() if c[:2] == ["session", "close"]
                and sid in c]

    def finish(self, rid, sid, text):
        self.note(rid, text)
        r = self.status_event(sid, "completed")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def set_registry(self, **fields):
        from dwlib import paths, store
        store.update_json(paths.registry_path(), lambda reg: {**reg, **fields},
                          store.default_registry())

    def test_done_closes_the_session_and_starts_the_next_queued_run_once(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        rid2, _ = self.start("alpha", "/other")
        self.finish(rid, sid, "DONE\nok\n")
        self.assertEqual(self.record(rid)["state"], "done")
        self.assertEqual(len(self.close_calls(sid)), 1)
        self.assertNotIn(sid, self.fake_sessions())
        self.assertEqual(self.record(rid2)["state"], "running")
        self.assertEqual(len(self.new_session_calls()), 2)
        # The close comes after the state change, the notification and the next run's start,
        # so a slow or failing close cannot hold up the queue.
        calls = self.agterm_calls()
        close_at = calls.index(self.close_calls(sid)[0])
        self.assertLess(calls.index(self.notify_calls()[0]), close_at)
        self.assertLess(calls.index(self.new_session_calls()[1]), close_at)
        # The session-closed event that follows the close leaves everything as it is.
        before = self.record(rid)
        self.assertEqual(self.closed_event(sid).returncode, 0)
        self.assertEqual(self.record(rid), before)
        self.assertEqual(len(self.new_session_calls()), 2)

    def test_failed_and_blocked_keep_the_session(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.finish(rid, sid, "BLOCKED: need a key\n")
        self.assertEqual(self.close_calls(sid), [])
        self.finish(rid, sid, "FAILED\nno\n")
        self.assertEqual(self.record(rid)["state"], "failed")
        self.assertEqual(self.close_calls(sid), [])

    def test_the_registry_setting_switches_it_off(self):
        self.add_project("alpha")
        self.set_registry(close_done_sessions=False)
        rid, sid = self.start("alpha")
        self.finish(rid, sid, "DONE\n")
        self.assertEqual(self.close_calls(sid), [])

    def test_keep_open_wins_and_survives_resume(self):
        self.add_project("alpha")
        r = self.dw("run", "--keep-open", "alpha", "/scrum-team", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        rid = r.stdout.split()[0]
        self.assertTrue(self.record(rid)["keep_open"])
        self.set_record(rid, state="interrupted", harness_session="h-1")
        self.assertEqual(self.dw("resume", rid).returncode, 0)
        rec = self.record(rid)
        self.assertTrue(rec["keep_open"])
        self.finish(rid, rec["agterm_session"], "DONE\n")
        self.assertEqual(self.record(rid)["state"], "done")
        self.assertEqual(self.close_calls(rec["agterm_session"]), [])
        r = self.dw("run", "--keep-open", "alpha", "x", env={"DW_RUN_ID": rid})
        self.assertEqual(r.returncode, 2)

    def test_a_failed_close_is_logged_and_the_run_stays_done(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        rid2, _ = self.start("alpha", "/other")
        from dwlib import paths
        sessions = self.fake_sessions()
        del sessions[sid]  # the close fails: unknown session
        (self.fake_agterm_dir / "sessions.json").write_text(json.dumps(sessions))
        self.finish(rid, sid, "DONE\n")
        self.assertEqual(self.record(rid)["state"], "done")
        self.assertIn("close session", (paths.home() / "dw.log").read_text())
        self.assertEqual(self.record(rid2)["state"], "running")

    def test_interrupted_keeps_the_session(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.set_record(rid, state="interrupted")
        self.note(rid, "DONE\n")
        self.assertEqual(self.status_event(sid, "completed").returncode, 0)
        self.assertEqual(self.record(rid)["state"], "interrupted")
        self.assertEqual(self.close_calls(sid), [])

    def test_dismiss_logs_a_failed_close_and_still_acknowledges(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.finish(rid, sid, "FAILED\nbroken\n")
        (self.fake_agterm_dir / "fail-next").write_text("session close")
        r = self.dw("dismiss", rid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "%s dismissed\n" % rid)
        self.assertTrue(self.record(rid)["acknowledged"])
        from dwlib import paths
        self.assertIn("dismiss close session", (paths.home() / "dw.log").read_text())

    def test_dismiss_closes_an_open_session_and_status_marks_it(self):
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.finish(rid, sid, "FAILED\nbroken\n")
        r = self.dw("status")
        self.assertIn("session still open", r.stdout)
        data = json.loads(self.dw("status", "--json").stdout)
        self.assertTrue([v for v in data["needs_owner"] if v["id"] == rid][0]["session_open"])
        r = self.dw("dismiss", rid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("session was closed", r.stdout)
        self.assertEqual(len(self.close_calls(sid)), 1)
        self.assertNotIn("session still open", self.dw("status").stdout)
        r = self.dw("dismiss", rid)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("session was closed", r.stdout)
        self.assertNotIn("session still open", self.dw("status", env={"FAKE_AGTERM_DOWN": "1"}).stdout)
