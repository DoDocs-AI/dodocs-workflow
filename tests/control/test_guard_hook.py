from __future__ import annotations

import json
import time

from helpers import DwTestCase

PENDING_REASON = ("Approval is pending with the owner. Do not work around it. "
                  "Continue other work, then retry this exact action later.")
DENIED_REASON = "Denied by the owner. Do not attempt this action another way."


class GuardHookBase(DwTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user_home = self.tmp / "user-home"
        self.user_home.mkdir()
        self.env["HOME"] = str(self.user_home)
        self.env["DW_GUARD_ASK_TIMEOUT"] = "5"

    def start_run(self, name="slotme"):
        path = self.add_project(name)
        r = self.dw("run", name, "/scrum-team", "build")
        self.assertEqual(r.returncode, 0, r.stderr)
        return path, r.stdout.split()[0]

    def record(self, run_id):
        from dwlib import store
        return store.load_run(run_id)

    def payload(self, cwd, command=None, tool="Bash", tool_input=None):
        return {"session_id": "abc", "cwd": str(cwd), "hook_event_name": "PreToolUse",
                "tool_name": tool, "tool_input": tool_input or {"command": command},
                "tool_use_id": "toolu_1"}

    def guard(self, payload, env=None, raw=None):
        r = self.dw("guard", stdin=raw if raw is not None else json.dumps(payload), env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        if not r.stdout.strip():
            return None
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        return out

    def ask_calls(self):
        return [c for c in self.agterm_calls() if c[0] == "ask"]

    def clear_answer(self):
        path = self.fake_agterm_dir / "ask-answer"
        if path.exists():
            path.unlink()


class GuardHookTests(GuardHookBase):
    def test_no_active_run_allows_silently(self):
        r = self.dw("guard", stdin=json.dumps(self.payload("/tmp", "git push origin main")))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        path = self.add_project("slotme")
        r = self.dw("guard", stdin=json.dumps(self.payload(path, "git push origin main")))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.agterm_calls(), [])

    def test_guard_resolves_project_from_subdir_and_symlink(self):
        path, rid = self.start_run()
        deep = path / "src" / "deep"
        deep.mkdir(parents=True)
        link = self.tmp / "link"
        link.symlink_to(path)
        self.script_ask("deny")
        for cwd in (deep, link):
            with self.subTest(cwd=cwd):
                out = self.guard(self.payload(cwd, "git push origin main"))
                self.assertEqual(out["permissionDecision"], "deny")
                self.assertEqual(out["permissionDecisionReason"], DENIED_REASON)
        self.assertEqual(len(self.ask_calls()), 2)

    def test_unguarded_call_in_active_run_allows_silently(self):
        path, rid = self.start_run()
        before = len(self.agterm_calls())
        self.assertIsNone(self.guard(self.payload(path, "ls -la")))
        self.assertEqual(len(self.agterm_calls()), before)

    def test_approve_once_allows_and_asks_again_next_time(self):
        path, rid = self.start_run()
        self.script_ask("once")
        for _ in range(2):
            out = self.guard(self.payload(path, "git push origin main"))
            self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(len(self.ask_calls()), 2)
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["reason"], rec["pending_approval"]), ("running", None, None))
        self.assertEqual(rec["approvals"], [])

    def test_approve_for_run_is_remembered(self):
        path, rid = self.start_run()
        self.script_ask("run")
        out = self.guard(self.payload(path, "git push origin main"))
        self.assertEqual(out["permissionDecision"], "allow")
        self.clear_answer()
        out = self.guard(self.payload(path, "git push -f origin main"))
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(len(self.ask_calls()), 1)
        rec = self.record(rid)
        self.assertEqual(len(rec["approvals"]), 1)
        self.assertEqual((rec["state"], rec["pending_approval"]), ("running", None))

    def test_deny_returns_owner_denied_reason(self):
        path, rid = self.start_run()
        self.script_ask("deny")
        out = self.guard(self.payload(path, "kubectl apply -f k8s/"))
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(out["permissionDecisionReason"], DENIED_REASON)
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["pending_approval"]), ("running", None))

    def test_no_answer_denies_and_leaves_pending(self):
        path, rid = self.start_run()
        out = self.guard(self.payload(path, "git push origin main"))
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(out["permissionDecisionReason"], PENDING_REASON)
        rec = self.record(rid)
        self.assertEqual(rec["state"], "blocked")
        self.assertTrue(rec["reason"].startswith("awaiting approval"), rec["reason"])
        pending = rec["pending_approval"]
        for key in ("rule", "describe", "tool", "since"):
            self.assertIn(key, pending)
        self.assertEqual(pending["tool"], "Bash")
        self.assertIn(pending["describe"], rec["reason"])
        ask = self.ask_calls()[0]
        self.assertEqual(ask[ask.index("--target") + 1], rec["agterm_session"])
        self.assertEqual([ask[i + 1] for i, a in enumerate(ask) if a == "--button"],
                         ["once=Approve once", "run=Approve for this run", "deny=Deny"])
        self.assertEqual(ask[ask.index("--default") + 1], "deny")

    def test_retry_of_same_pending_action_asks_again(self):
        path, rid = self.start_run()
        self.guard(self.payload(path, "git push origin main"))
        self.script_ask("once")
        out = self.guard(self.payload(path, "git push origin main"))
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(self.record(rid)["pending_approval"], None)

    def test_ask_already_pending_counts_as_no_answer(self):
        path, rid = self.start_run()
        self.script_ask("@already-pending")
        out = self.guard(self.payload(path, "git push origin main"))
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))
        self.assertIsNotNone(self.record(rid)["pending_approval"])

    def test_dw_approve_grants_exactly_one_retry(self):
        path, rid = self.start_run()
        self.guard(self.payload(path, "git push origin main"))
        r = self.dw("approve", rid)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["reason"], rec["pending_approval"]), ("running", None, None))
        self.assertEqual(len(rec["grants"]), 1)
        asks = len(self.ask_calls())
        out = self.guard(self.payload(path, "git push origin main"))
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(len(self.ask_calls()), asks)
        self.assertEqual(self.record(rid)["grants"], [])
        out = self.guard(self.payload(path, "git push origin main"))
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(len(self.ask_calls()), asks + 1)
        self.assertEqual(self.dw("approve", "r-unknown").returncode, 2)

    def test_dw_approve_grant_does_not_cover_a_different_action(self):
        path, rid = self.start_run()
        self.guard(self.payload(path, "git push origin main"))
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        out = self.guard(self.payload(path, "git push origin master"))
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(len(self.record(rid)["grants"]), 1)

    def test_dw_deny_clears_pending(self):
        path, rid = self.start_run()
        self.guard(self.payload(path, "git push origin main"))
        r = self.dw("deny", rid)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["reason"], rec["pending_approval"], rec["grants"]),
                         ("running", None, None, []))
        r = self.dw("deny", rid)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.dw("approve", rid).returncode, 2)

    def test_control_actions_offer_no_run_wide_approval_and_dw_approve_refuses(self):
        path, rid = self.start_run()
        out = self.guard(self.payload(path, "dw approve %s" % rid))
        self.assertEqual(out["permissionDecision"], "deny")
        ask = self.ask_calls()[-1]
        self.assertEqual([ask[i + 1] for i, a in enumerate(ask) if a == "--button"],
                         ["once=Approve once", "deny=Deny"])
        r = self.dw("approve", rid)
        self.assertEqual(r.returncode, 2)
        self.assertIsNotNone(self.record(rid)["pending_approval"])
        # A forged "run" answer is treated as once: nothing is remembered.
        self.assertEqual(self.dw("deny", rid).returncode, 0)
        self.script_ask("run")
        out = self.guard(self.payload(path, "dw approve %s" % rid))
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(self.record(rid)["approvals"], [])

    def test_second_guarded_call_while_one_pending_is_denied_without_second_dialog(self):
        path, rid = self.start_run()
        self.guard(self.payload(path, "git push origin main"))
        asks = len(self.ask_calls())
        self.script_ask("once")
        out = self.guard(self.payload(path, "kubectl apply -f k8s/"))
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))
        self.assertEqual(len(self.ask_calls()), asks)
        self.assertIn("push", self.record(rid)["pending_approval"]["describe"])

    def test_pending_approval_sets_session_blocked_and_notifies(self):
        path, rid = self.start_run()
        sid = self.record(rid)["agterm_session"]
        self.script_ask("once")
        self.guard(self.payload(path, "git push origin main"))
        calls = self.agterm_calls()
        kinds = [c[0] if c[0] != "session" else "session " + c[1] for c in calls]
        status_i = next(i for i, c in enumerate(calls) if c[:3] == ["session", "status", "blocked"])
        notify_i = kinds.index("notify")
        ask_i = kinds.index("ask")
        self.assertLess(status_i, ask_i)
        self.assertLess(notify_i, ask_i)
        self.assertEqual(calls[status_i][calls[status_i].index("--target") + 1], sid)
        notify = calls[notify_i]
        self.assertEqual(notify[notify.index("--target") + 1], sid)
        text = " ".join(notify)
        self.assertIn("slotme", text)
        self.assertIn("git push origin main", text)

    def test_status_and_notify_failures_do_not_skip_the_hold(self):
        path, rid = self.start_run()
        (self.fake_agterm_dir / "fail-next").write_text("session status")
        out = self.guard(self.payload(path, "git push origin main"))
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(len(self.ask_calls()), 1)

    def test_guard_denies_when_agterm_unreachable_in_active_run(self):
        path, rid = self.start_run()
        out = self.guard(self.payload(path, "git push origin main"), env={"FAKE_AGTERM_DOWN": "1"})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertTrue(out["permissionDecisionReason"].startswith("Guard error"), out)
        self.assertIsNotNone(self.record(rid)["pending_approval"])
        self.assertTrue((self.dw_home / "dw.log").read_text().strip())

    def test_guard_fail_open_outside_runs_fail_closed_inside(self):
        path, rid = self.start_run()
        (self.dw_home / "registry.json").write_text("{not json")
        self.assertIsNone(self.guard(self.payload(self.tmp, "git push origin main")))
        out = self.guard(self.payload(path, "git push origin main"))
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertTrue(out["permissionDecisionReason"].startswith("Guard error: "), out)
        self.assertTrue((self.dw_home / "dw.log").read_text().strip())

    def test_malformed_payload_never_prints_a_traceback(self):
        path, rid = self.start_run()
        self.assertIsNone(self.guard(None, raw="not json"))
        out = self.guard(None, raw="not json", env={"DW_RUN_ID": rid})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertTrue(out["permissionDecisionReason"].startswith("Guard error: "))

    def test_guard_latency_outside_runs(self):
        projects = []
        for i in range(50):
            p = self.tmp / "many" / ("p%d" % i)
            p.mkdir(parents=True)
            projects.append({"id": "p%d" % i, "name": "p%d" % i, "path": str(p), "group": "g",
                             "harness": "claude", "notes": "", "guard_rules": []})
        self.dw_home.mkdir(parents=True, exist_ok=True)
        (self.dw_home / "registry.json").write_text(json.dumps(
            {"version": 1, "limits": {"per_project": 1, "total": 3}, "stall_minutes": 30,
             "projects": projects}))
        payload = json.dumps(self.payload(self.tmp / "elsewhere", "git push origin main"))
        start = time.time()
        for _ in range(20):
            r = self.dw("guard", stdin=payload)
            self.assertEqual((r.returncode, r.stdout), (0, ""))
        average = (time.time() - start) / 20
        self.assertLess(average, 0.150, "average %.0f ms" % (average * 1000))


