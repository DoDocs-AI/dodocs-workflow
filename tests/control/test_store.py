from __future__ import annotations

import json
import subprocess
import sys
import unittest

from helpers import DwTestCase, REPO_ROOT


class StoreTests(DwTestCase):
    def test_update_json_creates_file_with_default(self):
        from dwlib import store

        path = self.dw_home / "x.json"
        out = store.update_json(path, lambda d: {**d, "n": 1}, {"n": 0})
        self.assertEqual(out, {"n": 1})
        self.assertEqual(json.loads(path.read_text()), {"n": 1})

    def test_read_json_corrupt_raises(self):
        from dwlib import store

        path = self.dw_home / "bad.json"
        path.parent.mkdir(parents=True)
        path.write_text("{")
        with self.assertRaises(store.CorruptFile):
            store.read_json(path, {})

    def test_concurrent_updates_do_not_lose_writes(self):
        path = self.dw_home / "counter.json"
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "from pathlib import Path\n"
            "from dwlib import store\n"
            "p = Path(%r)\n"
            "for _ in range(25):\n"
            "    store.update_json(p, lambda d: {'n': d['n'] + 1}, {'n': 0})\n"
        ) % (str(REPO_ROOT / "control"), str(path))
        procs = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(8)]
        for p in procs:
            self.assertEqual(p.wait(), 0)
        self.assertEqual(json.loads(path.read_text()), {"n": 200})

    def test_corrupt_run_record_is_reported_and_skipped(self):
        from dwlib import paths, store

        paths.runs_dir().mkdir(parents=True)
        paths.run_path("good").write_text(json.dumps({"id": "good", "state": "queued"}))
        paths.run_path("bad").write_text('{"id": "bad", "sta')
        records, corrupt = store.list_runs()
        self.assertEqual([r["id"] for r in records], ["good"])
        self.assertEqual(corrupt, [paths.run_path("bad")])

    def test_load_and_update_run(self):
        from dwlib import paths, store

        paths.runs_dir().mkdir(parents=True)
        paths.run_path("r1").write_text(json.dumps({"id": "r1", "state": "queued"}))
        self.assertEqual(store.load_run("r1")["state"], "queued")
        out = store.update_run("r1", lambda r: {**r, "state": "running"})
        self.assertEqual(out["state"], "running")
        self.assertEqual(store.load_run("r1")["state"], "running")

    def test_path_helpers(self):
        from dwlib import paths

        self.assertEqual(paths.home(), self.dw_home)
        self.assertEqual(paths.registry_path(), self.dw_home / "registry.json")
        self.assertEqual(paths.run_path("a"), self.dw_home / "runs" / "a.json")
        self.assertEqual(paths.result_note_path("a"), self.dw_home / "runs" / "a.result.md")
        self.assertEqual(paths.prompt_path("a"), self.dw_home / "runs" / "a.prompt")

    def _registry(self):
        return {"projects": [
            {"id": "slotme-app", "name": "SlotMe App"},
            {"id": "slotme-python", "name": "SlotMe Python"},
            {"id": "traderep", "name": "TradeRep"},
        ]}

    def test_find_project_by_id_name_and_unique_substring(self):
        from dwlib import store

        reg = self._registry()
        self.assertEqual(store.find_project(reg, "slotme-app")["id"], "slotme-app")
        self.assertEqual(store.find_project(reg, "TRADEREP")["id"], "traderep")
        self.assertEqual(store.find_project(reg, "slotme python")["id"], "slotme-python")
        self.assertEqual(store.find_project(reg, "trade")["id"], "traderep")

    def test_find_project_ambiguous_raises_with_candidates(self):
        from dwlib import store

        with self.assertRaises(store.AmbiguousProject) as cm:
            store.find_project(self._registry(), "slotme")
        self.assertEqual({c["id"] for c in cm.exception.candidates},
                         {"slotme-app", "slotme-python"})

    def test_find_project_missing_raises(self):
        from dwlib import store

        with self.assertRaises(store.ProjectNotFound):
            store.find_project(self._registry(), "nope")

    def test_load_registry_default(self):
        from dwlib import store

        reg = store.load_registry()
        self.assertEqual(reg["version"], 1)
        self.assertEqual(reg["limits"], {"per_project": 1, "total": 3})
        self.assertEqual(reg["stall_minutes"], 30)
        self.assertEqual(reg["projects"], [])


    def test_read_json_non_dict_raises_corrupt(self):
        from dwlib import store

        path = self.dw_home / "list.json"
        path.parent.mkdir(parents=True)
        for text in ("[1, 2]", "null", "3", '"s"'):
            path.write_text(text)
            with self.assertRaises(store.CorruptFile):
                store.read_json(path, {})

    def test_list_runs_skips_record_that_vanishes_before_reading(self):
        from pathlib import Path
        from unittest import mock
        from dwlib import paths, store

        paths.runs_dir().mkdir(parents=True)
        paths.run_path("good").write_text(json.dumps({"id": "good", "state": "queued"}))
        listing = [paths.run_path("gone"), paths.run_path("good")]
        with mock.patch.object(Path, "glob", return_value=listing):
            records, corrupt = store.list_runs()
        self.assertEqual(records, [{"id": "good", "state": "queued"}])
        self.assertEqual(corrupt, [])

    def test_unknown_run_raises_and_creates_nothing(self):
        from dwlib import paths, store

        with self.assertRaises(store.RunNotFound):
            store.load_run("r-missing")
        with self.assertRaises(store.RunNotFound):
            store.update_run("r-missing", lambda r: {**r, "state": "running"})
        self.assertFalse(paths.run_path("r-missing").exists())
        self.assertFalse(paths.runs_dir().exists() and list(paths.runs_dir().iterdir()))

    def test_create_run_is_the_only_way_to_make_a_record(self):
        from dwlib import store

        store.create_run({"id": "r-1", "state": "queued"})
        self.assertEqual(store.load_run("r-1")["state"], "queued")
        with self.assertRaises(ValueError):
            store.create_run({"id": "r-1", "state": "queued"})

    def test_run_id_with_path_parts_is_rejected(self):
        from dwlib import paths, store

        for bad in ("../evil", "a/b", "..", "x..y", "", "a\\b"):
            with self.assertRaises(store.RunNotFound):
                store.load_run(bad)
            with self.assertRaises(store.RunNotFound):
                store.update_run(bad, lambda r: r)
            with self.assertRaises(store.RunNotFound):
                store.create_run({"id": bad})
        self.assertFalse(paths.runs_dir().exists() and list(paths.runs_dir().iterdir()))
        self.assertFalse((self.dw_home / "evil.json").exists())


if __name__ == "__main__":
    unittest.main()
