"""NameRTS on the same changes as the other selectors (rows in the same format, selector "namerts").
NameRTS selects test files; a file's selection = all its tests in the universe. Universe, ground truth and test times
are computed exactly as in run_planted.py / run_sqlglot_real.py / run_sympy_real.py.

Usage: python run_namerts.py planted-sqlglot COMMIT OUT.json | planted-sympy OUT.json | real-sqlglot OUT.json |
       real-sympy OUT.json"""
import glob, json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "research", "ripple"))
sys.path.insert(0, os.path.join(ROOT, "research", "sympy"))
import rts as SEL  # noqa: E402
import mutants as M  # noqa: E402

S = "/tmp/claude-0/-home-claude/ba1d6daa-9321-5797-910e-8a169f93d9bd/scratchpad"
NR = "/home/claude/cmp/nr"
DRIVER = os.path.join(HERE, "namerts_driver.py")


def driver(action, tree, cache, repo, scope=None):
    env = dict(os.environ)
    if scope:
        env["NAMERTS_SCOPE"] = ",".join(scope)
    r = subprocess.run(["python3", DRIVER, action, tree, cache, repo], capture_output=True, text=True, env=env,
                       timeout=14400)
    if action == "select":
        for line in r.stdout.splitlines():
            if line.startswith("NAMERTS_SELECTED "):
                return json.loads(line[len("NAMERTS_SELECTED "):])
        raise RuntimeError("NameRTS selection failed: " + (r.stdout + r.stderr)[-800:])
    if r.returncode != 0 or not os.path.isfile(os.path.join(cache, "nbdp_cache.json")):
        raise RuntimeError("NameRTS init failed: " + (r.stdout + r.stderr)[-800:])


def base_tree(name, src_tree, repo, scope=None):
    """A copy of src_tree reset to its HEAD (the base), with NameRTS initialised on it."""
    d = os.path.join(NR, name)
    tree, cache = os.path.join(d, "tree"), os.path.join(d, "cache")
    if not os.path.isfile(os.path.join(cache, "nbdp_cache.json")):
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(src_tree, tree, ignore=shutil.ignore_patterns("__pycache__", ".testmondata", ".pytest_cache"))
        subprocess.run(["git", "checkout", "-q", "--", "."], cwd=tree)
        subprocess.run(["git", "clean", "-fdq"], cwd=tree)
        driver("init", tree, cache, repo, scope)
    return tree, cache


def reset(tree, pkg):
    subprocess.run(["git", "checkout", "-q", "--", pkg], cwd=tree)
    st = subprocess.run(["git", "status", "--porcelain", "-uall", "--", pkg], cwd=tree, capture_output=True,
                        text=True).stdout
    for l in st.splitlines():  # files a change added
        if l.startswith("??"):
            os.remove(os.path.join(tree, l[3:]))


def row(selected_files, universe, truth, cov):
    files = set(selected_files)
    s = {n for n in universe if n.split("::", 1)[0] in files}
    tsum = lambda ns: sum(cov.get(n, {}).get("time", 0) or 0 for n in ns)
    return {"selector": "namerts", "selected": len(s), "universe": len(universe),
            "time_share": round(tsum(s) / (tsum(universe) or 1e-9), 4), "truth": len(truth),
            "missed": SEL.missed(truth, s), "selected_files": len(files)}


def ok_filter(base_fail):
    bad_files = {k for k in base_fail if "::" not in k}
    return lambda n: n not in base_fail and n.split("::", 1)[0] not in bad_files


def load(out):
    return json.load(open(out)) if os.path.exists(out) else []


def planted(repo, tag, tree, cache, bugs, cov, base_fail, scope, pkg, out):
    ok = ok_filter(base_fail)
    universe = {n for n in cov if not n.startswith("__") and ok(n)}
    if scope:
        universe = {n for n in universe if any(n.startswith(s + "/") for s in scope)}
    rows = load(out)
    done = {(r["file"], r["line"]) for r in rows}
    reset(tree, pkg)
    ov = {(c[0], c[1], c[2]): c for c in M.override_candidates(tree)} if any(b["kind"] == "override" for b in bugs) \
        else {}
    for b in bugs:
        if (b["file"], b["line"]) in done or b.get("killed") is None:
            continue
        reset(tree, pkg)
        if b["kind"] == "override":
            cand = next(c for k, c in ov.items()
                        if k[0] == b["file"] and k[1] == b["line"] and b["code"].startswith(k[2] + " "))
            M.apply_override(tree, cand)
        else:
            M.apply(tree, b["file"], b["line"], b["op"])
        if not SEL.git(tree, "diff", "--stat", "--", pkg).strip():
            raise RuntimeError(f"planted bug not applied: {b['file']}:{b['line']}")
        truth = sorted(t for t in (b.get("failing_set") or b.get("failing") or []) if ok(t)) if b["killed"] else []
        sel = driver("select", tree, cache, repo, scope)
        rows.append({"repo": repo, "dataset": "planted", "base": tag, "kind": b["kind"], "file": b["file"],
                     "line": b["line"], "op": b["op"], "killed": bool(b["killed"]), **row(sel, universe, truth, cov)})
        r = rows[-1]
        print(tag, b["kind"], b["file"], b["line"], "truth", len(truth), "namerts", r["selected"],
              "MISSED" if r["missed"] else "", flush=True)
        json.dump(rows, open(out, "w"), indent=1)
    reset(tree, pkg)


