"""Proviso: trajectory capture, replay against last-seen behaviour, test regressions, context."""

from __future__ import annotations

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

from dc_engine import proviso as P

CALC = textwrap.dedent('''\
    def area(w, h):
        return w * h


    def label(x):
        if x < 0:
            raise ValueError("negative")
        return f"size={x}"
''')

TEST = textwrap.dedent('''\
    from shapes.calc import area, label


    def test_area():
        assert area(2, 3) == 6


    def test_label():
        assert label(4) == "size=4"
''')


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="proviso-")
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.root, "shapes"))
        os.makedirs(os.path.join(self.root, "tests"))
        with open(os.path.join(self.root, "shapes", "__init__.py"), "w") as fh:
            fh.write("")
        with open(os.path.join(self.root, "shapes", "calc.py"), "w") as fh:
            fh.write(CALC)
        with open(os.path.join(self.root, "tests", "__init__.py"), "w") as fh:
            fh.write("")
        with open(os.path.join(self.root, "tests", "test_calc.py"), "w") as fh:
            fh.write(TEST)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "t@t")
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "base")
        os.makedirs(os.path.join(self.root, ".dc-engine"))
        self.cfg = {"context": True, "trajectory": True, "tests": True, "python": sys.executable}
        with open(os.path.join(self.root, ".dc-engine", "proviso.json"), "w") as fh:
            json.dump(self.cfg, fh)
        P.ensure_session(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_calc(self, text):
        with open(os.path.join(self.root, "shapes", "calc.py"), "w") as fh:
            fh.write(text)

    def bash(self, command):
        return P.handle_event("proviso-capture", {"tool_name": "Bash",
                                                  "tool_input": {"command": command}}, self.root)

    def stop(self):
        return P.handle_event("proviso-verify", {}, self.root)


class Extraction(unittest.TestCase):
    def test_heredoc_dash_c_and_writes(self):
        cmd = ("cd /x; python -c \"from shapes.calc import area; print(area(2, 3))\"; "
               "python - <<'EOF'\nimport shapes.calc as c\nprint(c.label(1))\nEOF\n"
               "python - <<'EOF'\nopen('shapes/calc.py','w').write('x')\nimport shapes\nEOF\n")
        got = P.extract_probes(cmd, "/nonexistent", packages=["shapes"])
        self.assertEqual(len(got), 2)
        self.assertIn("area(2, 3)", got[1] if "label" in got[0] else got[0])

    def test_requires_repo_package(self):
        self.assertEqual(P.extract_probes('python -c "print(1)"', "/x", packages=["shapes"]), [])

    def test_venv_python_and_script_file(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, "check.py"), "w") as fh:
            fh.write("from shapes.calc import area\nprint(area(1, 1))\n")
        cmd = f"../venv/bin/python -c 'import shapes; print(1)'; python3 {d}/check.py"
        self.assertEqual(len(P.extract_probes(cmd, d, packages=["shapes"])), 2)


class Comparison(unittest.TestCase):
    def test_normalise_collapses_traceback_and_drops_ansi(self):
        text = ("ok\nTraceback (most recent call last):\n  File \"x\", line 1\n    boom()\n"
                "ValueError: bad\n  SELECT \x1b[4mFROM\x1b[0m t\n")
        self.assertEqual(P.normalise(text, "/r"), ["ok", "EXC: ValueError: bad"])

    def test_classify(self):
        self.assertEqual(P.classify_block(["EXC: ParseError: x"], ["SELECT 1"]), "none")
        self.assertEqual(P.classify_block(["SELECT 1"], ["EXC: ParseError: x"]), "hard")
        self.assertEqual(P.classify_block(["SELECT 1"], ["SELECT 2"]), "soft")
        self.assertEqual(P.classify_block(["ERR a"], ["ERR b"]), "none")


