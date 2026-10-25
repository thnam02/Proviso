"""TDAD (Alonso, Yovine, Braberman 2026; github.com/pepealonso95/TDAD @ 73d1234) as a baseline selector, run through
its own Python API, unmodified, with its default NetworkX backend and "balanced" strategy:
  index(tree)                    build_graph + link_tests on the base tree (TDAD keeps its graph in TREE/.tdad/)
  select(tree, files, cap)       get_impacted_tests(tree, db, changed files, strategy="balanced", max_tests=cap)
TDAD's default cap is 50 tests; select(..., cap=None) gives the uncapped selection (to separate the cap's effect).
Its test ids ("test::FILE::Class.method:LINE") are mapped to pytest node ids (FILE::Class::method, all parameters)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

TDAD_SRC = os.environ.get("TDAD_SRC", os.path.expanduser("~/proviso-work/v2/TDAD/tdad/src"))
_ID = re.compile(r"^test::(?P<file>[^:]+\.py)::(?P<name>.+?)(?::\d+)?$")


def _api():
    if TDAD_SRC not in sys.path:
        sys.path.insert(0, TDAD_SRC)
    from tdad.core.config import get_settings, get_db
    from tdad.indexer.graph_builder import build_graph
    from tdad.indexer.test_linker import link_tests
    from tdad.analyzer.impact import get_impacted_tests
    return get_settings, get_db, build_graph, link_tests, get_impacted_tests


def index(tree: str) -> None:
    get_settings, get_db, build_graph, link_tests, _ = _api()
    repo = Path(tree).resolve()
    if (repo / ".tdad" / "graph.pkl").exists():
        return
    with get_db(get_settings(), repo_path=repo) as db:
        build_graph(repo, db, force=True)
        link_tests(repo, db)


def select(tree: str, files: list[str], cap: int | None = 50) -> set[str]:
    """Pytest node-id bases (FILE::Class::method) of the tests TDAD selects for the changed files."""
    get_settings, get_db, _, _, get_impacted_tests = _api()
    repo = Path(tree).resolve()
    with get_db(get_settings(), repo_path=repo) as db:
        tests = get_impacted_tests(repo, db, files, strategy="balanced", max_tests=cap if cap else 10 ** 9)
    out = set()
    for t in tests:
        m = _ID.match(t.get("test_id", ""))
        if m:
            out.add(f"{m.group('file')}::{m.group('name').replace('.', '::')}")
        elif t.get("test_file") and t.get("test_name"):
            out.add(f"{t['test_file']}::{t['test_name'].replace('.', '::')}")
    return out


def expand(bases: set[str], universe: set[str]) -> set[str]:
    """All node ids of the universe whose base (without [parameters]) TDAD selected."""
    return {n for n in universe if n.split("[", 1)[0] in bases}
