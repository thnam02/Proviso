"""Create, validate, check and close delta contracts.

Kept off Engine so the Phase 1 facade stays small; Engine methods
delegate here. Validation against the baseline *before* the agent edits
is the point: a wrong picture of current behaviour is rejected, not
silently scored later.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from . import active, baseline, checkpoints, probes
from .contracts import (
    CheckReport, CreateResult, DeltaContract, Probe, allocate_id, cache_path,
    load_cache, load_contract, list_saved, now_iso, parse_probe_list,
    save_cache, save_contract,
)

if TYPE_CHECKING:
    from .engine import Engine

_MAX_REPORT_LINES = 15


def create_contract(engine: Engine, task: str, targets: list[str],
                    must_change: Any, must_preserve: Any = None,
                    pytest_ids: list[str] | None = None) -> CreateResult:
    engine.ensure_fresh()
    change, extra_py = parse_probe_list(must_change)
    preserve, extra_py2 = parse_probe_list(must_preserve)
    py_ids = list(pytest_ids or []) + extra_py + extra_py2

    errors: list[str] = []
    resolved: list[str] = []
    for ref in targets or []:
        sym, err = engine.resolve_ref(ref)
        if err:
            errors.append(err)
        else:
            resolved.append(sym.qualname)

    for p in change:
        if not p.call:
            errors.append(f"✗ must_change probe {p.id!r} is missing `call`")
        if p.expect_new is None:
            errors.append(f"✗ must_change probe {p.label()} needs expect_new")
    for p in preserve:
        if not p.call:
            errors.append(f"✗ must_preserve probe {p.id!r} is missing `call`")

    if errors:
        return CreateResult(False, None, "\n".join(errors))

    cid = allocate_id(engine.root, task)
    try:
        ref = baseline.snapshot(engine.root, cid)
    except Exception as exc:
        return CreateResult(False, None, f"✗ could not freeze baseline: {exc}")

    tree = baseline.baseline_path(engine.root, cid)
    timeout = engine.probe_timeout
    cache: dict[str, dict] = {}
    flaky: list[str] = []
    seen_ids: set[str] = set()

    def unique(p: Probe) -> Probe:
        pid, n = p.id, 2
        while pid in seen_ids:
            pid = f"{p.id}-{n}"
            n += 1
        seen_ids.add(pid)
        if pid != p.id:
            p.id = pid
        return p

    change = [unique(p) for p in change]
    preserve = [unique(p) for p in preserve]
    change_ids = {p.id for p in change}

    try:
        for p in change + preserve:
            result, is_flaky = probes.run_twice(tree, p, timeout)
            cache[p.id] = result.to_dict()
            if is_flaky:
                flaky.append(p.id)
                continue
            if p.id in change_ids:
                if p.expect_old is not None and not probes.matches_expect(result, p.expect_old):
                    errors.append(
                        f"✗ {p.label()}: your understanding of the current behaviour "
                        f"is wrong: got {result.display()}")
                if p.expect_new is not None and probes.matches_expect(result, p.expect_new):
                    errors.append(
                        f"✗ {p.label()}: already matches expect_new "
                        f"({p.expect_new.describe()}) — nothing to change")
    except Exception as exc:
        baseline.close(engine.root, cid)
        return CreateResult(False, None, f"✗ probe runner failed: {exc}")

    if errors:
        baseline.close(engine.root, cid)
        return CreateResult(False, None, "\n".join(errors))

    contract = DeltaContract(
        id=cid, task=task, targets=resolved, must_change=change,
        must_preserve=preserve, pytest_ids=py_ids, baseline_ref=ref,
        created_at=now_iso(), status="open", flaky=flaky,
    )
    save_contract(engine.root, contract)
    save_cache(engine.root, cid, cache)
    active.set_active(engine.root, cid)
    lines = [
        f"✓ contract created: {cid}",
        f"  task: {task}",
        f"  targets: {', '.join(resolved) or '(none)'}",
        f"  must_change: {len(change)}  must_preserve: {len(preserve)}"
        + (f"  pytest: {len(py_ids)}" if py_ids else ""),
        f"  baseline: {ref[:12] if len(ref) > 12 else ref}",
    ]
    if flaky:
        lines.append(f"  ⚠ flaky (excluded from scoring): {', '.join(flaky)}")
    return CreateResult(True, cid, "\n".join(lines), contract)


def check_contract(engine: Engine, cid: str) -> CheckReport | str:
    contract = load_contract(engine.root, cid)
    if contract is None:
        return f"✗ no contract '{cid}'"
    if contract.status == "closed":
        return f"✗ contract {cid} is closed"
    tree_new = engine.root
    tree_old = baseline.baseline_path(engine.root, cid)
    timeout = engine.probe_timeout
    cache = load_cache(engine.root, cid)
    flaky = set(contract.flaky)
    lines: list[str] = []
    satisfied = 0
    scorable = 0

    def old_result(p: Probe) -> probes.ProbeResult:
        cached = probes.ProbeResult.from_dict(cache.get(p.id))
        if cached is not None:
            return cached
        if os.path.isdir(tree_old):
            return probes.run_probe(tree_old, p, timeout)
        return probes.ProbeResult(kind="error", exc_msg="no baseline")

    def note(ok: bool, text: str) -> None:
        nonlocal satisfied, scorable
        scorable += 1
        if ok:
            satisfied += 1
        lines.append(("✓ " if ok else "✗ ") + text)

    for p in contract.must_change:
        if p.id in flaky:
            lines.append(f"⚠ flaky: {p.label()} (excluded)")
            continue
        old = old_result(p)
        new = probes.run_probe(tree_new, p, timeout)
        want = p.expect_new
        if want is not None and probes.matches_expect(new, want):
            note(True, f"{p.label()} {want.describe()} (was: {old.short()})")
        elif old.same_as(new):
            note(False, f"not changed: {p.label()}  still {old.display()}")
        else:
            expected = want.describe() if want else "?"
            note(False, (f"changed wrongly: {p.label()}  "
                         f"old={old.display()}  new={new.display()}  expected {expected}"))

    for p in contract.must_preserve:
        if p.id in flaky:
            lines.append(f"⚠ flaky: {p.label()} (excluded)")
            continue
        old = old_result(p)
        new = probes.run_probe(tree_new, p, timeout)
        if old.same_as(new):
            note(True, f"preserved: {p.label()}")
        else:
            note(False, f"unintended: {p.label()}  old={old.display()}  new={new.display()}")

    if contract.pytest_ids:
        old_py = probes.run_pytest_ids(tree_old, contract.pytest_ids) if os.path.isdir(tree_old) else None
        new_py = probes.run_pytest_ids(tree_new, contract.pytest_ids)
        if old_py is None or new_py is None:
            lines.append("⚠ pytest not importable; node ids skipped")
        else:
            for nid in contract.pytest_ids:
                o, n = old_py.get(nid, "fail"), new_py.get(nid, "fail")
                if o == n:
                    note(True, f"pytest {nid} still {n}")
                else:
                    note(False, f"pytest {nid}  old={o}  new={n}")

    score = (satisfied / scorable) if scorable else 1.0
    header = f"contract {cid}: {satisfied}/{scorable} satisfied  score { _fmt_score(score) }"
    extras: list[str] = []
    meta = checkpoints.load_meta(engine.root, cid)
    prev_best = checkpoints.best_score(meta)
    if prev_best >= 0 and score < prev_best - 1e-12:
        bsat, bsco, bn = meta.get("best_satisfied"), meta.get("best_scorable"), meta.get("best_n")
        extras.append(
            f"⚠ score dropped {bsat}/{bsco} → {satisfied}/{scorable} since "
            f"checkpoint {bn} (best). dc_restore_checkpoint to roll back.")
    else:
        try:
            snapped = checkpoints.maybe_snapshot(engine.root, cid, satisfied, scorable)
        except Exception as exc:
            extras.append(f"⚠ checkpoint failed: {exc}")
            snapped = None
        if snapped:
            extras.append(f"✓ checkpoint {snapped} saved")
    body = extras + lines
    room = _MAX_REPORT_LINES - 1
    if len(body) > room:
        extra_n = len(body) - (room - 1)
        body = body[: room - 1] + [f"  … +{extra_n} more"]
    report_lines = [header] + body
    return CheckReport(cid, satisfied, scorable, score, report_lines)


def get_contract(engine: Engine, cid: str) -> str:
    contract = load_contract(engine.root, cid)
    if contract is None:
        return f"✗ no contract '{cid}'"
    return _render(contract)


def list_contracts(engine: Engine) -> str:
    items = list_saved(engine.root)
    if not items:
        return "(no contracts)"
    return "\n".join(
        f"{c.id}  {c.status}  {c.task}" + (f"  [{', '.join(c.targets)}]" if c.targets else "")
        for c in items
    )


def close_contract(engine: Engine, cid: str) -> str:
    contract = load_contract(engine.root, cid)
    if contract is None:
        return f"✗ no contract '{cid}'"
    baseline.close(engine.root, cid)
    cache = cache_path(engine.root, cid)
    if os.path.isfile(cache):
        try:
            os.remove(cache)
        except OSError:
            pass
    contract.status = "closed"
    save_contract(engine.root, contract)
    active.clear_active(engine.root, cid)
    return f"✓ closed {cid} (baseline removed)"


def amend_contract(engine: Engine, cid: str, add_targets: Any = None,
                   add_must_change: Any = None, add_must_preserve: Any = None,
                   add_pytest_ids: list[str] | None = None) -> CreateResult:
    """Add targets/probes to an open contract; validate new probes on the baseline."""
    engine.ensure_fresh()
    contract = load_contract(engine.root, cid)
    if contract is None:
        return CreateResult(False, cid, f"✗ no contract '{cid}'")
    if contract.status == "closed":
        return CreateResult(False, cid, f"✗ contract {cid} is closed")

    extra_targets = list(add_targets or [])
    if isinstance(add_targets, str):
        extra_targets = [add_targets] if add_targets.strip() else []
    change, extra_py = parse_probe_list(add_must_change)
    preserve, extra_py2 = parse_probe_list(add_must_preserve)
    py_ids = list(add_pytest_ids or []) + extra_py + extra_py2

    errors: list[str] = []
    resolved: list[str] = []
    existing = set(contract.targets)
    for ref in extra_targets:
        if not ref or ref in existing:
            if ref in existing:
                resolved.append(ref)
            continue
        sym, err = engine.resolve_ref(ref)
        if err:
            errors.append(err)
        else:
            resolved.append(sym.qualname)
            existing.add(sym.qualname)

    for p in change:
        if not p.call:
            errors.append(f"✗ must_change probe {p.id!r} is missing `call`")
        if p.expect_new is None:
            errors.append(f"✗ must_change probe {p.label()} needs expect_new")
    for p in preserve:
        if not p.call:
            errors.append(f"✗ must_preserve probe {p.id!r} is missing `call`")
    if not extra_targets and not change and not preserve and not py_ids:
        errors.append("✗ amend: give add_targets, add_must_change or add_must_preserve")
    if errors:
        return CreateResult(False, cid, "\n".join(errors))

    tree = baseline.baseline_path(engine.root, cid)
    if not os.path.isdir(tree):
        return CreateResult(False, cid, f"✗ baseline for {cid} is gone; create a new contract")

    seen = {p.id for p in contract.must_change + contract.must_preserve}

    def unique(p: Probe) -> Probe:
        pid, n = p.id, 2
        while pid in seen:
            pid = f"{p.id}-{n}"
            n += 1
        seen.add(pid)
        p.id = pid
        return p

    change = [unique(p) for p in change]
    preserve = [unique(p) for p in preserve]
    change_ids = {p.id for p in change}
    timeout = engine.probe_timeout
    cache = load_cache(engine.root, cid)
    flaky = list(contract.flaky)

    try:
        for p in change + preserve:
            result, is_flaky = probes.run_twice(tree, p, timeout)
            cache[p.id] = result.to_dict()
            if is_flaky:
                flaky.append(p.id)
                continue
            if p.id in change_ids:
                if p.expect_old is not None and not probes.matches_expect(result, p.expect_old):
                    errors.append(
                        f"✗ {p.label()}: your understanding of the current behaviour "
                        f"is wrong: got {result.display()}")
                if p.expect_new is not None and probes.matches_expect(result, p.expect_new):
                    errors.append(
                        f"✗ {p.label()}: already matches expect_new "
                        f"({p.expect_new.describe()}) — nothing to change")
    except Exception as exc:
        return CreateResult(False, cid, f"✗ probe runner failed: {exc}")
    if errors:
        return CreateResult(False, cid, "\n".join(errors))

    contract.targets = list(dict.fromkeys(contract.targets + resolved))
    contract.must_change.extend(change)
    contract.must_preserve.extend(preserve)
    contract.pytest_ids = list(dict.fromkeys(contract.pytest_ids + py_ids))
    contract.flaky = flaky
    save_contract(engine.root, contract)
    save_cache(engine.root, cid, cache)
    bits = []
    if resolved:
        bits.append(f"targets +{len(resolved)}")
    if change:
        bits.append(f"must_change +{len(change)}")
    if preserve:
        bits.append(f"must_preserve +{len(preserve)}")
    if py_ids:
        bits.append(f"pytest +{len(py_ids)}")
    report = f"✓ amended {cid}: {', '.join(bits) or 'no-op'}"
    if flaky:
        report += f"\n  ⚠ flaky: {', '.join(flaky)}"
    return CreateResult(True, cid, report, contract)


def list_checkpoints(engine: Engine, cid: str) -> str:
    if load_contract(engine.root, cid) is None:
        return f"✗ no contract '{cid}'"
    return checkpoints.list_checkpoints(engine.root, cid)


def restore_checkpoint(engine: Engine, cid: str, n: int) -> str:
    if load_contract(engine.root, cid) is None:
        return f"✗ no contract '{cid}'"
    try:
        _, msg = checkpoints.restore(engine.root, cid, n)
    except Exception as exc:
        return f"✗ restore failed: {exc}"
    if msg.startswith("✓"):
        engine.ensure_fresh(force=True)
    return msg


def auto_check_line(engine: Engine, budget: float = 15.0) -> str:
    """One-line active-contract status, or a skip note if it exceeds `budget`."""
    import time
    cid = active.get_active_id(engine.root)
    if not cid:
        return ""
    t0 = time.monotonic()
    try:
        report = check_contract(engine, cid)
    except Exception as exc:
        return f"contract {cid}: check failed ({exc})"
    if time.monotonic() - t0 > budget:
        return f"contract {cid}: check skipped (>15s)"
    if isinstance(report, str):
        return report.splitlines()[0] if report else ""
    return report.one_line()


def _render(c: DeltaContract) -> str:
    lines = [
        f"contract {c.id}  status={c.status}",
        f"task: {c.task}",
        f"targets: {', '.join(c.targets) or '(none)'}",
        f"baseline: {c.baseline_ref}  created: {c.created_at}",
    ]
    if c.must_change:
        lines.append("must_change:")
        for p in c.must_change:
            exp = p.expect_new.describe() if p.expect_new else ""
            lines.append(f"  {p.label()}  {p.call}" + (f"  → {exp}" if exp else ""))
    if c.must_preserve:
        lines.append("must_preserve:")
        for p in c.must_preserve:
            lines.append(f"  {p.label()}  {p.call}")
    if c.pytest_ids:
        lines.append("pytest: " + ", ".join(c.pytest_ids))
    if c.flaky:
        lines.append("flaky: " + ", ".join(c.flaky))
    return "\n".join(lines)


def _fmt_score(score: float) -> str:
    if abs(score - round(score, 1)) < 1e-9:
        return f"{score:.1f}"
    return f"{score:.2f}"