class CaptureVerify(RepoCase):
    def test_silent_when_nothing_changed_since_last_seen(self):
        self.write_calc(CALC.replace("w * h", "(w * h)"))
        self.bash('python -c "from shapes.calc import area; print(area(2, 3))"')
        self.assertEqual(self.stop(), {})

    def test_change_after_last_check_is_reported_soft_once(self):
        with open(os.path.join(self.root, ".dc-engine", "proviso.json"), "w") as fh:
            json.dump(dict(self.cfg, tests=False), fh)  # isolate the trajectory path
        self.write_calc(CALC.replace('f"size={x}"', 'f"size: {x}"'))
        self.bash('python -c "from shapes.calc import label; print(label(4))"')
        self.write_calc(CALC.replace('f"size={x}"', 'f"size - {x}"'))
        out = self.stop()
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("after you last looked", out["reason"])
        self.assertEqual(self.stop(), {})  # soft items never block twice

    def test_result_becoming_error_is_hard(self):
        self.write_calc(CALC + "\n# touched\n")
        self.bash('python -c "from shapes.calc import area; print(area(2, 3))"')
        self.write_calc(CALC.replace("return w * h", "return w * h * undefined_name"))
        out = self.stop()
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("looks unintended", out["reason"])

    def test_changed_result_seen_only_before_edits_is_not_reported(self):
        with open(os.path.join(self.root, ".dc-engine", "proviso.json"), "w") as fh:
            json.dump(dict(self.cfg, tests=False), fh)
        self.bash('python -c "from shapes.calc import label; print(label(4))"')  # before edits
        self.write_calc(CALC.replace('f"size={x}"', 'f"size: {x}"'))
        self.assertEqual(self.stop(), {})

    def test_error_fixed_is_intended(self):
        self.bash('python -c "from shapes.calc import label; print(label(-1))"')  # before edits: error
        self.write_calc(CALC.replace('raise ValueError("negative")', 'return "size=0"'))
        self.assertEqual(self.stop(), {})

    def test_existing_test_regression_is_hard_and_limit_holds(self):
        self.write_calc(CALC.replace("return w * h", "return w + h"))
        out = self.stop()
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("test_area", out["reason"])
        self.assertEqual(self.stop().get("decision"), "block")  # second block allowed
        self.assertEqual(self.stop(), {})  # MAX_BLOCKS reached
        summary = P.summarize_log(self.root)
        self.assertEqual(summary["proviso_blocks"], 2)
        self.assertGreaterEqual(summary["proviso_test_regressions"], 1)

    def test_agent_test_edits_do_not_hide_regressions(self):
        self.write_calc(CALC.replace("return w * h", "return w + h"))
        with open(os.path.join(self.root, "tests", "test_calc.py"), "w") as fh:
            fh.write(TEST.replace("== 6", "== 5"))
        out = self.stop()
        self.assertIn("test_area", out.get("reason", ""))

    def test_no_source_change_is_silent(self):
        self.bash('python -c "from shapes.calc import area; print(area(2, 3))"')
        self.assertEqual(self.stop(), {})

    def test_tests_only_mode_ignores_trajectory(self):
        cfg = dict(self.cfg, trajectory=False)
        with open(os.path.join(self.root, ".dc-engine", "proviso.json"), "w") as fh:
            json.dump(cfg, fh)
        self.bash('python -c "from shapes.calc import label; print(label(4))"')
        self.assertEqual(P.load_trajectory(self.root), [])
        self.write_calc(CALC.replace('f"size={x}"', 'f"size: {x}"'))
        out = self.stop()
        self.assertIn("test_label", out.get("reason", ""))


