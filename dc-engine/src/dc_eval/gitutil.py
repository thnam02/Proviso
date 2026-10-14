"""Thin git subprocess helpers (stdlib only)."""

from __future__ import annotations

import os
import subprocess
from typing import Sequence


class GitError(RuntimeError):
    def __init__(self, args: Sequence[str], stderr: str, returncode: int) -> None:
        self.args = list(args)
        self.stderr = stderr
        self.returncode = returncode
        super().__init__(f"git {args[0] if args else ''} failed ({returncode}): {stderr.strip()[:400]}")


def git(
    args: Sequence[str],
    cwd: str,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    r = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and r.returncode != 0:
        raise GitError(args, r.stderr or r.stdout, r.returncode)
    return r


def git_out(args: Sequence[str], cwd: str, timeout: int = 120) -> str:
    return git(args, cwd, timeout=timeout).stdout


def is_git_url(repo: str) -> bool:
    s = repo.strip()
    return s.startswith(("git@", "http://", "https://", "ssh://", "git://")) or s.endswith(".git")


def git_root(path: str) -> str:
    r = git(["rev-parse", "--show-toplevel"], cwd=path)
    return r.stdout.strip()


def is_git_repo(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    r = git(["rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
    return r.returncode == 0 and r.stdout.strip() == "true"


def realpath(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))