class GuardRunIdTests(GuardHookBase):
    def test_dw_run_id_of_active_run_is_used_outside_the_project(self):
        path, rid = self.start_run()
        out = self.guard(self.payload(self.tmp, "git push origin main"), env={"DW_RUN_ID": rid})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIsNotNone(self.record(rid)["pending_approval"])

    def test_dw_run_id_of_finished_run_falls_back_to_cwd(self):
        path, rid = self.start_run()
        from dwlib import runs
        runs.finish_run(rid, "done", None)
        self.assertIsNone(self.guard(self.payload(self.tmp, "git push origin main"),
                                     env={"DW_RUN_ID": rid}))
        other_path, other = self.start_run("other")
        out = self.guard(self.payload(other_path, "git push origin main"), env={"DW_RUN_ID": rid})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIsNotNone(self.record(other)["pending_approval"])
        self.assertIsNone(self.record(rid)["pending_approval"])

    def test_unknown_dw_run_id_falls_back_to_cwd(self):
        path, rid = self.start_run()
        self.assertIsNone(self.guard(self.payload(self.tmp, "git push origin main"),
                                     env={"DW_RUN_ID": "r-nope"}))
        out = self.guard(self.payload(path, "git push origin main"), env={"DW_RUN_ID": "r-nope"})
        self.assertEqual(out["permissionDecision"], "deny")

    def test_corrupt_dw_run_id_record_fails_closed(self):
        path, rid = self.start_run()
        from dwlib import paths
        paths.run_path(rid).write_text("{broken")
        out = self.guard(self.payload(self.tmp, "git push origin main"), env={"DW_RUN_ID": rid})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertTrue(out["permissionDecisionReason"].startswith("Guard error: "))


