"""Hidden test files a task adds beyond its fix commit are applied from the task's patch."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from dc_eval.grade import patch_for_files  # noqa: E402

PATCH = ("diff --git a/tests/a.py b/tests/a.py\n--- a/tests/a.py\n+++ b/tests/a.py\n@@ -1 +1 @@\n-x\n+y\n"
         "diff --git a/tests/new.py b/tests/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/tests/new.py\n"
         "@@ -0,0 +1 @@\n+z\n")


class PatchForFiles(unittest.TestCase):
    def test_keeps_only_requested_files(self):
        out = patch_for_files(PATCH, ["tests/new.py"])
        self.assertTrue(out.startswith("diff --git a/tests/new.py"))
        self.assertNotIn("tests/a.py", out)
        self.assertEqual(patch_for_files(PATCH, []), "")
