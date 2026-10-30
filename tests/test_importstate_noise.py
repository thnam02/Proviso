"""The import-time snapshot must not report changes that come from how a tree is installed rather than from the code:
a version module generated at install time (setuptools-scm's _version.py), and the logging registry state that a
missing version module leaves behind (a warning logged during import). Real changes must still be reported."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_engine import importstate as S  # noqa: E402

INIT = '''import logging
logger = logging.getLogger("pkg")
try:
    from pkg._version import __version__
except ImportError:
    logger.warning("version unknown")
    __version__ = "0"
'''
CORE = '''import logging
logger = logging.getLogger("pkg")
TABLE = {"a": 1, "b": 2}
'''


def _git(cwd, *a):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True, capture_output=True)


class ImportStateNoise(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "pkg"))
        open(os.path.join(self.root, "pkg", "__init__.py"), "w").write(INIT)
        open(os.path.join(self.root, "pkg", "core.py"), "w").write(CORE)
        _git(self.root, "init", "-q")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "base")
        self.files = ["pkg/__init__.py", "pkg/core.py"]
        self.base = S.base_snapshot(self.root, self.files, sys.executable, os.path.join(self.root, "base.json"))
        self.assertIsNotNone(self.base)

    def changed(self):
        d = S.diff(self.base, S.snapshot(self.root, self.files, sys.executable), set())
        return set(d if isinstance(d, (set, list)) else d.get("changed", d))

    def test_generated_version_module_is_not_a_change(self):
        open(os.path.join(self.root, "pkg", "_version.py"), "w").write('__version__ = "1.2.3"\n')
        self.assertEqual(self.changed(), set())

    def test_real_table_change_is_reported(self):
        open(os.path.join(self.root, "pkg", "core.py"), "w").write(CORE.replace('"b": 2', '"b": 3'))
        self.assertIn("pkg.core:TABLE", self.changed())

    def test_logger_level_change_is_reported(self):
        open(os.path.join(self.root, "pkg", "core.py"), "w").write(CORE + "logger.setLevel(logging.ERROR)\n")
        self.assertIn("pkg.core:logger", self.changed())


if __name__ == "__main__":
    unittest.main()
