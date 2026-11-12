from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

from helpers import DW, DwTestCase

PENDING_REASON = ("Approval is pending with the owner. Do not work around it. "
                  "Continue other work, then retry this exact action later.")
DENIED_REASON = "Denied by the owner. Do not attempt this action another way."
INACTIVE_REASON = ("Run %s is %s; guarded actions are refused in this session. "
                   "The owner can do this by hand or start a new run.")


class GuardHookBase(DwTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user_home = self.tmp / "user-home"
        self.user_home.mkdir()
        self.env["HOME"] = str(self.user_home)
        self.env["DW_GUARD_ASK_TIMEOUT"] = "1"
        self.env["DW_GUARD_POLL_INTERVAL"] = "0.05"

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

    def raw_guard(self, payload, env=None):
        r = self.dw("guard", stdin=json.dumps(payload), env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def start_guard(self, payload, env=None):
        run_env = dict(self.env)
        run_env.update(env or {})
        proc = subprocess.Popen([sys.executable, str(DW), "guard"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=run_env)
        proc.stdin.write(json.dumps(payload))
        proc.stdin.close()
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        return proc

    def finish_guard(self, proc, limit=10):
        out = proc.stdout.read()
        proc.wait(timeout=limit)
        proc.stdout.close()
        proc.stderr.close()
        self.assertEqual(proc.returncode, 0)
        return json.loads(out)["hookSpecificOutput"] if out.strip() else None

    def wait_for(self, check, limit=10):
        end = time.time() + limit
        while time.time() < end:
            if check():
                return
            time.sleep(0.05)
        self.fail("condition not reached")

    def ask_calls(self):
        return [c for c in self.agterm_calls() if c[:2] == ["ask", "open"]]

    def cancel_calls(self):
        return [c for c in self.agterm_calls() if c[:2] == ["ask", "cancel"]]

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
            self.assertIsNone(self.guard(self.payload(path, "git push origin main")))
        self.assertEqual(len(self.ask_calls()), 2)
        rec = self.record(rid)
        self.assertEqual((rec["state"], rec["reason"], rec["pending_approval"]), ("running", None, None))
        self.assertEqual(rec["approvals"], [])

    def test_approve_for_run_is_remembered(self):
        path, rid = self.start_run()
        self.script_ask("run")
        self.assertIsNone(self.guard(self.payload(path, "git push origin main")))
        self.clear_answer()
        self.assertIsNone(self.guard(self.payload(path, "git push -f origin main")))
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
        self.assertIsNone(self.guard(self.payload(path, "git push origin main")))
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
        self.assertIsNone(self.guard(self.payload(path, "git push origin main")))
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
        self.assertIsNone(self.guard(self.payload(path, "dw approve %s" % rid)))
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

    def test_held_command_with_newline_and_tab_still_opens_a_dialog(self):
        path, rid = self.start_run()
        self.script_ask("once")
        command = "echo 'st\x1b[0mart'\n\tgit push origin main"
        self.assertIsNone(self.guard(self.payload(path, command)))
        asks = json.loads((self.fake_agterm_dir / "asks.json").read_text())
        self.assertEqual([a["state"] for a in asks.values()], ["answered"])
        ask = self.ask_calls()[0]
        notify = [c for c in self.agterm_calls() if c[0] == "notify"][0]
        for text in ask + notify:
            self.assertFalse(any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in text), text)
        message = ask[ask.index("--message") + 1]
        self.assertEqual(message, "push to the default branch: git push origin main"
                                  " \u2014 Bash: echo 'st?[0mart'\u23ce\u2423git push origin main")
        self.assertEqual(self.record(rid)["pending_approval"], None)

    def question(self):
        ask = self.ask_calls()[-1]
        return ask[ask.index("--message") + 1]

    def test_long_multiline_command_keeps_the_match_whole_and_marks_the_cut(self):
        path, rid = self.start_run()
        lines = ["git push origin main"]
        while len("\n".join(lines)) < 3000:
            lines.append("echo line %04d of a long script that keeps going" % len(lines))
        command = "\n".join(lines)[:3000]
        self.assertEqual(len(command), 3000)
        self.held_pending(path, command)
        message = self.question()
        describe = "push to the default branch: git push origin main"
        self.assertLessEqual(len(message), 240)
        self.assertTrue(message.startswith(describe + " \u2014 Bash: git push origin main\u23ce"),
                        message)
        self.assertIn("\u23ce", message)
        cut = re.search(r"\u2026 \(\+(\d+) chars; full command in dw\.log\)$", message)
        self.assertIsNotNone(cut, message)
        shown = message[len(describe + " \u2014 Bash: "):cut.start()]
        self.assertEqual(len(shown) + int(cut.group(1)), 3000)
        log = (self.dw_home / "dw.log").read_text()
        self.assertIn(rid, log)
        self.assertIn(json.dumps(command), log)

    def test_short_single_line_command_is_shown_whole(self):
        path, rid = self.start_run()
        self.held_pending(path, "git push origin main")
        self.assertEqual(self.question(), "push to the default branch: git push origin main"
                                          " \u2014 Bash: git push origin main")

    def test_a_describe_over_the_limit_is_cut_with_a_marker(self):
        from dwlib import guard
        message = guard._question_message("d" * 300, "Bash", "git push origin main")
        self.assertEqual(len(message), 240)
        self.assertTrue(message.startswith("d" * 200))
        self.assertTrue(message.endswith("\u2026"))

    def held_pending(self, path, command):
        out = self.guard(self.payload(path, command))
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))

    def test_format_characters_never_reach_the_dialog_or_notification(self):
        import unicodedata
        path, rid = self.start_run("slo\u202etme")
        self.script_ask("once")
        command = "echo '\u202eevil\u2066x\u2069\u200b' && git push origin main"
        self.assertIsNone(self.guard(self.payload(path, command)))
        ask = self.ask_calls()[0]
        notify = [c for c in self.agterm_calls() if c[0] == "notify"][0]
        for text in ask + notify:
            self.assertFalse([c for c in text if unicodedata.category(c) in ("Cf", "Zl", "Zp")],
                             ascii(text))

    def test_ask_open_failure_text_is_not_relayed_to_the_agent(self):
        path, rid = self.start_run()
        self.fake_agterm_dir.mkdir(parents=True, exist_ok=True)
        (self.fake_agterm_dir / "fail-next").write_text("ask open")
        out = self.guard(self.payload(path, "git push origin main"))
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))
        self.assertIn("scripted failure", (self.dw_home / "dw.log").read_text())
        self.assertIsNotNone(self.record(rid)["pending_approval"])

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

    def test_approved_paths_print_nothing(self):
        path, rid = self.start_run()
        self.script_ask("once")
        self.assertEqual(self.raw_guard(self.payload(path, "git push origin main")).stdout, "")
        self.script_ask("run")
        self.assertEqual(self.raw_guard(self.payload(path, "kubectl apply -f k8s/")).stdout, "")
        self.clear_answer()
        self.assertEqual(self.raw_guard(self.payload(path, "kubectl apply -f other/")).stdout, "")
        self.raw_guard(self.payload(path, "docker push a/b:1"))
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        self.assertEqual(self.raw_guard(self.payload(path, "docker push a/b:1")).stdout, "")

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
        out = self.guard(self.payload(self.tmp, "git push origin main"), env={"DW_RUN_ID": rid})
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", INACTIVE_REASON % (rid, "done")))
        other_path, other = self.start_run("other")
        out = self.guard(self.payload(other_path, "git push origin main"), env={"DW_RUN_ID": rid})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIsNotNone(self.record(other)["pending_approval"])
        self.assertIsNone(self.record(rid)["pending_approval"])

    def test_unknown_dw_run_id_falls_back_to_cwd(self):
        path, rid = self.start_run()
        out = self.guard(self.payload(self.tmp, "git push origin main"), env={"DW_RUN_ID": "r-nope"})
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", INACTIVE_REASON % ("r-nope", "unknown")))
        out = self.guard(self.payload(path, "git push origin main"), env={"DW_RUN_ID": "r-nope"})
        self.assertEqual(out["permissionDecision"], "deny")

    def test_corrupt_dw_run_id_record_fails_closed(self):
        path, rid = self.start_run()
        from dwlib import paths
        paths.run_path(rid).write_text("{broken")
        out = self.guard(self.payload(self.tmp, "git push origin main"), env={"DW_RUN_ID": rid})
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertTrue(out["permissionDecisionReason"].startswith("Guard error: "))


    def set_state(self, rid, state):
        from dwlib import store
        store.update_run(rid, lambda r: {**r, "state": state})
        return self.record(rid)

    def test_inactive_dw_run_id_refuses_guarded_calls_without_asking(self):
        from dwlib import paths
        for state in ("queued", "done", "failed", "interrupted", "cancelled"):
            with self.subTest(state=state):
                path, rid = self.start_run("p-" + state)
                before = self.set_state(rid, state)
                asks = len(self.ask_calls())
                env = {"DW_RUN_ID": rid}
                out = self.guard(self.payload(path, "git push origin main"), env=env)
                self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                                 ("deny", INACTIVE_REASON % (rid, state)))
                out = self.guard(self.payload(path, "dw run p x"), env=env)
                self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                                 ("deny", INACTIVE_REASON % (rid, state)))
                self.assertIsNone(self.guard(self.payload(path, "ls"), env=env))
                note = str(paths.result_note_path(rid))
                self.assertIsNone(self.guard(self.payload(
                    path, tool="Write", tool_input={"file_path": note, "content": "DONE"}), env=env))
                self.assertEqual(len(self.ask_calls()), asks)
                self.assertEqual(self.record(rid), before)

    def test_inactive_dw_run_id_leaves_the_hold_to_another_active_run_here(self):
        path, first = self.start_run()
        from dwlib import runs
        runs.finish_run(first, "done", None)
        r = self.dw("run", "slotme", "/scrum-team", "again")
        self.assertEqual(r.returncode, 0, r.stderr)
        second = r.stdout.split()[0]
        done_before = self.record(first)
        out = self.guard(self.payload(path, "git push origin main"), env={"DW_RUN_ID": first})
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))
        self.assertEqual(len(self.ask_calls()), 1)
        self.assertIsNotNone(self.record(second)["pending_approval"])
        self.assertEqual(self.record(first), done_before)

    def corruptions(self):
        """name -> a file the guard reads; `with_corrupt` breaks it for one check."""
        from dwlib import paths
        return {"rules": paths.home() / "guard-rules.default.json",
                "registry": paths.home() / "registry.json",
                "sibling run": paths.runs_dir() / "r-sibling.json"}

    def with_corrupt(self, path, check):
        saved = path.read_bytes() if path.exists() else None
        path.write_text("{broken")
        try:
            check()
        finally:
            if saved is None:
                path.unlink()
            else:
                path.write_bytes(saved)

    def test_guard_error_with_any_dw_run_id_fails_closed(self):
        path, rid = self.start_run()
        from dwlib import runs
        runs.finish_run(rid, "done", None)
        for run_id in (rid, "r-nope"):
            for name, corrupt in self.corruptions().items():
                for cwd in (path, self.tmp):
                    if name == "sibling run" and cwd != path:
                        continue  # a sibling record is read only for a cwd inside a project
                    with self.subTest(run_id=run_id, corrupt=name, cwd=str(cwd)):
                        def check():
                            out = self.guard(self.payload(cwd, "git push origin main"),
                                             env={"DW_RUN_ID": run_id})
                            self.assertIsNotNone(out)
                            self.assertEqual(out["permissionDecision"], "deny")
                            self.assertTrue(out["permissionDecisionReason"].startswith("Guard error: "),
                                            out)
                        self.with_corrupt(corrupt, check)

    def test_guard_error_without_dw_run_id_outside_projects_stays_silent(self):
        path, rid = self.start_run()
        from dwlib import runs
        runs.finish_run(rid, "done", None)
        for name, corrupt in self.corruptions().items():
            with self.subTest(corrupt=name):
                self.with_corrupt(corrupt, lambda: self.assertEqual(
                    self.raw_guard(self.payload(self.tmp, "git push origin main")).stdout, ""))

    def test_hold_denies_when_the_run_ended_before_the_claim(self):
        path, rid = self.start_run()
        from dwlib import guard, runs
        runs.finish_run(rid, "interrupted", "x")
        before = self.record(rid)
        project = {"id": "slotme", "name": "slotme", "path": str(path), "guard_rules": []}
        match = {"id": "git-push", "category": "publish", "describe": "git push"}
        out = guard._hold(project, {"id": rid}, match, "Bash", {"command": "git push origin main"})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecisionReason"],
                         INACTIVE_REASON % (rid, "interrupted"))
        self.assertEqual(self.ask_calls(), [])
        self.assertEqual(self.record(rid), before)


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


    def guard_entry(self, program):
        settings = self.tmp / "entry-settings.json"
        settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "'%s' guard" % program, "timeout": 900}]}]}}))
        return {"DW_CLAUDE_SETTINGS": str(settings)}

    def broken_entries(self):
        return {"missing": self.tmp / "gone" / "old" / "bin" / "dw",
                "exits 1": self.write_dw_script(self.tmp / "exits1", "exit 1"),
                "prints": self.write_dw_script(self.tmp / "prints", "cat >/dev/null; echo '{}'")}

    def test_run_refuses_a_guard_entry_that_does_not_run(self):
        path = self.add_project("slotme")
        for name, program in self.broken_entries().items():
            with self.subTest(entry=name):
                r = self.dw("run", "slotme", "/scrum-team", "x", env=self.guard_entry(program))
                self.assertEqual(r.returncode, 2)
                self.assertEqual(len(r.stderr.strip().splitlines()), 1)
                self.assertIn("dw setup", r.stderr)
                runs_dir = self.dw_home / "runs"
                self.assertEqual(list(runs_dir.glob("*.json")) if runs_dir.exists() else [], [])
        self.assertEqual([c for c in self.agterm_calls() if c[:2] == ["session", "new"]], [])

    def test_resume_refuses_a_guard_entry_that_does_not_run(self):
        path, rid = self.start_run()
        from dwlib import runs
        runs.finish_run(rid, "interrupted", "x")
        before = self.record(rid)
        for name, program in self.broken_entries().items():
            with self.subTest(entry=name):
                r = self.dw("resume", rid, env=self.guard_entry(program))
                self.assertEqual(r.returncode, 2)
                self.assertEqual(len(r.stderr.strip().splitlines()), 1)
                self.assertIn("dw setup", r.stderr)
                self.assertEqual(self.record(rid), before)

    def narrow_entry(self, matcher):
        settings = self.tmp / "narrow-settings.json"
        settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": matcher, "hooks": [
            {"type": "command", "command": "'%s' guard" % self.dw_wrapper, "timeout": 900}]}]}}))
        return {"DW_CLAUDE_SETTINGS": str(settings)}

    def test_run_and_resume_refuse_a_guard_entry_that_does_not_cover_all_tools(self):
        path, rid = self.start_run()
        from dwlib import runs
        runs.finish_run(rid, "interrupted", "x")
        before = self.record(rid)
        self.add_project("other")
        for matcher in ("Read", "Bash"):
            with self.subTest(matcher=matcher):
                env = self.narrow_entry(matcher)
                for args in (("run", "other", "/scrum-team", "x"), ("resume", rid)):
                    r = self.dw(*args, env=env)
                    self.assertEqual(r.returncode, 2, r.stdout)
                    self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
                    self.assertIn("does not cover all tools", r.stderr)
                    self.assertIn("dw setup", r.stderr)
                self.assertEqual(self.record(rid), before)
                self.assertEqual(len(list((self.dw_home / "runs").glob("r-*.json"))), 1)

    def test_preflight_runs_the_entry_with_a_harmless_payload_and_no_run_id(self):
        self.add_project("slotme")
        seen = self.tmp / "seen"
        seen.mkdir()
        probe = self.write_dw_script(self.tmp / "probe", 'cat > %s/stdin; env > %s/env; echo "$1" > %s/argv'
                                     % (seen, seen, seen))
        env = self.guard_entry(probe)
        env["DW_RUN_ID"] = "r-outer"
        r = self.dw("run", "slotme", "/scrum-team", "x", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads((seen / "stdin").read_text())
        self.assertEqual((payload["hook_event_name"], payload["tool_name"]), ("PreToolUse", "Read"))
        self.assertTrue(payload["tool_input"]["file_path"].startswith(payload["cwd"]))
        self.assertNotIn(str(self.tmp / "checkouts"), payload["cwd"])
        self.assertNotIn("DW_RUN_ID=", (seen / "env").read_text())
        self.assertEqual((seen / "argv").read_text(), "guard\n")


class GuardEntryPointTests(GuardHookBase):
    """`dw guard` fails closed inside a run even when the library cannot be used at all."""

    def broken_copy(self):
        import shutil
        from helpers import REPO_ROOT
        dest = self.tmp / "broken-install"
        shutil.copytree(str(REPO_ROOT / "control"), str(dest),
                        ignore=shutil.ignore_patterns("__pycache__"))
        (dest / "dwlib" / "status.py").write_text("this is not python (\n")
        return dest / "dw"

    def run_copy(self, dw, *args, env=None, stdin=""):
        run_env = dict(self.env)
        run_env.update(env or {})
        return subprocess.run([sys.executable, str(dw), *args], input=stdin, env=run_env,
                              capture_output=True, text=True)

    def test_import_failure_denies_inside_a_run(self):
        dw = self.broken_copy()
        r = self.run_copy(dw, "guard", env={"DW_RUN_ID": "r-x"},
                          stdin=json.dumps(self.payload(self.tmp, "ls")))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertTrue(out["permissionDecisionReason"].startswith("Guard error: "))
        self.assertEqual(len(r.stdout.strip().splitlines()), 1)

    def test_import_failure_outside_a_run_prints_no_decision(self):
        dw = self.broken_copy()
        r = self.run_copy(dw, "guard", stdin=json.dumps(self.payload(self.tmp, "ls")))
        self.assertNotIn("permissionDecision", r.stdout)

    def test_import_failure_in_dw_hook_exits_zero_silently(self):
        dw = self.broken_copy()
        r = self.run_copy(dw, "hook", "status", env={"AGT_SESSION_ID": "s", "AGT_EVENT_STATUS": "active"})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def load_dw_module(self):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader("dw_entry_under_test", str(DW))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    def last_net(self, run_id):
        import io
        import os
        from unittest import mock
        module = self.load_dw_module()
        if run_id:
            os.environ["DW_RUN_ID"] = run_id
        out = io.StringIO()
        with mock.patch.object(module.guard, "run_hook", side_effect=RuntimeError("boom")), \
                mock.patch.object(module.sys, "stdin", io.StringIO("{}")), \
                mock.patch.object(module.sys, "stdout", out):
            self.assertEqual(module.run_guard(), 0)
        return out.getvalue()

    def test_last_net_denies_inside_a_run(self):
        out = json.loads(self.last_net("r-x"))["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(out["permissionDecisionReason"], "Guard error: boom")

    def test_last_net_outside_a_run_prints_nothing(self):
        self.assertEqual(self.last_net(None), "")


class GuardWaitTests(GuardHookBase):
    """The question is opened without blocking and polled together with the run record."""

    def setUp(self) -> None:
        super().setUp()
        self.path, self.rid = self.start_run()
        self.push = self.payload(self.path, "git push origin main")

    def opened(self):
        return bool(self.ask_calls())

    def test_answer_after_some_polls_is_used(self):
        self.script_ask("once@3")
        self.assertIsNone(self.guard(self.push, env={"DW_GUARD_ASK_TIMEOUT": "20"}))
        results = [c for c in self.agterm_calls() if c[:2] == ["ask", "result"]]
        self.assertGreaterEqual(len(results), 3)
        self.assertIn("--no-block", self.ask_calls()[0])
        self.assertEqual(self.cancel_calls(), [])

    def test_timeout_cancels_the_dialog_and_leaves_pending(self):
        out = self.guard(self.push)
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))
        self.assertEqual(len(self.cancel_calls()), 1)
        self.assertIsNotNone(self.record(self.rid)["pending_approval"])
        self.assertEqual(self.fake_open_asks(), [])

    def test_owner_escape_denies_as_no_answer(self):
        self.script_ask("@cancelled")
        out = self.guard(self.push, env={"DW_GUARD_ASK_TIMEOUT": "20"})
        self.assertEqual(out["permissionDecisionReason"], PENDING_REASON)
        self.assertIsNotNone(self.record(self.rid)["pending_approval"])

    def test_dw_approve_while_waiting_lets_the_action_through_at_once(self):
        start = time.time()
        proc = self.start_guard(self.push, env={"DW_GUARD_ASK_TIMEOUT": "30"})
        self.wait_for(self.opened)
        self.assertEqual(self.dw("approve", self.rid).returncode, 0)
        self.assertIsNone(self.finish_guard(proc))
        self.assertLess(time.time() - start, 15)
        self.assertEqual(len(self.cancel_calls()), 1)
        self.assertEqual(self.fake_open_asks(), [])
        rec = self.record(self.rid)
        self.assertEqual((rec["grants"], rec["pending_approval"], rec["state"]), ([], None, "running"))

    def test_dw_deny_while_waiting_denies_at_once(self):
        proc = self.start_guard(self.push, env={"DW_GUARD_ASK_TIMEOUT": "30"})
        self.wait_for(self.opened)
        self.assertEqual(self.dw("deny", self.rid).returncode, 0)
        out = self.finish_guard(proc)
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", DENIED_REASON))
        self.assertEqual(len(self.cancel_calls()), 1)

    def test_run_finished_while_waiting_denies(self):
        proc = self.start_guard(self.push, env={"DW_GUARD_ASK_TIMEOUT": "30"})
        self.wait_for(self.opened)
        from dwlib import runs
        runs.finish_run(self.rid, "interrupted", "x")
        out = self.finish_guard(proc)
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(len(self.cancel_calls()), 1)
        self.assertEqual(self.record(self.rid)["state"], "interrupted")

    def test_rule_approved_for_run_while_waiting_lets_it_through(self):
        proc = self.start_guard(self.push, env={"DW_GUARD_ASK_TIMEOUT": "30"})
        self.wait_for(self.opened)
        from dwlib import store
        rule = self.record(self.rid)["pending_approval"]["rule"]
        store.update_run(self.rid, lambda r: {**r, "approvals": [rule]})
        self.assertIsNone(self.finish_guard(proc))
        rec = self.record(self.rid)
        self.assertEqual((rec["pending_approval"], rec["state"]), (None, "running"))
        self.assertEqual(len(self.cancel_calls()), 1)

    def test_ask_already_pending_polls_only_the_record(self):
        self.script_ask("@already-pending")
        proc = self.start_guard(self.push, env={"DW_GUARD_ASK_TIMEOUT": "30"})
        self.wait_for(self.opened)
        self.assertEqual(self.dw("approve", self.rid).returncode, 0)
        self.assertIsNone(self.finish_guard(proc))
        self.assertEqual([c for c in self.agterm_calls() if c[:2] == ["ask", "result"]], [])
        self.assertEqual(self.cancel_calls(), [])


