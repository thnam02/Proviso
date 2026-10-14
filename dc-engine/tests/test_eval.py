"""Unit tests for dc_eval. Never call the real Claude CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_eval.arms import BASELINE_TOOLS, LAYER_TOOLS, claude_argv, write_layer_files
from dc_eval.cli import main as eval_main
from dc_eval.grade import grade_repo, is_test_path, layer_disk_stats, working_tree_stats
from dc_eval.mine import collect_node_ids_ast, mine_repo
from dc_eval.report import bootstrap_ci, paired_diffs, per_task_arm_summary, render_report
from dc_eval.gitutil import git_root
from dc_eval.run import format_plan, plan_runs, repo_is_working_copy, resolve_repo
from dc_eval.stream import metrics_from_stream, parse_stream
from dc_eval.tasks import Task, load_tasks, save_task

SAMPLE_STREAM = os.path.join(HERE, "data", "sample_stream.jsonl")


def _git(args, cwd):
    subprocess.check_call(["git", *args], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _init_git(path: str) -> None:
    _git(["init"], path)
    _git(["config", "user.email", "eval@test.local"], path)
    _git(["config", "user.name", "Eval Test"], path)
    _git(["config", "commit.gpgsign", "false"], path)


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


class StreamParseTests(unittest.TestCase):
    def test_sample_stream_metrics(self):
        self.assertTrue(os.path.isfile(SAMPLE_STREAM), "recorded sample stream missing")
        with open(SAMPLE_STREAM, encoding="utf-8") as fh:
            text = fh.read()
        m = metrics_from_stream(text)
        self.assertEqual(m["input_tokens"], 1500)
        self.assertEqual(m["output_tokens"], 400)
        self.assertEqual(m["cache_read_tokens"], 8000)
        self.assertEqual(m["cache_creation_tokens"], 200)
        self.assertEqual(m["cost_usd"], 0.12)
        self.assertEqual(m["turns"], 4)
        self.assertEqual(m["tool_calls"]["Read"], 1)
        self.assertEqual(m["tool_calls"]["Edit"], 1)
        self.assertEqual(m["read_chars"], 10)  # ABCDEFGHIJ
        self.assertEqual(m["stop_hook_blocks_stream"], 1)
        self.assertEqual(m["checkpoints_restored"], 1)
        self.assertFalse(m["is_error"])
        self.assertEqual(m["wall_time_s"], 45.0)

    def test_skips_non_json_lines(self):
        events = parse_stream("not json\n{\"type\":\"result\",\"num_turns\":1}\n")
        self.assertEqual(len(events), 1)


class BootstrapTests(unittest.TestCase):
    def test_deterministic_and_contains_mean(self):
        values = [1.0, 2.0, 3.0]
        a = bootstrap_ci(values)
        b = bootstrap_ci(values)
        self.assertEqual(a, b)
        self.assertIsNotNone(a)
        mean, lo, hi = a
        self.assertAlmostEqual(mean, 2.0)
        self.assertLessEqual(lo, mean)
        self.assertGreaterEqual(hi, mean)

    def test_empty_is_none(self):
        self.assertIsNone(bootstrap_ci([]))

    def test_n1_degenerate_ci(self):
        mean, lo, hi = bootstrap_ci([4.5])
        self.assertEqual(mean, lo)
        self.assertEqual(mean, hi)

    def test_report_notes_small_n(self):
        rows = [
            {"task": "t1", "arm": "baseline", "resolved": True, "regressions": 0,
             "input_tokens": 100, "output_tokens": 20, "cost_usd": 0.1, "wall_time_s": 10,
             "read_chars": 50, "turns": 3},
            {"task": "t1", "arm": "layer", "resolved": True, "regressions": 0,
             "input_tokens": 80, "output_tokens": 20, "cost_usd": 0.08, "wall_time_s": 12,
             "read_chars": 20, "turns": 4},
        ]
        md = render_report(rows)
        self.assertIn("too small to conclude", md)
        self.assertIn("layer − baseline", md)
        summary = per_task_arm_summary(rows)
        diffs = paired_diffs(summary, "cost_usd", ["t1"])
        self.assertEqual(len(diffs), 1)
        self.assertAlmostEqual(diffs[0], -0.02)


class GradeTests(unittest.TestCase):
    def test_is_test_path(self):
        self.assertTrue(is_test_path("tests/test_foo.py"))
        self.assertTrue(is_test_path("foo_test.py"))
        self.assertTrue(is_test_path("tests/conftest.py"))
        self.assertFalse(is_test_path("tests/fixtures/shop/shop/billing.py"))
        self.assertFalse(is_test_path("src/app.py"))

    def test_apply_patch_and_hidden_tests(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-grade-")
        try:
            _write(os.path.join(tmp, "app.py"), "value = 2\n")
            _write(os.path.join(tmp, "test_ok.py"), "def test_ok():\n    assert True\n")
            patch = (
                "diff --git a/test_hidden.py b/test_hidden.py\n"
                "new file mode 100644\n"
                "--- /dev/null\n"
                "+++ b/test_hidden.py\n"
                "@@ -0,0 +1,3 @@\n"
                "+def test_hidden():\n"
                "+    from app import value\n"
                "+    assert value == 2\n"
            )
            task = Task(
                id="g1", repo=tmp, commit="HEAD",
                prompt="x",
                hidden_tests=["test_hidden.py::test_hidden"],
                test_patch=patch,
                regression_tests=["test_ok.py::test_ok"],
            )
            result = grade_repo(task, tmp)
            self.assertTrue(result["resolved"], result)
            self.assertEqual(result["regressions"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unresolved_when_hidden_fails(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-grade-")
        try:
            _write(os.path.join(tmp, "app.py"), "value = 1\n")
            patch = (
                "diff --git a/test_hidden.py b/test_hidden.py\n"
                "new file mode 100644\n"
                "--- /dev/null\n"
                "+++ b/test_hidden.py\n"
                "@@ -0,0 +1,3 @@\n"
                "+def test_hidden():\n"
                "+    from app import value\n"
                "+    assert value == 2\n"
            )
            task = Task(
                id="g2", repo=tmp, commit="HEAD", prompt="x",
                hidden_tests=["test_hidden.py::test_hidden"],
                test_patch=patch,
            )
            result = grade_repo(task, tmp)
            self.assertFalse(result["resolved"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_layer_disk_stats(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-layer-")
        try:
            folder = os.path.join(tmp, ".dc-engine", "contracts")
            os.makedirs(folder)
            _write(
                os.path.join(folder, "c1.json"),
                json.dumps({"id": "c1", "close_score": 0.5, "status": "closed"}),
            )
            _write(os.path.join(folder, "c1.cache.json"), "{}")
            _write(
                os.path.join(tmp, ".dc-engine", "stop-history.json"),
                json.dumps({"scores": [0.0, 0.5]}),
            )
            stats = layer_disk_stats(tmp)
            self.assertEqual(stats["contracts_created"], 1)
            self.assertEqual(stats["final_contract_score"], 0.5)
            self.assertEqual(stats["stop_hook_blocks_disk"], 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_modified_tests_via_git(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-wt-")
        try:
            _init_git(tmp)
            _write(os.path.join(tmp, "app.py"), "x = 1\n")
            _write(os.path.join(tmp, "test_app.py"), "def test_x():\n    assert True\n")
            _git(["add", "."], tmp)
            _git(["commit", "-m", "init"], tmp)
            _write(os.path.join(tmp, "test_app.py"), "def test_x():\n    assert True\n    assert 1\n")
            stats = working_tree_stats(tmp)
            self.assertTrue(stats["modified_tests"])
            self.assertGreater(stats["diff_size"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _build_mine_repo() -> str:
    """Parent has add(); commit adds mul() + test_mul. Small non-test diff."""
    tmp = tempfile.mkdtemp(prefix="dc-eval-mine-")
    _init_git(tmp)
    _write(os.path.join(tmp, "app.py"), "def add(a, b):\n    return a + b\n")
    _write(
        os.path.join(tmp, "test_app.py"),
        "from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    )
    _write(os.path.join(tmp, "test_sane.py"), "def test_sane():\n    assert 1 + 1 == 2\n")
    _git(["add", "."], tmp)
    _git(["commit", "-m", "parent: add works"], tmp)
    _write(
        os.path.join(tmp, "app.py"),
        "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n",
    )
    _write(
        os.path.join(tmp, "test_app.py"),
        "from app import add\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n\n"
        "def test_mul():\n    from app import mul\n    assert mul(2, 3) == 6\n",
    )
    _git(["add", "."], tmp)
    _git(["commit", "-m", "Add mul helper\n\nNeed a product helper next to add.\n"], tmp)
    return tmp


class MineTests(unittest.TestCase):
    def test_collect_node_ids(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-ast-")
        try:
            _write(
                os.path.join(tmp, "test_x.py"),
                "def test_a():\n    pass\n\nclass TestB:\n    def test_c(self):\n        pass\n",
            )
            ids = collect_node_ids_ast(tmp, ["test_x.py"])
            self.assertEqual(ids, ["test_x.py::test_a", "test_x.py::TestB::test_c"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_mines_small_fail_to_pass_commit(self):
        repo = _build_mine_repo()
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-out-")
        try:
            found = mine_repo(repo, eval_dir, verify=True)
            self.assertEqual(len(found), 1, found)
            task = found[0]
            self.assertTrue(any("test_mul" in h for h in task.hidden_tests), task.hidden_tests)
            self.assertIn("test_sane.py::test_sane", task.regression_tests)
            self.assertIn("def test_mul", task.test_patch)
            self.assertNotIn("return a * b", task.test_patch)
            parent = subprocess.check_output(
                ["git", "rev-parse", "HEAD^"], cwd=repo, text=True,
            ).strip()
            self.assertEqual(task.commit, parent)
            self.assertIn("Add mul helper", task.prompt)
            loaded = load_tasks(eval_dir)
            self.assertEqual(len(loaded), 1)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_skips_large_non_test_diff(self):
        repo = tempfile.mkdtemp(prefix="dc-eval-big-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-out-")
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 0\n")
            _write(os.path.join(repo, "test_app.py"), "def test_x():\n    assert True\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "base"], repo)
            _write(os.path.join(repo, "app.py"), "x = 0\n" + ("y = 1\n" * 80))
            _write(
                os.path.join(repo, "test_app.py"),
                "def test_x():\n    assert True\n\ndef test_y():\n    assert True\n",
            )
            _git(["add", "."], repo)
            _git(["commit", "-m", "huge src change"], repo)
            found = mine_repo(repo, eval_dir, verify=False, max_non_test_lines=60)
            self.assertEqual(found, [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_skips_src_only_commit(self):
        repo = tempfile.mkdtemp(prefix="dc-eval-src-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-out-")
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 0\n")
            _write(os.path.join(repo, "test_app.py"), "def test_x():\n    assert True\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "base"], repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "src only"], repo)
            found = mine_repo(repo, eval_dir, verify=False)
            self.assertEqual(found, [])
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)


class ArmsAndPlanTests(unittest.TestCase):
    def test_cli_flags_match_docs(self):
        base = claude_argv("fix the bug", "baseline", model="sonnet", budget_usd=2.0)
        self.assertEqual(base[1:4], ["--bare", "-p", "fix the bug"])
        self.assertIn("--output-format", base)
        self.assertEqual(base[base.index("--output-format") + 1], "stream-json")
        self.assertIn("--verbose", base)
        self.assertEqual(base[base.index("--permission-mode") + 1], "acceptEdits")
        self.assertEqual(base[base.index("--allowedTools") + 1], BASELINE_TOOLS)
        self.assertEqual(base[base.index("--max-budget-usd") + 1], "2.0")
        self.assertNotIn("--mcp-config", base)
        self.assertNotIn("--settings", base)

        tmp = tempfile.mkdtemp(prefix="dc-eval-arm-")
        try:
            mcp, settings = write_layer_files(tmp)
            layer = claude_argv(
                "fix the bug", "layer", model="sonnet", budget_usd=2.0,
                mcp_config=mcp, settings=settings,
            )
            self.assertEqual(layer[layer.index("--mcp-config") + 1], mcp)
            self.assertEqual(layer[layer.index("--settings") + 1], settings)
            self.assertIn("mcp__dc-engine", layer[layer.index("--allowedTools") + 1])
            self.assertIn("--include-hook-events", layer)
            self.assertEqual(LAYER_TOOLS.split(",")[0], "Bash")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_interleaved_plan(self):
        t1 = Task(id="a", repo=".", commit="c", prompt="p")
        t2 = Task(id="b", repo=".", commit="c", prompt="p")
        plan = plan_runs([t1, t2], reps=2)
        order = [(t.id, arm, rep) for t, arm, rep in plan]
        self.assertEqual(
            order,
            [
                ("a", "baseline", 1), ("a", "layer", 1),
                ("a", "baseline", 2), ("a", "layer", 2),
                ("b", "baseline", 1), ("b", "layer", 1),
                ("b", "baseline", 2), ("b", "layer", 2),
            ],
        )

    def test_dry_run_plan_text(self):
        t = Task(id="shop", repo=".", commit="abc1234ffff", prompt="p")
        text = format_plan(plan_runs([t], reps=1), model="sonnet", budget_usd=2.0, timeout_s=1200, eval_dir="eval")
        self.assertIn("shop", text)
        self.assertIn("baseline", text)
        self.assertIn("layer", text)
        self.assertIn("--max-budget-usd", text)

    def test_working_copy_detection(self):
        cwd = os.getcwd()
        self.assertTrue(repo_is_working_copy(cwd, cwd))
        self.assertTrue(repo_is_working_copy(os.path.dirname(cwd), cwd) or os.path.dirname(cwd) == cwd)
        self.assertFalse(repo_is_working_copy("/this/does/not/exist-eval", cwd))

    def test_resolve_dot_via_eval_dir_when_cwd_is_not_git(self):
        eval_dir = os.path.abspath(os.path.join(os.path.dirname(HERE), "eval"))
        task = Task(id="t", repo=".", commit="x", prompt="p")
        tmp = tempfile.mkdtemp(prefix="dc-eval-cwd-")
        old = os.getcwd()
        try:
            os.chdir(tmp)
            root = resolve_repo(task, eval_dir)
        finally:
            os.chdir(old)
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(os.path.realpath(root), os.path.realpath(git_root(eval_dir)))

    def test_never_calls_claude_binary_in_this_module(self):
        # Guard: these tests must not spawn `claude`.
        from dc_eval import run as runmod
        with open(runmod.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("dry_run", src)

    def test_cli_dry_run_exits_zero_without_claude(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-cli-")
        try:
            save_task(tmp, Task(
                id="t", repo=".", commit="HEAD", prompt="fix it",
                hidden_tests=["test_x.py::test_x"],
            ))
            with self.assertRaises(SystemExit) as cm:
                eval_main(["run", "--dry-run", "--eval-dir", tmp, "--reps", "1"])
            self.assertEqual(cm.exception.code, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
