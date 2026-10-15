"""Fast static checks run around every edit.

The point is not to report every problem in a file, but only the ones an
edit *introduced*: diagnostics are collected before and after the edit and
diffed by (tool, code, message), so pre-existing noise (missing third-party
stubs, old lint warnings) never reaches the agent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass(frozen=True)
class Diag:
    tool: str
    code: str
    message: str
    line: int
    severity: str = "error"
    path: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.tool, self.code, self.message)

    def render(self) -> str:
        where = f"{self.path}:L{self.line}" if self.path else f"L{self.line}"
        return f"{self.tool} {where} {self.code}: {self.message}"


@dataclass
class CheckResult:
    ran: list[str]
    skipped: dict[str, str]
    diags: list[Diag]


def diff_diags(before: list[Diag], after: list[Diag]) -> tuple[list[Diag], int]:
    """Return (diagnostics introduced by the edit, count of diagnostics fixed)."""
    remaining = Counter(d.key for d in before)
    new: list[Diag] = []
    for d in after:
        if remaining[d.key] > 0:
            remaining[d.key] -= 1
        else:
            new.append(d)
    fixed = sum(remaining.values())
    return new, fixed


class Checker:
    def __init__(self, root: str, typecheck: str | None = None, timeout: int = 90):
        self.root = root
        self.timeout = timeout
        self.ruff = shutil.which("ruff")
        mode = (typecheck or os.environ.get("DC_TYPECHECK", "pyright")).lower()
        self.pyright = shutil.which("pyright") if mode == "pyright" else None
        self.typecheck_mode = mode
        self._cache: dict[tuple[str, str, str], list[Diag]] = {}

    def available(self) -> dict[str, str]:
        return {
            "ruff": self.ruff or "not installed",
            "pyright": self.pyright or ("disabled" if self.typecheck_mode != "pyright" else "not installed"),
        }

    # --- ruff: works on in-memory text via stdin -------------------------
    def ruff_diags(self, rel: str, text: str) -> list[Diag]:
        assert self.ruff
        proc = subprocess.run(
            [self.ruff, "check", "--no-cache", "--output-format", "json", "--exit-zero",
             "--stdin-filename", os.path.join(self.root, rel), "-"],
            input=text.encode(), capture_output=True, cwd=self.root, timeout=self.timeout,
        )
        try:
            items = json.loads(proc.stdout.decode() or "[]")
        except json.JSONDecodeError:
            return []
        return [Diag("ruff", it.get("code") or "syntax", it.get("message", ""),
                     (it.get("location") or {}).get("row", 0)) for it in items]

    # --- pyright: needs the file on disk ---------------------------------
    def pyright_diags(self, rel: str) -> list[Diag]:
        assert self.pyright
        proc = subprocess.run(
            [self.pyright, "--outputjson", os.path.join(self.root, rel)],
            capture_output=True, cwd=self.root, timeout=self.timeout,
        )
        try:
            data = json.loads(proc.stdout.decode() or "{}")
        except json.JSONDecodeError:
            return []
        out = []
        for d in data.get("generalDiagnostics", []):
            if d.get("severity") != "error":
                continue
            line = ((d.get("range") or {}).get("start") or {}).get("line", -1) + 1
            out.append(Diag("pyright", d.get("rule") or "error", d.get("message", "").split("\n")[0], line))
        return out

    def pyright_files(self, rels: list[str]) -> dict[str, list[Diag]] | None:
        """Type-check several files in one pyright run; None if unavailable."""
        if not self.pyright or not rels:
            return None
        try:
            proc = subprocess.run(
                [self.pyright, "--outputjson", *[os.path.join(self.root, r) for r in rels]],
                capture_output=True, cwd=self.root, timeout=self.timeout,
            )
            data = json.loads(proc.stdout.decode() or "{}")
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
            return None
        out: dict[str, list[Diag]] = {r: [] for r in rels}
        for d in data.get("generalDiagnostics", []):
            if d.get("severity") != "error":
                continue
            rel = os.path.relpath(d.get("file", ""), self.root).replace(os.sep, "/")
            if rel in out:
                line = ((d.get("range") or {}).get("start") or {}).get("line", -1) + 1
                out[rel].append(Diag("pyright", d.get("rule") or "error",
                                     d.get("message", "").split("\n")[0], line, path=rel))
        return out

    def run(self, rel: str, text: str, digest: str, on_disk: bool) -> CheckResult:
        """Run available checkers on `text` (which must equal the file on disk
        when on_disk is True; pyright is skipped otherwise)."""
        ran: list[str] = []
        skipped: dict[str, str] = {}
        jobs = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            if self.ruff:
                key = ("ruff", rel, digest)
                jobs["ruff"] = (key, self._cache[key] if key in self._cache
                                else pool.submit(self.ruff_diags, rel, text))
            else:
                skipped["ruff"] = "not installed"
            if self.pyright and on_disk:
                key = ("pyright", rel, digest)
                jobs["pyright"] = (key, self._cache[key] if key in self._cache
                                   else pool.submit(self.pyright_diags, rel))
            elif not self.pyright:
                skipped["pyright"] = self.available()["pyright"]
            diags: list[Diag] = []
            for tool, (key, fut) in jobs.items():
                try:
                    result = fut if isinstance(fut, list) else fut.result()
                except subprocess.TimeoutExpired:
                    skipped[tool] = "timeout"
                    continue
                except OSError as exc:
                    skipped[tool] = f"failed: {exc}"
                    continue
                self._cache[key] = result
                ran.append(tool)
                diags.extend(result)
        return CheckResult(ran, skipped, diags)
