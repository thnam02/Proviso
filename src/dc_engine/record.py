"""Record Proviso's coverage map (v2) for a repository: one fresh interpreter per test file, so that results cached
by one file's tests (memoised values, compiled-statement caches) cannot hide another file's dependencies, then merge.

  python -m dc_engine.record --root TREE --pkg PACKAGE_DIR --out covmap.json [--workers N] [--before-test MOD:FN]
                             [--] [pytest targets ...]

Each file runs `python -m pytest -p dc_engine.covplugin FILE`; the partial maps are merged: tests are disjoint,
fixture records with the same key (session-scoped fixtures, the "<session>" record) and the global (package import)
record are unions.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)


def collect_files(root: str, python: str, targets: list[str], env: dict) -> list[str]:
    r = subprocess.run([python, "-m", "pytest", "--collect-only", "-qq", "-p", "no:cacheprovider",
                        "--continue-on-collection-errors", *targets], cwd=root, env=env, capture_output=True, text=True)
    files = []
    for line in r.stdout.splitlines():
        f = line.split("::", 1)[0].split(":", 1)[0].strip()
        # any file pytest collects tests from: test modules, and data files that a conftest turns into tests
        # (e.g. golden-output files); each gets its own interpreter like a test module
        if f and os.path.isfile(os.path.join(root, f)) and f not in files:
            files.append(f)
    return files


def merge(parts: list[dict]) -> dict:
    out: dict = {"__fixtures__": {}, "__global__": {"funcs": []}}
    glob: set = set()
    for m in parts:
        for k, v in m.items():
            if k == "__fixtures__":
                for fk, r in v.items():
                    cur = out["__fixtures__"].setdefault(fk, {"funcs": set(), "classes": set(), "always": False})
                    cur["funcs"] |= {tuple(x) for x in r["funcs"]}
                    cur["classes"] |= set(r["classes"])
                    cur["always"] = cur["always"] or r["always"]
            elif k == "__global__":
                glob |= {tuple(x) for x in v["funcs"]}
            else:
                out[k] = v
    out["__fixtures__"] = {k: {"funcs": sorted(r["funcs"]), "classes": sorted(r["classes"]), "always": r["always"]}
                           for k, r in out["__fixtures__"].items()}
    out["__global__"] = {"funcs": sorted(glob)}
    return out


def record(root: str, pkg: str, out: str, python: str | None = None, targets: list[str] | None = None,
           workers: int | None = None, before_test: str = "", extra_args: list[str] | None = None,
           env: dict | None = None) -> dict:
    python = python or sys.executable
    root = os.path.abspath(root)
    base_env = dict(env or os.environ)
    base_env["PYTHONPATH"] = os.pathsep.join([SRC, *[p for p in base_env.get("PYTHONPATH", "").split(os.pathsep) if p]])
    base_env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    files = collect_files(root, python, targets or [], base_env)
    tmp = tempfile.mkdtemp(prefix="dc-record-")

    def one(i_f):
        i, f = i_f
        part = os.path.join(tmp, f"part{i}.json")
        e = {**base_env, "COVMAP_OUT": part, "COVMAP_PKG": pkg}
        if before_test:
            e["COVMAP_BEFORE_TEST"] = before_test
        subprocess.run([python, "-m", "pytest", "-p", "dc_engine.covplugin", "-p", "no:cacheprovider", "-q",
                        "--tb=no", "-p", "no:randomly", *(extra_args or []), f], cwd=root, env=e, capture_output=True)
        try:
            return json.load(open(part))
        except (OSError, ValueError):
            return {}

    with ThreadPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 1)) as ex:
        parts = list(ex.map(one, enumerate(files)))
    m = merge(parts)
    json.dump(m, open(out, "w"))
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m dc_engine.record")
    ap.add_argument("--root", default=".")
    ap.add_argument("--pkg", required=True, help="package directory relative to the root, e.g. sqlglot or lib/sqlalchemy")
    ap.add_argument("--out", required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--before-test", default="")
    ap.add_argument("targets", nargs="*")
    a = ap.parse_args(argv)
    m = record(a.root, a.pkg, a.out, a.python, a.targets, a.workers, a.before_test)
    print(json.dumps({"tests": sum(1 for k in m if not k.startswith("__")), "fixture_records": len(m["__fixtures__"]),
                      "import_funcs": len(m["__global__"]["funcs"])}))


if __name__ == "__main__":
    main()
