"""Grade a run copy: restore hidden tests from the fix commit, run pytest."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Any

from .gitutil import git, is_git_repo
from . import offline as _offline
from .tasks import Task, pytest_selection

TEST_BASENAMES = ("conftest.py",)
GRADING_LOG = "grading.log"
_PKG_SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", ".env",
    "__pycache__", ".dc-engine", ".pytest_cache", ".mypy_cache",
    "build", "dist", "docs", "doc", "examples", "scripts",
    "tests", "test", "node_modules", ".tox", ".eggs",
}
_EXTRA_NAMES = ("test", "tests", "testing", "dev")
_GROUP_NAMES = ("test", "tests", "testing")
_REQ_FILES = (
    "requirements-dev.txt",
    "requirements_dev.txt",
    "dev-requirements.txt",
    "requirements-test.txt",
    "requirements_test.txt",
    "test-requirements.txt",
    "tests/requirements.txt",
    "requirements/test.txt",
    "requirements/dev.txt",
)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class GradingError(RuntimeError):
    """Environment is not ready to grade. Never report as unresolved."""


def is_test_path(path: str) -> bool:
    path = path.replace("\\", "/")
    base = path.rsplit("/", 1)[-1]
    if base in TEST_BASENAMES:
        return True
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.py"):
        return True
    return False


_DIFF_GIT = re.compile(r"^diff --git a/(.+) b/(.+)$", re.M)
_HEX = re.compile(r"^[0-9a-fA-F]{7,40}$")
AGENT_TEST_CHANGES = "agent_test_changes"
_SAVED_MARK = ".saved"


def files_in_test_patch(patch: str) -> list[str]:
    """Paths the hidden-test patch adds or edits (b/ side, unique, ordered)."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _DIFF_GIT.finditer(patch or ""):
        path = (m.group(2) or "").replace("\\", "/").strip()
        if not path or path == "/dev/null" or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def resolve_fix_commit(task: Task, git_cwd: str) -> str | None:
    """Fix commit SHA: explicit field, task-id prefix, or first child of parent."""
    if not git_cwd or not is_git_repo(git_cwd):
        return None
    candidates: list[str] = []
    if (task.fix_commit or "").strip():
        candidates.append(task.fix_commit.strip())
    prefix = (task.id or "").split("-", 1)[0]
    if _HEX.match(prefix):
        candidates.append(prefix)
    for ref in candidates:
        r = git(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=git_cwd, check=False)
        if r.returncode == 0 and (r.stdout or "").strip():
            return r.stdout.strip()
    parent = (task.commit or "").strip()
    if parent:
        r = git(["rev-list", "--reverse", f"{parent}..HEAD"], cwd=git_cwd, check=False)
        if r.returncode == 0:
            first = (r.stdout or "").strip().splitlines()
            if first:
                return first[0].strip()
    return None


def _ensure_commit(run_repo: str, src_repo: str | None, sha: str) -> bool:
    if is_git_repo(run_repo):
        r = git(["cat-file", "-e", f"{sha}^{{commit}}"], cwd=run_repo, check=False)
        if r.returncode == 0:
            return True
        if src_repo and is_git_repo(src_repo):
            fetched = git(
                ["fetch", "--no-tags", src_repo, sha], cwd=run_repo, check=False,
            )
            if fetched.returncode == 0:
                return True
    return is_git_repo(src_repo or "") and git(
        ["cat-file", "-e", f"{sha}^{{commit}}"], cwd=src_repo, check=False,
    ).returncode == 0


def checkout_fix_files(
    repo: str,
    files: list[str],
    sha: str,
    src_repo: str | None = None,
) -> None:
    """Replace `files` with the versions at `sha` (fetch into the run copy if needed)."""
    if not files:
        return
    if is_git_repo(repo) and _ensure_commit(repo, src_repo, sha):
        r = git(["checkout", sha, "--", *files], cwd=repo, check=False)
        if r.returncode == 0:
            return
    show_cwd = src_repo if src_repo and is_git_repo(src_repo) else repo
    missing: list[str] = []
    for rel in files:
        r = git(["show", f"{sha}:{rel}"], cwd=show_cwd, check=False)
        if r.returncode != 0:
            missing.append(rel)
            continue
        dest = os.path.join(repo, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest) or repo, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(r.stdout)
    if missing:
        raise RuntimeError(
            f"could not restore hidden tests from {sha[:12]}: {', '.join(missing)}"
        )