class GuardInstalledTests(GuardHookBase):
    def test_run_refuses_without_guard_entry(self):
        path = self.add_project("slotme")
        for content in (None, "", json.dumps({"hooks": {}})):
            settings = self.tmp / "empty-settings.json"
            if settings.exists():
                settings.unlink()
            if content is not None:
                settings.write_text(content)
            with self.subTest(content=content):
                r = self.dw("run", "slotme", "/scrum-team", "x",
                            env={"DW_CLAUDE_SETTINGS": str(settings)})
                self.assertEqual(r.returncode, 2)
                self.assertEqual(len(r.stderr.strip().splitlines()), 1)
                self.assertIn("dw setup", r.stderr)
                runs_dir = self.dw_home / "runs"
                self.assertEqual(list(runs_dir.glob("*.json")) if runs_dir.exists() else [], [])

    def test_resume_refuses_without_guard_entry(self):
        path, rid = self.start_run()
        from dwlib import runs
        runs.finish_run(rid, "interrupted", "x")
        r = self.dw("resume", rid, env={"DW_CLAUDE_SETTINGS": str(self.tmp / "missing.json")})
        self.assertEqual(r.returncode, 2)
        self.assertIn("dw setup", r.stderr)
        self.assertEqual(self.record(rid)["state"], "interrupted")
