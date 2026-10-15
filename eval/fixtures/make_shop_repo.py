#!/usr/bin/env python3
"""Build a standalone git repo for the shop-reject-zero eval task.

Copies tests/fixtures/shop into a fresh repo *outside* this checkout
(default: ~/dc-eval-fixtures/shop) with two commits:

  1. base  — zero-dollar charges are allowed
  2. fix   — zero is rejected, plus the hidden test

Writes eval/tasks/shop-reject-zero.json (repo, base commit, test_patch)
unless --no-write-task is passed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_DIR = os.path.dirname(HERE)
ENGINE_ROOT = os.path.dirname(EVAL_DIR)
SHOP_SRC = os.path.join(ENGINE_ROOT, "tests", "fixtures", "shop")
TASK_PATH = os.path.join(EVAL_DIR, "tasks", "shop-reject-zero.json")
DEFAULT_DEST = os.path.expanduser("~/dc-eval-fixtures/shop")
DEST_DISPLAY = "~/dc-eval-fixtures/shop"

PROMPT = (
    "Reject zero-dollar charges in shop billing\n"
    "\n"
    "Charging a user with amount 0 currently succeeds and sends a receipt.\n"
    "Zero should be rejected the same way negative amounts already are.\n"
)

PYPROJECT = """\
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "shop"
version = "0.1.0"
description = "Tiny shop package for dc-eval (standalone fixture, not dc-engine)"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
include = ["shop"]
"""

TEST_BILLING = '''\
"""Regression: negative amounts stay rejected; positive charges still work."""
from decimal import Decimal

from shop.billing import charge
from shop.models import User


def test_negative_amount_rejected():
    user = User("a", "US")
    try:
        charge(user, Decimal("-1"))
    except ValueError:
        return
    raise AssertionError("negative amount must raise ValueError")


def test_positive_charge_ok():
    user = User("a", "US")
    receipt = charge(user, Decimal("10"))
    assert receipt.amount == Decimal("10")
'''

TEST_ZERO = '''\
"""Charge(amount=0) must be rejected like a negative amount."""
from decimal import Decimal

from shop.billing import charge
from shop.models import User


def test_zero_amount_rejected():
    user = User("a", "US")
    try:
        charge(user, Decimal("0"))
    except ValueError:
        return
    raise AssertionError("charge(user, 0) must raise ValueError")
'''

FIX_VALIDATE = '''\
def validate_amount(amount: Decimal) -> None:
    """Reject negative and zero amounts."""
    if amount <= 0:
        raise ValueError("negative amount")
'''

GIT_ENV = {
    "GIT_AUTHOR_NAME": "dc-eval",
    "GIT_AUTHOR_EMAIL": "dc-eval@local",
    "GIT_COMMITTER_NAME": "dc-eval",
    "GIT_COMMITTER_EMAIL": "dc-eval@local",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+0000",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+0000",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(args: list[str], cwd: str, env: dict[str, str] | None = None) -> str:
    merged = os.environ.copy()
    merged.update(GIT_ENV)
    if env:
        merged.update(env)
    r = subprocess.run(
        ["git", *args], cwd=cwd, env=merged,
        capture_output=True, text=True, check=True,
    )
    return r.stdout


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _paths_overlap(a: str, b: str) -> bool:
    a, b = os.path.realpath(a), os.path.realpath(b)
    return a == b or a.startswith(b + os.sep) or b.startswith(a + os.sep)


def build_shop_repo(dest: str) -> dict[str, str]:
    dest = os.path.abspath(os.path.expanduser(dest))
    if not os.path.isdir(SHOP_SRC):
        raise FileNotFoundError(f"shop fixture not found: {SHOP_SRC}")
    if _paths_overlap(dest, ENGINE_ROOT):
        raise SystemExit(
            f"refusing to create the shop fixture inside the dc-engine checkout "
            f"({ENGINE_ROOT}). Pass --dest outside this repo."
        )
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(
        SHOP_SRC, dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
    )
    _write(os.path.join(dest, "pyproject.toml"), PYPROJECT)
    _write(os.path.join(dest, "tests", "test_billing.py"), TEST_BILLING)
    _write(os.path.join(dest, "README.md"), "Standalone shop fixture for dc-eval.\n")

    _git(["init"], dest)
    _git(["config", "user.email", "dc-eval@local"], dest)
    _git(["config", "user.name", "dc-eval"], dest)
    _git(["config", "commit.gpgsign", "false"], dest)
    _git(["add", "-A"], dest)
    _git(["commit", "-m", "base: shop allows zero-dollar charges"], dest)
    base = _git(["rev-parse", "HEAD"], dest).strip()

    billing = os.path.join(dest, "shop", "billing.py")
    with open(billing, encoding="utf-8") as fh:
        src = fh.read()
    old = (
        "def validate_amount(amount: Decimal) -> None:\n"
        '    """Reject negative amounts."""\n'
        "    if amount < 0:\n"
        '        raise ValueError("negative amount")\n'
    )
    if old not in src:
        raise RuntimeError("shop/billing.py validate_amount did not match expected base text")
    _write(billing, src.replace(old, FIX_VALIDATE))
    _write(os.path.join(dest, "tests", "test_zero.py"), TEST_ZERO)
    _git(["add", "-A"], dest)
    _git(
        ["commit", "-m", "Reject zero-dollar charges in shop billing"],
        dest,
        env={
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:01+0000",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:01+0000",
        },
    )
    fix = _git(["rev-parse", "HEAD"], dest).strip()
    test_patch = _git(["diff", base, fix, "--", "tests/test_zero.py"], dest)
    return {
        "dest": dest,
        "base": base,
        "fix": fix,
        "test_patch": test_patch,
    }


def write_task(info: dict[str, str], repo_display: str) -> str:
    task = {
        "id": "shop-reject-zero",
        "repo": repo_display,
        "commit": info["base"],
        "prompt": PROMPT,
        "hidden_tests": ["tests/test_zero.py::test_zero_amount_rejected"],
        "test_patch": info["test_patch"],
        "regression_tests": [
            "tests/test_billing.py::test_negative_amount_rejected",
            "tests/test_billing.py::test_positive_charge_ok",
        ],
        "setup": "python -m pip install -e . pytest -q",
    }
    os.makedirs(os.path.dirname(TASK_PATH), exist_ok=True)
    tmp = TASK_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(task, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, TASK_PATH)
    return TASK_PATH


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dest", default=DEFAULT_DEST, help=f"git repo to create (default: {DEST_DISPLAY})")
    p.add_argument("--no-write-task", action="store_true", help="do not update eval/tasks/shop-reject-zero.json")
    args = p.parse_args(argv)
    info = build_shop_repo(args.dest)
    display = DEST_DISPLAY if os.path.realpath(os.path.expanduser(args.dest)) == os.path.realpath(DEFAULT_DEST) else info["dest"]
    if not args.no_write_task:
        path = write_task(info, display)
        print(f"wrote {path}")
    print(f"repo  {info['dest']}")
    print(f"base  {info['base']}")
    print(f"fix   {info['fix']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        raise SystemExit(exc.returncode)