def _file_differs_from_head(repo: str, rel: str, body: str) -> bool:
    if not is_git_repo(repo):
        return True
    r = git(["show", f"HEAD:{rel}"], cwd=repo, check=False)
    if r.returncode != 0:
        return True
    return r.stdout != body


def snapshot_agent_test_files(
    repo: str,
    run_dir: str,
    patch_files: list[str],
) -> list[str]:
    """Copy the agent's versions of hidden-test files, once, into run_dir/agent_test_changes."""
    dest_root = os.path.join(run_dir, AGENT_TEST_CHANGES)
    mark = os.path.join(dest_root, _SAVED_MARK)
    if not os.path.isfile(mark):
        os.makedirs(dest_root, exist_ok=True)
        for rel in patch_files:
            live = os.path.join(repo, rel.replace("/", os.sep))
            if not os.path.isfile(live):
                continue
            dest = os.path.join(dest_root, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(live, dest)
        with open(mark, "w", encoding="utf-8") as fh:
            fh.write("1\n")
    modified: list[str] = []
    for rel in patch_files:
        saved = os.path.join(dest_root, rel.replace("/", os.sep))
        if not os.path.isfile(saved):
            continue
        with open(saved, encoding="utf-8", errors="replace") as fh:
            body = fh.read()
        if _file_differs_from_head(repo, rel, body):
            modified.append(rel)
    return modified


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


def _patched_old_lines(test_patch: str) -> dict[str, set[int]]:
    """Lines of each file's base version that a unified diff touches: removed lines, and for an insertion the base
    line just before it (so an insertion inside a test body counts for that test)."""
    out: dict[str, set[int]] = {}
    cur = None
    old_ln = 0
    for line in test_patch.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            cur = m.group(1) if m else None
            continue
        m = _HUNK.match(line)
        if m:
            old_ln = int(m.group(1))
            continue
        if cur is None or line.startswith(("---", "+++", "index ", "new file", "deleted file", "similarity", "rename")):
            continue
        if line.startswith("-"):
            out.setdefault(cur, set()).add(old_ln)
            old_ln += 1
        elif line.startswith("+"):
            out.setdefault(cur, set()).add(max(old_ln - 1, 1))
        elif line.startswith(" ") or line == "":
            old_ln += 1
    return out


def _as_list(selection) -> list[str]:
    from .tasks import pytest_selection
    return pytest_selection(selection)


def tests_changed_by_patch(test_patch: str, base_source) -> set[str]:
    """Existing tests (node ids without parameters) whose body the hidden test patch edits. Such a test checks the
    new behaviour the agent was asked for, so failing it is a hidden-test failure, not a regression.
    base_source(path) returns the file's content at the task's base commit, or None."""
    import ast
    changed: set[str] = set()
    for path, lines in _patched_old_lines(test_patch).items():
        src = base_source(path)
        if not src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        def visit(node, prefix):
            for ch in getattr(node, "body", []):
                if isinstance(ch, ast.ClassDef):
                    visit(ch, prefix + [ch.name])
                elif isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) and ch.name.startswith("test"):
                    start = min([ch.lineno] + [d.lineno for d in ch.decorator_list])
                    if any(start <= ln <= (ch.end_lineno or ch.lineno) for ln in lines):
                        changed.add("::".join([path] + prefix + [ch.name]))
        visit(tree, [])
    return changed


def restore_hidden_tests(
    task: Task,
    repo: str,
    *,
    src_repo: str | None = None,
    run_dir: str | None = None,
) -> list[str]:
    """Save agent copies of test_patch files, then restore those files from the fix commit.

    Returns paths the agent modified (subset of test_patch files). Files the agent
    added or edited that are not in test_patch are left untouched.
    """
    files = files_in_test_patch(task.test_patch)
    modified: list[str] = []
    if run_dir and files:
        modified = snapshot_agent_test_files(repo, run_dir, files)
    src = src_repo or ""
    git_cwd = src if src and is_git_repo(src) else repo
    sha = resolve_fix_commit(task, git_cwd)
    if sha and files:
        # files the task adds beyond the fix commit (e.g. extra hidden checks) come from the patch itself
        show_cwd = src if src and is_git_repo(src) else repo
        in_fix = [f for f in files if git(["cat-file", "-e", f"{sha}:{f}"], cwd=show_cwd, check=False).returncode == 0]
        extra = [f for f in files if f not in in_fix]
        checkout_fix_files(repo, in_fix, sha, src_repo=src or None)
        if extra:
            _reset_to_head(repo, extra)
            apply_patch(repo, patch_for_files(task.test_patch, extra))
        return modified
    _reset_to_head(repo, files)
    apply_patch(repo, task.test_patch)
    return modified