class GuardDeadlineAndSiblingTests(GuardHookBase):
    def test_whole_hook_fits_the_limit_when_every_agterm_call_is_slow(self):
        path, rid = self.start_run()
        start = time.time()
        out = self.guard(self.payload(path, "git push origin main"),
                         env={"FAKE_AGTERM_DELAY": "1", "DW_GUARD_ASK_TIMEOUT": "2",
                              "DW_GUARD_HOOK_LIMIT": "3"})
        elapsed = time.time() - start
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertLess(elapsed, 3 + 1.5, "hook took %.1fs" % elapsed)

    def test_sibling_waiting_on_the_same_pending_gets_pending_reason_after_once(self):
        path, rid = self.start_run()
        push = self.payload(path, "git push origin main")
        first = self.start_guard(push, env={"DW_GUARD_ASK_TIMEOUT": "30"})
        self.wait_for(lambda: len(self.ask_calls()) >= 1)
        second = self.start_guard(push, env={"DW_GUARD_ASK_TIMEOUT": "30"})
        self.wait_for(lambda: len(self.ask_calls()) >= 2)
        self.script_ask("once")
        self.assertIsNone(self.finish_guard(first))
        out = self.finish_guard(second)
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))

    def test_sibling_gets_denied_reason_after_dw_deny(self):
        path, rid = self.start_run()
        push = self.payload(path, "git push origin main")
        first = self.start_guard(push, env={"DW_GUARD_ASK_TIMEOUT": "30"})
        self.wait_for(lambda: len(self.ask_calls()) >= 1)
        self.assertEqual(self.dw("deny", rid).returncode, 0)
        out = self.finish_guard(first)
        self.assertEqual(out["permissionDecisionReason"], DENIED_REASON)


