"""Mine SWE-bench-style tasks from git history."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from . import (
    MAX_HIDDEN_VERIFY,
    MAX_NON_TEST_LINES,
    MAX_REGRESSION_TESTS,
    MINE_PYTEST_TIMEOUT,
)
from .gitutil import git_out, git_root, is_git_repo, is_git_url
from .grade import apply_patch, install_test_env, is_test_path, run_pytest
from .run import create_run_venv, venv_env, venv_python
from .tasks import Task, save_task


def _slug(text: str, limit: int = 40) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    s = "".join(out).strip("-")
    return s[:limit] or "task"


def collect_node_ids_ast(root: str, rel_paths: list[str]) -> list[str]:
    ids: list[str] = []
    for rel in rel_paths:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                ids.append(f"{rel}::{node.name}")
            if isinstance(node, ast.ClassDef) and (
                node.name.startswith("Test") or node.name.endswith("Test")
            ):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                        ids.append(f"{rel}::{node.name}::{item.name}")
    return ids


def _numstat_lines(cwd: str, parent: str, commit: str) -> list[tuple[int, int, str]]:
    out = []
    text = git_out(["diff", "--numstat", parent, commit], cwd=cwd)
    for ln in text.splitlines():
        parts = ln.split("\t", 2)
        if len(parts) != 3:
            continue
        a, d, path = parts
        if a == "-" or d == "-":
            continue
        try:
            out.append((int(a), int(d), path))
        except ValueError:
            continue
    return out


def _changed_files(cwd: str, parent: str, commit: str) -> list[str]:
    text = git_out(["diff", "--name-only", parent, commit], cwd=cwd)
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _subject(cwd: str, commit: str) -> str:
    return git_out(["log", "-1", "--format=%s", commit], cwd=cwd).strip()


def _body(cwd: str, commit: str) -> str:
    return git_out(["log", "-1", "--format=%B", commit], cwd=cwd).strip()


def _parents(cwd: str, commit: str) -> list[str]:
    text = git_out(["rev-parse", f"{commit}^@"], cwd=cwd).strip()
    return [ln for ln in text.splitlines() if ln]


def _checkout_tree(repo: str, commit: str, dest: str) -> None:
    import subprocess
    os.makedirs(dest, exist_ok=True)
    proc = subprocess.run(
        ["git", "archive", "--format=tar", commit],
        cwd=repo, stdout=subprocess.PIPE, check=True,
    )
    subprocess.run(["tar", "-x", "-C", dest], input=proc.stdout, check=True)


def _has_pyproject(root: str) -> bool:
    return os.path.isfile(os.path.join(root, "pyproject.toml")) or os.path.isfile(
        os.path.join(root, "setup.py")
    )


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _pytest_pass_fail(
    root: str,
    node_ids: list[str],
    python: str | None = None,
) -> tuple[set[str], set[str]] | None:
    if not node_ids:
        return set(), set()
    xml_path = os.path.join(root, ".dc-eval-mine.xml")
    try:
        results = run_pytest(
            root, node_ids, xml_path, timeout=MINE_PYTEST_TIMEOUT, python=python,
        )
    except subprocess.TimeoutExpired:
        return None
    req_passed, req_failed = set(), set()
    for nid in node_ids:
        if results.get(nid):
            req_passed.add(nid)
        else:
            req_failed.add(nid)
    return req_passed, req_failed


def _regression_node_ids(root: str, skip_files: set[str], limit: int) -> list[str]:
    """Unchanged test files, capped so mine/eval do not run the whole suite."""
    out: list[str] = []
    if limit <= 0:
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "__pycache__", ".dc-engine", ".venv", "venv", "node_modules"}
        ]
        dirnames.sort()
        for fn in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
            if not is_test_path(rel) or rel in skip_files:
                continue
            for nid in collect_node_ids_ast(root, [rel]):
                out.append(nid)
                if len(out) >= limit:
                    return out
    return out


def candidate_from_commit(
    repo: str,
    commit: str,
    *,
    max_non_test_lines: int = MAX_NON_TEST_LINES,
    verify: bool = True,
) -> Task | None:
    parents = _parents(repo, commit)
    if len(parents) != 1:
        return None
    parent = parents[0]
    files = _changed_files(repo, parent, commit)
    test_files = [f for f in files if is_test_path(f)]
    non_test = [f for f in files if not is_test_path(f)]
    if not test_files or not non_test:
        return None
    non_test_lines = 0
    for a, d, path in _numstat_lines(repo, parent, commit):
        if not is_test_path(path):
            non_test_lines += a + d
    if non_test_lines > max_non_test_lines or non_test_lines <= 0:
        return None
    test_patch = git_out(["diff", parent, commit, "--", *test_files], cwd=repo)
    if not test_patch.strip():
        return None
    subject = _subject(repo, commit)
    short = commit[:10]
    tid = f"{short}-{_slug(subject)}"
    tmp: str | None = None
    hidden: list[str] = []
    regression: list[str] = []
    try:
        tmp = tempfile.mkdtemp(prefix="dc-eval-mine-")
        gold = os.path.join(tmp, "gold")
        base = os.path.join(tmp, "base")
        _checkout_tree(repo, commit, gold)
        hidden = collect_node_ids_ast(gold, test_files)
        if not hidden:
            return None
        _checkout_tree(repo, parent, base)
        regression = _regression_node_ids(base, set(test_files), MAX_REGRESSION_TESTS)
        if verify:
            apply_patch(base, test_patch)
            to_run = hidden[:MAX_HIDDEN_VERIFY]
            _log(f"  verify {commit[:10]}  hidden={len(to_run)}  regr={len(regression)}")
            venv = create_run_venv(os.path.join(tmp, "env"))
            venv_py = venv_python(venv)
            run_env = venv_env(venv)

            def _verify_tree(tree: str, nodes: list[str]) -> tuple[set[str], set[str]] | None:
                install_test_env(venv_py, tree, env=run_env)
                return _pytest_pass_fail(tree, nodes, python=venv_py)

            base_pf = _verify_tree(base, to_run)
            if base_pf is None:
                return None
            _passed_b, failed_b = base_pf
            hidden = [h for h in to_run if h in failed_b]
            if not hidden:
                return None
            gold_pf = _verify_tree(gold, hidden)
            if gold_pf is None:
                return None
            passed_g, failed_g = gold_pf
            if failed_g or not passed_g:
                return None
            if regression:
                clean = os.path.join(tmp, "parent")
                _checkout_tree(repo, parent, clean)
                regr_pf = _verify_tree(clean, regression)
                if regr_pf is None:
                    regression = []
                else:
                    passed_r, _failed_r = regr_pf
                    regression = [r for r in regression if r in passed_r]
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    setup = ""
    # prefer installing at the git root; caller may edit
    if _has_pyproject(repo):
        setup = "python -m pip install -e . -q"
    return Task(
        id=tid,
        repo=os.path.abspath(repo),
        commit=parent,
        prompt=_body(repo, commit),
        hidden_tests=hidden,
        test_patch=test_patch,
        regression_tests=regression,
        setup=setup,
        fix_commit=commit,
    )


def mine_repo(
    repo: str,
    eval_dir: str,
    *,
    max_non_test_lines: int = MAX_NON_TEST_LINES,
    max_commits: int = 200,
    verify: bool = True,
) -> list[Task]:
    if is_git_url(repo):
        raise ValueError("mine expects a local git checkout, not a URL")
    if not is_git_repo(repo):
        raise ValueError(f"not a git repo: {repo}")
    root = git_root(repo)
    commits = [
        ln.strip()
        for ln in git_out(["rev-list", f"--max-count={max_commits}", "HEAD"], cwd=root).splitlines()
        if ln.strip()
    ]
    found: list[Task] = []
    _log(f"mine {root}  commits={len(commits)}  verify={verify}")
    try:
        for i, commit in enumerate(commits, 1):
            if i == 1 or i % 20 == 0:
                _log(f"  scan {i}/{len(commits)} {commit[:10]}")
            try:
                task = candidate_from_commit(
                    root, commit,
                    max_non_test_lines=max_non_test_lines,
                    verify=verify,
                )
            except KeyboardInterrupt:
                raise
            except Exception:
                continue
            if task is None:
                continue
            save_task(eval_dir, task)
            found.append(task)
            _log(f"  wrote {task.id}  hidden={len(task.hidden_tests)}  regr={len(task.regression_tests) if isinstance(task.regression_tests, list) else task.regression_tests}")
    except KeyboardInterrupt:
        _log(f"mine interrupted ({len(found)} tasks so far)")
    return found
