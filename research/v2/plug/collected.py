"""pytest plugin: the node ids that remain after collection and deselection (e.g. by pytest-testmon), written to
COLLECTED_OUT; independent of output verbosity, which a project's addopts can change."""
import json, os

import pytest


@pytest.hookimpl(trylast=True)
def pytest_collection_finish(session):
    json.dump([it.nodeid for it in session.items], open(os.environ["COLLECTED_OUT"], "w"))