class GuardApprovalIdentityTests(GuardHookBase):
    """An approval is about the guarded segment (rule id and its describe text), not about the
    whole command line around it."""

    COMPOUND = "echo x >> README.md && git commit -qm m && git push origin main"
    PLAIN = "git push origin main"

    def held(self, path, command):
        out = self.guard(self.payload(path, command))
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))

    def test_a_dw_approve_of_a_compound_command_lets_the_plain_retry_through_once(self):
        path, rid = self.start_run()
        self.held(path, self.COMPOUND)
        self.assertIn("git push origin main", self.record(rid)["pending_approval"]["describe"])
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        asks = len(self.ask_calls())
        self.assertIsNone(self.guard(self.payload(path, self.PLAIN)))
        rec = self.record(rid)
        self.assertEqual((rec["grants"], rec["pending_approval"], rec["state"]), ([], None, "running"))
        self.assertEqual(len(self.ask_calls()), asks)
        self.held(path, self.PLAIN)
        self.assertEqual(len(self.ask_calls()), asks + 1)
        self.assertIsNotNone(self.record(rid)["pending_approval"])

    def test_b_a_different_rule_while_push_is_pending_is_denied_without_a_dialog(self):
        path, rid = self.start_run()
        self.held(path, self.COMPOUND)
        asks = len(self.ask_calls())
        self.script_ask("once")
        self.held(path, "gh pr merge 3")
        self.assertEqual(len(self.ask_calls()), asks)
        self.assertIn("push", self.record(rid)["pending_approval"]["describe"])

    def test_c_the_plain_form_while_the_compound_waits_is_a_sibling_not_a_second_question(self):
        path, rid = self.start_run()
        first = self.start_guard(self.payload(path, self.COMPOUND), env={"DW_GUARD_ASK_TIMEOUT": "30"})
        self.wait_for(lambda: len(self.ask_calls()) >= 1)
        pending = self.record(rid)["pending_approval"]
        second = self.start_guard(self.payload(path, self.PLAIN), env={"DW_GUARD_ASK_TIMEOUT": "30"})
        # The sibling claims the same pending action and tries to ask (AGTerm refuses a second
        # question on the session); a different action would be refused before any ask.
        self.wait_for(lambda: len(self.ask_calls()) >= 2)
        asks = json.loads((self.fake_agterm_dir / "asks.json").read_text())
        self.assertEqual(len(asks), 1)
        self.assertEqual(self.record(rid)["pending_approval"], pending)
        self.script_ask("once")
        self.assertIsNone(self.finish_guard(first))
        out = self.finish_guard(second)
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))
        self.assertEqual(len(json.loads((self.fake_agterm_dir / "asks.json").read_text())), 1)

    def test_d_a_dw_approve_of_the_plain_command_lets_the_compound_retry_through(self):
        path, rid = self.start_run()
        self.held(path, self.PLAIN)
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        asks = len(self.ask_calls())
        self.assertIsNone(self.guard(self.payload(path, self.COMPOUND)))
        self.assertEqual(self.record(rid)["grants"], [])
        self.assertEqual(len(self.ask_calls()), asks)

    def test_a_grant_does_not_cover_a_command_with_another_guarded_segment(self):
        path, rid = self.start_run()
        self.held(path, self.PLAIN)
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        self.held(path, "git push origin main && git push origin master")
        self.assertEqual(len(self.record(rid)["grants"]), 1)
        pending = self.record(rid)["pending_approval"]
        self.assertIn("git push origin master", pending["describe"])
        ask = self.ask_calls()[-1]
        message = ask[ask.index("--message") + 1]
        self.assertIn("git push origin main", message)
        self.assertIn("git push origin master", message)

    def test_the_same_set_of_segments_in_another_order_is_the_same_action(self):
        path, rid = self.start_run()
        self.held(path, "git push origin main && gh pr merge 3")
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        self.assertIsNone(self.guard(self.payload(path, "gh pr merge 3; git push origin main")))
        self.assertEqual(self.record(rid)["grants"], [])

    def test_an_mcp_grant_covers_only_the_same_arguments(self):
        path, rid = self.start_run()
        mcp = "mcp__claude_ai_Gmail__send_message"
        out = self.guard(self.payload(path, tool=mcp, tool_input={"to": "a@example.com"}))
        self.assertEqual(out["permissionDecisionReason"], PENDING_REASON)
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        out = self.guard(self.payload(path, tool=mcp, tool_input={"to": "b@example.com"}))
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(len(self.record(rid)["grants"]), 1)


