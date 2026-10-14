"""Run contract probes in an isolated subprocess and compare results.

Each probe is a fresh interpreter: cwd is the tree under test,
PYTHONPATH is that tree (plus `<tree>/src` when it exists), hashes are
stable (`PYTHONHASHSEED=0`), and `random` is seeded to 0 so a probe that
forgets to seed still comes out the same twice. Values are normalised so
object identity and dict/set order don't look like behaviour changes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from .contracts import Expect, Probe

DEFAULT_TIMEOUT = 10.0
VALUE_LIMIT = 300

# Self-contained runner: executed via `python -c`. Keep it independent of
# dc_engine so the tree under test is not polluted by the engine's imports.
_RUNNER = r"""
import json, random, sys, io, re, traceback

def normalise(obj, _depth=0,
              _addr=re.compile(r" at 0x[0-9a-fA-F]+"),
              _default=re.compile(r"^<[A-Za-z0-9_.]+ object at 0x[0-9a-fA-F]+>$")):
    if _depth > 8:
        s = "..."
    elif obj is None:
        s = "None"
    elif isinstance(obj, bool):
        s = "True" if obj else "False"
    elif isinstance(obj, (int, float, complex)):
        s = repr(obj)
    elif isinstance(obj, str):
        s = repr(obj)
    elif isinstance(obj, (bytes, bytearray)):
        s = repr(bytes(obj))
    elif isinstance(obj, dict):
        items = sorted((normalise(k, _depth + 1), normalise(v, _depth + 1)) for k, v in obj.items())
        s = "{" + ", ".join(f"{k}: {v}" for k, v in items) + "}"
    elif isinstance(obj, (set, frozenset)):
        items = sorted(normalise(x, _depth + 1) for x in obj)
        s = "{" + ", ".join(items) + "}"
    elif isinstance(obj, (list, tuple)):
        inner = ", ".join(normalise(x, _depth + 1) for x in obj)
        if isinstance(obj, list):
            s = "[" + inner + "]"
        else:
            s = "(" + inner + ("," if len(obj) == 1 else "") + ")"
    else:
        raw = repr(obj)
        if _default.match(raw):
            try:
                kv = vars(obj)
            except TypeError:
                s = type(obj).__name__
            else:
                parts = [f"{k}={normalise(v, _depth + 1)}"
                         for k, v in sorted(kv.items()) if not str(k).startswith("_")]
                s = type(obj).__name__ + "(" + ", ".join(parts) + ")"
        else:
            s = _addr.sub("", raw)
    return s[:297] + "..." if len(s) > 300 else s

payload = json.loads(sys.stdin.read())
setup = payload.get("setup") or ""
call = payload.get("call") or ""
ns = {"__name__": "__probe__"}
real_out, real_err = sys.stdout, sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
random.seed(0)
out = {"kind": "error", "type": None, "value": None, "exc_type": None, "exc_msg": None}
try:
    if setup:
        exec(compile(setup, "<setup>", "exec"), ns, ns)
    random.seed(0)
    value = eval(compile(call, "<call>", "eval"), ns, ns)
    out = {"kind": "return", "type": type(value).__name__, "value": normalise(value),
           "exc_type": None, "exc_msg": None}
except Exception as exc:
    out = {"kind": "raise", "type": type(exc).__name__, "value": None,
           "exc_type": type(exc).__name__,
           "exc_msg": (str(exc) or "")[:300]}
finally:
    sys.stdout = real_out
    sys.stderr = real_err
