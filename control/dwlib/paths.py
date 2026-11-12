from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    override = os.environ.get("DW_HOME")
    if override:
        return Path(override)
    return Path.home() / ".dodocs-workflow"


def registry_path() -> Path:
    return home() / "registry.json"


def runs_dir() -> Path:
    return home() / "runs"


def run_path(run_id: str) -> Path:
    return runs_dir() / (run_id + ".json")


def result_note_path(run_id: str) -> Path:
    return runs_dir() / (run_id + ".result.md")


def prompt_path(run_id: str) -> Path:
    return runs_dir() / (run_id + ".prompt")


def resume_prompt_path(run_id: str) -> Path:
    return runs_dir() / (run_id + ".resume.prompt")


def blocked_note_paths(run_id: str) -> list:
    """Moved-aside BLOCKED notes of a run, newest first."""
    found = []
    for p in runs_dir().glob(run_id + ".result.blocked-*.md"):
        stamp = p.name[len(run_id) + len(".result.blocked-"):-len(".md")]
        if stamp.isdigit():
            found.append((int(stamp), p))
    return [p for _, p in sorted(found, reverse=True)]
