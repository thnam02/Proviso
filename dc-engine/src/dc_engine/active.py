"""One active contract per repo, plus hook enforce mode.

Stored in `.dc-engine/active.json` and `.dc-engine/config.json` so hooks
can read them without opening the SQLite index.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from .indexer import IGNORE_DIRS
from .jsonio import exclusive_lock, read_json, write_json_atomic

ACTIVE_NAME = "active.json"
CONFIG_NAME = "config.json"
STOP_HISTORY_NAME = "stop-history.json"
SESSION_NAME = "session.json"
VALID_ENFORCE = {"block", "warn", "off"}


def state_dir(root: str) -> str:
    return os.path.join(root, ".dc-engine")


def _read_json(path: str) -> dict[str, Any]:
    return read_json(path)


def _write_json(path: str, data: dict[str, Any]) -> None:
    with exclusive_lock(path):
        write_json_atomic(path, data)


def get_active_id(root: str) -> str | None:
    cid = _read_json(os.path.join(state_dir(root), ACTIVE_NAME)).get("id")
    return str(cid) if cid else None


def set_active(root: str, cid: str) -> None:
    _write_json(os.path.join(state_dir(root), ACTIVE_NAME), {"id": cid})
    # a new active contract resets the stop-hook loop guard
    hist_path = os.path.join(state_dir(root), STOP_HISTORY_NAME)
    if os.path.isfile(hist_path):
        try:
            os.remove(hist_path)
        except OSError:
            pass


def clear_active(root: str, cid: str | None = None) -> None:
    path = os.path.join(state_dir(root), ACTIVE_NAME)
    with exclusive_lock(path):
        current = str(_read_json(path).get("id") or "") or None
        if cid is not None and current != cid:
            return
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    hist = os.path.join(state_dir(root), STOP_HISTORY_NAME)
    with exclusive_lock(hist):
        if os.path.isfile(hist):
            try:
                os.remove(hist)
            except OSError:
                pass


def enforce_mode(root: str) -> str:
    raw = str(_read_json(os.path.join(state_dir(root), CONFIG_NAME)).get("enforce") or "block")
    return raw if raw in VALID_ENFORCE else "block"


def set_enforce(root: str, mode: str) -> None:
    if mode not in VALID_ENFORCE:
        raise ValueError(f"enforce must be one of {sorted(VALID_ENFORCE)}")
    path = os.path.join(state_dir(root), CONFIG_NAME)
    with exclusive_lock(path):
        data = _read_json(path)
        data["enforce"] = mode
        write_json_atomic(path, data)


def stop_history(root: str) -> list[float]:
    data = _read_json(os.path.join(state_dir(root), STOP_HISTORY_NAME))
    scores = data.get("scores") or []
    out = []
    for s in scores:
        try:
            out.append(float(s))
        except (TypeError, ValueError):
            continue
    return out


def record_stop_block(root: str, score: float) -> None:
    path = os.path.join(state_dir(root), STOP_HISTORY_NAME)
    with exclusive_lock(path):
        data = _read_json(path)
        scores = data.get("scores") or []
        out = []
        for s in scores:
            try:
                out.append(float(s))
            except (TypeError, ValueError):
                continue
        out.append(float(score))
        write_json_atomic(path, {"scores": out[-8:]})


def hash_py_files(root: str) -> dict[str, str]:
    """sha1 of every .py file under root, skipping IGNORE_DIRS (incl. .dc-engine)."""
    out: dict[str, str] = {}
    base = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, base).replace(os.sep, "/")
            try:
                with open(path, "rb") as fh:
                    out[rel] = hashlib.sha1(fh.read()).hexdigest()
            except OSError:
                continue
    return out


def load_session(root: str) -> dict[str, Any]:
    return _read_json(os.path.join(state_dir(root), SESSION_NAME))


def save_session(root: str, data: dict[str, Any]) -> None:
    path = os.path.join(state_dir(root), SESSION_NAME)
    with exclusive_lock(path):
        write_json_atomic(path, data)


def _fill_session_snapshot(root: str, data: dict[str, Any]) -> dict[str, Any]:
    if data.get("hashes"):
        return data
    data["hashes"] = hash_py_files(root)
    data.setdefault("py_bypass_blocked", False)
    data.setdefault("closed_warned", [])
    try:
        from . import baseline
        if baseline.is_git_root(root):
            created = baseline._git(root, "stash", "create")
            sha = (created.stdout or "").strip() if created.returncode == 0 else ""
            if sha:
                data["git_ref"] = sha
    except Exception:
        pass
    return data


def ensure_session_snapshot(root: str) -> dict[str, Any]:
    """Freeze .py hashes (and a git stash ref when possible) on the first hook call."""
    path = os.path.join(state_dir(root), SESSION_NAME)
    with exclusive_lock(path):
        data = _read_json(path)
        if data.get("hashes"):
            return data
        data = _fill_session_snapshot(root, data)
        write_json_atomic(path, data)
        return data


def py_files_changed(root: str) -> list[str]:
    data = ensure_session_snapshot(root)
    old = data.get("hashes") or {}
    new = hash_py_files(root)
    changed = sorted(set(old) | set(new))
    hashed = [rel for rel in changed if old.get(rel) != new.get(rel)]
    extra = []
    for p in data.get("edited_paths") or []:
        s = str(p).replace("\\", "/")
        if s.endswith(".py") and s not in hashed:
            extra.append(s)
    return hashed + extra


def record_edited_path(root: str, path: str) -> None:
    """afterFileEdit: remember the path so stop can see .py edits."""
    sess_path = os.path.join(state_dir(root), SESSION_NAME)
    with exclusive_lock(sess_path):
        data = _fill_session_snapshot(root, _read_json(sess_path))
        paths = [str(x) for x in (data.get("edited_paths") or [])]
        rel = path.replace("\\", "/")
        base = os.path.realpath(root)
        abs_p = path if os.path.isabs(path) else os.path.abspath(os.path.join(root, path))
        try:
            real = os.path.realpath(abs_p)
            if real == base or real.startswith(base + os.sep):
                rel = os.path.relpath(real, base).replace(os.sep, "/")
        except OSError:
            pass
        if rel and rel not in paths:
            paths.append(rel)
            data["edited_paths"] = paths
        write_json_atomic(sess_path, data)
