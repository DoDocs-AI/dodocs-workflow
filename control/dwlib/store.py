from __future__ import annotations

import contextlib
import copy
import fcntl
import json
import os
import re
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


class RunNotFound(Exception):
    pass


class InvalidRunId(RunNotFound):
    pass


class AmbiguousProject(Exception):
    def __init__(self, candidates):
        super().__init__("ambiguous project: " + ", ".join(c["id"] for c in candidates))
        self.candidates = candidates


def read_json(path: Path, default):
    path = Path(path)
    try:
        text = path.read_text()
    except FileNotFoundError:
        return copy.deepcopy(default)
    try:
        value = json.loads(text)
    except ValueError:
        raise CorruptFile(path)
    if not isinstance(value, dict):
        raise CorruptFile(path)
    return value


@contextlib.contextmanager
def file_lock(path: Path):
    """Exclusive advisory lock held for the duration of the with block."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


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


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


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
            record = read_json(p, None)
        except CorruptFile:
            corrupt.append(p)
            continue
        if record is None:  # vanished between listing and reading
            continue
        records.append(record)
    return records, corrupt


def _run_file(run_id: str) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
        raise InvalidRunId("invalid run id: %r" % (run_id,))
    return paths.run_path(run_id)


def create_run(record: dict) -> dict:
    """Create a run record. The only way a run record comes into being."""
    path = _run_file(record["id"])

    def create(existing):
        if existing:
            raise ValueError("run already exists: %s" % record["id"])
        return record

    return update_json(path, create, {})


def load_run(run_id: str) -> dict:
    path = _run_file(run_id)
    record = read_json(path, None)
    if record is None:
        raise RunNotFound(run_id)
    return record


def update_run(run_id: str, fn: Callable[[dict], dict]) -> dict:
    path = _run_file(run_id)
    if not path.exists():
        raise RunNotFound(run_id)
    return update_json(path, fn, {})