def patch_for_files(patch: str, files: list[str]) -> str:
    """The sections of a unified git diff that touch `files`."""
    keep, out = False, []
    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[-1].strip()
            keep = path in files
        if keep:
            out.append(line)
    return "".join(out)


def _reset_to_head(repo: str, files: list[str]) -> None:
    """Undo agent edits to test_patch files so the patch applies to the base version.

    Used when the source clone has no fix commit (e.g. a clone cut off at the
    task's base commit so the agent cannot read the upstream fix from history).
    The agent's copies were already saved by snapshot_agent_test_files.
    """
    if not files or not is_git_repo(repo):
        return
    for rel in files:
        in_head = git(["cat-file", "-e", f"HEAD:{rel}"], cwd=repo, check=False).returncode == 0
        if in_head:
            git(["checkout", "HEAD", "--", rel], cwd=repo, check=False)
        else:
            path = os.path.join(repo, rel.replace("/", os.sep))
            if os.path.isfile(path):
                os.remove(path)


def apply_patch(repo: str, patch: str) -> None:
    if not patch or not patch.strip():
        return
    path = os.path.join(repo, ".dc-eval-test.patch")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(patch)
        if not patch.endswith("\n"):
            fh.write("\n")
    r = git(["apply", "--whitespace=nowarn", path], cwd=repo, check=False)
    if r.returncode != 0:
        r2 = subprocess.run(
            ["patch", "-p1", "--forward", "--batch", "-i", path],
            cwd=repo, capture_output=True, text=True,
        )
        if r2.returncode != 0:
            raise RuntimeError(
                "failed to apply test_patch:\n"
                + (r.stderr or r.stdout or "")
                + (r2.stderr or r2.stdout or "")
            )


def working_tree_stats(repo: str) -> dict[str, Any]:
    """Diff vs HEAD *before* the test patch is applied."""
    names = []
    r = git(["diff", "--name-only", "HEAD"], cwd=repo, check=False)
    if r.returncode == 0:
        names = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    untracked = git(["ls-files", "--others", "--exclude-standard"], cwd=repo, check=False)
    if untracked.returncode == 0:
        for ln in untracked.stdout.splitlines():
            s = ln.strip()
            if s and s not in names:
                names.append(s)
    modified_tests = any(is_test_path(n) for n in names)
    diff_size = 0
    numstat = git(["diff", "--numstat", "HEAD"], cwd=repo, check=False)
    if numstat.returncode == 0:
        for ln in numstat.stdout.splitlines():
            parts = ln.split("\t", 2)
            if len(parts) < 3:
                continue
            a, d = parts[0], parts[1]
            if a == "-" or d == "-":
                continue
            try:
                diff_size += int(a) + int(d)
            except ValueError:
                continue
    return {
        "modified_tests": modified_tests,
        "diff_size": diff_size,
        "changed_files": names,
    }


def _junit_results(xml_path: str) -> dict[str, bool]:
    if not os.path.isfile(xml_path):
        return {}
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return {}
    out: dict[str, bool] = {}
    for case in tree.iter("testcase"):
        classname = case.get("classname") or ""
        name = case.get("name") or ""
        file_ = (case.get("file") or "").replace("\\", "/")
        failed = any(child.tag in ("failure", "error") for child in list(case))
        passed = not failed
        keys = [name]
        if file_:
            keys.append(f"{file_}::{name}")
            short = classname.rsplit(".", 1)[-1] if classname else ""
            if short and short[:1].isupper():
                keys.append(f"{file_}::{short}::{name}")
            elif short:
                keys.append(f"{file_}::{short}::{name}")
        if classname:
            keys.append(f"{classname}::{name}")
        nodeid = case.get("nodeid")
        if nodeid:
            keys.append(nodeid)
        for k in keys:
            if k:
                out[k] = passed
    return out


