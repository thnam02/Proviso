"""One active contract per repo, plus hook enforce mode.

Stored in `.dc-engine/active.json` and `.dc-engine/config.json` so hooks
can read them without opening the SQLite index.
"""

from __future__ import annotations

import json
import os
from typing import Any

ACTIVE_NAME = "active.json"
CONFIG_NAME = "config.json"
STOP_HISTORY_NAME = "stop-history.json"
VALID_ENFORCE = {"block", "warn", "off"}


def state_dir(root: str) -> str:
    return os.path.join(root, ".dc-engine")


def _read_json(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


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
    current = get_active_id(root)
    if cid is not None and current != cid:
        return
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
    hist = os.path.join(state_dir(root), STOP_HISTORY_NAME)
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
    data = _read_json(path)
    data["enforce"] = mode
    _write_json(path, data)


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
    scores = stop_history(root)
    scores.append(float(score))
    _write_json(path, {"scores": scores[-8:]})
