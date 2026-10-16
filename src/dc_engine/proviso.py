"""Proviso: trajectory-mined behavioural checks for coding agents.

Three hook events (Claude Code hook JSON on stdin, see hooks.py):

    proviso-context  UserPromptSubmit  instruction line + up to ~1,500 tokens of matched code
    proviso-capture  PostToolUse/Bash  records each Python execution the agent ran, re-run in
                                       isolation, so its output is what the agent just saw
    proviso-verify   Stop              replays every recorded execution on the current code,
                                       runs the existing tests the change can affect, and
                                       blocks only for changes the agent did not see

The agent pays no model requests when nothing unintended changed. Design and evidence:
research/phase0 (the comparison point is the agent's last observation, not the original code).

Configuration: .dc-engine/proviso.json, written by the eval harness or by hand:
    {"context": true, "trajectory": true, "tests": true, "python": "/path/to/venv/python"}
"""

from __future__ import annotations

import difflib
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any

from .jsonio import exclusive_lock

STATE_DIR = ".dc-engine"
MAX_BLOCKS = 2
MAX_ITEMS = 3
PROBE_TIMEOUT = 20
TESTS_TIMEOUT = 240
CONTEXT_CHARS = 6000  # ~1,500 tokens at 4 chars/token

INSTRUCTION = (
    "Proviso is active in this session. When you finish, it {what} and tells you only if "
    "something changed that you did not intend. You do not need to re-run the whole test suite "
    "yourself."
)

# --------------------------------------------------------------------------- config / state


