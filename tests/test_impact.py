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
        self.assertIn("/h -m dc_engine.impact run --python /v -- tests;", r)
        self.assertNotIn("tail -5", r)
        self.assertIn("-- tests/a.py", r)  # whole test files are selected within too
        self.assertIsNotNone(I.rewrite("python -m unittest discover -s tests", "/h", "/v"))
        self.assertIsNotNone(I.rewrite("make unit", "/h", "/v"))
        self.assertIsNone(I.rewrite("python -m pytest tests -k foo", "/h", "/v"))
        self.assertIsNone(I.rewrite("python -m unittest tests.dialects.test_mysql", "/h", "/v"))
        self.assertIsNone(I.rewrite("pytest tests/a.py::TestA::test_b", "/h", "/v"))
        self.assertIsNone(I.rewrite("ls tests", "/h", "/v"))
        # any directory counts, in any layout; files and test ids are already narrow
        self.assertTrue(I.rewrite("python -m pytest sympy/solvers -q", "/h", "/v").endswith("-- sympy/solvers"))
        self.assertTrue(I.rewrite("pytest sympy/solvers/tests/ sympy/core", "/h", "/v").endswith(
            "-- sympy/solvers/tests/ sympy/core"))
        self.assertIsNotNone(I.rewrite("bin/test sympy/printing", "/h", "/v"))
        self.assertIsNone(I.rewrite("bin/test test_latex", "/h", "/v"))
        self.assertTrue(I.rewrite("pytest sympy/solvers/tests/test_solvers.py", "/h", "/v").endswith(
            "-- sympy/solvers/tests/test_solvers.py"))
        self.assertIsNone(I.rewrite("pytest 'sympy/core/tests/test_basic.py::test_x'", "/h", "/v"))
        self.assertTrue(I.rewrite("python -m pytest -q", "/h", "/v").endswith("--python /v"))


SRC = textwrap.dedent('''\
    TABLE = {"a": 1}
    UNUSED = 1


    class Calc:
        MODE = "x"

        def area(self, w, h):
            return w * h

        def label(self, x):
            return self.MODE + str(x)


    class Sub(Calc):
        pass


    def helper():
        return TABLE["a"]
''')


def _line(src, name):
    import ast
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            return node.lineno
    raise KeyError(name)


