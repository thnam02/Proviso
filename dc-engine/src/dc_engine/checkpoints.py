"""Score-gated snapshots of the working tree.

A checkpoint is taken when a contract check *beats* the best score so
far. In git we store a hidden ref (`refs/dc/<id>/cp-<n>`) from
`git stash create` so the user's branch and stash list stay untouched.
Without git we copy files into `.dc-engine/checkpoints/<id>/<n>/`.

Restore only overwrites files that differ; it never deletes untracked
files the checkpoint doesn't know about.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from . import baseline
from .indexer import IGNORE_DIRS

META_NAME = "meta.json"


def _meta_path(root: str, cid: str) -> str:
    return os.path.join(root, ".dc-engine", "checkpoints", cid, META_NAME)


def _copy_dir(root: str, cid: str, n: int) -> str:
    return os.path.join(root, ".dc-engine", "checkpoints", cid, str(n))


def load_meta(root: str, cid: str) -> dict[str, Any]:
    path = _meta_path(root, cid)
    if not os.path.isfile(path):
        return {"best_n": 0, "best_satisfied": -1, "best_scorable": 0, "items": []}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data.setdefault("items", [])
            data.setdefault("best_n", 0)
            data.setdefault("best_satisfied", -1)
            data.setdefault("best_scorable", 0)
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"best_n": 0, "best_satisfied": -1, "best_scorable": 0, "items": []}


def _save_meta(root: str, cid: str, meta: dict[str, Any]) -> None:
    path = _meta_path(root, cid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def best_score(meta: dict[str, Any]) -> float:
    sat, sco = meta.get("best_satisfied", -1), meta.get("best_scorable", 0)
    if sat < 0 or not sco:
        return -1.0
    return sat / sco


def maybe_snapshot(root: str, cid: str, satisfied: int, scorable: int) -> int | None:
    """Save a checkpoint if this score beats the best. Returns new n, or None."""
    score = (satisfied / scorable) if scorable else 1.0
    meta = load_meta(root, cid)
    if score <= best_score(meta):
        return None
    n = int(meta.get("best_n") or 0) + 1
    # if items skipped numbers, still increment from max n
    items = meta.get("items") or []
    if items:
        n = max(n, max(int(i.get("n") or 0) for i in items) + 1)
    ref = _save_tree(root, cid, n)
    item = {"n": n, "satisfied": satisfied, "scorable": scorable,
            "score": score, "ref": ref}
    items.append(item)
    meta["items"] = items
    meta["best_n"] = n
    meta["best_satisfied"] = satisfied
    meta["best_scorable"] = scorable
    _save_meta(root, cid, meta)
    return n


def list_checkpoints(root: str, cid: str) -> str:
    meta = load_meta(root, cid)
    items = meta.get("items") or []
    if not items:
        return f"(no checkpoints for {cid})"
    best = meta.get("best_n")
    lines = []
    for it in items:
        n = it.get("n")
        mark = "  (best)" if n == best else ""
        lines.append(f"{n}  {it.get('satisfied')}/{it.get('scorable')}  "
                     f"score {it.get('score'):.1f}  {it.get('ref')}{mark}")
    return "\n".join(lines)


def restore(root: str, cid: str, n: int) -> tuple[int, str]:
    """Restore checkpoint `n`. Returns (files_written, message)."""
    meta = load_meta(root, cid)
    item = next((i for i in meta.get("items") or [] if int(i.get("n") or 0) == n), None)
    if item is None:
        return 0, f"✗ no checkpoint {n} for {cid}"
    ref = str(item.get("ref") or "")
    if baseline.is_git_root(root) and ref.startswith("refs/"):
        written = _restore_git(root, ref)
    else:
        src = _copy_dir(root, cid, n)
        if not os.path.isdir(src):
            return 0, f"✗ checkpoint {n} files missing"
        written = _restore_copy(root, src)
    return written, f"✓ restored checkpoint {n} ({written} file{'s' if written != 1 else ''})"


def _save_tree(root: str, cid: str, n: int) -> str:
    if baseline.is_git_root(root):
        created = baseline._git(root, "stash", "create")
        sha = (created.stdout or "").strip() if created.returncode == 0 else ""
        if not sha:
            head = baseline._git(root, "rev-parse", "HEAD")
            sha = (head.stdout or "").strip()
        if not sha:
            raise RuntimeError("could not snapshot working tree for checkpoint")
        ref = f"refs/dc/{cid}/cp-{n}"
        updated = baseline._git(root, "update-ref", ref, sha)
        if updated.returncode != 0:
            raise RuntimeError(updated.stderr.strip() or "git update-ref failed")
        return ref
    dest = _copy_dir(root, cid, n)
    if os.path.exists(dest):
        shutil.rmtree(dest, ignore_errors=True)
    _copy_files(root, dest)
    return dest.replace(os.sep, "/")


def _copy_files(root: str, dest: str) -> None:
    """Copy non-ignored files (same skip list as a non-git baseline)."""
    def ignore(path: str, names: list[str]) -> list[str]:
        return [n for n in names
                if n in IGNORE_DIRS or n.endswith(".egg-info") or n == ".DS_Store"]
    shutil.copytree(root, dest, ignore=ignore, symlinks=True)


def _restore_git(root: str, ref: str) -> int:
    diff = baseline._git(root, "diff", "--name-only", ref)
    names = [p for p in (diff.stdout or "").splitlines() if p.strip()]
    if not names:
        return 0
    checked = baseline._git(root, "checkout", ref, "--", *names)
    if checked.returncode != 0:
        raise RuntimeError(checked.stderr.strip() or "git checkout failed")
    return len(names)


def _restore_copy(root: str, src: str) -> int:
    written = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            src_path = os.path.join(dirpath, fn)
            rel = os.path.relpath(src_path, src)
            dest_path = os.path.join(root, rel)
            try:
                with open(src_path, "rb") as fh:
                    new = fh.read()
                old = b""
                if os.path.isfile(dest_path):
                    with open(dest_path, "rb") as fh:
                        old = fh.read()
                if old != new:
                    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
                    with open(dest_path, "wb") as fh:
                        fh.write(new)
                    written += 1
            except OSError:
                continue
    return written


