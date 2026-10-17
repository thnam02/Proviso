"""Safety of impact selection on real agent edits: for each final working tree of a pilot run, the full suite is run
and every test failing there (and not at the base commit) must be in the selection computed for that tree.
Usage: python real_edit_check.py OUT.json RUN_REPO_DIR..."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from dc_engine import impact as I  # noqa: E402

rows = []
for repo in sys.argv[2:]:
    py = os.path.join(os.path.dirname(repo), "venv", "bin", "python")
    cov = json.load(open(os.path.join(repo, ".dc-engine", "covmap.json")))
    base_fail = set(json.load(open(os.path.join(repo, ".dc-engine", "base_failures.json"))))
    sel, why = I.selection(repo, cov, py)
    selected = (set(cov) - {"__global__"}) if sel is None else set(sel)
    xml = os.path.join(repo, ".dc-engine", "realcheck.xml")
    subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "--continue-on-collection-errors",
                    f"--junitxml={xml}", "tests"], cwd=repo, capture_output=True, timeout=1800)
    res = I._junit(xml)
    failing = sorted(n for n, ok in res.items() if not ok and n not in base_fail and n.split("::")[0] not in base_fail)
    missed = [n for n in failing if n not in selected and not ("::" not in n and any(s.startswith(n) for s in selected))]
    rows.append({"repo": repo, "selected": len(selected), "suite": len(cov) - 1, "full": sel is None,
                 "new_failures": failing, "missed": missed})
    print(repo.split("/runs/")[1][:40], "selected", len(selected), "new failures", len(failing), "MISSED" if missed else "ok",
          missed[:3], flush=True)
    json.dump(rows, open(sys.argv[1], "w"), indent=1)