def _dir(root: str) -> str:
    d = os.path.join(root, STATE_DIR)
    os.makedirs(d, exist_ok=True)
    gi = os.path.join(d, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as fh:
            fh.write("*\n")
    return d


def load_config(root: str) -> dict[str, Any]:
    cfg = {"context": True, "trajectory": True, "tests": True, "python": ""}
    path = os.path.join(root, STATE_DIR, "proviso.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update(data)
    except (OSError, ValueError):
        pass
    cfg["python"] = (cfg.get("python") or os.environ.get("DC_PROBE_PYTHON")
                     or _venv_python(root) or sys.executable)
    return cfg


def _venv_python(root: str) -> str | None:
    venv = os.environ.get("VIRTUAL_ENV")
    for cand in ([os.path.join(venv, "bin", "python")] if venv else []) + [
        os.path.join(root, ".venv", "bin", "python"), os.path.join(root, "venv", "bin", "python")]:
        if os.path.isfile(cand):
            return cand
    return None


def _state_path(root: str) -> str:
    return os.path.join(_dir(root), "proviso_state.json")


def load_state(root: str) -> dict[str, Any]:
    try:
        with open(_state_path(root), encoding="utf-8") as fh:
            s = json.load(fh)
            return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(root: str, state: dict[str, Any]) -> None:
    path = _state_path(root)
    with exclusive_lock(path):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
        os.replace(tmp, path)


def log_event(root: str, rec: dict[str, Any]) -> None:
    rec = {"t": round(time.time(), 3), **rec}
    path = os.path.join(_dir(root), "proviso.log")
    with exclusive_lock(path):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- git helpers


def _git(root: str, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout)


def is_test_path(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    base = parts[-1]
    return ("tests" in parts or "test" in parts or base.startswith("test_")
            or base.endswith("_test.py") or base == "conftest.py")


def changed_source_files(root: str) -> list[str]:
    """Python source files (not tests) that differ from HEAD, including new files."""
    out = set()
    r = _git(root, "diff", "--name-only", "HEAD")
    out.update(l.strip() for l in r.stdout.splitlines() if l.strip())
    r = _git(root, "ls-files", "--others", "--exclude-standard")
    out.update(l.strip() for l in r.stdout.splitlines() if l.strip())
    return sorted(p for p in out if p.endswith(".py") and not is_test_path(p)
                  and not p.startswith(STATE_DIR))


def source_state(root: str) -> str:
    """Hash of the working tree's source changes against HEAD (tests excluded)."""
    files = changed_source_files(root)
    h = hashlib.sha1()
    for rel in files:
        h.update(rel.encode())
        try:
            with open(os.path.join(root, rel), "rb") as fh:
                h.update(fh.read())
        except OSError:
            h.update(b"<deleted>")
    return h.hexdigest()[:16]


def repo_packages(root: str) -> list[str]:
    """Top-level importable packages of the repository (flat or src/ layout)."""
    pk = []
    for base in (root, os.path.join(root, "src")):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name)
            if (os.path.isdir(p) and os.path.isfile(os.path.join(p, "__init__.py"))
                    and name not in ("tests", "test", "docs", "examples", "benchmarks")
                    and not name.startswith(".")):
                pk.append(name)
    return pk


# --------------------------------------------------------------------------- probe extraction

_PYBIN = r"(?:python3?(?:\.\d+)?|\S*/bin/python3?|\$\{?V\}?(?:/python)?)"
_HEREDOC = re.compile(_PYBIN + r"\s+-\s+(?:2>&1\s*)?<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n\1[ \t]*(?:\n|$)", re.S)
_DASHC = re.compile(_PYBIN + r"\s+-c\s+")
_SCRIPT = re.compile(_PYBIN + r"\s+((?:/|\./|\w)[\w./-]*\.py)\b")
_WRITES = re.compile(r"open\([^)]*['\"][wax]\+?b?['\"]|\.write_text\(|\.write_bytes\(|\.write\(|shutil\.(?:copy|move)|os\.(?:remove|rename|replace)")


def _quoted(s: str, i: int) -> str | None:
    if i >= len(s) or s[i] not in "\"'":
        return None
    q, j, buf = s[i], i + 1, []
    while j < len(s):
        c = s[j]
        if q == '"' and c == "\\" and j + 1 < len(s) and s[j + 1] in '"\\$`':
            buf.append(s[j + 1]); j += 2; continue
        if c == q:
            return "".join(buf)
        buf.append(c); j += 1
    return None


def extract_probes(command: str, root: str, packages: list[str] | None = None) -> list[str]:
    """Python snippets in a shell command that exercise the repository and change nothing."""
    pk = packages if packages is not None else repo_packages(root)
    found: list[str] = []
    for m in _HEREDOC.finditer(command):
        found.append(m.group(2))
    for m in _DASHC.finditer(command):
        code = _quoted(command, m.end())
        if code:
            found.append(code)
    for m in _SCRIPT.finditer(command):
        path = m.group(1)
        full = path if os.path.isabs(path) else os.path.join(root, path)
        if "/tests/" in full or os.path.basename(full).startswith("test_"):
            continue
        try:
            with open(full, encoding="utf-8") as fh:
                found.append(fh.read())
        except OSError:
            continue
    out = []
    for code in found:
        if _WRITES.search(code):
            continue
        if pk and not any(re.search(rf"\b(?:import|from)\s+{re.escape(p)}\b", code) for p in pk):
            continue
        out.append(code)
    return out


# --------------------------------------------------------------------------- running & comparing

_ANSI = re.compile(r"\x1b\[[0-9;]*m|\[4m|\[0m")
_ERR = re.compile(r"(EXC: |Error\b|Exception\b|Invalid expression|Expecting|Required keyword|\bERR\b|Traceback)")


def normalise(text: str, root: str) -> list[str]:
    t = text.replace("\r", "")
    t = t.replace(os.path.abspath(root), "<R>")
    t = re.sub(r"0x[0-9a-fA-F]+", "0x?", t)
    lines = [l for l in t.split("\n") if l.strip() and "Unable to set __version__" not in l
             and "warnings.warn" not in l]
    out, tb = [], False
    for l in lines:
        if l.startswith("Traceback (most recent call last)"):
            tb = True; continue
        if tb and (l.startswith("  ") or l.strip().startswith("^")):
            continue
        if tb:
            out.append("EXC: " + l.strip()); tb = False; continue
        if _ANSI.search(l):
            continue  # highlighted error context lines (sqlglot and others)
        out.append(l.rstrip())
    return out


def run_probe(code: str, root: str, python: str) -> list[str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONHASHSEED": "0",
           "HOME": os.environ.get("HOME", "/tmp"), "PYTHONDONTWRITEBYTECODE": "1"}
    pp = [root] + ([os.path.join(root, "src")] if os.path.isdir(os.path.join(root, "src")) else [])
    env["PYTHONPATH"] = os.pathsep.join(pp)
    try:
        p = subprocess.run([python, "-c", code], cwd=root, env=env, capture_output=True,
                           text=True, timeout=PROBE_TIMEOUT)
        return normalise(p.stdout + p.stderr, root)
    except subprocess.TimeoutExpired:
        return ["EXC: timeout"]
    except OSError as exc:
        return [f"EXC: {exc}"]


def is_error(lines: list[str]) -> bool:
    return any(_ERR.search(l) for l in lines)


def diff_blocks(old: list[str], new: list[str]) -> list[tuple[list[str], list[str]]]:
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    blocks, cur = [], None
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            if cur:
                blocks.append(cur); cur = None
            continue
        if cur is None:
            cur = ([], [])
        cur[0].extend(old[i1:i2]); cur[1].extend(new[j1:j2])
    if cur:
        blocks.append(cur)
    return blocks


def classify_block(olds: list[str], news: list[str]) -> str:
    """hard: a result became an error; soft: a result changed; none: error fixed or both errors."""
    oe, ne = is_error(olds), is_error(news)
    if oe and not ne:
        return "none"
    if oe and ne:
        return "none"
    if ne and not oe:
        return "hard"
    return "soft"


# --------------------------------------------------------------------------- capture


def _traj_path(root: str) -> str:
    return os.path.join(_dir(root), "trajectory.jsonl")


def load_trajectory(root: str) -> list[dict[str, Any]]:
    recs = []
    try:
        with open(_traj_path(root), encoding="utf-8") as fh:
            for line in fh:
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return recs


def ensure_session(root: str) -> dict[str, Any]:
    st = load_state(root)
    if "base_sha" not in st:
        st["base_sha"] = _git(root, "rev-parse", "HEAD").stdout.strip()
        st["base_state"] = source_state(root)
        st["blocks"] = 0
        st["started"] = time.time()
        save_state(root, st)
    return st


def capture(payload: dict[str, Any], root: str, cfg: dict[str, Any]) -> dict[str, Any]:
    if not cfg.get("trajectory"):
        return {}
    if payload.get("tool_name") != "Bash":
        return {}
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    probes = extract_probes(cmd, root)
    if not probes:
        return {}
    st = ensure_session(root)
    state = source_state(root)
    edited = state != st.get("base_state")
    t0 = time.perf_counter()
    path = _traj_path(root)
    for code in probes:
        out = run_probe(code, root, cfg["python"])
        rec = {"id": hashlib.sha1(code.encode()).hexdigest()[:12], "code": code, "out": out,
               "state": state, "edited": edited, "t": time.time()}
        with exclusive_lock(path):
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log_event(root, {"event": "capture", "probes": len(probes), "edited": edited,
                     "ms": int((time.perf_counter() - t0) * 1000)})
    return {}


# --------------------------------------------------------------------------- tests


def _baseline_dir(root: str, sha: str) -> str:
    dest = os.path.join(_dir(root), "proviso-base")
    if not os.path.isdir(os.path.join(dest, ".git")) and not os.path.isfile(os.path.join(dest, ".git")):
        if os.path.exists(dest):
            import shutil
            shutil.rmtree(dest, ignore_errors=True)
        r = _git(root, "worktree", "add", "--detach", "--force", dest, sha, timeout=300)
        if r.returncode != 0:
            p = subprocess.run(["git", "archive", sha], cwd=root, stdout=subprocess.PIPE)
            os.makedirs(dest, exist_ok=True)
            subprocess.run(["tar", "x", "-C", dest], input=p.stdout)
    return dest


def _module_imported_widely(root: str, rel: str, threshold: int = 10) -> bool:
    mod = rel[:-3].replace("/", ".")
    if mod.startswith("src."):
        mod = mod[4:]
    if mod.endswith(".__init__"):
        mod = mod[: -len(".__init__")]
    leaf = mod.rsplit(".", 1)[-1]
    pat = re.compile(rf"\b(?:from\s+{re.escape(mod)}\s+import|import\s+{re.escape(mod)}\b|from\s+[\w.]*\s+import\s+[^\n]*\b{re.escape(leaf)}\b)")
    n = 0
    for pkg in repo_packages(root):
        base = os.path.join(root, pkg) if os.path.isdir(os.path.join(root, pkg)) else os.path.join(root, "src", pkg)
        for path in glob.glob(os.path.join(base, "**", "*.py"), recursive=True):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    if pat.search(fh.read()):
                        n += 1
                        if n >= threshold:
                            return True
            except OSError:
                pass
    return False


def select_tests(root: str, base: str, changed: list[str]) -> list[str] | None:
    """Test files (relative) affected by `changed`; None means the whole test directory."""
    tests_root = "tests" if os.path.isdir(os.path.join(base, "tests")) else ("test" if os.path.isdir(os.path.join(base, "test")) else None)
    if tests_root is None:
        return []
    picked: set[str] = set()
    for rel in changed:
        name = os.path.basename(rel)[:-3]
        if name == "__init__":
            name = os.path.basename(os.path.dirname(rel))
        if _module_imported_widely(root, rel):
            return None
        for path in glob.glob(os.path.join(base, tests_root, "**", f"test_{name}.py"), recursive=True):
            picked.add(os.path.relpath(path, base))
    return sorted(picked)


def _junit(xml_path: str) -> dict[str, bool]:
    res: dict[str, bool] = {}
    try:
        tree = ET.parse(xml_path)
    except (OSError, ET.ParseError):
        return res
    for c in tree.iter("testcase"):
        k = f"{c.get('classname') or ''}::{c.get('name') or ''}"
        res[k] = not any(ch.tag in ("failure", "error") for ch in c)
    return res


def _overlay(root: str, base: str) -> str:
    """Directory with the current source packages (from `root`) and everything else from the
    baseline copy (tests, conftest, config), so the original tests run against current code."""
    import shutil
    dest = os.path.join(_dir(root), "proviso-overlay")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    pkgs = set(repo_packages(root)) | set(repo_packages(base))
    for name in os.listdir(base):
        if name in (".git", STATE_DIR):
            continue
        src_dir = os.path.join(root if name in pkgs else base, name)
        if name == "src" and os.path.isdir(os.path.join(root, "src")):
            os.makedirs(os.path.join(dest, "src"))
            for sub in os.listdir(os.path.join(base, "src")):
                origin = root if sub in pkgs else base
                if os.path.exists(os.path.join(origin, "src", sub)):
                    os.symlink(os.path.join(origin, "src", sub), os.path.join(dest, "src", sub))
            continue
        if os.path.exists(src_dir):
            os.symlink(src_dir, os.path.join(dest, name))
    for name in pkgs:  # packages the agent added
        if not os.path.exists(os.path.join(dest, name)) and os.path.isdir(os.path.join(root, name)):
            os.symlink(os.path.join(root, name), os.path.join(dest, name))
    return dest


def run_tests(run_root: str, targets: list[str] | None, python: str, xml: str) -> dict[str, bool]:
    """Run pytest inside `run_root` (the baseline copy, or an overlay of current code on it)."""
    if os.path.exists(xml):
        os.remove(xml)
    tdir = "tests" if os.path.isdir(os.path.join(run_root, "tests")) else "test"
    args = list(targets) if targets else [tdir]
    pp = [run_root] + ([os.path.join(run_root, "src")] if os.path.isdir(os.path.join(run_root, "src")) else [])
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/tmp"),
           "PYTHONPATH": os.pathsep.join(pp), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        subprocess.run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no",
                        "--continue-on-collection-errors", f"--junitxml={xml}", *args],
                       cwd=run_root, env=env, capture_output=True, text=True, timeout=TESTS_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {}
    return _junit(xml)


# --------------------------------------------------------------------------- verify


def _short(lines: list[str], n: int = 160) -> str:
    s = " / ".join(l.strip() for l in lines if l.strip())
    return (s[: n - 1] + "…") if len(s) > n else (s or "(no output)")


def _first_line(code: str) -> str:
    for l in code.strip().splitlines():
        l = l.strip()
        if l and not l.startswith(("import ", "from ", "#")):
            return (l[:90] + "…") if len(l) > 90 else l
    return code.strip().splitlines()[0][:90] if code.strip() else "(script)"


def verify(payload: dict[str, Any], root: str, cfg: dict[str, Any]) -> dict[str, Any]:
    st = ensure_session(root)
    t0 = time.perf_counter()
    changed = changed_source_files(root)
    if not changed:
        log_event(root, {"event": "verify", "result": "no-source-change", "ms": 0})
        return {}
    if st.get("blocks", 0) >= MAX_BLOCKS:
        log_event(root, {"event": "verify", "result": "block-limit", "ms": 0})
        return {}
    hard: list[str] = []
    soft: list[str] = []
    stats = {"probes": 0, "replayed": 0, "flaky": 0, "tests_run": 0, "regressions": 0}

    if cfg.get("trajectory"):
        last: dict[str, dict[str, Any]] = {}
        for rec in load_trajectory(root):
            last[rec["id"]] = rec  # file order is time order
        stats["probes"] = len(last)
        state = source_state(root)
        for pid, rec in last.items():
            cur = run_probe(rec["code"], root, cfg["python"])
            stats["replayed"] += 1
            if cur == rec["out"]:
                continue
            again = run_probe(rec["code"], root, cfg["python"])
            if again != cur or rec.get("state") == state:
                stats["flaky"] += 1
                continue
            for olds, news in diff_blocks(rec["out"], cur):
                kind = classify_block(olds, news)
                when = "after your last edit check" if rec.get("edited") else "since the original code"
                item = f"`{_first_line(rec['code'])}`: was {_short(olds)}, now {_short(news)} ({when})"
                if kind == "hard":
                    hard.append(item)
                elif kind == "soft" and rec.get("edited"):
                    soft.append(item)
                elif kind == "soft":
                    # Seen only before any edit: the agent was looking at the bug, so a changed
                    # result there is almost always the fix itself (Phase 0 and Phase 3 smoke).
                    stats["intended_unseen"] = stats.get("intended_unseen", 0) + 1

    if cfg.get("tests"):
        base = _baseline_dir(root, st.get("base_sha") or "HEAD")
        targets = select_tests(root, base, changed)
        if targets is None or targets:
            cache = st.get("base_tests", {})
            key = "ALL" if targets is None else ",".join(targets)
            if key not in cache:
                cache[key] = run_tests(base, targets, cfg["python"], os.path.join(_dir(root), "proviso-base.xml"))
                st["base_tests"] = cache
                save_state(root, st)
            base_res = cache[key]
            cur_res = run_tests(_overlay(root, base), targets, cfg["python"], os.path.join(_dir(root), "proviso-cur.xml"))
            stats["tests_run"] = len(cur_res)
            regs = [k for k, ok in base_res.items() if ok and k in cur_res and not cur_res[k]]
            stats["regressions"] = len(regs)
            for k in regs:
                cls, name = k.split("::", 1)
                hard.append(f"existing test `{cls.rsplit('.', 1)[-1]}.{name}` passed before your change and fails now")

    ms = int((time.perf_counter() - t0) * 1000)
    st = load_state(root) | {"base_tests": st.get("base_tests", {})}
    blocks = st.get("blocks", 0)
    if not hard and (not soft or blocks >= 1):
        log_event(root, {"event": "verify", "result": "silent", "hard": 0, "soft": len(soft), "ms": ms, **stats})
        return {}
    items = (hard + soft)[:MAX_ITEMS]
    more = len(hard) + len(soft) - len(items)
    if hard:
        head = "Proviso replayed your checks and the affected tests. These behaviours changed in a way that looks unintended:"
        tail = "Fix them before finishing, or explain why the change is intended."
    else:
        head = "Proviso replayed your checks. These outputs changed after you last looked at them:"
        tail = "If these changes are intended, just finish; otherwise fix them."
    text = head + "\n" + "\n".join(f"- {i}" for i in items)
    if more > 0:
        text += f"\n- …and {more} more"
    text += "\n" + tail
    st["blocks"] = blocks + 1
    save_state(root, st)
    log_event(root, {"event": "verify", "result": "block", "hard": len(hard), "soft": len(soft),
                     "ms": ms, "report_chars": len(text), **stats})
    return {"decision": "block", "reason": text}


# --------------------------------------------------------------------------- pushed context

_COMMON = {"the", "and", "for", "with", "from", "that", "this", "should", "into", "when", "where",
           "select", "table", "string", "value", "values", "example", "expected", "currently",
           "python", "import", "print", "true", "false", "none", "test", "tests", "error"}


def _prompt_words(prompt: str) -> tuple[dict[str, int], set[str]]:
    counts: dict[str, int] = {}
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", prompt):
        lw = w.lower()
        if lw not in _COMMON:
            counts[lw] = counts.get(lw, 0) + 1
    ident = set(re.findall(r"\b(?:[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+|[a-z]+_[a-z0-9_]+|[a-z]\w*(?=\())", prompt))
    ident |= set(re.findall(r"exp\.(\w+)", prompt))
    return counts, ident


def build_context(prompt: str, root: str) -> str:
    """Files named after words the report repeats, with their outline, plus symbols it names."""
    counts, ident = _prompt_words(prompt)
    pk = repo_packages(root)
    scored: list[tuple[int, str]] = []
    for p in pk:
        base = os.path.join(root, p) if os.path.isdir(os.path.join(root, p)) else os.path.join(root, "src", p)
        for path in glob.glob(os.path.join(base, "**", "*.py"), recursive=True):
            name = os.path.basename(path)[:-3]
            n = counts.get(name, 0)
            if n >= 2 and name != "__init__":
                scored.append((n, os.path.relpath(path, root)))
    scored.sort(key=lambda x: (-x[0], x[1].count("/"), x[1]))
    try:
        from .engine import Engine
        eng = Engine(root, typecheck="off", refresh_interval=0)
        eng.ensure_fresh(force=False)
    except Exception:
        eng = None
    parts: list[str] = []
    budget = CONTEXT_CHARS
    if eng is not None:
        for _, rel in scored[:6]:
            syms = eng.store.symbols_in_file(rel)
            lines = [rel]
            for c in [s for s in syms if s.kind == "class"][:3]:
                meths = [s.name for s in syms if s.parent == c.qualname and not s.name.startswith("__")][:30]
                lines.append(f"  class {c.name} (L{c.def_line})" + (": " + ", ".join(meths) if meths else ""))
            funcs = [s.name for s in syms if s.kind == "function"][:15]
            if funcs:
                lines.append("  functions: " + ", ".join(funcs))
            block = "\n".join(lines)
            if len(block) + 1 > budget:
                break
            parts.append(block); budget -= len(block) + 1
        seen = set()
        for w in sorted(ident):
            leaf = w.split(".")[-1]
            for sym in eng.store.search(leaf, 8):
                if sym.name == leaf and sym.qualname not in seen:
                    seen.add(sym.qualname)
                    line = f"{sym.qualname}  {sym.path}:L{sym.def_line}  {sym.signature}"
                    if len(line) + 1 > budget:
                        break
                    parts.append(line); budget -= len(line) + 1
        eng.close()
    return "\n".join(parts)


BRIEF_HEADER = (
    "Proviso pre-fetched what is relevant to this task. Everything below was read or run in this "
    "repository at its current commit, before any change. Rely on it instead of re-reading these "
    "files or re-running these commands; read further only for what it does not cover."
)
BRIEF_CHARS = 40000  # hard cap on a pre-fetched brief (~10k tokens)


def load_brief(root: str) -> str:
    """A pre-built brief at .dc-engine/brief.md (oracle and pre-fetch arms)."""
    try:
        with open(os.path.join(root, STATE_DIR, "brief.md"), encoding="utf-8") as fh:
            return fh.read()[:BRIEF_CHARS].strip()
    except OSError:
        return ""


def context(payload: dict[str, Any], root: str, cfg: dict[str, Any]) -> dict[str, Any]:
    ensure_session(root)
    what = []
    if cfg.get("trajectory"):
        what.append("replays the Python checks you ran")
    if cfg.get("tests"):
        what.append("re-runs the existing tests your change can affect")
    text = ""
    if what:
        text = INSTRUCTION.format(what=" and ".join(what))
    t0 = time.perf_counter()
    ctx = ""
    if cfg.get("brief"):
        ctx = load_brief(root)
        if ctx:
            text = (text + "\n\n" if text else "") + BRIEF_HEADER + "\n\n" + ctx
    if cfg.get("context"):
        ctx = build_context(str(payload.get("prompt") or ""), root)
        if ctx:
            text = (text + "\n\n" if text else "") + "Code that likely matters for this task (from the repository index):\n" + ctx
    log_event(root, {"event": "context", "chars": len(text), "context_chars": len(ctx),
                     "ms": int((time.perf_counter() - t0) * 1000)})
    if not text:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}


