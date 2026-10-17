"""Build eval/tasks_sympy/*.json from verified candidates (verify.json) and prompts (prompts.py).

hidden tests     = verify.py's: tests in the merge's changed test files that fail with the base source and pass with
                   the fix source
regression tests = tests in the subpackages the fix's source touches that pass at both commits, minus hidden
Usage: python build.py [PREFIX ...]
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from prompts import SPEC  # noqa: E402
from verify import G, WORK, istest, run, tree  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "eval", "tasks_sympy")
EVAL = r'''
import sys, json, signal, warnings
warnings.filterwarnings("ignore")
from sympy import *
from sympy.abc import x, y, z, s, t
def _alarm(*a):
    raise TimeoutError
signal.signal(signal.SIGALRM, _alarm)
out = []
for e in json.loads(sys.argv[1]):
    signal.alarm(60)
    try:
        out.append(str(eval(e)))
    except TimeoutError:
        out.append("(does not finish within 60 s)")
    except Exception as x_:
        out.append(f"{type(x_).__name__}: {str(x_).splitlines()[0][:160] if str(x_) else ''}")
    finally:
        signal.alarm(0)
print(json.dumps(out))
'''


def run_exprs(root, exprs):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": root, "HOME": "/tmp"}
    p = subprocess.run(["python3", "-c", EVAL, json.dumps(exprs)], cwd=root, env=env, capture_output=True, text=True,
                       timeout=600)
    return json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else [p.stderr[-200:]] * len(exprs)


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:40].strip("-")


def build(pre, v):
    base, fix = v["base"], v["fix"]
    d = f"{WORK}/{fix[:10]}"
    if not os.path.isdir(d + "/base"):
        tree(fix, d + "/fix")
        tree(base, d + "/base")
    src = [f for f in G("diff", "--name-only", base, fix).stdout.split()
           if f.startswith("sympy/") and f.endswith(".py") and not istest(f)]
    pkgs = sorted({"/".join(f.split("/")[:2]) for f in src})
    rb, rf = run(d + "/base", pkgs, fix[:10] + "-regb"), run(d + "/fix", pkgs, fix[:10] + "-regf")
    hidden = v["hidden"]
    regression = sorted(n for n, ok in rb.items() if ok and rf.get(n) and "::" in n and n not in hidden)
    desc, exprs = SPEC[pre]
    eb, ef = run_exprs(d + "/base", exprs), run_exprs(d + "/fix", exprs)
    body = "\n\n".join(f"{e}\n# currently: {b}\n# expected:  {f}" for e, b, f in zip(exprs, eb, ef) if b != f)
    prompt = desc
    if body:
        prompt += (f"\n\nFor example (with x, y, z, s, t from sympy.abc):\n\n```python\nfrom sympy import *\n\n{body}\n```")
    prompt += "\n\nOther inputs with the same problem should be handled as well."
    subject = G("log", "-1", "--format=%b", fix).stdout.strip().split("\n")[0] or G("log", "-1", "--format=%s", fix).stdout
    tid = f"{pre}-{slug(subject)}"
    task = {"id": tid, "repo": "https://github.com/sympy/sympy.git", "commit": base, "prompt": prompt,
            "hidden_tests": hidden, "test_patch": G("diff", base, fix, "--", *v["test_files"]).stdout,
            "regression_tests": regression, "setup": "python -m pip install -e . -q", "prompt_original": subject,
            "fix_commit": fix, "verified": True, "source_files_changed": len(src), "subpackages": pkgs,
            "hidden_tests_note": "hidden tests = tests in the fix's changed test files that fail with the base source and "
                                 "pass with the fix source; regression tests = tests in the subpackages the fix touches "
                                 "that pass at both commits"}
    os.makedirs(OUT, exist_ok=True)
    json.dump(task, open(os.path.join(OUT, tid + ".json"), "w"), indent=2)
    print(tid, "hidden", len(hidden), "regression", len(regression), "examples differing",
          sum(b != f for b, f in zip(eb, ef)), "of", len(exprs), flush=True)


if __name__ == "__main__":
    V = json.load(open(os.path.join(HERE, "verify.json")))
    for pre in sys.argv[1:] or [k for k, v in V.items() if v["hidden"]]:
        build(pre, V[pre])
