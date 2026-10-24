"""Import-time state of a package, for change-impact selection.

Many edits touch code that also runs while modules load (module constants, class tables built by metaclasses, a
parser that is exercised at import). Selection cannot treat those edits like ordinary function edits, because their
effect is baked into state that every test then reads. Instead of falling back to the full suite, we compare that
state directly: import the package at the base commit and in the working tree, fingerprint every module-level value
and every class attribute of classes defined in the package, and diff.

  no difference   the edit has no import-time effect; function-level selection is sound
  differences     the names whose values changed (STRICT_TIME_FORMATS, Hive.TIME_MAPPING, ...); tests are selected
                  by which code reads those names (impact.selection)

Fingerprints: plain data by value (sets/dicts order-free), functions by qualified name plus a hash of their code
(so a changed lambda inside a table counts), classes and modules by identity (classes are fingerprinted on their
own), other objects by type and attributes, memory addresses stripped.

Usage inside the subprocess: python importstate.py TREE PACKAGE_FILES.json OUT.json
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.abspath(__file__)
SNAPSHOT_TIMEOUT = 300
FORMAT = 9  # bump when fingerprints change; cached base snapshots of another format are rebuilt
# bookkeeping that changes whenever lines move, or that Python fills in itself
IGNORED_CLASS_KEYS = {"__dict__", "__weakref__", "__doc__", "__module__", "__qualname__", "__annotations__",
                      "__firstlineno__", "__static_attributes__", "__annotate__", "__annotate_func__",
                      "__annotations_cache__", "_abc_impl"}


SRC_DIRS = ("src", "lib")  # src layouts: the importable package lives in one of these, which is not a package itself


def layout_prefix(files) -> str:
    """'src/' or 'lib/' if the package files are under such a directory, else ''."""
    tops = {f.split("/", 1)[0] for f in files if "/" in f}
    return f"{next(iter(tops))}/" if len(tops) == 1 and next(iter(tops)) in SRC_DIRS else ""


def _module_name(rel: str) -> str | None:
    if not rel.endswith(".py"):
        return None
    parts = rel[:-3].split("/")
    if len(parts) > 1 and parts[0] in SRC_DIRS:
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or parts[-1] == "__main__":
        return None
    return ".".join(parts)


def _snapshot_main(tree: str, files_path: str, out_path: str) -> None:
    import functools
    import importlib
    import logging
    import re
    import types
    import warnings
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    sys.setrecursionlimit(10000)
    addr = re.compile(r" at 0x[0-9a-fA-F]+")
    files = json.load(open(files_path))
    # import-time code may draw random numbers (sympy's combinatorics uses randomised algorithms); generators seeded
    # from the OS would make the state differ on every run, so unseeded generators get a fixed seed here
    import random
    _orig_seed = random.Random.seed

    def _fixed_seed(self, a=None, version=2):
        return _orig_seed(self, 0 if a is None else a, version)
    random.Random.seed = _fixed_seed
    random.seed(0)
    # shift the heap so that values whose order depends on memory addresses (tuple(set_of_classes)) come out
    # differently between the base runs and can be recognised as order-unstable
    pad = [object() for _ in range(int(os.environ.get("DC_HEAP_PAD", "0")))]  # noqa: F841
    pad_bytes = [bytearray(64 * (i % 7 + 1)) for i in range(int(os.environ.get("DC_HEAP_PAD", "0")) // 3)]  # noqa: F841
    mods = {}
    errors = {}
    for rel in files:
        name = _module_name(rel)
        if not name:
            continue
        try:
            mods[name] = importlib.import_module(name)
        except BaseException as e:  # noqa: BLE001
            errors[name] = type(e).__name__

    def code_hash(co, h):
        h.update(co.co_code)
        h.update(repr(co.co_names).encode())
        for c in co.co_consts:
            if isinstance(c, types.CodeType):
                code_hash(c, h)
            else:
                h.update(addr.sub("", repr(c)).encode())

    sha = lambda x: hashlib.sha1(x.encode()).hexdigest()
    # Each object is fingerprinted once per snapshot and reused wherever it is reached again (sympy reaches the same
    # tables and singletons from thousands of attributes). A fingerprint is reused only if computing it met no cycle
    # and no depth cut-off, the two things that make it depend on the path it was reached by. Objects are kept
    # alive in `keep` so that a memoised id is never reused by another object.
    memo: dict = {}
    keep: list = []
    USE_MEMO = os.environ.get("DC_NO_MEMO") != "1"  # for checking the memoisation against plain fingerprinting
    impure = [0]

    def dig(v, depth, seen):
        t = type(v)
        if v is None or t in (bool, int, float, complex, str, bytes):
            r = t.__name__ + ":" + repr(v)
            return r if len(r) <= 40 else "h:" + sha(r)
        if depth > 80:
            impure[0] += 1
            return "<deep>"
        key = (id(v), mode["ordered"])
        got = memo.get(key) if USE_MEMO else None
        if got is not None:
            if got[1]:
                mode["seq"] = True
            return got[0]
        imp0, seq0 = impure[0], mode["seq"]
        mode["seq"] = False
        r = body(v, t, depth, seen)
        r = r if len(r) <= 40 else "h:" + sha(r)
        has_seq = mode["seq"]
        mode["seq"] = seq0 or has_seq
        if impure[0] == imp0:
            memo[key] = (r, has_seq)
            keep.append(v)
        return r

    def dict_body(name, items, depth, seen):
        return name + "{" + ",".join(sorted(sha(dig(k, depth + 1, seen) + "=" + dig(x, depth + 1, seen))
                                            for k, x in items)) + "}"

    def body(v, t, depth, seen):
        if isinstance(v, types.FunctionType):
            r = f"fn:{v.__module__}.{v.__qualname__};"
            if "<" in v.__qualname__:
                # lambdas and closures made at import time: their body lives inside a table or a factory call,
                # not in a function the line-level rule can see, so their code and captured values count
                h = hashlib.sha1()
                code_hash(v.__code__, h)
                r += h.hexdigest()
                if v.__defaults__:
                    r += dig(v.__defaults__, depth + 1, seen)
                for cell in v.__closure__ or ():
                    try:
                        r += dig(cell.cell_contents, depth + 1, seen)
                    except ValueError:
                        r += "<empty cell>"
            return r
        if isinstance(v, functools.partial):
            return "partial" + dig(v.func, depth + 1, seen) + dig(v.args, depth + 1, seen) + \
                dict_body("kw", sorted((v.keywords or {}).items()), depth + 1, seen)
        if isinstance(v, (types.BuiltinFunctionType, types.MethodWrapperType, types.WrapperDescriptorType)):
            return f"bf:{getattr(v, '__qualname__', repr(v))};"
        if isinstance(v, (classmethod, staticmethod)):
            return t.__name__ + dig(v.__func__, depth + 1, seen)
        if isinstance(v, property):
            return "prop" + "".join(dig(f, depth + 1, seen) for f in (v.fget, v.fset, v.fdel))
        if isinstance(v, type):
            return f"cls:{v.__module__}.{v.__qualname__};"
        if isinstance(v, types.ModuleType):
            return f"mod:{v.__name__};"
        if isinstance(v, types.MethodType):
            return "bound" + dig(v.__func__, depth + 1, seen)
        if id(v) in seen:
            impure[0] += 1
            return "<cycle>"
        seen = seen | {id(v)}
        if isinstance(v, (list, tuple)):
            mode["seq"] = True
            parts = [dig(x, depth + 1, seen) for x in v]
            return "[" + ",".join(parts) + "]" if mode["ordered"] else "[~" + ",".join(sorted(parts)) + "]"
        if isinstance(v, (set, frozenset)):
            return "{" + ",".join(sorted(dig(x, depth + 1, seen) for x in v)) + "}"
        if isinstance(v, dict):
            return dict_body(t.__name__, v.items(), depth, seen)
        try:
            d = vars(v)
        except TypeError:
            d = None
        slots = [n for c in t.__mro__ for n in (getattr(c, "__slots__", ()) or ())
                 if isinstance(n, str) and n not in ("__dict__", "__weakref__")]
        if d is not None or slots:
            state = dict(d or {})
            for n in slots:
                if hasattr(v, n):
                    state["slot:" + n] = getattr(v, n)
            # a cached hash (e.g. sympy's _mhash) is derived data whose value can depend on memory addresses
            try:
                own = hash(v)
            except Exception:  # noqa: BLE001
                own = None
            if own is not None:
                state = {k: x for k, x in state.items() if not (type(x) is int and x == own)}
            return f"obj:{t.__module__}.{t.__qualname__}" + dict_body("dict", state.items(), depth, seen)
        try:
            r = repr(v)
        except Exception:  # noqa: BLE001
            r = "<unrepr>"
        return f"{t.__module__}.{t.__qualname__}:{addr.sub('', r)};"

    mode = {"ordered": True, "seq": False}

    def one(v):
        # the two fingerprints differ only in how lists and tuples are hashed: without any, the second pass is skipped
        res = []
        mode["seq"] = False
        for ordered in (True, False):
            if not ordered and not mode["seq"]:
                break
            mode["ordered"] = ordered
            try:
                d = dig(v, 0, frozenset())
            except Exception as e:  # noqa: BLE001
                d = f"<error {type(e).__name__}>"
            res.append(sha(d)[:16])
        return res[0] if len(res) == 1 or res[0] == res[1] else f"{res[0]}~{res[1]}"

    out: dict[str, str] = {}
    overrides: list[str] = []
    done_classes = set()

    def do_class(modname, cls, prefix):
        if id(cls) in done_classes:
            return
        done_classes.add(id(cls))
        out[f"{modname}:{prefix}.__mro__"] = one(cls.__mro__)
        if type(cls) is not type:
            out[f"{modname}:{prefix}.__class__"] = one(type(cls))
        for k, v in list(vars(cls).items()):
            if k in IGNORED_CLASS_KEYS:
                continue
            key = f"{modname}:{prefix}.{k}"
            out[key] = one(v)
            if any(k in vars(b) for b in cls.__mro__[1:] if b is not object):
                overrides.append(key)
            if isinstance(v, type) and v.__module__ == modname and v.__qualname__ == f"{cls.__qualname__}.{k}":
                do_class(modname, v, f"{prefix}.{k}")

    for name, m in mods.items():
        for k, v in list(vars(m).items()):
            if k.startswith("__") and k.endswith("__"):
                continue
            out[f"{name}:{k}"] = one(v)
            if isinstance(v, type) and v.__module__ == name and v.__qualname__ == k:
                do_class(name, v, k)
    json.dump({"state": out, "overrides": sorted(overrides), "errors": errors}, open(out_path, "w"))


def snapshot(tree: str, files: list[str], python: str, heap_pad: int = 0) -> dict | None:
    """Import-time state of `tree` (only `tree` importable). None if the snapshot could not be taken."""
    fd, files_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    out_path = files_path + ".out"
    try:
        json.dump(files, open(files_path, "w"))
        path = os.pathsep.join([tree] + [os.path.join(tree, d) for d in SRC_DIRS if os.path.isdir(os.path.join(tree, d))
                                         and not os.path.exists(os.path.join(tree, d, "__init__.py"))])
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": path, "HOME": os.environ.get("HOME", "/tmp"),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": str(heap_pad % 97),
               "DC_HEAP_PAD": str(heap_pad)}
        r = subprocess.run([python, HERE, tree, files_path, out_path], cwd=tree, env=env, capture_output=True,
                           text=True, timeout=SNAPSHOT_TIMEOUT)
        if r.returncode != 0 or not os.path.exists(out_path):
            return None
        return json.load(open(out_path))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    finally:
        for p in (files_path, out_path):
            if os.path.exists(p):
                os.remove(p)


def cache_key(root: str, tops: list[str], python: str, files: list[str] | None = None) -> str:
    """Content of the base commit's package directories (git tree hashes, so a copy of the same code in another
    repository matches) and the interpreter (bytecode differs between versions)."""
    trees = [subprocess.run(["git", "-C", root, "rev-parse", f"HEAD:{t}"], capture_output=True, text=True).stdout.strip()
             for t in tops]
    ver = subprocess.run([python, "-c", "import sys; print(sys.version)"], capture_output=True, text=True).stdout.strip()
    return hashlib.sha1(json.dumps([trees, ver, sorted(files or [])]).encode()).hexdigest()


def base_snapshot(root: str, files: list[str], python: str, cache_path: str) -> dict | None:
    """Snapshot of the HEAD commit (exported to a temporary directory), cached per commit."""
    tops = sorted({f.split("/", 1)[0] for f in files})
    head = cache_key(root, tops, python, files)
    try:
        cached = json.load(open(cache_path))
        if cached.get("head") == head and cached.get("format") == FORMAT:
            return cached["snapshot"]
    except (OSError, ValueError, KeyError):
        pass
    tmp = tempfile.mkdtemp(prefix="dc-base-")
    try:
        arch = subprocess.run(["git", "-C", root, "archive", "HEAD", *tops], capture_output=True)
        if arch.returncode != 0:
            return None
        subprocess.run(["tar", "-x", "-C", tmp], input=arch.stdout, capture_output=True)
        snap = snapshot(tmp, files, python)
        unstable: set[str] = set()
        for pad in (5003, 20011):
            if snap is None:
                break
            again = snapshot(tmp, files, python, heap_pad=pad)
            if again is None:
                snap = None
                break
            unstable |= {k for k, v in snap["state"].items() if again["state"].get(k) != v}
        if snap is not None:
            snap["unstable"] = sorted(unstable)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if snap is not None:
        try:
            os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
            json.dump({"head": head, "format": FORMAT, "snapshot": snap}, open(cache_path, "w"))
        except OSError:
            pass
    return snap


def _same(a: str | None, b: str | None, unstable: bool) -> bool:
    """Fingerprints are 'ordered' or 'ordered~unordered'; unstable keys (sequence order differs between two
    imports of the same code, e.g. tuple(set_of_classes)) are compared without order."""
    if a == b:
        return True
    if a is None or b is None or not unstable:
        return False
    return a.split("~")[-1] == b.split("~")[-1]


def diff(base: dict, cur: dict, ignore_added: set[str] = frozenset()) -> dict[str, list[str]]:
    """changed: keys whose value changed or disappeared, plus keys that are new (except module-level names in
    `ignore_added`: new top-level functions and imports, which existing code cannot be reading).
    added_class_attrs: the new class-attribute keys (their classes may dispatch to them by computed name).
    errors: modules that import at base but not now."""
    b, c = base["state"], cur["state"]
    unstable = set(base.get("unstable", []))
    changed = sorted(k for k in b if not _same(b[k], c.get(k), k in unstable))
    added = sorted(k for k in c if k not in b)
    added_class = [k for k in added if "." in k.split(":", 1)[1]]
    added_mod = [k for k in added if "." not in k.split(":", 1)[1] and k.split(":", 1)[1] not in ignore_added]
    errors = sorted(set(cur.get("errors", {})) - set(base.get("errors", {})))
    return {"changed": changed + added_mod + added_class, "added_class_attrs": added_class, "errors": errors}


if __name__ == "__main__":
    _snapshot_main(sys.argv[1], sys.argv[2], sys.argv[3])