class Selection(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="impact-")
        os.makedirs(os.path.join(self.root, "pkg"))
        os.makedirs(os.path.join(self.root, "tests"))
        open(os.path.join(self.root, "pkg", "__init__.py"), "w").write("")
        open(os.path.join(self.root, "pkg", "calc.py"), "w").write(SRC)
        open(os.path.join(self.root, "tests", "test_calc.py"), "w").write("def test_mode():\n    pass\n")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "b"], cwd=self.root, check=True)
        f = "pkg/calc.py"
        calc = ["pkg/calc.py:Calc"]
        self.cov = {"t::area": {"funcs": [[f, _line(SRC, "area")]], "classes": calc, "time": 1.0},
                    "t::label": {"funcs": [[f, _line(SRC, "label")]], "classes": calc, "time": 1.0},
                    "t::sub_label": {"funcs": [[f, _line(SRC, "label")]], "classes": ["pkg/calc.py:Sub"] + calc,
                                     "time": 1.0},
                    "t::helper": {"funcs": [[f, _line(SRC, "helper")]], "time": 1.0},
                    "tests/test_calc.py::test_mode": {"funcs": [], "time": 1.0}}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def edit(self, old, new):
        p = os.path.join(self.root, "pkg", "calc.py")
        text = open(p).read()
        assert old in text
        open(p, "w").write(text.replace(old, new))

    def sel(self):
        return I.selection(self.root, self.cov, sys.executable)

    def test_function_edit_selects_its_tests(self):
        self.edit("return w * h", "return w + h")
        self.assertEqual(self.sel()[0], ["t::area"])

    def test_class_attribute_selects_its_readers_among_users_of_the_class(self):
        self.edit('MODE = "x"', 'MODE = "y"')
        sel, why = self.sel()
        self.assertEqual(sel, ["t::label", "t::sub_label"])
        self.assertEqual(why["import_state_n"], 1)

    def test_module_constant_selects_its_readers(self):
        self.edit('TABLE = {"a": 1}', 'TABLE = {"a": 2}')
        self.assertEqual(self.sel()[0], ["t::helper"])

    def test_unread_constant_and_new_definitions_select_nothing(self):
        self.edit("UNUSED = 1", "UNUSED = 2")
        self.assertEqual(self.sel()[0], [])
        self.edit("UNUSED = 2\n", "UNUSED = 2\nimport json\n\n\ndef extra():\n    return json.dumps(2)\n")
        self.assertEqual(self.sel()[0], [])

    def test_override_in_subclass_selects_tests_of_the_subclass(self):
        self.edit("class Sub(Calc):\n    pass", "class Sub(Calc):\n    def label(self, x):\n        return str(x)")
        self.assertEqual(self.sel()[0], ["t::sub_label"])

    def test_constant_read_by_the_test_itself(self):
        open(os.path.join(self.root, "tests", "test_calc.py"), "w").write(
            "from pkg.calc import UNUSED\n\ndef test_mode():\n    assert UNUSED == 1\n")
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "t"], cwd=self.root)
        self.edit("UNUSED = 1", "UNUSED = 2")
        self.assertEqual(self.sel()[0], ["tests/test_calc.py::test_mode"])

    def test_new_base_class_selects_users_of_the_class(self):
        self.edit("class Sub(Calc):", "class Sub(Calc, dict):")
        self.assertEqual(self.sel()[0], ["t::sub_label"])

    def test_module_that_stops_importing_falls_back_to_full_suite(self):
        self.edit('TABLE = {"a": 1}', 'TABLE = {"a": 1}\nraise RuntimeError("boom")')
        sel, why = self.sel()
        self.assertIsNone(sel)
        self.assertIn("no longer imports", why["reason"])

    def test_new_source_file_falls_back_to_full_suite(self):
        open(os.path.join(self.root, "pkg", "new.py"), "w").write("x = 1\n")
        sel, why = self.sel()
        self.assertIsNone(sel)
        self.assertIn("new source file", why["reason"])

    def test_no_change_selects_nothing(self):
        self.assertEqual(self.sel()[0], [])


