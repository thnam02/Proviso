"""Delta contracts: declared old/new behaviour, persisted as JSON.

A contract is what an agent writes *before* editing: which symbols it will
touch, which probes must change (with expected old and new results), and
which must stay the same. The engine freezes a baseline, checks that the
agent's picture of current behaviour is right, then later diffs baseline
vs working tree by actually running the probes.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

CONTRACTS_SUBDIR = "contracts"
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class Expect:
    """One expected outcome: a normalised return value, or an exception class."""

    returns: str | None = None
    raises: str | None = None

    def to_dict(self) -> dict[str, str]:
        if self.raises is not None:
            return {"raises": self.raises}
        return {"returns": self.returns if self.returns is not None else ""}

    def describe(self) -> str:
        if self.raises is not None:
            return f"raises {self.raises}"
        return f"returns {self.returns}"

    @classmethod
    def from_dict(cls, data: Any) -> Expect | None:
        if not data:
            return None
        if isinstance(data, Expect):
            return data
        if not isinstance(data, dict):
            return None
        if "raises" in data and data["raises"] is not None:
            return cls(raises=str(data["raises"]))
        if "returns" in data:
            return cls(returns="" if data["returns"] is None else str(data["returns"]))
        return None


@dataclass
class Probe:
    """A tiny program: optional setup, one expression, optional expectations."""

    id: str
    call: str
    setup: str = ""
    expect_old: Expect | None = None
    expect_new: Expect | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "call": self.call}
        if self.setup:
            d["setup"] = self.setup
        if self.expect_old:
            d["expect_old"] = self.expect_old.to_dict()
        if self.expect_new:
            d["expect_new"] = self.expect_new.to_dict()
        return d

    def label(self) -> str:
        return self.id or self.call

    @classmethod
    def from_dict(cls, data: Any) -> Probe:
        if isinstance(data, Probe):
            return data
        if not isinstance(data, dict):
            raise TypeError(f"probe must be an object, got {type(data).__name__}")
        call = str(data.get("call") or "")
        pid = str(data.get("id") or _slug(call) or f"probe-{uuid.uuid4().hex[:6]}")
        return cls(
            id=pid,
            call=call,
            setup=str(data.get("setup") or ""),
            expect_old=Expect.from_dict(data.get("expect_old")),
            expect_new=Expect.from_dict(data.get("expect_new")),
        )


@dataclass
class DeltaContract:
    id: str
    task: str
    targets: list[str]
    must_change: list[Probe]
    must_preserve: list[Probe] = field(default_factory=list)
    pytest_ids: list[str] = field(default_factory=list)
    baseline_ref: str = ""
    created_at: str = ""
    status: str = "open"  # open | closed
    flaky: list[str] = field(default_factory=list)
    close_reason: str = ""
    close_score: float | None = None
    closed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "targets": list(self.targets),
            "must_change": [p.to_dict() for p in self.must_change],
            "must_preserve": [p.to_dict() for p in self.must_preserve],
            "pytest_ids": list(self.pytest_ids),
            "baseline_ref": self.baseline_ref,
            "created_at": self.created_at,
            "status": self.status,
            "flaky": list(self.flaky),
            "close_reason": self.close_reason,
            "close_score": self.close_score,
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeltaContract:
        score = data.get("close_score")
        try:
            close_score = float(score) if score is not None and score != "" else None
        except (TypeError, ValueError):
            close_score = None
        return cls(
            id=data["id"],
            task=data.get("task") or "",
            targets=list(data.get("targets") or []),
            must_change=[Probe.from_dict(p) for p in data.get("must_change") or []],
            must_preserve=[Probe.from_dict(p) for p in data.get("must_preserve") or []],
            pytest_ids=list(data.get("pytest_ids") or []),
            baseline_ref=data.get("baseline_ref") or "",
            created_at=data.get("created_at") or "",
            status=data.get("status") or "open",
            flaky=list(data.get("flaky") or []),
            close_reason=str(data.get("close_reason") or ""),
            close_score=close_score,
            closed_at=str(data.get("closed_at") or ""),
        )


@dataclass
class CreateResult:
    ok: bool
    contract_id: str | None
    report: str
    contract: DeltaContract | None = None

    def __str__(self) -> str:
        return self.report


@dataclass
class CheckReport:
    contract_id: str
    satisfied: int
    scorable: int
    score: float
    lines: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return "\n".join(self.lines)

    def one_line(self) -> str:
        """Single-line status for edit results and PostToolUse context."""
        head = f"contract {self.contract_id}: {self.satisfied}/{self.scorable}"
        fail = next((ln for ln in self.lines if ln.startswith("✗ ")), "")
        if fail:
            body = fail[2:].strip()
            if len(body) > 60:
                body = body[:59] + "…"
            return f"{head} ✗ {body}"
        ok = next((ln for ln in self.lines if ln.startswith("✓ ")), "")
        if ok and not ok.startswith("✓ checkpoint") and not ok.startswith("✓ restored"):
            body = ok[2:].strip()
            if len(body) > 50:
                body = body[:49] + "…"
            return f"{head} ✓ {body}"
        return f"{head}  score {self.score:.1f}"


def contracts_dir(root: str) -> str:
    return os.path.join(root, ".dc-engine", CONTRACTS_SUBDIR)


def contract_path(root: str, cid: str) -> str:
    return os.path.join(contracts_dir(root), f"{cid}.json")


def cache_path(root: str, cid: str) -> str:
    return os.path.join(contracts_dir(root), f"{cid}.cache.json")


def save_contract(root: str, contract: DeltaContract) -> None:
    os.makedirs(contracts_dir(root), exist_ok=True)
    path = contract_path(root, contract.id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(contract.to_dict(), fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def load_contract(root: str, cid: str) -> DeltaContract | None:
    path = contract_path(root, cid)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return DeltaContract.from_dict(json.load(fh))


def list_saved(root: str) -> list[DeltaContract]:
    folder = contracts_dir(root)
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json") and not name.endswith(".cache.json"):
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                out.append(DeltaContract.from_dict(json.load(fh)))
    return out


def save_cache(root: str, cid: str, results: dict[str, dict[str, Any]]) -> None:
    os.makedirs(contracts_dir(root), exist_ok=True)
    path = cache_path(root, cid)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def load_cache(root: str, cid: str) -> dict[str, dict[str, Any]]:
    path = cache_path(root, cid)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def allocate_id(root: str, task: str) -> str:
    base = _slug(task)[:40] or "contract"
    cid = base
    n = 2
    while os.path.exists(contract_path(root, cid)):
        cid = f"{base}-{n}"
        n += 1
    return cid


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-")


def parse_probe_list(raw: Any) -> tuple[list[Probe], list[str]]:
    """Accept JSON objects, Probe instances, or pytest node-id strings."""
    probes: list[Probe] = []
    pytest_ids: list[str] = []
    if raw is None or raw == "":
        return probes, pytest_ids
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else []
    if not isinstance(raw, list):
        raw = [raw]
    for item in raw:
        if isinstance(item, str):
            pytest_ids.append(item)
        else:
            probes.append(Probe.from_dict(item))
    return probes, pytest_ids


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def executed_probe_text(probes: list[Probe]) -> str:
    """Exact setup/call strings the runner will exec/eval — for agent visibility."""
    if not probes:
        return ""
    chunks = ["  probes that will run (exact code):"]
    for p in probes:
        chunks.append(f"  --- {p.id} ---")
        if p.setup:
            chunks.append("  setup:")
            chunks.append(p.setup if p.setup.endswith("\n") else p.setup + "\n")
        chunks.append("  call:")
        chunks.append(p.call)
    return "\n".join(chunks)
