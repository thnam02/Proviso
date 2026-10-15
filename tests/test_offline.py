"""Offline mode and host-authenticated Claude Code runs."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_eval import offline
from dc_eval.arms import claude_argv
from dc_eval.grade import restore_hidden_tests
from dc_eval.tasks import Task


class OfflineHelpers(unittest.TestCase):
    def test_editable_install_detection(self):
        self.assertTrue(offline.is_editable_install("python -m pip install -e . -q"))
        self.assertTrue(offline.is_editable_install(["py", "-m", "pip", "install", "-q", "-e", ".[dev]"]))
        self.assertFalse(offline.is_editable_install("python -m pip install requests"))
        self.assertFalse(offline.offline_setup("make build", "/x", sys.executable, None))

    def test_link_editable_writes_pth_into_venv(self):
        d = tempfile.mkdtemp(prefix="dc-off-")
        self.addCleanup(shutil.rmtree, d, True)
        repo = os.path.join(d, "repo")
        os.makedirs(os.path.join(repo, "pkg"))
        open(os.path.join(repo, "pkg", "__init__.py"), "w").write("X = 1\n")
        venv = os.path.join(d, "venv")
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", venv], check=True)
        py = os.path.join(venv, "bin", "python")
        offline.link_editable(py, repo)
        r = subprocess.run([py, "-c", "import pkg; print(pkg.X)"], capture_output=True, text=True,
                           cwd=d)
        self.assertEqual(r.stdout.strip(), "1", r.stderr)

    def test_agent_env_is_clean(self):
        d = tempfile.mkdtemp(prefix="dc-env-")
        self.addCleanup(shutil.rmtree, d, True)
        base = {
            "PATH": "/usr/bin", "HOME": "/root", "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "CLAUDE_CODE_SESSION_ID": "parent", "CLAUDECODE": "1", "HTTPS_PROXY": "http://p:1",
            "https_proxy": "http://p:1", "ANTHROPIC_API_KEY": "should-not-leak",
        }
        env = offline.claude_agent_env(d, {"PATH": "/v/bin:/usr/bin", "VIRTUAL_ENV": "/v"}, base)
        self.assertEqual(env["HOME"], os.path.join(d, "home"))
        self.assertTrue(os.path.isdir(env["HOME"]))
        self.assertEqual(env["PATH"], "/v/bin:/usr/bin")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.anthropic.com")
        for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE", "HTTPS_PROXY", "https_proxy",
                  "ANTHROPIC_API_KEY"):
            self.assertNotIn(k, env)

    def test_claude_argv_bare_toggle(self):
        self.assertIn("--bare", claude_argv("p", "baseline", model="m", budget_usd=1))
        self.assertNotIn("--bare", claude_argv("p", "baseline", model="m", budget_usd=1, bare=False))


PATCH = """diff --git a/t_test.py b/t_test.py
--- a/t_test.py
+++ b/t_test.py
@@ -1,2 +1,5 @@
 def test_a():
     assert True
+
+def test_b():
+    assert True
"""


class GradeWithoutFixCommit(unittest.TestCase):
    def test_agent_edit_reset_then_patch_applied(self):
        d = tempfile.mkdtemp(prefix="dc-nofix-")
        self.addCleanup(shutil.rmtree, d, True)
        repo = os.path.join(d, "repo")
        os.makedirs(repo)
        run = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
        run("init", "-q")
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        with open(os.path.join(repo, "t_test.py"), "w") as fh:
            fh.write("def test_a():\n    assert True\n")
        run("add", ".")
        run("commit", "-q", "-m", "base")
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                              text=True).stdout.strip()
        with open(os.path.join(repo, "t_test.py"), "w") as fh:  # agent edit
            fh.write("def test_a():\n    assert 1 == 1  # agent\n")
        task = Task(id="zzzz-no-fix", repo=repo, commit=base, prompt="p",
                    hidden_tests=["t_test.py::test_b"], test_patch=PATCH)
        run_dir = os.path.join(d, "slot")
        modified = restore_hidden_tests(task, repo, src_repo=repo, run_dir=run_dir)
        self.assertEqual(modified, ["t_test.py"])
        body = open(os.path.join(repo, "t_test.py")).read()
        self.assertIn("def test_b", body)
        self.assertNotIn("# agent", body)
        saved = os.path.join(run_dir, "agent_test_changes", "t_test.py")
        self.assertIn("# agent", open(saved).read())


if __name__ == "__main__":
    unittest.main()


class FreshCopyHistory(unittest.TestCase):
    """The run copy must not expose commits after the task's base commit."""

    def test_future_commits_are_not_reachable(self):
        from dc_eval.run import _fresh_copy
        d = tempfile.mkdtemp(prefix="dc-hist-")
        self.addCleanup(shutil.rmtree, d, True)
        src = os.path.join(d, "src")
        os.makedirs(src)
        g = lambda *a, cwd=src: subprocess.run(["git", *a], cwd=cwd, check=True,
                                               capture_output=True, text=True).stdout.strip()
        g("init", "-q")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        for i, msg in enumerate(("one", "base", "the-fix")):
            open(os.path.join(src, "f.py"), "w").write(f"x = {i}\n")
            g("add", ".")
            g("commit", "-q", "-m", msg)
        fix = g("rev-parse", "HEAD")
        base = g("rev-parse", "HEAD~1")
        dest = os.path.join(d, "runs", "copy")
        _fresh_copy(src, base, dest)
        self.assertEqual(g("rev-parse", "HEAD", cwd=dest), base)
        self.assertEqual(open(os.path.join(dest, "f.py")).read(), "x = 1\n")
        self.assertIn("one", g("log", "--all", "--format=%s", cwd=dest))
        self.assertNotIn("the-fix", g("log", "--all", "--format=%s", cwd=dest))
        r = subprocess.run(["git", "cat-file", "-e", fix], cwd=dest, capture_output=True)
        self.assertNotEqual(r.returncode, 0, "fix commit object leaked into the run copy")
        self.assertEqual(g("remote", cwd=dest), "")
        self.assertNotIn("dc-eval", g("for-each-ref", cwd=src))
