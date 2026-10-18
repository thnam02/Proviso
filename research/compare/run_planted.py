"""Score all selectors on the planted bugs (ground truth stored by research/ripple/mutants.py and
research/sympy/mutants_sympy.py). Each bug is re-planted in a clean base tree; testmon's selection comes from a
collect-only run against the base database, Proviso's from dc_engine.impact.selection.

Usage: python run_planted.py sqlglot COMMIT OUT.json      (base tree and database from prep_sqlglot_real.py)
       python run_planted.py sympy OUT.json               (builds the testmon database for sympy/functions first)"""
import json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "research", "ripple"))
import rts as SEL  # noqa: E402
import mutants as M  # noqa: E402
from score import score_change  # noqa: E402

S = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad"
TOOLS = "/home/claude/tools/coveragepy:/home/claude/tools/pytest-testmon"


def env(tree):
    return {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp", "PYTHONPATH": f"{tree}:{TOOLS}",
            "PYTHONDONTWRITEBYTECODE": "1"}


def testmon_select(tree, db, target):
    shutil.copy(db, os.path.join(tree, ".testmondata"))
    r = subprocess.run(["python3", "-m", "pytest", "-q", "--co", "--testmon", "--continue-on-collection-errors",
                        target], cwd=tree, env=env(tree), capture_output=True, text=True, timeout=1800)
    os.remove(os.path.join(tree, ".testmondata"))
    shutil.rmtree(os.path.join(tree, ".pytest_cache"), ignore_errors=True)
    if "collected" not in r.stdout:
        raise RuntimeError("testmon selection failed: " + (r.stdout + r.stderr)[-500:])
    return [l for l in r.stdout.splitlines() if "::" in l and not l.startswith(("ERROR", "FAILED"))]


def run(repo, work, bugs, cov, db, base_fail, target, roots, pkgs, out_path, tag, db_cc=None):
    bad_files = {k for k in base_fail if "::" not in k}
    ok_at_base = lambda n: n not in base_fail and n.split("::", 1)[0] not in bad_files
    universe = {n for n in cov if n != "__global__" and ok_at_base(n)}
    if target != "tests":
        universe = {n for n in universe if n.startswith(target + "/")}
    rows = json.load(open(out_path)) if os.path.exists(out_path) else []
    done = {(r["file"], r["line"], r["base"]) for r in rows}
    g = lambda *a: subprocess.run(["git", *a], cwd=work, capture_output=True)
    g("checkout", "-q", "--", ".")
    ov = {(c[0], c[1], c[2]): c for c in M.override_candidates(work)} if any(b["kind"] == "override" for b in bugs) \
        else {}
    for b in bugs:
        if (b["file"], b["line"], tag) in done or b.get("killed") is None:
            continue
        g("checkout", "-q", "--", ".")
        if b["kind"] == "override":
            cand = next(c for k, c in ov.items()
                        if k[0] == b["file"] and k[1] == b["line"] and b["code"].startswith(k[2] + " "))
            M.apply_override(work, cand)
        else:
            M.apply(work, b["file"], b["line"], b["op"])
        if not SEL.git(work, "diff", "--stat").strip():
            raise RuntimeError(f"planted bug not applied: {b['file']}:{b['line']}")
        truth = sorted(t for t in (b.get("failing_set") or b.get("failing") or []) if ok_at_base(t)) \
            if b["killed"] else []
        ch = SEL.Change(work, pkgs)
        ctx = {"testmon_db": db, "testmon_selected": testmon_select(work, db, target), "roots": roots}
        if db_cc:
            ctx.update(testmon_db_cc=db_cc, testmon_selected_cc=testmon_select(work, db_cc, target))
        for r in score_change(ch, universe, truth, cov, ctx):
            rows.append({"repo": repo, "dataset": "planted", "base": tag, "kind": b["kind"], "file": b["file"],
                         "line": b["line"], "op": b["op"], "killed": bool(b["killed"]), **r})
        last = [r for r in rows if (r["file"], r["line"]) == (b["file"], b["line"])]
        print(tag, b["kind"], b["file"], b["line"], "truth", len(truth), " ".join(
            f"{r['selector']}={r['selected']}{'!' if r['missed'] else ''}" for r in last), flush=True)
        json.dump(rows, open(out_path, "w"), indent=1)
    g("checkout", "-q", "--", ".")


def main():
    if sys.argv[1] == "sqlglot":
        tid, out = sys.argv[2], sys.argv[3]
        src = f"/home/claude/cmp/sq/{tid}"
        work = f"/home/claude/cmp/mut-{tid}"
        if not os.path.isdir(work):
            shutil.copytree(os.path.join(src, "tree"), work)
            subprocess.run(["git", "checkout", "-q", "--", "."], cwd=work)
            subprocess.run(["git", "clean", "-fdq"], cwd=work)
        cov = json.load(open(os.path.join(S, "ripple", f"cov2_{tid}.json")))
        base = SEL.I._junit(os.path.join(src, "base.xml"))
        bugs = [b for b in json.load(open(os.path.join(ROOT, "research", "ripple", "mutants2_scored.json")))
                if b["commit"] == tid]
        run("sqlglot", work, bugs, cov, os.path.join(src, "testmondata.base"), {k for k, ok in base.items() if not ok},
            "tests", ("sqlglot", "tests"), ["sqlglot"], out, tid)
    else:
        out = sys.argv[2]
        work = os.path.join(S, "mut-sympy")
        subprocess.run(["git", "checkout", "-q", "--", "."], cwd=work)
        db = "/home/claude/cmp/sympy-mut.testmondata"
        xml = "/home/claude/cmp/sympy-mut-base.xml"
        if not os.path.exists(db):
            subprocess.run(["python3", "-m", "pytest", "-q", "--tb=no", "--continue-on-collection-errors", "--testmon",
                            f"--junitxml={xml}", "sympy/functions"], cwd=work, env=env(work), capture_output=True,
                           timeout=7200)
            shutil.move(os.path.join(work, ".testmondata"), db)
            shutil.rmtree(os.path.join(work, ".pytest_cache"), ignore_errors=True)
        db_cc = "/home/claude/cmp/sympy-mut-cc.testmondata"
        if not os.path.exists(db_cc):
            e = env(work)
            e["PYTHONPATH"] += ":/home/claude/cmp/plug"
            subprocess.run(["python3", "-m", "pytest", "-q", "--tb=no", "--continue-on-collection-errors", "--testmon",
                            "-p", "clearcache", "sympy/functions"], cwd=work, env=e, capture_output=True, timeout=7200)
            shutil.move(os.path.join(work, ".testmondata"), db_cc)
            shutil.rmtree(os.path.join(work, ".pytest_cache"), ignore_errors=True)
        cov = json.load(open(os.path.join(S, "cov_mut_sympy_functions.json")))
        base = SEL.I._junit(xml)
        bugs = json.load(open(os.path.join(ROOT, "research", "sympy", "mutants.json")))
        run("sympy", work, bugs, cov, db, {k for k, ok in base.items() if not ok}, "sympy/functions", ("sympy",),
            ["sympy"], out, "sympy-functions", db_cc=db_cc)


if __name__ == "__main__":
    main()
