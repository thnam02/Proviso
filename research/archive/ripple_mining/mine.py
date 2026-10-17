"""Mine sqlglot history for real ripple regressions.

For every commit in a window, the same probes (inputs from the existing tests of the newest commit, each run in its own
dialect and in every dialect that inherits from it) are replayed, so consecutive commits can be compared:

  divergent ripple at commit P   a child dialect's output on an input changed at P, and not in the way its parent's
                                 output on the same input changed (or the parent's did not change)
  restored at commit F > P       the child's output returns to its pre-P value while the parent's keeps P's change:
                                 evidence that the child's change at P was unintended, and F is its fix

Usage:
  python mine.py replay REPO FIRST_COMMIT LAST_COMMIT OUT_DIR    replay every commit (first-parent) in the range
  python mine.py analyse OUT_DIR                                 find divergent ripples and their restores
"""
import json, os, shutil, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ripple"))
import replay as R  # noqa: E402


def export(repo, commit, paths):
    d = tempfile.mkdtemp(prefix="mine-")
    arch = subprocess.run(["git", "-C", repo, "archive", commit, *paths], capture_output=True)
    subprocess.run(["tar", "-x", "-C", d], input=arch.stdout, capture_output=True)
    return d


def replay_range(repo, first, last, out):
    """Outputs per commit are stored as the difference from the previous commit (the first one in full)."""
    os.makedirs(out, exist_ok=True)
    commits = subprocess.run(["git", "-C", repo, "rev-list", "--first-parent", "--reverse", f"{first}^..{last}"],
                             capture_output=True, text=True).stdout.split()
    probes_p = os.path.join(out, "probes.json")
    if not os.path.exists(probes_p):
        t = export(repo, last, ["sqlglot", "tests"])
        probes = R.probes(R.corpus(t), R.ripple(t))
        shutil.rmtree(t)
        json.dump(probes, open(probes_p, "w"))
    json.dump(commits, open(os.path.join(out, "commits.json"), "w"))
    full = None
    for i, c in enumerate(commits):
        dest = os.path.join(out, f"{i:05d}-{c[:10]}.json")
        if os.path.exists(dest):
            d = json.load(open(dest))
            if "error" not in d:
                full = d["outputs"] if i == 0 else {**full, **d["outputs"]}
            continue
        changed = subprocess.run(["git", "-C", repo, "diff", "--name-only", f"{c}^", c, "--", "sqlglot"],
                                 capture_output=True, text=True).stdout.split()
        if full is not None and not [f for f in changed if f.endswith(".py")]:
            json.dump({"outputs": {}}, open(dest, "w"))  # no source change: same behaviour
            continue
        t0 = time.time()
        t = export(repo, c, ["sqlglot"])
        tmp = dest + ".full"
        try:
            R.run(t, probes_p, tmp)
            cur = json.load(open(tmp))
            if full is None:
                delta = cur
            else:
                delta = {k: v for k, v in cur.items() if full.get(k) != v}
            full = cur
            json.dump({"outputs": delta}, open(dest, "w"))
        except Exception as e:  # noqa: BLE001
            json.dump({"error": str(e)[-300:]}, open(dest, "w"))
        finally:
            shutil.rmtree(t, ignore_errors=True)
            if os.path.exists(tmp):
                os.remove(tmp)
        print(i, c[:10], f"{time.time() - t0:.1f}s", len(delta) if full is not None else "", flush=True)


def _edit(a, b):
    a, b = a or "", b or ""
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    j = 0
    while j < min(len(a), len(b)) - i and a[-1 - j] == b[-1 - j]:
        j += 1
    return a[i:len(a) - j], b[i:len(b) - j]


def analyse(out, horizon=400):
    import bisect
    probes = json.load(open(os.path.join(out, "probes.json")))
    commits = json.load(open(os.path.join(out, "commits.json")))
    own = {(p[0], p[2]): str(i) for i, p in enumerate(probes) if p[0] == p[1]}
    files = sorted(f for f in os.listdir(out) if f[:5].isdigit() and f.endswith(".json"))
    timeline: dict[str, list] = {}  # key -> [(idx, value)] at each change
    broken = set()
    for f in files:
        i = int(f[:5])
        d = json.load(open(os.path.join(out, f)))
        if "error" in d:
            broken.add(i)  # behaviour unknown at this commit (does not import): treated as unchanged
            continue
        for k, v in d["outputs"].items():
            timeline.setdefault(k, []).append((i, v))

    def at(k, i):
        tl = timeline.get(k, [])
        j = bisect.bisect_right([x[0] for x in tl], i) - 1
        return tl[j][1] if j >= 0 else None

    found = []
    for k, tl in timeline.items():
        src, dia, sql = probes[int(k)]
        if src == dia:
            continue
        pk = own.get((src, sql))
        for n in range(1, len(tl)):
            i, after = tl[n]
            before = tl[n - 1][1]
            pa, pb = (at(pk, i - 1), at(pk, i)) if pk else (None, None)
            if pk and pa != pb and _edit(pa, pb) == _edit(before, after):
                continue  # the child follows its parent exactly
            restore = None
            for m in range(n + 1, len(tl)):
                j, v = tl[m]
                if j >= i + horizon:
                    break
                if v == before and (pk is None or pa == pb or at(pk, j) == pb):
                    restore = j
                    break
            found.append({"commit": commits[i], "idx": i, "child": dia, "parent": src, "input": sql,
                          "child_before": before, "child_after": after, "parent_before": pa, "parent_after": pb,
                          "parent_changed": pa != pb, "restored_at": commits[restore] if restore else None,
                          "restore_idx": restore})
    found.sort(key=lambda x: (x["idx"], x["child"]))
    json.dump(found, open(os.path.join(out, "ripples.json"), "w"), indent=1)
    return found


if __name__ == "__main__":
    if sys.argv[1] == "replay":
        replay_range(*sys.argv[2:6])
    else:
        f = analyse(sys.argv[2])
        import collections
        print(len(f), "divergent child changes;", sum(1 for x in f if x["restored_at"]), "later restored")
        by = collections.Counter((x["commit"][:10], x["child"], bool(x["restored_at"])) for x in f)
        for (c, ch, r), n in sorted(by.items(), key=lambda kv: -kv[1])[:40]:
            print(c, ch, "RESTORED" if r else "", n)
