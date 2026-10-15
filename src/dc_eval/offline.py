"""Offline and host-auth helpers for machines without package-index access.

DC_EVAL_OFFLINE=1
    Run venvs are created with --system-site-packages, pytest must already be
    importable from the harness interpreter, and `pip install -e .` is replaced by
    a .pth file that puts the run copy on sys.path (same import behaviour as an
    editable install, no build step, no network).

DC_EVAL_CLAUDE_HOST_AUTH=1
    Claude Code runs without --bare (which only accepts ANTHROPIC_API_KEY) and
    authenticates through the host, e.g. a Claude cloud session. To keep the
    baseline a plain Claude Code, the agent gets a clean environment: a fresh
    HOME per run (no user settings, plugins, CLAUDE.md or memory), none of the
    parent session's CLAUDE_* variables, and no HTTP(S) proxy, so the agent's
    shell has no web access.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any

PTH_NAME = "dc_eval_editable.pth"

_TRUE = ("1", "true", "yes", "on")

# Variables the nested Claude Code may keep from the host. Everything else
# (CLAUDE_*, proxies, session tokens, tool config) is dropped.
_KEEP_ENV = ("ANTHROPIC_BASE_URL", "LANG", "LC_ALL", "TZ", "TERM")


def is_offline(env: dict[str, str] | None = None) -> bool:
    return (env or os.environ).get("DC_EVAL_OFFLINE", "").strip().lower() in _TRUE


def claude_host_auth(env: dict[str, str] | None = None) -> bool:
    return (env or os.environ).get("DC_EVAL_CLAUDE_HOST_AUTH", "").strip().lower() in _TRUE


def _site_packages(python: str, env: dict[str, str] | None = None) -> str:
    r = subprocess.run(
        [python, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        capture_output=True, text=True, timeout=60, env=env,
    )
    if r.returncode != 0 or not (r.stdout or "").strip():
        raise RuntimeError(f"cannot locate site-packages for {python}: {r.stderr}")
    return r.stdout.strip()


def import_roots(repo: str) -> list[str]:
    """Directories to put on sys.path: src/ layout first, else the repo root."""
    repo = os.path.abspath(repo)
    src = os.path.join(repo, "src")
    if os.path.isdir(src) and any(
        os.path.isfile(os.path.join(src, d, "__init__.py"))
        for d in os.listdir(src) if os.path.isdir(os.path.join(src, d))
    ):
        return [src]
    return [repo]


def link_editable(python: str, repo: str, env: dict[str, str] | None = None) -> str:
    """Write the .pth file that stands in for `pip install -e .`."""
    site = _site_packages(python, env)
    os.makedirs(site, exist_ok=True)
    path = os.path.join(site, PTH_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        for root in import_roots(repo):
            fh.write(root + "\n")
    return path


_EDITABLE_RE = re.compile(r"\bpip\s+install\b.*\s-e\s+\.(\[[^\]]*\])?(\s|$)")


def is_editable_install(cmd: str | list[str]) -> bool:
    text = cmd if isinstance(cmd, str) else " ".join(cmd)
    text = " " + text.strip() + " "
    return bool(_EDITABLE_RE.search(text)) or (
        " pip " in text and " install " in text and " -e " in text and " . " in text
    )


def is_pytest_install(cmd: list[str]) -> bool:
    return "pip" in cmd and "install" in cmd and cmd[-1] == "pytest"


def pytest_importable(python: str, env: dict[str, str] | None = None) -> bool:
    r = subprocess.run(
        [python, "-c", "import pytest"], capture_output=True, text=True, timeout=60, env=env,
    )
    return r.returncode == 0


def offline_setup(setup: str, repo: str, python: str, env: dict[str, str] | None) -> bool:
    """Handle a task's setup command offline. Returns True if handled here."""
    parts = [p.strip() for p in re.split(r"&&|;", setup or "") if p.strip()]
    if not parts or not all(is_editable_install(p) for p in parts):
        return False
    link_editable(python, repo, env)
    return True


def claude_agent_env(
    slot: str,
    run_env: dict[str, str] | None,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Clean environment for a nested Claude Code run (see module docstring)."""
    src = dict(base or os.environ)
    env: dict[str, str] = {k: src[k] for k in _KEEP_ENV if src.get(k)}
    home = os.path.join(slot, "home")
    os.makedirs(home, exist_ok=True)
    env["HOME"] = home
    path = (run_env or {}).get("PATH") or src.get("PATH", "/usr/bin:/bin")
    env["PATH"] = path
    if run_env and run_env.get("VIRTUAL_ENV"):
        env["VIRTUAL_ENV"] = run_env["VIRTUAL_ENV"]
    env["DISABLE_AUTOUPDATER"] = "1"
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return env


def describe(env: dict[str, Any] | None = None) -> list[str]:
    out = []
    if is_offline(env):
        out.append("offline: system-site-packages venvs, editable installs via .pth")
    if claude_host_auth(env):
        out.append("claude host auth: no --bare, clean env, fresh HOME, no proxy")
    return out


__all__ = [
    "PTH_NAME", "is_offline", "claude_host_auth", "link_editable", "import_roots",
    "is_editable_install", "is_pytest_install", "pytest_importable", "offline_setup",
    "claude_agent_env", "describe",
]
