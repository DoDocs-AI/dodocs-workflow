from __future__ import annotations

import hashlib
import json
import os
import time

from helpers import DwTestCase


class StatusBase(DwTestCase):
    def make_run(self, project, state="running", command="/scrum-team x", **fields):
        from dwlib import store
        rid = fields.pop("id", "r-20260101-%06d-%04x" % (int(time.time() * 1000) % 1000000,
                                                          len(self.made)))
        self.made.append(rid)
        now = time.time()
        record = {
            "id": rid, "project_id": project, "command": command, "state": state, "reason": None,
            "agterm_session": None, "harness_session": None, "created_at": now - 7200,
            "started_at": None, "ended_at": None, "approvals": [], "pending_approval": None,
            "grants": [],
        }
        if state in ("running", "blocked", "done", "failed", "interrupted", "cancelled"):
            record["started_at"] = now - 3600
        if state in ("done", "failed", "interrupted", "cancelled"):
            record["ended_at"] = now - 600
        record.update(fields)
        store.create_run(record)
        return rid

    def setUp(self):
        super().setUp()
        self.made = []

    def live_run(self, project, status="active", changed_at=None, **fields):
        """A running run backed by a session in the fake AGTerm."""
        r = self.dw("run", project, fields.pop("command", "/scrum-team x"))
        self.assertEqual(r.returncode, 0, r.stderr)
        rid = r.stdout.split()[0]
        from dwlib import store
        sid = store.load_run(rid)["agterm_session"]
        self.set_session_status(sid, status, changed_at)
        return rid, sid

    def status_json(self, *args, env=None):
        r = self.dw("status", "--json", *args, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def find_view(self, data, rid):
        for p in data["projects"]:
            for key in ("active", "queued", "recent"):
                for v in p[key]:
                    if v["id"] == rid:
                        return v
        self.fail("run %s not in status" % rid)


class StatusTests(StatusBase):
    def test_blocked_run_listed_under_needs_owner_with_reason(self):
        self.add_project("slotme")
        rid = self.make_run("slotme", "blocked", reason="awaiting approval: git push")
        data = self.status_json()
        self.assertEqual([v["id"] for v in data["needs_owner"]], [rid])
        self.assertEqual(data["needs_owner"][0]["reason"], "awaiting approval: git push")
        text = self.dw("status").stdout
        self.assertLess(text.index("Needs owner:"), text.index(rid))
        self.assertIn("awaiting approval: git push", text)

    def test_failed_and_interrupted_need_owner_done_does_not(self):
        self.add_project("slotme")
        f = self.make_run("slotme", "failed", reason="boom")
        i = self.make_run("slotme", "interrupted")
        d = self.make_run("slotme", "done")
        data = self.status_json()
        self.assertEqual({v["id"] for v in data["needs_owner"]}, {f, i})
        self.assertIn(d, [v["id"] for v in data["projects"][0]["recent"]])

    def test_stalled_flag_after_threshold(self):
        self.add_project("slotme")
        old, _ = self.live_run("slotme", "active", time.time() - 31 * 60)
        data = self.status_json()
        view = self.find_view(data, old)
        self.assertTrue(view["stalled"])
        self.assertEqual(view["live"], "active")
        self.assertIn("STALLED", self.dw("status").stdout)

    def test_not_stalled_before_threshold(self):
        self.add_project("slotme")
        rid, _ = self.live_run("slotme", "active", time.time() - 29 * 60)
        self.assertFalse(self.find_view(self.status_json(), rid)["stalled"])

    def test_idle_session_is_never_stalled(self):
        self.add_project("slotme")
        rid, _ = self.live_run("slotme", "idle", time.time() - 120 * 60)
        view = self.find_view(self.status_json(), rid)
        self.assertFalse(view["stalled"])
        self.assertEqual(view["live"], "idle")

    def test_stall_threshold_comes_from_registry(self):
        self.add_project("slotme")
        rid, _ = self.live_run("slotme", "active", time.time() - 10 * 60)
        reg = json.loads((self.dw_home / "registry.json").read_text())
        reg["stall_minutes"] = 5
        (self.dw_home / "registry.json").write_text(json.dumps(reg))
        self.assertTrue(self.find_view(self.status_json(), rid)["stalled"])

    def test_scrum_progress_extracted(self):
        path = self.add_project("slotme")
        rid, _ = self.live_run("slotme")
        feat = path / "docs" / "features" / "login"
        feat.mkdir(parents=True)
        (feat / "PROGRESS.md").write_text(
            "# Progress\n\n## Current Phase\nPhase 4: Build + Test\n\n"
            "## Phase Status\n| Phase | Status |\n|---|---|\n| 1 | done |\n\n## Notes\nignore me\n")
        view = self.find_view(self.status_json(), rid)
        self.assertIn("Phase 4: Build + Test", view["progress"])
        self.assertIn("| 1 | done |", view["progress"])
        self.assertNotIn("ignore me", view["progress"])

    def test_progress_ignores_files_older_than_run(self):
        path = self.add_project("slotme")
        feat = path / "docs" / "features" / "old"
        feat.mkdir(parents=True)
        f = feat / "PROGRESS.md"
        f.write_text("## Current Phase\nPhase 9: stale\n")
        past = time.time() - 86400
        os.utime(str(f), (past, past))
        rid, _ = self.live_run("slotme")
        self.assertIsNone(self.find_view(self.status_json(), rid)["progress"])

    def test_progress_only_for_scrum_team_commands(self):
        path = self.add_project("slotme")
        rid, _ = self.live_run("slotme", command="/fix-the-issue 12")
        feat = path / "docs" / "features" / "x"
        feat.mkdir(parents=True)
        (feat / "PROGRESS.md").write_text("## Current Phase\nPhase 1\n")
        self.assertIsNone(self.find_view(self.status_json(), rid)["progress"])

    def test_result_note_shown_for_finished_run(self):
        self.add_project("slotme")
        rid = self.make_run("slotme", "done")
        note = "\n".join(["DONE"] + ["line %d" % i for i in range(1, 40)])
        (self.dw_home / "runs" / (rid + ".result.md")).write_text(note)
        view = self.find_view(self.status_json(), rid)
        lines = view["result"].splitlines()
        self.assertEqual(len(lines), 20)
        self.assertEqual(lines[0], "DONE")
        self.assertIn("line 19", view["result"])
        self.assertNotIn("line 20", view["result"])
        self.assertIn("DONE", self.dw("status").stdout)

    def test_recent_keeps_last_five_ended_newest_first(self):
        self.add_project("slotme")
        now = time.time()
        ids = [self.make_run("slotme", "done", ended_at=now - 1000 + i) for i in range(7)]
        recent = self.status_json()["projects"][0]["recent"]
        self.assertEqual([v["id"] for v in recent], list(reversed(ids))[:5])

    def test_queued_listed(self):
        self.add_project("slotme")
        rid = self.make_run("slotme", "queued", reason="project busy")
        text = self.dw("status").stdout
        self.assertLess(text.index("Queued:"), text.index(rid))
        self.assertIn("project busy", text)

    def test_text_section_order(self):
        self.add_project("slotme")
        self.add_project("other")
        running, _ = self.live_run("other")
        done = self.make_run("slotme", "done")
        queued = self.make_run("slotme", "queued", reason="project busy")
        blocked = self.make_run("slotme", "blocked", reason="awaiting approval: x")
        text = self.dw("status").stdout
        pos = [text.index(x) for x in ("Needs owner:", "Running:", "Queued:", "Recently finished:")]
        self.assertEqual(pos, sorted(pos))
        for rid in (done, queued, running, blocked):
            self.assertIn(rid, text)

    def test_status_without_agterm(self):
        self.add_project("slotme")
        rid, _ = self.live_run("slotme")
        r = self.dw("status", env={"FAKE_AGTERM_DOWN": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(rid, r.stdout)
        self.assertEqual(r.stdout.rstrip().splitlines()[-1],
                         "AGTerm not reachable: live state unavailable")
        r = self.dw("status", "--json", env={"FAKE_AGTERM_DOWN": "1"})
        view = self.find_view(json.loads(r.stdout), rid)
        self.assertIsNone(view["live"])
        self.assertFalse(view["stalled"])

    def test_status_reports_corrupt_files(self):
        self.add_project("slotme")
        good = self.make_run("slotme", "done")
        bad = self.dw_home / "runs" / "r-bad.json"
        bad.write_text("{not json")
        r = self.dw("status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(str(bad), r.stdout)
        self.assertIn(good, r.stdout)
        self.assertEqual(self.status_json()["corrupt_files"], [str(bad)])

    def test_project_filter_loose_match(self):
        self.add_project("slotme-app")
        self.add_project("other")
        mine = self.make_run("slotme-app", "done")
        theirs = self.make_run("other", "failed", reason="x")
        r = self.dw("status", "slot")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(mine, r.stdout)
        self.assertNotIn(theirs, r.stdout)
        data = self.status_json("slot")
        self.assertEqual([p["project"] for p in data["projects"]], ["slotme-app"])
        self.assertEqual(data["needs_owner"], [])

    def test_unknown_project_exits_2_with_one_line(self):
        self.add_project("slotme")
        r = self.dw("status", "nope")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "")
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_ambiguous_project_lists_candidates(self):
        self.add_project("slotme-app")
        self.add_project("slotme-api")
        r = self.dw("status", "slotme")
        self.assertEqual(r.returncode, 2)
        self.assertIn("slotme-app", r.stderr)
        self.assertIn("slotme-api", r.stderr)

    def test_running_run_without_session_is_flagged_missing(self):
        self.add_project("slotme")
        rid, sid = self.live_run("slotme")
        self.assertEqual(self.dw("status").returncode, 0)
        sessions = self.fake_sessions()
        del sessions[sid]
        (self.fake_agterm_dir / "sessions.json").write_text(json.dumps(sessions))
        view = self.find_view(self.status_json(), rid)
        self.assertIsNone(view["live"])
        self.assertTrue(view["session_missing"])
        self.assertEqual(view["state"], "running")  # status only reports it
        from dwlib import store
        self.assertEqual(store.load_run(rid)["state"], "running")

    def test_status_does_not_modify_run_records_or_agterm(self):
        self.add_project("slotme")
        rid, sid = self.live_run("slotme")
        self.make_run("slotme", "queued", reason="project busy")
        self.make_run("slotme", "done")

        def snapshot():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((self.dw_home).rglob("*"))
                    if p.is_file() and "fake-agterm" not in p.parts}

        before = snapshot()
        sessions_before = (self.fake_agterm_dir / "sessions.json").read_bytes()
        self.dw("status")
        self.dw("status", "--json")
        self.dw("status", "slotme")
        self.assertEqual(snapshot(), before)
        self.assertEqual((self.fake_agterm_dir / "sessions.json").read_bytes(), sessions_before)
        writes = [c for c in self.agterm_calls()
                  if c[:1] not in (["window"], ["tree"]) and c[:2] != ["session", "new"]
                  and c[:2] not in (["session", "restore"], ["session", "context"])]
        self.assertEqual(writes, [])

    def test_status_does_not_wait_for_start_lock(self):
        from dwlib import paths, store
        self.add_project("slotme")
        self.make_run("slotme", "done")
        with store.file_lock(paths.home() / "start.lock"):
            import subprocess
            import sys
            from helpers import DW
            r = subprocess.run([sys.executable, str(DW), "status"], env=self.env,
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)


class TailTests(StatusBase):
    def test_tail_prints_session_text_and_fails_for_ended_run(self):
        self.add_project("slotme")
        rid, sid = self.live_run("slotme")
        sessions = self.fake_sessions()
        sessions[sid]["text"] = "hello from the session"
        (self.fake_agterm_dir / "sessions.json").write_text(json.dumps(sessions))
        r = self.dw("tail", rid, "--lines", "7")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hello from the session", r.stdout)
        call = [c for c in self.agterm_calls() if c[:2] == ["session", "text"]][-1]
        self.assertEqual(call[call.index("--lines") + 1], "7")
        done = self.make_run("slotme", "done")
        r = self.dw("tail", done)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no live session", r.stderr)

    def test_tail_default_is_40_lines_and_unknown_run_fails(self):
        self.add_project("slotme")
        rid, _ = self.live_run("slotme")
        self.assertEqual(self.dw("tail", rid).returncode, 0)
        call = [c for c in self.agterm_calls() if c[:2] == ["session", "text"]][-1]
        self.assertEqual(call[call.index("--lines") + 1], "40")
        r = self.dw("tail", "r-nope")
        self.assertEqual(r.returncode, 2)


class BlockedNoteStatusTests(StatusBase):
    def test_blocked_run_shows_moved_aside_note(self):
        from dwlib import paths
        self.add_project("alpha")
        rid, sid = self.live_run("alpha")
        self.dw("hook", "status", env={"AGT_SESSION_ID": sid, "AGT_EVENT_STATUS": "blocked"})
        old = paths.runs_dir() / (rid + ".result.blocked-100.md")
        new = paths.runs_dir() / (rid + ".result.blocked-200.md")
        old.write_text("BLOCKED\nold question\n")
        new.write_text("BLOCKED\nneed the API key\n")
        view = self.find_view(self.status_json(), rid)
        self.assertEqual(view["state"], "blocked")
        self.assertIn("need the API key", view["result"])
        self.assertNotIn("old question", view["result"])
        paths.result_note_path(rid).write_text("DONE\ncurrent\n")
        self.assertIn("current", self.find_view(self.status_json(), rid)["result"])
