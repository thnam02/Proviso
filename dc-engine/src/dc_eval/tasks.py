"""Task JSON: one SWE-bench-style instance."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


@dataclass
class Task:
    id: str
    repo: str
    commit: str
    prompt: str
    hidden_tests: list[str] = field(default_factory=list)
    test_patch: str = ""
    regression_tests: list[str] | str = field(default_factory=list)
    setup: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        if not isinstance(data, dict):
            raise TypeError("task must be a JSON object")
        tid = str(data.get("id") or "").strip()
        if not tid or not _ID.match(tid):
            raise ValueError(f"invalid task id: {tid!r}")
        hidden = data.get("hidden_tests") or []
        if isinstance(hidden, str):
            hidden = [hidden]
        regr = data.get("regression_tests") or []
        return cls(
            id=tid,
            repo=str(data.get("repo") or ""),
            commit=str(data.get("commit") or ""),
            prompt=str(data.get("prompt") or ""),
            hidden_tests=[str(x) for x in hidden],
            test_patch=str(data.get("test_patch") or ""),
            regression_tests=regr if isinstance(regr, str) else [str(x) for x in regr],
            setup=str(data.get("setup") or ""),
        )


def tasks_dir(eval_dir: str) -> str:
    return os.path.join(eval_dir, "tasks")


def load_task(path: str) -> Task:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return Task.from_dict(data)


def load_tasks(eval_dir: str, ids: list[str] | None = None) -> list[Task]:
    folder = tasks_dir(eval_dir)
    if not os.path.isdir(folder):
        return []
    out: list[Task] = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        task = load_task(os.path.join(folder, name))
        if ids and task.id not in ids:
            continue
        out.append(task)
    return out


def save_task(eval_dir: str, task: Task) -> str:
    folder = tasks_dir(eval_dir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{task.id}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(task.to_dict(), fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def pytest_selection(selection: list[str] | str | None) -> list[str]:
    """Turn a task's pytest field into argv fragments."""
    if selection is None or selection == "" or selection == []:
        return []
    if isinstance(selection, str):
        import shlex
        return shlex.split(selection)
    return [str(x) for x in selection]
