"""Diagnose the two baseline problems that need data from the evaluation machine (read-only; changes nothing):
  1. pygments: testmon recorded no test executions (its rows are missing)
  2. datasette: file_coverage (from testmon's database) selects ~3% of tests and misses every planted bug
Usage (inside WSL, in the repository):  python research/v2/diagnose.py
Prints a report to paste back."""
import collections
import json
import os
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0]]
sys.path.insert(0, HERE)
import pipeline as P  # noqa: E402


def db_summary(db):
    if not os.path.exists(db):
        print("  database missing:", db)
        return None
    c = sqlite3.connect(db)
    tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
    print("  tables:", tabs)
    if "test_execution" not in tabs:
        return None
    n = c.execute("select count(*) from test_execution").fetchone()[0]
    print("  test executions:", n, "| file fingerprints:", c.execute("select count(*) from file_fp").fetchone()[0])
    rows = c.execute("select te.test_name, fp.filename from test_execution te "
                     "join test_execution_file_fp x on x.test_execution_id = te.id "
                     "join file_fp fp on fp.id = x.fingerprint_id").fetchall()
    c.close()
    m = collections.defaultdict(set)
    for t, f in rows:
        m[t].add(f)
    return m


def pygments():
    print("=" * 70, "\n1. pygments: testmon")
    P.use("pygments")
    log = os.path.join(P.WORK, "testmon.log")
    print("  testmon.log:", "present" if os.path.exists(log) else "absent")
    if os.path.exists(log):
        print("  --- last 40 lines ---")
        print("\n".join(open(log, errors="replace").read().splitlines()[-40:]))
    db_summary(os.path.join(P.WORK, "testmondata.base"))
    # a small live check: record testmon on two test files in a scratch tree
    tree = P.make_tree("diag", P.CFG["commit"])
    P.reset(tree)
    r = subprocess.run([P.PY, "-m", "pytest", "--testmon", "-p", "no:randomly", "-q", "--tb=short",
                        "tests/test_irc_formatter.py", "tests/examplefiles/docker"], cwd=tree,
                       env=P.env(tree, [P.PLUG]), capture_output=True, text=True, timeout=600)
    print("  live testmon run, exit", r.returncode, "\n  --- stdout tail ---\n" + r.stdout[-1500:],
          "\n  --- stderr tail ---\n" + r.stderr[-1500:])
    m = db_summary(os.path.join(tree, ".testmondata"))
    if m:
        print("  sample:", list(m.items())[:2])
    P.reset(tree)
    for f in (".testmondata",):
        if os.path.exists(os.path.join(tree, f)):
            os.remove(os.path.join(tree, f))


def datasette():
    print("=" * 70, "\n2. datasette: file_coverage")
    P.use("datasette")
    m = db_summary(os.path.join(P.WORK, "testmondata.base"))
    if not m:
        return
    files = collections.Counter(f for fs in m.values() for f in fs)
    print("  distinct files in the database:", len(files))
    print("  most common files:", files.most_common(12))
    print("  sample test names (db):", list(m)[:5])
    cov = P.jload(os.path.join(P.WORK, "covmap.json"), {}) or {}
    names = {k for k in cov if not k.startswith("__")}
    print("  covmap tests:", len(names), "| db tests:", len(m), "| in both:", len(names & set(m)))
    print("  sample test names (covmap):", sorted(names)[:5])
    for f in ("datasette/app.py", "datasette/views/database.py", "datasette/utils/internal_db.py"):
        print(f"  tests mapped to {f}: {sum(1 for fs in m.values() if f in fs)}")
    # what the planted bugs changed, versus what the database knows
    bugs = P.merged("truth")
    changed = collections.Counter(b["file"] for b in bugs.values() if b.get("failing"))
    print("  files of breaking planted bugs:", changed.most_common(8))
    print("  ...of these, files present in the database:", [f for f in changed if f in files])


if __name__ == "__main__":
    for step in (pygments, datasette):
        try:
            step()
        except Exception as e:  # noqa: BLE001
            print("  step failed:", repr(e)[:400])
