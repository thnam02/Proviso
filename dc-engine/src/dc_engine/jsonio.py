"""Atomic JSON writes and exclusive locks for `.dc-engine` state files.

Cursor runs several hooks as concurrent processes. A shared `path.tmp` plus
unlocked read-modify-write loses updates and raises FileNotFoundError on
`os.replace`. Every write uses a unique temp file in the same directory;
every read-modify-write holds an exclusive lock on a sibling `.lock` file.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator

# path -> (lock file handle, nest count). flock is not re-entrant across
# two fds on the same file; hooks call snapshot then save under one stack.
_HELD: dict[str, tuple[Any, int]] = {}


def read_json(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json_atomic(path: str, data: Any) -> None:
    """Write `data` via mkstemp in the same directory, then os.replace."""
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".",
        suffix=".tmp",
        dir=folder,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _acquire(fh: Any) -> None:
    if os.name == "nt":
        import msvcrt
        fh.seek(0)
        if fh.read(1) == b"":
            fh.write(b"\0")
            fh.flush()
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


def _release(fh: Any) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _drop(key: str) -> None:
    cur = _HELD.get(key)
    if cur is None:
        return
    fh, n = cur
    if n <= 1:
        _release(fh)
        try:
            fh.close()
        except OSError:
            pass
        _HELD.pop(key, None)
    else:
        _HELD[key] = (fh, n - 1)


@contextmanager
def exclusive_lock(path: str) -> Iterator[None]:
    """Exclusive lock on `path + '.lock'` (fcntl.flock; msvcrt.locking on Windows)."""
    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    key = os.path.abspath(lock_path)
    held = _HELD.get(key)
    if held is not None:
        _HELD[key] = (held[0], held[1] + 1)
        try:
            yield
        finally:
            _drop(key)
        return
    fh = open(lock_path, "a+b")
    try:
        _acquire(fh)
    except Exception:
        try:
            fh.close()
        except OSError:
            pass
        raise
    _HELD[key] = (fh, 1)
    try:
        yield
    finally:
        _drop(key)
