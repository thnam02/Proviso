"""Change-impact assets for sympy tasks: coverage map of the task's subpackages at the base commit (sympy's cache cleared before every test,
so a test records everything it depends on, not only what an earlier test left uncached), base failures (from a
normal run), and the base import-time snapshot.
Usage: python assets.py EVAL_DIR [TASK_ID_PREFIX ...]"""
import glob, json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, os.path.join(ROOT, "research", "ripple"))
from verify import WORK, tree  # noqa: E402
from build_assets import _import_state  # noqa: E402


def covmap(base_tree, pkgs, out):
    if os.path.exists(out):
        return json.load(open(out))
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONPATH": f"{base_tree}:{os.path.join(ROOT, 'research', 'ripple')}",
           "HOME": "/tmp", "COVMAP_OUT": out, "COVMAP_PKG": "sympy",
           "COVMAP_BEFORE_TEST": "sympy.core.cache:clear_cache",
           "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run(["python3", "-m", "pytest", "-q", "-p", "covplugin", "-p", "no:cacheprovider", "--tb=no",
                    "--continue-on-collection-errors", *pkgs], cwd=base_tree, env=env, capture_output=True, timeout=14400)
    return json.load(open(out))


def build(eval_dir, task):
    fix10 = task["fix_commit"][:10]
    d = f"{WORK}/{fix10}"
    if not os.path.isdir(d + "/base"):
        tree(task["commit"], d + "/base")
    cov = covmap(d + "/base", task["subpackages"], f"{WORK}/cov-{fix10}.json")
    dest = os.path.join(eval_dir, "impact", task["id"])
    os.makedirs(dest, exist_ok=True)
    json.dump({n: {k: v for k, v in e.items() if k != "ok"} for n, e in cov.items()},
              open(os.path.join(dest, "covmap.json"), "w"))
    regb = json.load(open(f"{WORK}/out-{fix10}-regb.json"))  # normal run of the same subpackages at base
    json.dump(sorted(n for n, ok in regb.items() if not ok), open(os.path.join(dest, "base_failures.json"), "w"))
    _import_state(d + "/base", cov, "/usr/bin/python3",  # same module list as selection computes at run time
                  os.path.join(dest, "importstate_base.json"))
    print(task["id"], "covered tests", len(cov) - 1, flush=True)


if __name__ == "__main__":
    ev = sys.argv[1]
    for f in sorted(glob.glob(os.path.join(ev, "tasks", "*.json"))):
        t = json.load(open(f))
        if len(sys.argv) > 2 and not any(t["id"].startswith(p) for p in sys.argv[2:]):
            continue
        build(ev, t)