def junit_counts(xml_path: str) -> tuple[int, int]:
    """(passed, total) checks in a JUnit file, counting subtests as their own checks.

    pytest reports each subtest as a test in the suite totals, so a task whose
    hidden test has 35 subtests contributes 35+ checks instead of a single 0/1.
    """
    if not os.path.isfile(xml_path):
        return 0, 0
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return 0, 0
    total = bad = 0
    for suite in tree.iter("testsuite"):
        try:
            total += int(suite.get("tests") or 0)
            bad += int(suite.get("failures") or 0) + int(suite.get("errors") or 0)
            bad += int(suite.get("skipped") or 0)
        except ValueError:
            continue
    if total <= 0:
        cases = list(tree.iter("testcase"))
        total = len(cases)
        bad = sum(
            1 for c in cases
            if any(ch.tag in ("failure", "error", "skipped") for ch in list(c))
        )
    return max(total - bad, 0), total


def _toml_section_body(text: str, header: str) -> str:
    marker = f"[{header}]"
    lines = text.splitlines()
    capturing = False
    body: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            capturing = stripped == marker
            continue
        if capturing:
            body.append(raw)
    return "\n".join(body)


def _toml_keys(body: str) -> list[str]:
    keys: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_-]+)\s*=", line)
        if m:
            keys.append(m.group(1))
    return keys


def _toml_quoted(body: str, key: str) -> str | None:
    pat = re.compile(
        rf"^{re.escape(key)}\s*=\s*[\"']([^\"']+)[\"']",
        re.M,
    )
    m = pat.search(body)
    return m.group(1) if m else None


def detect_import_name(repo: str) -> str | None:
    """Import name of the package in `repo`, or None if none can be determined."""
    pyproject = os.path.join(repo, "pyproject.toml")
    if os.path.isfile(pyproject):
        with open(pyproject, encoding="utf-8") as fh:
            text = fh.read()
        name = _toml_quoted(_toml_section_body(text, "project"), "name")
        if not name:
            name = _toml_quoted(_toml_section_body(text, "tool.poetry"), "name")
        if name:
            ident = name.replace("-", "_")
            if _IDENT.match(ident):
                return ident
    setup_cfg = os.path.join(repo, "setup.cfg")
    if os.path.isfile(setup_cfg):
        with open(setup_cfg, encoding="utf-8") as fh:
            text = fh.read()
        name = _toml_quoted(_toml_section_body(text, "metadata"), "name")
        if name:
            ident = name.replace("-", "_")
            if _IDENT.match(ident):
                return ident
    src = os.path.join(repo, "src")
    for root in ((src,) if os.path.isdir(src) else ()) + (repo,):
        found: list[str] = []
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            if n in _PKG_SKIP_DIRS or n.startswith("."):
                continue
            ident = n.replace("-", "_")
            if not _IDENT.match(ident):
                continue
            if os.path.isfile(os.path.join(root, n, "__init__.py")):
                found.append(ident)
        if len(found) == 1:
            return found[0]
    return None


def _optional_extras(repo: str) -> list[str]:
    path = os.path.join(repo, "pyproject.toml")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    keys = _toml_keys(_toml_section_body(text, "project.optional-dependencies"))
    return [k for k in keys if k in _EXTRA_NAMES]


def _dependency_groups(repo: str) -> list[str]:
    path = os.path.join(repo, "pyproject.toml")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    keys = _toml_keys(_toml_section_body(text, "dependency-groups"))
    return [k for k in keys if k in _GROUP_NAMES]


def _has_project(repo: str) -> bool:
    return os.path.isfile(os.path.join(repo, "pyproject.toml")) or os.path.isfile(
        os.path.join(repo, "setup.py")
    )


def install_command_argv(python: str, repo: str) -> list[list[str]]:
    """pip argv lists: pytest, then editable + extras / groups / requirements."""
    cmds: list[list[str]] = [
        [python, "-m", "pip", "install", "-q", "pytest"],
    ]
    extras = _optional_extras(repo)
    if _has_project(repo):
        if extras:
            cmds.append(
                [python, "-m", "pip", "install", "-q", "-e", ".[" + ",".join(extras) + "]"]
            )
        else:
            cmds.append([python, "-m", "pip", "install", "-q", "-e", "."])
    for group in _dependency_groups(repo):
        cmds.append([python, "-m", "pip", "install", "-q", "--group", group])
    for rel in _REQ_FILES:
        if os.path.isfile(os.path.join(repo, rel.replace("/", os.sep))):
            cmds.append([python, "-m", "pip", "install", "-q", "-r", rel])
    return cmds


