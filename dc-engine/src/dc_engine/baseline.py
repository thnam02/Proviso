"""Freeze a copy of the repo as it was when a contract was created.

Git repos: `git stash create` captures uncommitted changes to tracked
files without touching the working tree (empty output means the tree is
clean — fall back to HEAD), then `git worktree add --detach` materialises
that commit under `.dc-engine/baseline/<id>`.

Non-git trees are copied, skipping indexer.IGNORE_DIRS so we don't drag
virtualenvs or the engine's own state dir along.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from .indexer import IGNORE_DIRS

_GIT_IDENT = ["-c", "user.name=dc-engine", "-c", "user.email=dc-engine@local"]


def is_git_root(root: str) -> bool:
    return os.path.isdir(os.path.join(root, ".git"))


def baseline_path(root: str, cid: str) -> str:
    return os.path.join(root, ".dc-engine", "baseline", cid)


def snapshot(root: str, cid: str) -> str:
    """Create a frozen tree for `cid`. Returns a ref (`<sha>`, `HEAD`, or `copy`)."""
    dest = baseline_path(root, cid)
    parent = os.path.dirname(dest)
    os.makedirs(parent, exist_ok=True)
    if os.path.exists(dest):
        close(root, cid)
    if is_git_root(root):
        return _snapshot_git(root, dest)
    _copy_tree(root, dest)
    return "copy"


def close(root: str, cid: str) -> None:
    """Remove the worktree or copied tree for `cid`."""
    dest = baseline_path(root, cid)
    if is_git_root(root):
        r = _git(root, "worktree", "remove", "--force", dest)
        if r.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            _git(root, "worktree", "prune")
        return
    shutil.rmtree(dest, ignore_errors=True)


def _snapshot_git(root: str, dest: str) -> str:
    created = _git(root, "stash", "create")
    if created.returncode != 0:
        raise RuntimeError(f"git stash create failed: {created.stderr.strip() or created.stdout}")
    ref = (created.stdout or "").strip() or "HEAD"
    added = _git(root, "worktree", "add", "--detach", dest, ref)
    if added.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed for {ref}: {added.stderr.strip() or added.stdout}")
    return ref


def _copy_tree(root: str, dest: str) -> None:
    def ignore(path: str, names: list[str]) -> list[str]:
        drop = []
        for n in names:
            if n in IGNORE_DIRS or n.endswith(".egg-info") or n == ".DS_Store":
                drop.append(n)
        return drop

    shutil.copytree(root, dest, ignore=ignore, symlinks=True)


def _git(root: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", root, *_GIT_IDENT, *args],
        capture_output=True, text=True,
    )