class GuardApprovalSegmentTests(GuardHookBase):
    """The identity of an approval uses the full matched segment (Bash) or the whole tool
    input (other tools), never the display text."""

    def held(self, path, command=None, **kw):
        out = self.guard(self.payload(path, command, **kw))
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))

    def test_e_an_approved_push_does_not_cover_a_forced_push(self):
        path, rid = self.start_run()
        self.held(path, "git push origin main")
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        asks = len(self.ask_calls())
        self.held(path, "git push origin main --force")
        self.assertEqual(len(self.ask_calls()), asks + 1)
        self.assertEqual(len(self.record(rid)["grants"]), 1)

    def test_f_one_unreadable_command_is_not_another(self):
        path, rid = self.start_run()
        self.held(path, "$X one")
        asks = len(self.ask_calls())
        self.held(path, "$X two")  # a different action while one is pending: no dialog
        self.assertEqual(len(self.ask_calls()), asks)
        self.assertEqual(self.record(rid)["pending_approval"]["describe"], "command cannot be read")
        self.script_ask("once")
        self.assertIsNone(self.guard(self.payload(path, "$X one")))  # the same action: asked
        self.assertEqual(len(self.ask_calls()), asks + 1)
        self.clear_answer()
        self.held(path, "$X two")
        self.assertEqual(len(self.ask_calls()), asks + 2)

    def test_g_a_write_of_other_content_to_the_same_protected_file_is_another_action(self):
        path, rid = self.start_run()
        target = str(path / ".git" / "hooks" / "pre-push")

        def write(content):
            return self.payload(path, tool="Write", tool_input={"file_path": target, "content": content})

        self.held(path, tool="Write", tool_input={"file_path": target, "content": "A"})
        asks = len(self.ask_calls())
        out = self.guard(write("B"))
        self.assertEqual(out["permissionDecisionReason"], PENDING_REASON)
        self.assertEqual(len(self.ask_calls()), asks)
        self.script_ask("once")
        self.assertIsNone(self.guard(write("A")))
        self.assertEqual(len(self.ask_calls()), asks + 1)
        self.clear_answer()
        out = self.guard(write("B"))
        self.assertEqual(out["permissionDecisionReason"], PENDING_REASON)
        self.assertEqual(len(self.ask_calls()), asks + 2)
        self.script_ask("once")
        self.assertIsNone(self.guard(write("B")))

    def test_h_long_segments_with_the_same_display_text_are_different_actions(self):
        path, rid = self.start_run()
        first = "kubectl apply -f " + "a" * 380 + "1.yaml"
        second = "kubectl apply -f " + "a" * 380 + "2.yaml"
        self.held(path, first)
        describe = self.record(rid)["pending_approval"]["describe"]
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        self.held(path, second)
        self.assertEqual(self.record(rid)["pending_approval"]["describe"], describe)
        self.assertEqual(len(self.record(rid)["grants"]), 1)
        self.assertIsNone(self.guard(self.payload(path, "true && " + first)))
        self.assertEqual(self.record(rid)["grants"], [])

    # Each is a different action from an approved plain `git push origin main`: it may run the
    # segment more than once, under a wrapper or inline code, or apart from the line.
    NOT_STRAIGHT = (
        "git push origin main && git push origin main",
        "for i in 1 2; do git push origin main; done",
        "echo x | xargs -I{} git push origin main",
        "foreach i (1 2); git push origin main; end",
        "repeat 3 git push origin main",
        "systemd-run --on-calendar=daily git push origin main",
        "python3 -c 'import os; os.system(\"git push origin main\")'",
        "bash -c 'git push origin main'",
        "git push origin main | cat",
        "(git push origin main)",
        "git push origin main &",
    )

    def test_i_a_grant_for_one_run_of_a_segment_covers_only_straight_line_commands(self):
        path, rid = self.start_run()
        self.held(path, "git push origin main")
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        for other in self.NOT_STRAIGHT:
            with self.subTest(command=other):
                self.dw("deny", rid)  # clear the previous hold, if any; the grant stays
                self.held(path, other)
                self.assertEqual(len(self.record(rid)["grants"]), 1)
        self.dw("deny", rid)
        self.assertIsNone(self.guard(self.payload(path, "git push origin main")))
        self.assertEqual(self.record(rid)["grants"], [])
        self.held(path, "git push origin main")

    def test_j_a_straight_line_compound_still_matches_its_plain_segment(self):
        path, rid = self.start_run()
        self.held(path, "true; git push origin main")
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        self.assertIsNone(self.guard(self.payload(
            path, 'git commit -qm "$(date)" && git push origin main')))
        self.assertEqual(self.record(rid)["grants"], [])



