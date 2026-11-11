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
