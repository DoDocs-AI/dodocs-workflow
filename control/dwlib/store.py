from __future__ import annotations

import copy
import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from . import paths


class CorruptFile(Exception):
    def __init__(self, path):
        super().__init__("corrupt file: %s" % path)
        self.path = Path(path)


class ProjectNotFound(Exception):
    pass


class AmbiguousProject(Exception):
    def __init__(self, candidates):
        super().__init__("ambiguous project: " + ", ".join(c["id"] for c in candidates))
        self.candidates = candidates


def read_json(path: Path, default: dict) -> dict:
    path = Path(path)
    try:
        text = path.read_text()
    except FileNotFoundError:
        return copy.deepcopy(default)
    try:
        return json.loads(text)
    except ValueError:
        raise CorruptFile(path)


def update_json(path: Path, fn: Callable[[dict], dict], default: dict) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with open(str(lock_path), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            value = fn(read_json(path, default))
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as fh:
                    json.dump(value, fh, indent=2)
                    fh.write("\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, str(path))
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
            return value
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def default_registry() -> dict:
    return {
        "version": 1,
        "limits": {"per_project": 1, "total": 3},
        "stall_minutes": 30,
        "projects": [],
    }


def load_registry() -> dict:
    return read_json(paths.registry_path(), default_registry())


def find_project(registry: dict, query: str) -> dict:
    projects = registry.get("projects", [])
    for p in projects:
        if p["id"] == query:
            return p
    q = query.lower()
    for p in projects:
        if p["name"].lower() == q:
            return p
    matches = [p for p in projects if q in p["id"] or q in p["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ProjectNotFound(query)
    raise AmbiguousProject(matches)


def list_runs() -> tuple[list[dict], list[Path]]:
    records: list[dict] = []
    corrupt: list[Path] = []
    directory = paths.runs_dir()
    if not directory.is_dir():
        return records, corrupt
    for p in sorted(directory.glob("*.json")):
        try:
            records.append(read_json(p, {}))
        except CorruptFile:
            corrupt.append(p)
    return records, corrupt


def load_run(run_id: str) -> dict:
    return read_json(paths.run_path(run_id), {})


def update_run(run_id: str, fn: Callable[[dict], dict]) -> dict:
    return update_json(paths.run_path(run_id), fn, {})