# --------------------------------------------------------------------------- dispatch


def handle_event(event: str, payload: dict[str, Any], root: str) -> dict[str, Any]:
    cfg = load_config(root)
    if event == "proviso-context":
        return context(payload, root, cfg)
    if event == "proviso-capture":
        return capture(payload, root, cfg)
    if event == "proviso-verify":
        return verify(payload, root, cfg)
    return {}


def summarize_log(root: str) -> dict[str, Any]:
    """Counts for eval metrics."""
    out = {"proviso_captures": 0, "proviso_probes_captured": 0, "proviso_verifies": 0,
           "proviso_blocks": 0, "proviso_hard": 0, "proviso_soft": 0, "proviso_verify_ms": 0,
           "proviso_context_chars": 0, "proviso_test_regressions": 0, "proviso_flaky": 0}
    try:
        with open(os.path.join(root, STATE_DIR, "proviso.log"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                ev = r.get("event")
                if ev == "capture":
                    out["proviso_captures"] += 1
                    out["proviso_probes_captured"] += int(r.get("probes") or 0)
                elif ev == "verify":
                    out["proviso_verifies"] += 1
                    out["proviso_verify_ms"] += int(r.get("ms") or 0)
                    out["proviso_hard"] += int(r.get("hard") or 0)
                    out["proviso_soft"] += int(r.get("soft") or 0)
                    out["proviso_test_regressions"] += int(r.get("regressions") or 0)
                    out["proviso_flaky"] += int(r.get("flaky") or 0)
                    if r.get("result") == "block":
                        out["proviso_blocks"] += 1
                elif ev == "context":
                    out["proviso_context_chars"] = int(r.get("chars") or 0)
    except OSError:
        pass
    return out