class NoteFixture(GuardHookBase):
    """An active run, its state directory and its result note path."""

    def setUp(self) -> None:
        super().setUp()
        self.path, self.rid = self.start_run()
        self.home = str(self.dw_home.resolve())
        self.runs = self.home + "/runs"
        self.note = "%s/%s.result.md" % (self.runs, self.rid)

    def allowed(self, command):
        asks = len(self.ask_calls())
        self.assertIsNone(self.guard(self.payload(self.path, command)), command)
        self.assertEqual(len(self.ask_calls()), asks)

    def held_as_control(self, command):
        out = self.guard(self.payload(self.path, command))
        self.assertEqual(out["permissionDecision"], "deny", command)
        pending = self.record(self.rid)["pending_approval"]
        self.assertEqual(pending["category"], "control", command)
        self.assertEqual(self.dw("deny", self.rid).returncode, 0)


class GuardResultNoteTests(NoteFixture):
    """The agent's own result note must be writable the way agents write it; nothing else in
    the control point's state directory is."""

    def test_the_observed_note_command_is_allowed_silently(self):
        self.allowed("mkdir -p %s && cat > %s <<'EOF'\nDONE\nAll good.\nEOF" % (self.runs, self.note))

    def test_mkdir_of_the_existing_state_directories_is_allowed(self):
        for command in ("mkdir -p %s" % self.runs, "mkdir -p %s" % self.home,
                        "mkdir -p %s/" % self.runs,
                        "mkdir --parents %s" % self.runs, "mkdir -pv %s %s" % (self.home, self.runs),
                        "mkdir --parents %s/" % self.runs,
                        "test -d %s" % self.runs, "[ -d %s ]" % self.runs, "ls %s" % self.runs,
                        "stat %s" % self.runs):
            with self.subTest(command=command):
                self.allowed(command)

    def test_the_note_stays_writable_every_usual_way(self):
        for command in ("echo DONE > %s" % self.note, "printf 'DONE\\n' > %s" % self.note,
                        "echo DONE | tee %s" % self.note):
            with self.subTest(command=command):
                self.allowed(command)
        for tool in ("Write", "Edit"):
            with self.subTest(tool=tool):
                self.assertIsNone(self.guard(self.payload(
                    self.path, tool=tool, tool_input={"file_path": self.note, "content": "DONE"})))

    def test_everything_else_in_the_state_directory_stays_held(self):
        other = "%s/r-other.result.md" % self.runs
        for command in ("mkdir -p %s/sub" % self.runs,
                        "mkdir -p %s && echo x > %s" % (self.runs, other),
                        "mkdir -p %s && echo x > %s/registry.json" % (self.runs, self.home),
                        "mkdir %s/bin" % self.home, "mkdir %s" % self.runs,
                        "mkdir -p %s > %s/registry.json" % (self.runs, self.home),
                        "touch %s" % self.runs, "chmod 700 %s" % self.runs, "rm -r %s" % self.runs,
                        "echo x > %s/%s.json" % (self.runs, self.rid),
                        "mkdir -p %s/new/.." % self.runs, "mkdir -p %s/x/../runs" % self.home,
                        "mkdir -p %s/./sub" % self.runs, "mkdir -p %s/RUNS/../bin" % self.home,
                        "mkdir -p %s/." % self.runs,
                        "mkdir -p %s -m %s/bin" % (self.runs, self.home),
                        "mkdir -p %s --mode %s/bin" % (self.runs, self.home),
                        "mkdir -p -m 700 %s" % self.runs, "mkdir -pm700 %s" % self.runs,
                        "mkdir --mode=700 -p %s" % self.runs, "mkdir %s -p" % self.runs,
                        "mkdir -p %s -v" % self.runs):
            with self.subTest(command=command):
                self.held_as_control(command)


