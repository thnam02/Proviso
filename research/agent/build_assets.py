"""Proviso assets per agent task (v2): the dependency map, the base failures and the base import-time snapshot, in
EVAL_DIR/impact/<task id>/. The run harness (dc_eval, arms "impact" and "impact-noreport") copies them into each
run's .dc-engine/ folder, so Proviso's hook can select tests from the agent's first test command on.

Usage (in WSL, from the repository root, with the interpreter that the runs will use):
  python research/agent/build_assets.py EVAL_DIR [TASK_ID_PREFIX ...]     (no prefixes: every task in EVAL_DIR/tasks)
Resumable: a task whose assets exist is skipped."""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))
from dc_engine import importstate, record  # noqa: E402
from dc_engine.impact import _is_test_path, map_files  # noqa: E402
from dc_eval.run import clone_url  # noqa: E402
from dc_eval.tasks import load_tasks  # noqa: E402

PKG = {"sqlglot": "sqlglot"}  # repository name -> package directory


def _snapshot_current(path: str) -> bool:
    """A precomputed base snapshot in the current snapshot format (an older format is rebuilt)."""
    try:
        return json.load(open(path)).get("format") == importstate.FORMAT
    except (OSError, ValueError, AttributeError):
        return False


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def build(eval_dir: str, task, python: str) -> str:
    dest = os.path.join(eval_dir, "impact", task.id)
    snap_path = os.path.join(dest, "importstate_base.json")
    if os.path.isfile(os.path.join(dest, "covmap.json")) and _snapshot_current(snap_path):
        return dest + " (exists)"
    os.makedirs(dest, exist_ok=True)
    src = clone_url(task.repo, eval_dir)
    name = task.repo.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    tree = os.path.join(eval_dir, "cache", "build", task.id[:10])
    if not os.path.isdir(tree):
        git(src, "worktree", "add", "-f", "--detach", tree, task.commit)
    git(tree, "checkout", "-q", "-f", task.commit)
    git(tree, "clean", "-q", "-fdx")
    env = {"PATH": os.path.dirname(python) + os.pathsep + os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/tmp"),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join([tree, os.path.join(ROOT, "src")])}
    cov_path = os.path.join(dest, "covmap.json")
    if not os.path.isfile(cov_path):
        record.record(tree, PKG[name], cov_path, python, ["tests"], None, "", ["-p", "no:randomly"], env)
    cov = json.load(open(cov_path))
    tests = [n for n in cov if not n.startswith("__")]
    if not tests:
        os.remove(cov_path)
        raise RuntimeError(f"{task.id}: the dependency map recorded no tests")
    json.dump(sorted(n for n in tests if not cov[n].get("ok", True)), open(os.path.join(dest, "base_failures.json"), "w"))
    # the base snapshot, as selection computes it (files = the package files in the map); cached by content
    files = sorted(f for f in map_files(cov) if not _is_test_path(f))
    if importstate.base_snapshot(tree, files, python, os.path.join(dest, "importstate_base.json")) is None:
        raise RuntimeError(f"{task.id}: import-time snapshot failed")
    return f"{dest} ({len(tests)} tests)"


def main():
    args = sys.argv[1:]
    eval_dir, prefixes = os.path.abspath(args[0]), args[1:]
    python = sys.executable
    tasks = [t for t in load_tasks(eval_dir) if not prefixes or any(t.id.startswith(x) for x in prefixes)]
    if not tasks:
        sys.exit(f"no task in {eval_dir}/tasks matches {prefixes}")
    for t in tasks:
        try:
            print(build(eval_dir, t, python), flush=True)
        except Exception as e:  # noqa: BLE001
            print(t.id, "ERROR", repr(e)[:400], flush=True)


if __name__ == "__main__":
    main()
