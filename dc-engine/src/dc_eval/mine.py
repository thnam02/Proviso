"""Mine SWE-bench-style tasks from git history."""

from __future__ import annotations

import ast
import os
import shutil
import tempfile
from . import MAX_NON_TEST_LINES
from .gitutil import git_out, git_root, is_git_repo, is_git_url
from .grade import apply_patch, is_test_path, run_pytest
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


def _pytest_pass_fail(root: str, node_ids: list[str]) -> tuple[set[str], set[str]]:
    if not node_ids:
        return set(), set()
    xml_path = os.path.join(root, ".dc-eval-mine.xml")
    results = run_pytest(root, node_ids, xml_path, timeout=180)
    req_passed, req_failed = set(), set()
    for nid in node_ids:
        if results.get(nid):
            req_passed.add(nid)
        else:
            req_failed.add(nid)
    return req_passed, req_failed


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
        # regression: tests that already existed on the parent, from unchanged test files
        all_parent_tests: list[str] = []
        _checkout_tree(repo, parent, base)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", ".dc-engine"}]
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), base).replace("\\", "/")
                if is_test_path(rel) and rel not in test_files:
                    all_parent_tests.append(rel)
        regression = collect_node_ids_ast(base, all_parent_tests)
        if verify:
            apply_patch(base, test_patch)
            _passed_b, failed_b = _pytest_pass_fail(base, hidden)
            hidden = [h for h in hidden if h in failed_b]
            if not hidden:
                return None
            passed_g, failed_g = _pytest_pass_fail(gold, hidden)
            if failed_g or not passed_g:
                return None
            if regression:
                clean = os.path.join(tmp, "parent")
                _checkout_tree(repo, parent, clean)
                passed_r, _failed_r = _pytest_pass_fail(clean, regression)
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
    for commit in commits:
        try:
            task = candidate_from_commit(
                root, commit,
                max_non_test_lines=max_non_test_lines,
                verify=verify,
            )
        except Exception:
            continue
        if task is None:
            continue
        save_task(eval_dir, task)
        found.append(task)
    return found
