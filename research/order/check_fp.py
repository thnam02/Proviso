"""Check that the memoised fingerprinter (importstate FORMAT 9) finds exactly the same changed import-time values as
the previous one (FORMAT 8, saved copy) on every benchmark change: real sqlglot commits and all planted bugs.
For each change: base snapshot (with the order-instability runs) and working-tree snapshot under both versions,
then importstate.diff; the changed-key sets must be equal. Usage: python check_fp.py OLD_IMPORTSTATE.py OUT.json"""
import glob, importlib.util, json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import order as O  # noqa: E402
from dc_engine import importstate as NEW  # noqa: E402
spec = importlib.util.spec_from_file_location("importstate_old", sys.argv[1])
OLD = importlib.util.module_from_spec(spec); spec.loader.exec_module(OLD)
out_path = sys.argv[2]
rows = json.load(open(out_path)) if os.path.exists(out_path) else []
done = {r["id"] for r in rows}


def base_snaps(tree, files):
    res = {}
    for name, mod in (("old", OLD), ("new", NEW)):
        cache = os.path.join(O.S, f"fpcheck_{name}_{abs(hash((tree, tuple(files))))}.json")
        if os.path.exists(cache):
            os.remove(cache)
        t = time.time()
        res[name] = mod.base_snapshot(tree, files, "python3", cache)
        res[name + "_s"] = time.time() - t
    return res


def compare(cid, tree, files, base):
    if cid in done:
        return
    r = {"id": cid}
    for name, mod in (("old", OLD), ("new", NEW)):
        t = time.time()
        cur = mod.snapshot(tree, files, "python3")
        r[name + "_s"] = round(time.time() - t, 2)
        d = mod.diff(base[name], cur) if cur and base[name] else None
        r[name] = None if d is None else sorted(d["changed"])
    r["same"] = r["old"] == r["new"]
    r["n_changed"] = len(r["new"] or [])
    print(cid, "same" if r["same"] else "DIFFERENT", r["n_changed"], r["old_s"], r["new_s"], flush=True)
    rows.append({k: v for k, v in r.items() if k not in ("old", "new")} | ({} if r["same"] else
                {"only_old": sorted(set(r["old"] or []) - set(r["new"] or []))[:20],
                 "only_new": sorted(set(r["new"] or []) - set(r["old"] or []))[:20]}))
    json.dump(rows, open(out_path, "w"), indent=1)


def files_of(cov):
    return sorted({f for k, v in cov.items() for f, _ in v["funcs"] if not O.SEL.I._is_test_path(f)})


g = lambda w, *a: subprocess.run(["git", *a], cwd=w, capture_output=True)
# real sqlglot commits (working tree = commit's source changes on the parent)
for d in sorted(glob.glob(os.path.join(O.SQ, "*"))):
    tid = os.path.basename(d)
    if not os.path.isfile(os.path.join(d, "proviso.json")) or f"real:{tid}" in done:
        continue
    tree = os.path.join(d, "tree")
    files = files_of(json.load(open(os.path.join(O.S, "ripple", f"cov2_{tid}.json"))))
    compare(f"real:{tid}", tree, files, base_snaps(tree, files))
allbugs = json.load(open(os.path.join(O.ROOT, "research", "ripple", "mutants2_scored.json")))
sets = [(t, f"/home/claude/cmp/mut-{t}", os.path.join(O.S, "ripple", f"cov2_{t}.json"), [b for b in allbugs if b["commit"] == t])
        for t in ("7f1cf60c88", "862fd55467")]
sets.append(("sympy", os.path.join(O.S, "mut-sympy"), os.path.join(O.S, "cov_mut_sympy_functions.json"),
             json.load(open(os.path.join(O.ROOT, "research", "sympy", "mutants.json")))))
for tag, work, covp, bugs in sets:
    g(work, "checkout", "-q", "--", ".")
    files = files_of(json.load(open(covp)))
    todo = [b for b in bugs if b.get("killed") is not None and f"{tag}:{b['file']}:{b['line']}" not in done]
    if not todo:
        continue
    base = base_snaps(work, files)
    print(tag, "base snapshot s: old", round(base["old_s"], 1), "new", round(base["new_s"], 1), flush=True)
    ov = {(c[0], c[1], c[2]): c for c in O.M.override_candidates(work)} if any(b["kind"] == "override" for b in todo) else {}
    for b in todo:
        g(work, "checkout", "-q", "--", ".")
        if b["kind"] == "override":
            cand = next(c for k, c in ov.items() if k[0] == b["file"] and k[1] == b["line"] and b["code"].startswith(k[2] + " "))
            O.M.apply_override(work, cand)
        else:
            O.M.apply(work, b["file"], b["line"], b["op"])
        try:
            compare(f"{tag}:{b['file']}:{b['line']}", work, files, base)
        finally:
            g(work, "checkout", "-q", "--", ".")
print("ALL", len(rows), "same", sum(r["same"] for r in rows))
