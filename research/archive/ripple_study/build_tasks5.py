"""Build eval/tasks_ripple_mined/*.json from the mined ripple commits.

hidden tests  = (a) tests in the commit's changed test files that fail with the base source and pass with the fix
                source (both with the fix's test files), and (b) child checks in a new file tests/test_ripple_hidden.py:
                one test per input on which a child dialect silently regressed at the commit. Each child check must
                pass at the base commit and fail at the fix commit (the real ripple), else it is dropped.
regression tests = every existing test passing at both commits, minus hidden.
Usage: python build_tasks5.py [COMMIT ...]
"""
import json, os, re, shutil, subprocess, sys, xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from candidates import COMMITS, ripples  # noqa: E402
from prompt_spec5 import SPEC  # noqa: E402

SRC = "/home/claude/sources/sqlglot"
WORK = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad/rs-work"
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "eval", "tasks_ripple_mined")
G = lambda *a: subprocess.run(["git", *a], cwd=SRC, capture_output=True, text=True)
ENV = lambda r: {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": r, "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"}

# how each regressed child is checked
CHECK = {"ba0bff3d91": ("no_crash", None), "efbc5e220c": ("same_as_before", None),
         "5d997d94d8": ("same_as_before", None), "7f1cf60c88": ("not_contains", "'KEY_BLOCK_SIZE'"),
         "9114355463": ("keeps", "PRIMARY KEY"), "862fd55467": ("same_as_before", None),
         "4ada15a429": ("keeps", "ON CONFLICT"), "a313c8bee1": ("keeps", "ON CONFLICT"), "d7fd83a7dc": ("keeps", "WITH (")}

HEADER = '''"""Behaviour of dialects that inherit from the dialect the change is about."""
import unittest

from sqlglot import parse_one
from sqlglot.errors import ErrorLevel, UnsupportedError


def _out(dialect, sql):
    return parse_one(sql, read=dialect).sql(dialect=dialect)


class TestRippleHidden(unittest.TestCase):
    def assert_same_as_before(self, dialect, sql, before):
        self.assertEqual(_out(dialect, sql), before)

    def assert_no_crash(self, dialect, sql):
        _out(dialect, sql)

    def assert_keeps(self, dialect, sql, part):
        # rejecting the input, or declaring the construct unsupported, is acceptable; silently dropping it is not
        try:
            expr = parse_one(sql, read=dialect)
        except Exception:
            return
        try:
            out = expr.sql(dialect=dialect, unsupported_level=ErrorLevel.RAISE)
        except UnsupportedError:
            return
        self.assertIn(part, out)

    def assert_not_contains(self, dialect, sql, part):
        self.assertNotIn(part, _out(dialect, sql))
'''


def tree(sha, dest):
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    p = subprocess.run(["git", "archive", sha], cwd=SRC, stdout=subprocess.PIPE, check=True)
    subprocess.run(["tar", "x", "-C", dest], input=p.stdout, check=True)


def junit(root, targets, tag):
    x = f"{WORK}/junit-{tag}.xml"
    if os.path.exists(x):
        os.remove(x)
    subprocess.run(["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "--continue-on-collection-errors",
                    f"--junitxml={x}", *targets], cwd=root, env=ENV(root), capture_output=True, text=True, timeout=1800)
    res = {}
    if not os.path.exists(x):
        return res
    for c in ET.parse(x).iter("testcase"):
        parts = (c.get("classname") or "").split(".")
        node = f"{'/'.join(parts[:-1])}.py::{parts[-1]}::{c.get('name')}"
        res[node] = not any(ch.tag in ("failure", "error", "skipped") for ch in c)
    return res


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", re.sub(r"\(#\d+\)|\[\w+\]|CLAUDE|CODEX", "", s).lower())).strip("-")[:40].strip("-")


EVAL = r'''
import sys, json, warnings, logging
logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")
from sqlglot import parse_one, transpile, exp
out = []
for e in json.loads(sys.argv[1]):
    try: v = eval(e); out.append(str(v))
    except Exception as x: out.append(f"{type(x).__name__}: {str(x).splitlines()[0][:160]}")
print(json.dumps(out))
'''


def run_exprs(root, exprs):
    p = subprocess.run(["python3", "-c", EVAL, json.dumps(exprs)], cwd=root, env=ENV(root), capture_output=True,
                       text=True, timeout=120)
    return json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else [p.stderr[-200:]] * len(exprs)


def child_tests(pre, rows):
    kind, part = CHECK[pre]
    lines, names, seen = [], [], set()
    for x in rows:
        k = (x["child"], x["input"])
        if k in seen:
            continue
        seen.add(k)
        name = f"test_{x['child']}_{len(names) + 1}"
        args = [repr(x["child"]), repr(x["input"])]
        if kind == "same_as_before":
            args.append(repr(x["child_before"]))
        elif kind in ("keeps", "not_contains"):
            args.append(repr(part))
        lines.append(f"    def {name}(self):\n        self.assert_{kind}({', '.join(args)})\n")
        names.append(name)
    return HEADER + "\n" + "\n".join(lines), names


def new_file_patch(path, text):
    body = text.split("\n")
    if body and body[-1] == "":
        body = body[:-1]
    return (f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(body)} @@\n" + "".join(f"+{l}\n" for l in body))


def build(pre, rows):
    fix = G("rev-parse", pre).stdout.strip()
    base = G("rev-parse", fix + "^").stdout.strip()
    d = f"{WORK}/{pre}"
    tree(fix, d + "/fix")
    tree(base, d + "/base")
    tfiles = [p for p in G("diff", "--name-only", base, fix, "--", "tests/").stdout.split() if p.endswith(".py")]
    # (a) hidden tests from the commit's own tests
    shutil.rmtree(d + "/basefix", ignore_errors=True)
    shutil.copytree(d + "/base", d + "/basefix")
    for f in tfiles:
        os.makedirs(os.path.dirname(f"{d}/basefix/{f}"), exist_ok=True)
        if os.path.exists(f"{d}/fix/{f}"):
            shutil.copy(f"{d}/fix/{f}", f"{d}/basefix/{f}")
    rf = junit(d + "/fix", tfiles, pre + "-f")
    rb = junit(d + "/basefix", tfiles, pre + "-b")
    hidden = sorted(n for n, ok in rf.items() if ok and not rb.get(n, False))
    # (b) child checks: must pass at base and fail at fix
    text, names = child_tests(pre, rows)
    rp = "tests/test_ripple_hidden.py"
    for side in ("base", "fix"):
        open(f"{d}/{side}/{rp}", "w").write(text)
    cb, cf = junit(d + "/base", [rp], pre + "-rb"), junit(d + "/fix", [rp], pre + "-rf")
    node = lambda n: f"{rp}::TestRippleHidden::{n}"
    keep = [n for n in names if cb.get(node(n)) and cf.get(node(n)) is False]
    dropped = [n for n in names if n not in keep]
    if dropped:  # rebuild the file with the verified checks only
        text, _ = child_tests(pre, [x for x, n in zip(_dedup(rows), names) if n in keep])
        # names are renumbered by child_tests; recompute
        text, keep = child_tests(pre, [x for x, n in zip(_dedup(rows), names) if n in keep])
    for side in ("base", "fix"):
        os.remove(f"{d}/{side}/{rp}")
    # regression tests: full suite at both commits
    fb, ff = junit(d + "/base", ["tests"], pre + "-fullb"), junit(d + "/fix", ["tests"], pre + "-fullf")
    hidden_all = hidden + [node(n) for n in keep]
    regression = sorted(n for n, ok in fb.items() if ok and ff.get(n) and n not in hidden_all)
    desc, exprs = SPEC[pre]
    eb, ef = run_exprs(d + "/base", exprs), run_exprs(d + "/fix", exprs)
    body = "\n\n".join(f"{e}\n# currently: {b}\n# expected:  {f}" for e, b, f in zip(exprs, eb, ef) if b != f)
    prompt = (f"{desc}\n\nFor example:\n\n```python\nfrom sqlglot import parse_one, transpile, exp\n\n{body}\n```\n\n"
              "Other forms of the same constructs described above should work as well.")
    subject = G("log", "-1", "--format=%s", fix).stdout.strip()
    tid = f"{pre}-{slug(subject)}"
    task = {"id": tid, "repo": "https://github.com/tobymao/sqlglot.git", "commit": base, "prompt": prompt,
            "hidden_tests": hidden_all, "test_patch": G("diff", base, fix, "--", "tests").stdout + new_file_patch(rp, text),
            "regression_tests": regression, "setup": "python -m pip install -e . -q", "prompt_original": subject,
            "fix_commit": fix, "verified": True, "ripple_tests": [node(n) for n in keep],
            "ripple_children": sorted({x["child"] for x in rows}), "ripple_check": CHECK[pre][0],
            "source_files_changed": len([p for p in G("diff", "--name-only", base, fix, "--", "sqlglot").stdout.split()
                                         if p.endswith(".py")]),
            "hidden_tests_note": "hidden tests = tests in the fix's changed test files that fail with the base source and "
                                 "pass with the fix source, plus child-dialect checks (tests/test_ripple_hidden.py) that pass "
                                 "at the base commit and fail at the fix commit; regression tests = every existing test that "
                                 "passes at both commits"}
    json.dump(task, open(os.path.join(OUT, tid + ".json"), "w"), indent=2)
    print(tid, "hidden", len(hidden), "ripple checks", len(keep), "dropped", len(dropped), "regression", len(regression),
          "examples differing", sum(b != f for b, f in zip(eb, ef)), "of", len(exprs), flush=True)


def _dedup(rows):
    seen, out = set(), []
    for x in rows:
        k = (x["child"], x["input"])
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    rip = ripples()
    for pre in sys.argv[1:] or COMMITS:
        build(pre, rip[pre])