class GuardApprovalDirectoryTests(GuardHookBase):
    """An approval is for the directory the guarded segment runs in."""

    def held(self, path, command):
        out = self.guard(self.payload(path, command))
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))

    def test_an_approval_does_not_carry_over_to_another_directory(self):
        path, rid = self.start_run()
        other = self.tmp / "other"
        other.mkdir()
        self.held(path, "git push origin main")
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        self.held(path, "cd %s && git push origin main" % other)
        self.assertEqual(len(self.record(rid)["grants"]), 1)
        ask = self.ask_calls()[-1]
        message = ask[ask.index("--message") + 1]
        self.assertIn("(in %s)" % other.resolve(), message)
        self.assertEqual(self.dw("deny", rid).returncode, 0)
        self.held(path, "cd $SOMEWHERE && git push origin main")
        self.assertEqual(len(self.record(rid)["grants"]), 1)
        self.assertEqual(self.dw("deny", rid).returncode, 0)
        self.assertIsNone(self.guard(self.payload(path, "cd . && git push origin main")))
        self.assertEqual(self.record(rid)["grants"], [])


    def test_the_directory_note_survives_a_long_command_and_a_long_directory(self):
        path, rid = self.start_run()
        far = str(self.tmp.resolve()) + "/"
        far += "/".join(["segment%02d" % i for i in range(40)])[:200 - len(far)].rstrip("/")
        self.assertGreaterEqual(len(far), 190)
        command = "cd %s && git push origin main && echo %s" % (far, "x" * 3000)
        command = command[:3000]
        self.held(path, command)
        ask = self.ask_calls()[-1]
        message = ask[ask.index("--message") + 1]
        self.assertLessEqual(len(message), 240)
        describe = "push to the default branch: git push origin main (in "
        self.assertTrue(message.startswith(describe), message)
        note = message[len(describe):message.index(")")]
        self.assertIn("…", note)
        self.assertTrue(far.startswith(note.split("…")[0]), note)
        self.assertTrue(far.endswith(note.split("…")[1]), note)
        self.assertLess(message.index(")"), message.index(" — Bash: "))
        self.assertTrue(message.endswith("full command in dw.log)"), message)

