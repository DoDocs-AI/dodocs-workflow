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

    def test_blocked_note_is_handled_once(self):
        from dwlib import paths
        self.add_project("alpha")
        rid, sid = self.start("alpha")
        self.note(rid, "BLOCKED\nneed the API key\n")
        self.status_event(sid, "completed")
        self.assertEqual(self.record(rid)["state"], "blocked")
        self.assertFalse(paths.result_note_path(rid).exists())
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
        self.assertFalse(paths.result_note_path(rid).exists())
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
