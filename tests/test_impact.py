"""Change impact: test-command rewriting, selection from coverage, ripple wiring."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_engine import impact as I  # noqa: E402


class Rewrite(unittest.TestCase):
    def test_broad_runs_rewritten_targeted_left_alone(self):
        r = I.rewrite("cd /x && python -m pytest tests -q 2>&1 | tail -5; python -m pytest tests/a.py", "/h", "/v")
        self.assertIn("/h -m dc_engine.impact run --python /v | tail -5", r)
        self.assertIn("python -m pytest tests/a.py", r)
        self.assertIsNotNone(I.rewrite("python -m unittest discover -s tests", "/h", "/v"))
        self.assertIsNotNone(I.rewrite("make unit", "/h", "/v"))
        self.assertIsNone(I.rewrite("python -m pytest tests -k foo", "/h", "/v"))
        self.assertIsNone(I.rewrite("python -m unittest tests.dialects.test_mysql", "/h", "/v"))
        self.assertIsNone(I.rewrite("ls tests", "/h", "/v"))


SRC = textwrap.dedent('''\
    TABLE = {"a": 1}


    class Calc:
        MODE = "x"

        def area(self, w, h):
            return w * h

        def label(self, x):
            return str(x)


    def helper():
        return 1
''')


class Selection(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="impact-")
        os.makedirs(os.path.join(self.root, "pkg"))
        open(os.path.join(self.root, "pkg", "calc.py"), "w").write(SRC)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "b"], cwd=self.root, check=True)
        self.cov = {"t::area": {"funcs": [["pkg/calc.py", 7]], "time": 1.0},
                    "t::label": {"funcs": [["pkg/calc.py", 10]], "time": 1.0},
                    "t::helper": {"funcs": [["pkg/calc.py", 14]], "time": 1.0}}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def edit(self, old, new):
        p = os.path.join(self.root, "pkg", "calc.py")
        text = open(p).read().replace(old, new)
        open(p, "w").write(text)

    def test_function_edit_selects_its_tests(self):
        self.edit("return w * h", "return w + h")
        sel, _ = I.selection(self.root, self.cov)
        self.assertEqual(sel, ["t::area"])

    def test_class_statement_selects_tests_of_that_class(self):
        self.edit('MODE = "x"', 'MODE = "y"')
        sel, _ = I.selection(self.root, self.cov)
        self.assertEqual(sel, ["t::area", "t::label"])

    def test_module_statement_selects_whole_file(self):
        self.edit('TABLE = {"a": 1}', 'TABLE = {"a": 2}')
        sel, _ = I.selection(self.root, self.cov)
        self.assertEqual(len(sel), 3)

    def test_new_source_file_falls_back_to_full_suite(self):
        open(os.path.join(self.root, "pkg", "new.py"), "w").write("x = 1\n")
        sel, why = I.selection(self.root, self.cov)
        self.assertIsNone(sel)
        self.assertIn("new source file", why["reason"])

    def test_no_change_selects_nothing(self):
        self.assertEqual(I.selection(self.root, self.cov)[0], [])


class Hooks(unittest.TestCase):
    def test_impact_arm_hooks_and_assets(self):
        from dc_eval.arms import arm_config, proviso_settings, write_proviso_files
        flags = arm_config("impact")["proviso"]
        hooks = proviso_settings("/py", "/probe", flags)["hooks"]
        self.assertEqual(set(hooks), {"UserPromptSubmit", "PreToolUse", "Stop"})
        self.assertIn("proviso-pretool", hooks["PreToolUse"][0]["hooks"][0]["command"])
        self.assertEqual(set(proviso_settings("/py", "/probe", arm_config("intercept-only")["proviso"])["hooks"]),
                         {"UserPromptSubmit", "PreToolUse"})
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with self.assertRaises(FileNotFoundError):
            write_proviso_files(os.path.join(d, "s"), os.path.join(d, "r"), "/p", flags, assets=os.path.join(d, "no"))
        os.makedirs(os.path.join(d, "a"))
        open(os.path.join(d, "a", "covmap.json"), "w").write("{}")
        write_proviso_files(os.path.join(d, "s"), os.path.join(d, "r"), "/p", flags, assets=os.path.join(d, "a"))
        self.assertTrue(os.path.isfile(os.path.join(d, "r", ".dc-engine", "covmap.json")))

    def test_pretool_rewrites_only_with_coverage_map(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        payload = {"tool_name": "Bash", "tool_input": {"command": "python -m pytest tests -q"}}
        cfg = {"impact": True, "python": "/v"}
        self.assertEqual(I.pretool(payload, d, cfg), {})
        os.makedirs(os.path.join(d, ".dc-engine"))
        open(os.path.join(d, ".dc-engine", "covmap.json"), "w").write("{}")
        out = I.pretool(payload, d, cfg)
        self.assertIn("dc_engine.impact run", out["hookSpecificOutput"]["updatedInput"]["command"])


if __name__ == "__main__":
    unittest.main()