def install_test_env(
    python: str,
    repo: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> None:
    """Install pytest and the repo's test dependencies into `python`'s env."""
    offline = _offline.is_offline(env) or _offline.is_offline()
    for cmd in install_command_argv(python, repo):
        if offline:
            if _offline.is_pytest_install(cmd):
                if _offline.pytest_importable(python, env):
                    continue
                raise RuntimeError(
                    "DC_EVAL_OFFLINE=1 but pytest is not importable from "
                    f"{python} (install it into the harness interpreter first)"
                )
            if _offline.is_editable_install(cmd):
                _offline.link_editable(python, repo, env)
                continue
            continue  # dependency groups / requirement files need an index
        r = subprocess.run(
            cmd, cwd=repo, capture_output=True, text=True, timeout=timeout, env=env,
        )
        if r.returncode == 0:
            continue
        if "--group" in cmd:
            continue
        raise RuntimeError(
            f"venv install failed ({r.returncode}): {' '.join(cmd)}\n"
            f"{r.stderr or r.stdout}"
        )


def _append_grading_log(path: str, title: str, proc: subprocess.CompletedProcess) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"===== {title} =====\n")
        fh.write(f"returncode={proc.returncode}\n")
        out = proc.stdout or ""
        err = proc.stderr or ""
        if out:
            fh.write(out)
            if not out.endswith("\n"):
                fh.write("\n")
        if err:
            fh.write(err)
            if not err.endswith("\n"):
                fh.write("\n")


def preflight_grade_env(
    repo: str,
    python: str | None,
    log_path: str | None = None,
) -> None:
    """Fail grading if pytest or the package cannot be used from this interpreter."""
    py = python or sys.executable
    r = subprocess.run(
        [py, "-m", "pytest", "--version"],
        cwd=repo, capture_output=True, text=True, timeout=60,
    )
    if log_path:
        _append_grading_log(log_path, "preflight pytest --version", r)
    if r.returncode != 0:
        raise GradingError(
            "pytest is not available in the run venv: "
            + (r.stderr or r.stdout or f"exit {r.returncode}").strip()
        )
    name = detect_import_name(repo)
    if not name:
        return
    r = subprocess.run(
        [py, "-c", f"import {name}"],
        cwd=repo, capture_output=True, text=True, timeout=60,
    )
    if log_path:
        _append_grading_log(log_path, f"preflight import {name}", r)
    if r.returncode != 0:
        raise GradingError(
            f"package {name!r} is not importable from the run copy: "
            + (r.stderr or r.stdout or f"exit {r.returncode}").strip()
        )


def run_pytest(
    repo: str,
    selection: list[str] | str,
    xml_path: str,
    timeout: int = 300,
    python: str | None = None,
    log_path: str | None = None,
    log_title: str = "pytest",
) -> dict[str, bool]:
    args = pytest_selection(selection)
    if not args:
        return {}
    cmd = [
        python or sys.executable, "-m", "pytest",
        "--tb=no", "-q",
        f"--junitxml={xml_path}",
        *args,
    ]
    proc = subprocess.run(
        cmd, cwd=repo, capture_output=True, text=True, timeout=timeout,
    )
    if log_path:
        _append_grading_log(log_path, log_title, proc)
    results = _junit_results(xml_path)
    requested = [item for item in args if not item.startswith("-")]
    if not results:
        return {item: False for item in requested}
    return {item: _lookup_node(item, results) for item in requested}


def _lookup_node(requested: str, results: dict[str, bool]) -> bool:
    if requested in results:
        return results[requested]
    req_parts = requested.split("::")
    req_name = req_parts[-1]
    req_file = req_parts[0] if len(req_parts) > 1 else ""
    req_base = os.path.basename(req_file.replace("\\", "/"))
    req_mod = req_base[:-3] if req_base.endswith(".py") else req_base
    for k, ok in results.items():
        parts = k.split("::")
        if parts[-1] != req_name:
            continue
        blob = k.replace("\\", "/")
        if req_base and req_base in blob:
            return ok
        if req_mod and req_mod in blob:
            return ok
    return False


def _contract_files(root: str) -> list[str]:
    folder = os.path.join(root, ".dc-engine", "contracts")
    if not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, n)
        for n in sorted(os.listdir(folder))
        if n.endswith(".json") and not n.endswith(".cache.json")
    ]