def main():
    what = sys.argv[1]
    if what == "planted-sqlglot":
        tid, out = sys.argv[2], sys.argv[3]
        tree, cache = base_tree(tid, f"/home/claude/cmp/sq/{tid}/tree", "sqlglot")
        cov = json.load(open(os.path.join(S, "ripple", f"cov2_{tid}.json")))
        base = SEL.I._junit(f"/home/claude/cmp/sq/{tid}/base.xml")
        bugs = [b for b in json.load(open(os.path.join(ROOT, "research", "ripple", "mutants2_scored.json")))
                if b["commit"] == tid]
        planted("sqlglot", tid, tree, cache, bugs, cov, {k for k, v in base.items() if not v}, None, "sqlglot", out)
    elif what == "planted-sympy":
        out = sys.argv[2]
        tree, cache = base_tree("sympy-mut", os.path.join(S, "mut-sympy"), "sympy", ["sympy/functions"])
        cov = json.load(open(os.path.join(S, "cov_mut_sympy_functions.json")))
        base = SEL.I._junit("/home/claude/cmp/sympy-mut-base.xml")
        bugs = json.load(open(os.path.join(ROOT, "research", "sympy", "mutants.json")))
        planted("sympy", "sympy-functions", tree, cache, bugs, cov, {k for k, v in base.items() if not v},
                ["sympy/functions"], "sympy", out)
    elif what == "real-sqlglot":
        out = sys.argv[2]
        rows = load(out)
        done = {r["change"] for r in rows}
        for d in sorted(glob.glob("/home/claude/cmp/sq/*")):
            tid = os.path.basename(d)
            if tid in done or not os.path.isfile(os.path.join(d, "proviso.json")):
                continue
            try:
                tree, cache = base_tree(tid, os.path.join(d, "tree"), "sqlglot")
                cov = json.load(open(os.path.join(S, "ripple", f"cov2_{tid}.json")))
                base = SEL.I._junit(os.path.join(d, "base.xml"))
                change = SEL.I._junit(os.path.join(d, "change.xml"))
                ok = ok_filter({k for k, v in base.items() if not v})
                universe = {n for n in cov if not n.startswith("__") and ok(n)}
                truth = sorted(n for n, v in change.items() if not v and ok(n))
                reset(tree, "sqlglot")
                diff = SEL.git(os.path.join(d, "tree"), "diff", "HEAD", "--binary", "--", "sqlglot")
                subprocess.run(["git", "apply"], cwd=tree, input=diff, text=True, check=True)
                sel = driver("select", tree, cache, "sqlglot")
                reset(tree, "sqlglot")
            except Exception as e:  # noqa: BLE001  reported, the commit is left out of NameRTS's rows
                print(tid, "ERROR", repr(e)[:400], flush=True)
                continue
            rows.append({"repo": "sqlglot", "dataset": "real", "change": tid, **row(sel, universe, truth, cov)})
            r = rows[-1]
            print(tid, "truth", len(truth), "namerts", r["selected"], "MISSED" if r["missed"] else "", flush=True)
            json.dump(rows, open(out, "w"), indent=1)
            shutil.rmtree(os.path.join(NR, tid, "tree", "coverage"), ignore_errors=True)
    elif what == "real-sympy":
        from verify import G, istest
        out = sys.argv[2]
        rows = load(out)
        done = {r["change"] for r in rows}
        ev = "/home/claude/eval-sy-imp"
        for f in sorted(glob.glob(os.path.join(ev, "tasks", "*.json"))):
            t = json.load(open(f))
            if t["id"] in done:
                continue
            tid = t["id"][:10]
            subs = t["subpackages"] if isinstance(t["subpackages"], list) else eval(t["subpackages"])
            a = os.path.join(ev, "impact", t["id"])
            cov = json.load(open(os.path.join(a, "covmap.json")))
            ok = ok_filter(set(json.load(open(os.path.join(a, "base_failures.json")))))
            universe = {n for n in cov if not n.startswith("__") and any(n.startswith(s + "/") for s in subs) and ok(n)}
            try:
                tree, cache = base_tree(f"sy-{tid}", f"/home/claude/cmp/sy/{tid}/tree", "sympy", subs)
                reset(tree, "sympy")
                for p in [p for p in G("diff", "--name-only", t["commit"], t["fix_commit"]).stdout.split()
                          if p.endswith(".py") and not istest(p)]:
                    open(os.path.join(tree, p), "w").write(G("show", f"{t['fix_commit']}:{p}").stdout)
                sel = driver("select", tree, cache, "sympy", subs)
                reset(tree, "sympy")
            except Exception as e:  # noqa: BLE001
                print(tid, "ERROR", repr(e)[:400], flush=True)
                continue
            rows.append({"repo": "sympy", "dataset": "real", "change": t["id"], **row(sel, universe, [], cov)})
            print(tid, "namerts", rows[-1]["selected"], "/", len(universe), flush=True)
            json.dump(rows, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
