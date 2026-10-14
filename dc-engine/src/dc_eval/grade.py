"""Grade a run copy: apply test_patch, run pytest, record tree/layer stats."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Any

from .gitutil import git
from .tasks import Task, pytest_selection

TEST_BASENAMES = ("conftest.py",)


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


def run_pytest(repo: str, selection: list[str] | str, xml_path: str, timeout: int = 300) -> dict[str, bool]:
    args = pytest_selection(selection)
    if not args:
        return {}
    cmd = [
        sys.executable, "-m", "pytest",
        "--tb=no", "-q",
        f"--junitxml={xml_path}",
        *args,
    ]
    subprocess.run(
        cmd, cwd=repo, capture_output=True, text=True, timeout=timeout,
    )
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


def grade_repo(task: Task, repo: str, pytest_timeout: int = 300) -> dict[str, Any]:
    tree = working_tree_stats(repo)
    apply_patch(repo, task.test_patch)
    hidden_xml = os.path.join(repo, ".dc-eval-hidden.xml")
    regr_xml = os.path.join(repo, ".dc-eval-regr.xml")
    hidden = run_pytest(repo, task.hidden_tests, hidden_xml, timeout=pytest_timeout)
    regression = run_pytest(repo, task.regression_tests, regr_xml, timeout=pytest_timeout)
    hidden_fail = [k for k, ok in hidden.items() if not ok]
    regr_fail = [k for k, ok in regression.items() if not ok]
    resolved = bool(task.hidden_tests) and bool(hidden) and not hidden_fail
    layer = layer_disk_stats(repo)
    return {
        "hidden": hidden,
        "regression": regression,
        "resolved": resolved,
        "regressions": len(regr_fail),
        "hidden_failed": hidden_fail,
        "regression_failed": regr_fail,
        **tree,
        **layer,
    }