class Runner(unittest.TestCase):
    """run_selected end to end with real pytest, tests living inside the package (sympy layout)."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="impact-run-")
        os.makedirs(os.path.join(self.root, "pkg", "tests"))
        os.makedirs(os.path.join(self.root, ".dc-engine"))
        open(os.path.join(self.root, "pkg", "__init__.py"), "w").write("")
        open(os.path.join(self.root, "pkg", "tests", "__init__.py"), "w").write("")
        open(os.path.join(self.root, "pkg", "calc.py"), "w").write(
            "def area(w, h):\n    return w * h\n\n\ndef label(x):\n    return str(x)\n")
        open(os.path.join(self.root, "pkg", "tests", "test_calc.py"), "w").write(
            "from pkg.calc import area, label\n\n\ndef test_area():\n    assert area(2, 3) == 6\n\n\n"
            "def test_label():\n    assert label(1) == '1'\n\n\ndef test_unknown():\n    assert True\n")
        g = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=self.root,
                                      capture_output=True)
        open(os.path.join(self.root, ".gitignore"), "w").write(".dc-engine/\n__pycache__/\n")
        g("init", "-q"); g("add", "-A"); g("commit", "-qm", "b")
        t = "pkg/tests/test_calc.py::"
        json.dump({t + "test_area": {"funcs": [["pkg/calc.py", 1]]}, t + "test_label": {"funcs": [["pkg/calc.py", 5]]}},
                  open(os.path.join(self.root, ".dc-engine", "covmap.json"), "w"))
        json.dump([], open(os.path.join(self.root, ".dc-engine", "base_failures.json"), "w"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_runs_affected_and_unknown_tests_only(self):
        p = os.path.join(self.root, "pkg", "calc.py")
        src = open(p).read()
        open(p, "w").write(src.replace("w * h", "w + h"))
        text = I.run_selected(self.root, sys.executable, ["pkg"])
        self.assertIn("Ran the 2 tests in pkg", text)  # test_area (affected) + test_unknown (no coverage record)
        self.assertIn("NEW failures (1)", text)
        self.assertIn("pkg/tests/test_calc.py::test_area", text)

    def test_unchanged_code_runs_only_unknown_tests(self):
        text = I.run_selected(self.root, sys.executable, ["pkg"])
        self.assertIn("Ran the 1 tests in pkg", text)
        self.assertIn("No new failures", text)


class TestPaths(unittest.TestCase):
    def test_test_files_anywhere(self):
        for p in ("tests/a.py", "sympy/core/tests/test_basic.py", "pkg/test_x.py", "sympy/conftest.py"):
            self.assertTrue(I._is_test_path(p), p)
        for p in ("sympy/core/basic.py", "sympy/testing/runtests.py", "pkg/contest.py"):
            self.assertFalse(I._is_test_path(p), p)


class Ripple(unittest.TestCase):
    def test_report_separates_inherited_from_divergent_changes(self):
        long = "SELECT " + "x, " * 60 + "a(nolock) FROM t"
        items = [{"component": "fabric", "parent": "tsql", "input": long, "was": long,
                  "now": long.replace("a(nolock)", "a WITH (nolock)"), "same": True, "error": False},
                 {"component": "doris", "parent": "mysql", "input": "q", "was": "CAST(a AS DATETIME)",
                  "now": "CAST(a AS TIMESTAMP)", "same": False, "error": False}]
        text = I.ripple_report(items)
        self.assertIn("doris (inherits from mysql)", text)
        self.assertIn("now `CAST(a AS TIMESTAMP)`", text)
        self.assertIn("fabric now follows tsql's change", text)
        self.assertIn("WITH (nolock)", text)  # the difference is visible despite the long input
        self.assertIn("Fix the unintended ones", text)
        self.assertNotIn("Fix the unintended", I.ripple_report(items[:1]))

    def test_new_input_items_show_parent_and_child_output(self):
        items = [{"component": "starrocks", "parent": "mysql", "input": "CREATE TABLE t (a INT, CONSTRAINT PRIMARY KEY (a))",
                  "was": "CREATE TABLE t (a INT, PRIMARY KEY (a))", "now": "CREATE TABLE t (a INT)", "same": False,
                  "error": False, "new": True}]
        text = I.ripple_report(items)
        self.assertIn("tests you added", text)
        self.assertIn("mysql gives `CREATE TABLE t (a INT, PRIMARY KEY (a))`", text)
        self.assertIn("starrocks gives `CREATE TABLE t (a INT)`", text)
        self.assertTrue(I._same_modulo_quoting("SELECT `a` FROM t", 'select "a"  from t'))
        self.assertFalse(I._same_modulo_quoting("ALTER TABLE t KEY_BLOCK_SIZE=8", "ALTER TABLE t 'KEY_BLOCK_SIZE'=9"))

    def test_edit_and_window(self):
        self.assertEqual(I._edit("abcXdef", "abcYYdef"), ("X", "YY"))
        w, n = I._window("p" * 100 + "old" + "s" * 100, "p" * 100 + "new" + "s" * 100)
        self.assertIn("old", w)
        self.assertIn("new", n)


class Hooks(unittest.TestCase):
    def test_impact_arm_hooks_and_assets(self):
        from dc_eval.arms import arm_config, proviso_settings, write_proviso_files
        flags = arm_config("impact")["proviso"]
        hooks = proviso_settings("/py", "/probe", flags)["hooks"]
        self.assertEqual(set(hooks), {"UserPromptSubmit", "PreToolUse"})  # selection only
        self.assertIn("proviso-pretool", hooks["PreToolUse"][0]["hooks"][0]["command"])
        self.assertEqual(set(proviso_settings("/py", "/probe", arm_config("impact-ripple")["proviso"])["hooks"]),
                         {"UserPromptSubmit", "PreToolUse", "Stop"})
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