def _load_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def layer_disk_stats(root: str) -> dict[str, Any]:
    contracts = _contract_files(root)
    scores: list[float] = []
    for path in contracts:
        data = _load_json(path)
        raw = data.get("close_score")
        if raw is None or raw == "":
            continue
        try:
            scores.append(float(raw))
        except (TypeError, ValueError):
            continue
    final: float | None = scores[-1] if scores else None
    if final is None:
        # open contract: best checkpoint score
        cp_root = os.path.join(root, ".dc-engine", "checkpoints")
        if os.path.isdir(cp_root):
            for cid in sorted(os.listdir(cp_root)):
                meta = _load_json(os.path.join(cp_root, cid, "meta.json"))
                sat, sco = meta.get("best_satisfied", -1), meta.get("best_scorable", 0)
                try:
                    sat_i, sco_i = int(sat), int(sco)
                except (TypeError, ValueError):
                    continue
                if sat_i >= 0 and sco_i:
                    sc = sat_i / sco_i
                    final = sc if final is None else max(final, sc)
    stop = _load_json(os.path.join(root, ".dc-engine", "stop-history.json"))
    stop_n = 0
    for s in stop.get("scores") or []:
        try:
            float(s)
            stop_n += 1
        except (TypeError, ValueError):
            continue
    return {
        "contracts_created": len(contracts),
        "final_contract_score": final,
        "stop_hook_blocks_disk": stop_n,
    }


# a slow suite (sympy's solvers: ~3 min alone) can exceed a few minutes when runs share the machine
GRADE_TIMEOUT = int(os.environ.get("DC_EVAL_GRADE_TIMEOUT", "1800"))


def grade_repo(
    task: Task,
    repo: str,
    pytest_timeout: int = GRADE_TIMEOUT,
    python: str | None = None,
    src_repo: str | None = None,
    run_dir: str | None = None,
) -> dict[str, Any]:
    log_path = os.path.join(run_dir, GRADING_LOG) if run_dir else None
    if log_path:
        os.makedirs(run_dir, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write("")
    preflight_grade_env(repo, python, log_path=log_path)
    tree = working_tree_stats(repo)
    agent_modified = restore_hidden_tests(
        task, repo, src_repo=src_repo, run_dir=run_dir,
    )
    hidden_xml = os.path.join(repo, ".dc-eval-hidden.xml")
    regr_xml = os.path.join(repo, ".dc-eval-regr.xml")
    hidden = run_pytest(
        repo, task.hidden_tests, hidden_xml, timeout=pytest_timeout, python=python,
        log_path=log_path, log_title="hidden tests",
    )
    # existing tests the hidden test patch edits check the new behaviour: count them with the hidden tests' outcome,
    # not as regressions (otherwise not implementing a hidden requirement looks like breaking an existing test)
    edited: set[str] = set()
    if src_repo and task.test_patch:
        def _base(path: str):
            r = subprocess.run(["git", "-C", src_repo, "show", f"{task.commit}:{path}"], capture_output=True, text=True)
            return r.stdout if r.returncode == 0 else None
        edited = tests_changed_by_patch(task.test_patch, _base)
    regr_ids = [t for t in _as_list(task.regression_tests) if t.split("[", 1)[0] not in edited]
    regression = run_pytest(
        repo, regr_ids, regr_xml, timeout=pytest_timeout, python=python,
        log_path=log_path, log_title="regression tests",
    )
    hidden_fail = [k for k, ok in hidden.items() if not ok]
    regr_fail = [k for k, ok in regression.items() if not ok]
    resolved = bool(task.hidden_tests) and bool(hidden) and not hidden_fail
    checks_passed, checks_total = junit_counts(hidden_xml) if hidden else (0, 0)
    if resolved and checks_total and checks_passed < checks_total:
        checks_passed = checks_total  # e.g. skips inside an otherwise passing selection
    if checks_total:
        hidden_score = checks_passed / checks_total
    else:
        hidden_score = 1.0 if resolved else 0.0
    layer = layer_disk_stats(repo)
    return {
        "hidden": hidden,
        "hidden_checks_passed": checks_passed,
        "hidden_checks_total": checks_total,
        "hidden_score": hidden_score,
        "regression": regression,
        "resolved": resolved,
        "regressions": len(regr_fail),
        "hidden_failed": hidden_fail,
        "regression_failed": regr_fail,
        "agent_modified_hidden_test_files": agent_modified,
        **tree,
        **layer,
    }