class GuardResultNoteLinkTests(NoteFixture):
    """The note is spared only for the Write or Edit tool, or for a straight-line command that
    names it only as a redirect target or the one file of tee; anything else naming it is
    held, and so is any write while the note is a symlink or not a regular file."""

    def test_plain_note_writes_are_allowed(self):
        for command in ("echo DONE > %s" % self.note, "printf 'DONE\\nall good\\n' > %s" % self.note,
                        "cat > %s <<'EOF'\nDONE\nEOF" % self.note,
                        "mkdir -p %s && cat > %s <<'EOF'\nDONE\nEOF" % (self.runs, self.note),
                        "git log --oneline -1 | tee %s" % self.note,
                        "echo more >> %s" % self.note, "echo DONE | tee -a %s" % self.note):
            with self.subTest(command=command):
                self.allowed(command)
        for tool in ("Write", "Edit"):
            with self.subTest(tool=tool):
                self.assertIsNone(self.guard(self.payload(
                    self.path, tool=tool, tool_input={"file_path": self.note, "content": "DONE"})))

    def test_anything_else_naming_the_note_is_held(self):
        for command in ("ln -s ../registry.json %s && echo x > %s" % (self.note, self.note),
                        "ln -sf /tmp/x %s" % self.note, "cp /tmp/n %s" % self.note,
                        "mv /tmp/n %s" % self.note, "busybox ln -s x %s" % self.note,
                        "cp --sym /tmp/x %s" % self.note,
                        "python3 -c 'open(\"%s\",\"w\")'" % self.note,
                        "for f in %s; do echo x > $f; done" % self.note,
                        "echo x > %s; rm %s" % (self.note, self.note),
                        "echo x | tee %s /tmp/other" % self.note,
                        "echo x > %s &" % self.note, "(echo x > %s)" % self.note,
                        "sudo tee %s" % self.note,
                        "echo $(rm %s) > %s" % (self.note, self.note),
                        "git log > %s" % self.note, "bash -c 'echo x > %s'" % self.note):
            with self.subTest(command=command):
                self.held_as_control(command)

    def test_a_missing_or_hard_linked_note_is_not_exempt(self):
        other = str(self.tmp / "hard")
        os.link(self.note, other)
        self.held_as_control("echo x > %s" % self.note)
        os.unlink(other)
        self.allowed("echo x > %s" % self.note)
        os.unlink(self.note)
        self.held_as_control("echo x > %s" % self.note)
        out = self.guard(self.payload(self.path, tool="Write",
                                      tool_input={"file_path": self.note, "content": "x"}))
        self.assertEqual(out["permissionDecision"], "deny")

    def test_a_note_that_is_a_symlink_or_a_directory_is_not_exempt(self):
        os.unlink(self.note)
        os.symlink(str(self.dw_home / "registry.json"), self.note)
        self.held_as_control("echo x > %s" % self.note)
        out = self.guard(self.payload(self.path, tool="Write",
                                      tool_input={"file_path": self.note, "content": "x"}))
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(self.record(self.rid)["pending_approval"]["category"], "control")
        self.assertEqual(self.dw("deny", self.rid).returncode, 0)
        os.unlink(self.note)
        os.mkdir(self.note)
        self.held_as_control("echo x > %s/inner" % self.note)
        out = self.guard(self.payload(self.path, tool="Write",
                                      tool_input={"file_path": self.note, "content": "x"}))
        self.assertEqual(out["permissionDecision"], "deny")

    def test_an_existing_regular_note_stays_writable(self):
        with open(self.note, "w") as fh:
            fh.write("DONE\n")
        self.allowed("echo DONE >> %s" % self.note)
        self.assertIsNone(self.guard(self.payload(
            self.path, tool="Write", tool_input={"file_path": self.note, "content": "DONE"})))


class GuardResultNoteLiteralTargetTests(NoteFixture):
    """The note is spared only for a redirect target that is one literal path to it."""

    def test_brace_glob_and_expansion_targets_are_held(self):
        rid = self.rid
        for command in ("echo x > %s/{%s.result.md,../registry.json}" % (self.runs, rid),
                        "echo x > %s/{runs/%s.result.md,registry.json}" % (self.home, rid),
                        "echo x > %s/{%s.result.md,../bin/dw}" % (self.runs, rid),
                        "cat > %s/{%s.result.md,../registry.json} <<'EOF'\nx\nEOF" % (self.runs, rid),
                        "printf x > %s/{%s.result.md,../registry.json}" % (self.runs, rid),
                        "echo x > %s{,.bak}" % self.note,
                        "echo x > %s/%s.result.m?" % (self.runs, rid),
                        "echo x > %s > /tmp/y" % self.note):
            with self.subTest(command=command):
                self.held_as_control(command)
        self.assertEqual(open(self.note).read(), "")

    def test_a_run_time_target_gets_no_note_exemption(self):
        # `echo x > "$X"` is judged by the ordinary check, which does not hold a run-time
        # redirect target (unchanged); the exemption itself never applies to such a word.
        from dwlib import guard
        ctx = guard._Ctx(str(self.path), str(self.path), [], self.rid)
        ctx.note_plain = True
        self.assertEqual(guard._spared_note_words(["echo", "x"], ["echo", "x"], ["$X"], ctx,
                                                  False, 0), set())
        self.assertEqual(guard._spared_note_words(["echo", "x"], ["echo", "x"], [self.note], ctx,
                                                  False, 0), {2})

    def test_one_literal_path_to_the_note_is_allowed(self):
        rid = self.rid
        for command in ("echo x > %s" % self.note, 'echo x > "%s"' % self.note,
                        "echo x > '%s'" % self.note, "echo x > $DW_HOME/runs/%s.result.md" % rid,
                        "echo x > ${DW_HOME}/runs/%s.result.md" % rid,
                        "cat > %s <<'EOF'\nDONE\nEOF" % self.note):
            with self.subTest(command=command):
                self.allowed(command)