class Context(RepoCase):
    def test_instruction_and_matched_file(self):
        out = P.handle_event("proviso-context",
                             {"prompt": "calc gives the wrong area; calc should use area(w, h)."},
                             self.root)
        text = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Proviso is active", text)
        self.assertIn("shapes/calc.py", text)
        self.assertLessEqual(len(text), P.CONTEXT_CHARS + 600)

    def test_context_off(self):
        cfg = dict(self.cfg, context=False)
        with open(os.path.join(self.root, ".dc-engine", "proviso.json"), "w") as fh:
            json.dump(cfg, fh)
        text = P.handle_event("proviso-context", {"prompt": "calc calc"}, self.root)[
            "hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("shapes/calc.py", text)


class Brief(RepoCase):
    def test_brief_pushed_at_prompt(self):
        with open(os.path.join(self.root, ".dc-engine", "proviso.json"), "w") as fh:
            json.dump(dict(self.cfg, context=False, trajectory=False, tests=False, brief=True), fh)
        with open(os.path.join(self.root, ".dc-engine", "brief.md"), "w") as fh:
            fh.write("$ sed -n 1,2p shapes/calc.py\ndef area(w, h):\n")
        text = P.handle_event("proviso-context", {"prompt": "x"}, self.root)[
            "hookSpecificOutput"]["additionalContext"]
        self.assertIn("pre-fetched", text)
        self.assertIn("def area(w, h):", text)
        self.assertNotIn("Proviso is active", text)

    def test_no_brief_file_is_silent(self):
        with open(os.path.join(self.root, ".dc-engine", "proviso.json"), "w") as fh:
            json.dump(dict(self.cfg, context=False, trajectory=False, tests=False, brief=True), fh)
        self.assertEqual(P.handle_event("proviso-context", {"prompt": "x"}, self.root), {})


class Arms(unittest.TestCase):
    def test_oracle_arm_prompt_hook_only_and_needs_brief(self):
        from dc_eval.arms import arm_config, proviso_settings, write_proviso_files
        flags = arm_config("oracle")["proviso"]
        self.assertEqual(set(proviso_settings("/py", "/probe", flags)["hooks"]), {"UserPromptSubmit"})
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with self.assertRaises(FileNotFoundError):
            write_proviso_files(os.path.join(d, "s"), os.path.join(d, "r"), "/p", flags,
                                brief=os.path.join(d, "missing.md"))
        b = os.path.join(d, "b.md")
        open(b, "w").write("brief")
        write_proviso_files(os.path.join(d, "s"), os.path.join(d, "r"), "/p", flags, brief=b)
        self.assertEqual(open(os.path.join(d, "r", ".dc-engine", "brief.md")).read(), "brief")

    def test_proviso_arms(self):
        from dc_eval.arms import arm_config, claude_argv, proviso_settings, write_proviso_files
        for arm, flags in (("proviso", (True, True, True)), ("replay-only", (False, True, True)),
                           ("tests-only", (False, False, True))):
            cfg = arm_config(arm)
            self.assertFalse(cfg["mcp"])
            self.assertEqual(tuple(cfg["proviso"][k] for k in ("context", "trajectory", "tests")), flags)
            argv = claude_argv("p", arm, model="m", budget_usd=1, settings="/s.json", bare=False)
            self.assertIn("--settings", argv)
            self.assertNotIn("--mcp-config", argv)
        hooks = proviso_settings("/py", "/probe")["hooks"]
        self.assertEqual(set(hooks), {"UserPromptSubmit", "PostToolUse", "Stop"})
        self.assertEqual(hooks["PostToolUse"][0]["matcher"], "Bash")
        self.assertIn("proviso-verify", hooks["Stop"][0]["hooks"][0]["command"])
        self.assertGreaterEqual(hooks["Stop"][0]["hooks"][0]["timeout"], 300)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        write_proviso_files(os.path.join(d, "slot"), os.path.join(d, "repo"), "/probe/python",
                            arm_config("tests-only")["proviso"])
        cfg = json.load(open(os.path.join(d, "repo", ".dc-engine", "proviso.json")))
        self.assertEqual(cfg["python"], "/probe/python")
        self.assertFalse(cfg["trajectory"])


if __name__ == "__main__":
    unittest.main()
