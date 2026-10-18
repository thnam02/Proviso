"""Run NameRTS (Wang, Pradel, Liu 2026; github.com/ZJU-CTAG/NameRTS @ f1acdae) on our changes, calling its own
classes in the order of its evaluation script (src/evaluate.py, evaluate_instance):

  init  (base tree)  : NameBDP(...).get_tests_to_run(init=True) + run_and_update(all tests)
                       = one instrumented, per-test-file isolated run of the suite; its caches are then saved
  select (changed)   : the base caches are restored and NameBDP(...).get_tests_to_run() returns the test FILES to run

Environment differences from the paper's setup: no conda (a stand-in `conda run` executes the command directly),
dependencies built from source at the versions pinned in environment_313.yml (tree-sitter 0.24.0,
tree-sitter-python 0.23.6, xxhash 3.5.0; execnet 2.1.1), `pytest` = system python3 -m pytest,, detect_indent replaced by a small equivalent,
pytest 9.1 instead of 8.4, 2 isolated workers instead of 30-50. NameRTS's files are unmodified; one edge-case fix is
applied at runtime (see setup()).

Usage: python namerts_driver.py init TREE CACHE_DIR [sympy]
       python namerts_driver.py select TREE CACHE_DIR [sympy]     (prints JSON list of selected test files)"""
import json
import os
import shutil
import sys

NR = "/home/claude/tools/NameRTS"
TOOLS = "/home/claude/tools"
DEPS = [f"{TOOLS}/nrts-bin", f"{TOOLS}/py-tree-sitter", f"{TOOLS}/tree-sitter-python/bindings/python",
        f"{TOOLS}/python-xxhash"]
# what the test processes need: the tree, NameRTS's instrumentor, its isolating pytest-xdist and execnet
TEST_PATH = [f"{NR}/src/instrumentor", f"{NR}/src/pytest-xdist-isolation/src", f"{TOOLS}/execnet/src"]
CACHED = ["dependencies.json", "py_checksums_cache.json", "nbdp_cache.json", "critical_names.json"]


def setup(tree, repo):
    os.environ["PATH"] = f"{TOOLS}/nrts-bin:" + os.environ.get("PATH", "/usr/bin:/bin")
    extra = [p for p in os.environ.get("NAMERTS_EXTRA_PATH", "").split(":") if p]  # a project's own test deps
    os.environ["PYTHONPATH"] = ":".join([tree] + TEST_PATH + extra)
    os.environ.pop("PYTEST_PLUGINS", None)  # pytest-xdist's entry point resolves to NameRTS's copy via PYTHONPATH
    os.environ["HOME"] = "/tmp"
    for p in [NR] + DEPS:
        sys.path.insert(0, p)
    import src.config as config
    config.REGISTRY_DECORATOR_KEYWORDS.clear()
    config.REGISTRY_DECORATOR_KEYWORDS.update({"register"} if repo == "sympy" else set())
    config.LOGGING = "/home/claude/cmp/nr-logs"
    os.makedirs(config.LOGGING, exist_ok=True)
    from src.instance_logger import InstanceLogger
    InstanceLogger(logger_id=f"NameBDP_{os.path.basename(os.path.dirname(tree))}",
                   logger_dir=f"NameBDP_{os.path.basename(os.path.dirname(tree))}")
    # Fix for one edge case (our only change to NameRTS's behaviour, applied at runtime): compute_coverage skips a test
    # file that imports nothing from the project (it is not a node of the graph), and NameBDP then fails on the
    # missing entry. As its own comment intends ("includes itself"), such a file depends on itself only.
    import networkx as nx
    import src.utils as U
    import src.framework as F

    def compute_coverage(graph, entries):
        g = nx.DiGraph()
        for node, neighbors in graph.items():
            for neighbor, _, _ in neighbors:
                g.add_edge(node, neighbor)
        return {e: (nx.descendants(g, e) | {e}) if e in g else {e} for e in entries}
    U.compute_coverage = F.compute_coverage = compute_coverage
    # Scope (sympy): the comparison scores the tests of the changed subpackages only, so NameRTS's test files are
    # limited to those directories (NAMERTS_SCOPE, comma-separated); its dependency analysis covers the whole tree.
    scope = [d for d in os.environ.get("NAMERTS_SCOPE", "").split(",") if d]
    if scope:
        orig = U.collect_all_heuristic

        def collect_scoped(project_path, *a, **k):
            return {t for t in orig(project_path, *a, **k) if any(t.startswith(d.rstrip("/") + "/") for d in scope)}
        U.collect_all_heuristic = F.collect_all_heuristic = collect_scoped
    from src.namebdp import NameBDP
    return NameBDP


def main():
    action, tree, cache = sys.argv[1], os.path.abspath(sys.argv[2]), sys.argv[3]
    repo = sys.argv[4] if len(sys.argv) > 4 else "sqlglot"
    NameBDP = setup(tree, repo)
    if action == "init":
        obj = NameBDP(project_path=tree, conda_env_name="local", n=2, use_isolation=True)
        tests = obj.get_tests_to_run(init=True)
        obj.run_and_update(tests)
        os.makedirs(cache, exist_ok=True)
        for f in CACHED:
            shutil.copy(os.path.join(tree, f), os.path.join(cache, f))
        print(json.dumps({"init_tests": len(tests), "test_time": obj.get_test_time()}))
    else:
        for f in CACHED:
            shutil.copy(os.path.join(cache, f), os.path.join(tree, f))
        obj = NameBDP(project_path=tree, conda_env_name="local", n=2, use_isolation=True)
        tests = obj.get_tests_to_run()
        print("NAMERTS_SELECTED " + json.dumps(sorted(tests)))


if __name__ == "__main__":
    main()