class UnreadableApprovalTests(GuardHookBase):
    """`unreadable` can be approved once, by `dw approve`, or for the rest of the run; a
    run-wide approval of it never lets another category through, and an ended run's session
    still refuses it."""

    def buttons(self, ask):
        return [ask[i + 1] for i, a in enumerate(ask) if a == "--button"]

    def held(self, path, command, env=None):
        out = self.guard(self.payload(path, command), env=env)
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", PENDING_REASON))

    def test_the_dialog_offers_a_run_wide_approval_named_for_its_scope(self):
        path, rid = self.start_run()
        self.held(path, "$X one")
        ask = self.ask_calls()[-1]
        self.assertEqual(self.buttons(ask), ["once=Approve once",
                                             "run=Approve unreadable commands for this run",
                                             "deny=Deny"])
        self.assertIn("approve unreadable", ask[2])
        pending = self.record(rid)["pending_approval"]
        self.assertEqual((pending["rule"], pending["category"]), ("control-unreadable", "unreadable"))

    def test_approved_for_the_run_later_unreadable_commands_pass_silently(self):
        path, rid = self.start_run()
        self.script_ask("run")
        self.assertIsNone(self.guard(self.payload(path, "$X one")))
        self.assertEqual(self.record(rid)["approvals"], ["control-unreadable"])
        self.clear_answer()
        asks = len(self.ask_calls())
        self.assertIsNone(self.guard(self.payload(path, "kubectl $VERB pods")))
        self.assertEqual(len(self.ask_calls()), asks)
        # Never another category: a push next to an unreadable command is asked for.
        self.held(path, "$X one; git push origin main")
        self.assertEqual(len(self.ask_calls()), asks + 1)
        self.assertEqual(self.record(rid)["pending_approval"]["category"], "merge")
        self.assertEqual(self.dw("deny", rid).returncode, 0)
        self.held(path, "$X one; dw approve %s" % rid)
        self.assertEqual(self.record(rid)["pending_approval"]["category"], "control")

    def test_dw_approve_grants_an_unreadable_command_once(self):
        path, rid = self.start_run()
        self.held(path, "$X one")
        r = self.dw("approve", rid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("command cannot be read", r.stdout)
        asks = len(self.ask_calls())
        self.assertIsNone(self.guard(self.payload(path, "$X one")))
        self.assertEqual(len(self.ask_calls()), asks)
        self.held(path, "$X one")
        self.assertEqual(self.record(rid)["approvals"], [])

    def test_dw_approve_of_a_push_next_to_an_unreadable_command(self):
        path, rid = self.start_run()
        self.held(path, "$X one; git push origin main")
        self.assertEqual(self.dw("approve", rid).returncode, 0)
        self.assertIsNone(self.guard(self.payload(path, "$X one; git push origin main")))

    def test_control_next_to_unreadable_stays_control(self):
        path, rid = self.start_run()
        self.held(path, "$X one; dw approve %s" % rid)
        self.assertEqual(self.buttons(self.ask_calls()[-1]), ["once=Approve once", "deny=Deny"])
        self.assertEqual(self.dw("approve", rid).returncode, 2)

    def test_run_wide_answer_to_a_mixed_question_leaves_unreadable_out(self):
        # The question is about the push (merge decides the dialog); answering it for the run
        # remembers the push rule only, never the unreadable class.
        path, rid = self.start_run()
        self.script_ask("run")
        self.assertIsNone(self.guard(self.payload(path, "$X one; git push origin main")))
        self.assertEqual(self.record(rid)["approvals"], ["git-push-default"])
        self.clear_answer()
        asks = len(self.ask_calls())
        self.held(path, "$X two")
        self.assertEqual(len(self.ask_calls()), asks + 1)

    def test_an_ended_runs_session_refuses_unreadable_commands(self):
        path, rid = self.start_run()
        self.script_ask("run")
        self.assertIsNone(self.guard(self.payload(path, "$X one")))  # approved for the run
        from dwlib import runs
        runs.finish_run(rid, "done", None)
        asks = len(self.ask_calls())
        out = self.guard(self.payload(path, "$X two"), env={"DW_RUN_ID": rid})
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", INACTIVE_REASON % (rid, "done")))
        self.assertEqual(len(self.ask_calls()), asks)


class UnreadableStateApprovalTests(GuardHookBase):
    def test_a_run_wide_unreadable_approval_does_not_cover_state_unreadable(self):
        path, rid = self.start_run()
        self.script_ask("run")
        self.assertIsNone(self.guard(self.payload(path, "$X one")))
        self.clear_answer()
        self.assertIsNone(self.guard(self.payload(path, "kubectl $VERB pods")))
        asks = len(self.ask_calls())
        for command in ("$(echo dw) approve %s" % rid, 'bash -c "$CMD"'):
            with self.subTest(command=command):
                out = self.guard(self.payload(path, command))
                self.assertEqual(out["permissionDecisionReason"], PENDING_REASON)
                ask = self.ask_calls()[-1]
                self.assertEqual([ask[i + 1] for i, a in enumerate(ask) if a == "--button"],
                                 ["once=Approve once", "deny=Deny"])
                pending = self.record(rid)["pending_approval"]
                self.assertEqual((pending["rule"], pending["category"]),
                                 ("control-unreadable-state", "control"))
                self.assertEqual(self.dw("approve", rid).returncode, 2)
                self.assertEqual(self.dw("deny", rid).returncode, 0)
        self.assertEqual(len(self.ask_calls()), asks + 2)