print(json.dumps(out, ensure_ascii=False))
"""


@dataclass
class ProbeResult:
    kind: str  # return | raise | timeout | error
    type: str | None = None
    value: str | None = None
    exc_type: str | None = None
    exc_msg: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "type": self.type, "value": self.value,
                "exc_type": self.exc_type, "exc_msg": self.exc_msg}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ProbeResult | None:
        if not data:
            return None
        return cls(kind=data.get("kind") or "error", type=data.get("type"),
                   value=data.get("value"), exc_type=data.get("exc_type"),
                   exc_msg=data.get("exc_msg"))

    def same_as(self, other: ProbeResult | None) -> bool:
        if other is None:
            return False
        if self.kind != other.kind:
            return False
        if self.kind == "return":
            return self.value == other.value
        if self.kind == "raise":
            return self.exc_type == other.exc_type and (self.exc_msg or "") == (other.exc_msg or "")
        return True

    def short(self) -> str:
        if self.kind == "return":
            return self.type or self.value or "return"
        if self.kind == "raise":
            return self.exc_type or "raise"
        return self.kind

    def display(self, limit: int = 80) -> str:
        if self.kind == "return":
            text = self.value or self.type or "None"
        elif self.kind == "raise":
            msg = f": {self.exc_msg}" if self.exc_msg else ""
            text = f"raised {self.exc_type}{msg}"
        elif self.kind == "timeout":
            text = "timeout"
        else:
            text = f"error: {self.exc_msg or self.type or '?'}"
        return text if len(text) <= limit else text[: limit - 1] + "…"


def pythonpath_for(tree: str) -> str:
    parts = [tree]
    src = os.path.join(tree, "src")
    if os.path.isdir(src):
        parts.append(src)
    return os.pathsep.join(parts)


def run_probe(tree: str, probe: Probe, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
    """Run `probe` against `tree` in a fresh subprocess."""
    env = os.environ.copy()
    env["PYTHONPATH"] = pythonpath_for(tree)
    env["PYTHONHASHSEED"] = "0"
    payload = json.dumps({"setup": probe.setup or "", "call": probe.call})
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _RUNNER],
            input=payload, capture_output=True, text=True,
            cwd=tree, env=env, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(kind="timeout", type="timeout")
    except OSError as exc:
        return ProbeResult(kind="error", type="OSError", exc_type="OSError", exc_msg=str(exc)[:300])
    if proc.returncode != 0 and not (proc.stdout or "").strip():
        err = (proc.stderr or proc.stdout or f"exit {proc.returncode}")[:300]
        return ProbeResult(kind="error", type="error", exc_type="error", exc_msg=err)
    line = _last_json_line(proc.stdout)
    if line is None:
        err = (proc.stderr or proc.stdout or "no JSON from probe runner")[:300]
        return ProbeResult(kind="error", type="error", exc_type="error", exc_msg=err)
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return ProbeResult(kind="error", type="error", exc_type="error",
                           exc_msg=(line[:300] if line else "bad JSON"))
    return ProbeResult.from_dict(data) or ProbeResult(kind="error")


def run_twice(tree: str, probe: Probe, timeout: float = DEFAULT_TIMEOUT) -> tuple[ProbeResult, bool]:
    """Run on baseline twice. Second return value is True when results differ (flaky)."""
    a = run_probe(tree, probe, timeout)
    b = run_probe(tree, probe, timeout)
    return a, not a.same_as(b)


def matches_expect(result: ProbeResult, expect: Expect | None) -> bool:
    if expect is None:
        return False
    if expect.raises is not None:
        return result.kind == "raise" and result.exc_type == expect.raises
    wanted = expect.returns
    if result.kind != "return":
        return False
    if wanted is None:
        return False
    if result.value == wanted or result.type == wanted:
        return True
    # agents sometimes paste a repr that still has a memory address
    stripped = re.sub(r" at 0x[0-9a-fA-F]+", "", wanted)
    return result.value == stripped


def run_pytest_ids(tree: str, node_ids: list[str],
                   timeout: float = 30.0) -> dict[str, str] | None:
    """`{nodeid: 'pass'|'fail'}` on `tree`, or None if pytest is not importable."""
    if not node_ids:
        return {}
    if importlib.util.find_spec("pytest") is None:
        return None
    env = os.environ.copy()
    env["PYTHONPATH"] = pythonpath_for(tree)
    env["PYTHONHASHSEED"] = "0"
    out: dict[str, str] = {}
    for nid in node_ids:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", nid, "-q", "--tb=no", "-p", "no:cacheprovider"],
                capture_output=True, text=True, cwd=tree, env=env, timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            out[nid] = "fail"
            continue
        out[nid] = "pass" if proc.returncode == 0 else "fail"
    return out


def _last_json_line(stdout: str | None) -> str | None:
    if not stdout:
        return None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return line
    return None
