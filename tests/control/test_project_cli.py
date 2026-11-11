from __future__ import annotations

import json
import os
import unittest

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
