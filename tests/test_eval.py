"""Unit tests for dc_eval. Never call the real Claude CLI."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_eval.arms import (
    BASELINE_TOOLS, LAYER_TOOLS, claude_argv, parse_arms, write_layer_files,
)
from unittest.mock import patch

from dc_eval.cli import main as eval_main
from dc_eval.grade import (
    GradingError, detect_import_name, files_in_test_patch, grade_repo,
    install_command_argv, is_test_path, layer_disk_stats, preflight_grade_env,
    working_tree_stats,
)
from dc_eval import MAX_REGRESSION_TESTS
from dc_eval.mine import collect_node_ids_ast, mine_repo, _regression_node_ids
from dc_eval.report import (
    bootstrap_ci, latest_non_error_rows, paired_diffs, per_task_arm_summary,
    render_report, write_report,
)
from dc_eval.gitutil import git_root
from dc_eval.run import (
    ENGINE_CHANGED,
    SafetyError,
    append_result,
    apply_cursor_offline_policy,
    capture_engine_pin,
    cursor_preflight_argv,
    execute_run,
    format_plan,
    grade_runs,
    plan_runs,
    regrade_slot,
    refuse_engine_inside_runs,
    repo_is_working_copy,
    resolve_repo,
    run_eval,
    run_setup,
    venv_env,
)
from dc_eval.stream import (
    count_model_requests, est_result_tokens, metrics_from_stream,
    normalize_tool_name, parse_stream, stream_has_result,
    tool_sizes_from_claude_events,
)
from dc_eval.tasks import (
    Task, TaskSelectError, load_tasks, match_task_id, save_task, select_task_ids,
)

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


def _eval_fake_run(real_run, calls=None):
    """Mock subprocess for execute_run: git/tar real, venv/pip/pytest/agent fake."""

    def fake_run(cmd, **kwargs):
        env = kwargs.get("env")
        if kwargs.get("shell"):
            if calls is not None:
                calls.append(("setup", cmd, env))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        argv = list(cmd)
        if argv and argv[0] in ("git", "tar"):
            return real_run(cmd, **kwargs)
        if len(argv) >= 3 and argv[1:3] == ["-m", "dc_engine"]:
            if calls is not None:
                calls.append(("dc_engine", argv, env))
            return real_run(cmd, **kwargs)
        if len(argv) >= 3 and argv[1:3] == ["-m", "venv"]:
            dest = argv[3]
            bindir = os.path.join(dest, "bin")
            os.makedirs(bindir, exist_ok=True)
            for name in ("python", "pip"):
                path = os.path.join(bindir, name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("#!/bin/sh\n")
                os.chmod(path, 0o755)
            if calls is not None:
                calls.append(("venv", argv, env))
            return subprocess.CompletedProcess(argv, 0, "", "")
        if len(argv) >= 3 and argv[1:3] == ["-m", "pip"]:
            if calls is not None:
                calls.append(("pip", argv, env))
            return subprocess.CompletedProcess(argv, 0, "ok\n", "")
        if "-c" in argv:
            if calls is not None:
                calls.append(("import", argv, env))
            return subprocess.CompletedProcess(argv, 0, "", "")
        if len(argv) >= 3 and argv[1:3] == ["-m", "pytest"]:
            if calls is not None:
                calls.append(("pytest", argv, env))
            for a in argv:
                if a.startswith("--junitxml="):
                    with open(a.split("=", 1)[1], "w", encoding="utf-8") as fh:
                        fh.write('<?xml version="1.0"?><testsuite></testsuite>\n')
            return subprocess.CompletedProcess(argv, 0, "pytest 8.0.0\n", "")
        base = os.path.basename(str(argv[0])) if argv else ""
        if base in ("claude", "agent") or (argv and argv[-1] == "--version"):
            if "--list-models" in argv:
                if calls is not None:
                    calls.append(("preflight", argv, env))
                return subprocess.CompletedProcess(argv, 0, "ok\n", "")
            if calls is not None and base in ("claude", "agent"):
                calls.append(("agent", argv, env))
            out = kwargs.get("stdout")
            if out is not None and hasattr(out, "write"):
                out.write(
                    '{"type":"result","subtype":"success","is_error":false,'
                    '"duration_ms":1}\n'
                )
                if hasattr(out, "flush"):
                    out.flush()
            return subprocess.CompletedProcess(argv, 0, "ok\n", "")
        raise AssertionError(f"unexpected subprocess: {argv!r} shell={kwargs.get('shell')}")

    return fake_run


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
        self.assertEqual(m["read_calls"], 1)
        self.assertGreaterEqual(m["dc_engine_calls"], 1)
        self.assertEqual(m["read_chars"], 10)  # ABCDEFGHIJ
        self.assertEqual(m["stop_hook_blocks_stream"], 1)
        self.assertEqual(m["checkpoints_restored"], 1)
        self.assertFalse(m["is_error"])
        self.assertEqual(m["wall_time_s"], 45.0)

    def test_skips_non_json_lines(self):
        events = parse_stream("not json\n{\"type\":\"result\",\"num_turns\":1}\n")
        self.assertEqual(len(events), 1)

    def test_stream_has_result(self):
        self.assertTrue(stream_has_result('{"type":"result","subtype":"success"}\n'))
        self.assertFalse(stream_has_result(""))
        self.assertFalse(stream_has_result('{"type":"assistant","text":"hi"}\n'))

    def test_tool_result_sizes_by_tool_and_mcp_name(self):
        with open(SAMPLE_STREAM, encoding="utf-8") as fh:
            text = fh.read()
        m = metrics_from_stream(text)
        self.assertEqual(m["tool_result_chars"]["Read"], 10)
        self.assertEqual(m["tool_result_chars"]["Edit"], 2)
        self.assertEqual(m["tool_result_chars"]["dc_restore_checkpoint"], 8)
        self.assertEqual(m["tool_result_chars_total"], 20)
        self.assertEqual(m["dc_engine_result_chars"]["dc_restore_checkpoint"], 8)
        self.assertEqual(m["dc_engine_largest"][0]["tool"], "dc_restore_checkpoint")
        self.assertEqual(normalize_tool_name("mcp__dc-engine__dc_get_slice"), "dc_get_slice")
        self.assertEqual(est_result_tokens(10), 3)
        sizes = tool_sizes_from_claude_events(parse_stream(text))
        self.assertEqual(sizes["tool_result_chars_total"], 20)

    def test_model_requests_from_assistant_events(self):
        with open(SAMPLE_STREAM, encoding="utf-8") as fh:
            text = fh.read()
        events = parse_stream(text)
        self.assertEqual(count_model_requests(events), 5)
        m = metrics_from_stream(text)
        self.assertEqual(m["model_requests"], 5)
        self.assertAlmostEqual(m["tokens_per_request"], 10100 / 5)
        self.assertEqual(
            count_model_requests([
                {"type": "assistant", "model_call_id": "a"},
                {"type": "tool_call", "model_call_id": "a"},
                {"type": "assistant", "model_call_id": "b"},
            ]),
            2,
        )


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
        self.assertNotIn("Contaminated runs", md)
        summary = per_task_arm_summary(rows)
        diffs = paired_diffs(summary, "cost_usd", ["t1"])
        self.assertEqual(len(diffs), 1)
        self.assertAlmostEqual(diffs[0], -0.02)

    def test_report_tool_result_size_tables(self):
        rows = [
            {
                "task": "t1", "arm": "baseline", "rep": 1, "status": "ok",
                "resolved": True, "regressions": 0,
                "tool_result_chars": {"read": 100, "write": 20},
                "dc_engine_results": [],
            },
            {
                "task": "t1", "arm": "layer", "rep": 1, "status": "ok",
                "resolved": True, "regressions": 0,
                "tool_result_chars": {"dc_start": 4000, "dc_get_slice": 1500, "read": 50},
                "dc_engine_results": [
                    {"tool": "dc_start", "chars": 4000, "tokens": 1000},
                    {"tool": "dc_get_slice", "chars": 1500, "tokens": 375},
                ],
            },
        ]
        md = render_report(rows)
        self.assertIn("## Tool result sizes", md)
        self.assertIn("dc_start", md)
        self.assertIn("### Layer: largest dc-engine responses", md)
        self.assertIn("| dc_start | 4000 |", md)

    def test_report_model_requests_and_catalog(self):
        rows = [
            {
                "task": "t1", "arm": "baseline", "rep": 1, "status": "ok",
                "resolved": True, "input_tokens": 100, "output_tokens": 20,
                "model_requests": 2, "tokens_per_request": 60,
            },
            {
                "task": "t1", "arm": "layer", "rep": 1, "status": "ok",
                "resolved": True, "input_tokens": 180, "output_tokens": 20,
                "model_requests": 2, "tokens_per_request": 100,
            },
        ]
        catalogs = {
            "full": {
                "mode": "full", "chars": 8000, "tokens": 2000, "tool_count": 18,
                "instructions": "long", "instructions_chars": 400,
                "instructions_tokens": 100, "instructions_words": 80,
                "tools": [{"name": "dc_get_slice", "chars": 500, "tokens": 125,
                           "text": "dc_get_slice\nslice\n{}"}],
            },
            "slim": {
                "mode": "slim", "chars": 3000, "tokens": 750, "tool_count": 5,
                "instructions": "short", "instructions_chars": 200,
                "instructions_tokens": 50, "instructions_words": 40,
                "tools": [{"name": "dc_start", "chars": 400, "tokens": 100,
                           "text": "dc_start\nstart\n{}"}],
            },
        }
        md = render_report(rows, catalogs=catalogs)
        self.assertIn("## Model requests", md)
        self.assertIn("## Tool surface (static)", md)
        self.assertIn("Before (full)", md)
        self.assertIn("After (slim)", md)
        self.assertIn("dc_start", md)
        self.assertIn("tokens/request", md)

    def test_report_groups_by_engine_commit_and_warns_on_mix(self):
        rows = [
            {
                "task": "t1", "arm": "baseline", "rep": 1, "status": "ok",
                "resolved": True, "regressions": 0,
                "dc_engine_git_commit": "aaa111",
                "dc_engine_git_dirty": "d" * 64,
                "dc_engine_path": "/engine-a",
            },
            {
                "task": "t1", "arm": "layer", "rep": 1, "status": "ok",
                "resolved": True, "regressions": 0,
                "dc_engine_git_commit": "aaa111",
                "dc_engine_git_dirty": "d" * 64,
                "dc_engine_path": "/engine-a",
            },
            {
                "task": "t2", "arm": "baseline", "rep": 1, "status": "ok",
                "resolved": False, "regressions": 0,
                "dc_engine_git_commit": "bbb222",
                "dc_engine_git_dirty": "e" * 64,
                "dc_engine_path": "/engine-b",
            },
            {
                "task": "t2", "arm": "layer", "rep": 1, "status": "ok",
                "resolved": True, "regressions": 0,
                "dc_engine_git_commit": "bbb222",
                "dc_engine_git_dirty": "e" * 64,
                "dc_engine_path": "/engine-b",
            },
        ]
        md = render_report(rows)
        self.assertIn("## dc-engine versions", md)
        self.assertIn("Runs grouped by dc-engine commit", md)
        self.assertIn("aaa111", md)
        self.assertIn("bbb222", md)
        self.assertIn("this comparison mixes dc-engine versions", md)
        self.assertIn("/engine-a", md)
        self.assertIn("/engine-b", md)

    def test_report_same_engine_commit_has_no_mix_warning(self):
        rows = [
            {
                "task": "t1", "arm": "baseline", "rep": 1, "status": "ok",
                "resolved": True,
                "dc_engine_git_commit": "aaa111",
                "dc_engine_git_dirty": "d1",
                "dc_engine_path": "/engine",
            },
            {
                "task": "t1", "arm": "layer", "rep": 1, "status": "ok",
                "resolved": True,
                "dc_engine_git_commit": "aaa111",
                "dc_engine_git_dirty": "d1",
                "dc_engine_path": "/engine",
            },
        ]
        md = render_report(rows)
        self.assertIn("## dc-engine versions", md)
        self.assertIn("aaa111", md)
        self.assertNotIn("mixes dc-engine versions", md)


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

    def test_files_in_test_patch(self):
        patch = (
            "diff --git a/tests/test_toml_document.py b/tests/test_toml_document.py\n"
            "index 1..2 100644\n"
            "--- a/tests/test_toml_document.py\n"
            "+++ b/tests/test_toml_document.py\n"
        )
        self.assertEqual(files_in_test_patch(patch), ["tests/test_toml_document.py"])

    def test_agent_edited_hidden_test_uses_fix_commit_version(self):
        src = tempfile.mkdtemp(prefix="dc-eval-fixsrc-")
        slot = tempfile.mkdtemp(prefix="dc-eval-fixrun-")
        try:
            _init_git(src)
            _write(os.path.join(src, "app.py"), "value = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "parent"], src)
            parent = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=src, text=True,
            ).strip()
            _write(os.path.join(src, "app.py"), "value = 2\n")
            official = (
                "def test_hidden():\n"
                "    from app import value\n"
                "    assert value == 2\n"
            )
            _write(os.path.join(src, "test_hidden.py"), official)
            _git(["add", "."], src)
            _git(["commit", "-m", "fix + hidden test"], src)
            fix = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=src, text=True,
            ).strip()
            patch = subprocess.check_output(
                ["git", "diff", parent, fix, "--", "test_hidden.py"],
                cwd=src, text=True,
            )
            repo = os.path.join(slot, "repo")
            subprocess.check_call(
                ["git", "clone", "--quiet", src, repo],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            subprocess.check_call(
                ["git", "checkout", "--quiet", parent], cwd=repo,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            _write(os.path.join(repo, "app.py"), "value = 2\n")
            agent_test = official + "\ndef test_agent_added():\n    assert True\n"
            _write(os.path.join(repo, "test_hidden.py"), agent_test)
            _write(os.path.join(repo, "test_extra.py"), "def test_extra():\n    assert True\n")
            task = Task(
                id=f"{fix[:10]}-hidden",
                repo=src, commit=parent, prompt="x",
                hidden_tests=["test_hidden.py::test_hidden"],
                test_patch=patch, fix_commit=fix,
            )
            result = grade_repo(task, repo, src_repo=src, run_dir=slot)
            self.assertTrue(result["resolved"], result)
            self.assertIn("test_hidden.py", result["agent_modified_hidden_test_files"])
            saved = os.path.join(slot, "agent_test_changes", "test_hidden.py")
            self.assertTrue(os.path.isfile(saved))
            with open(saved, encoding="utf-8") as fh:
                self.assertIn("test_agent_added", fh.read())
            with open(os.path.join(repo, "test_hidden.py"), encoding="utf-8") as fh:
                graded = fh.read()
            self.assertNotIn("test_agent_added", graded)
            self.assertIn("assert value == 2", graded)
            self.assertTrue(os.path.isfile(os.path.join(repo, "test_extra.py")))
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(slot, ignore_errors=True)


class HiddenScoreTests(unittest.TestCase):
    """Partial credit: subtests count as checks (sqlglot 98be baseline rep 1: 37/38)."""

    XML = (
        '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">'
        '<testsuite name="pytest" errors="0" failures="1" skipped="0" tests="38">'
        '<testcase classname="tests.dialects.test_oracle.TestOracle" name="test_partition_selection" />'
        '<testcase classname="tests.dialects.test_oracle.TestOracle" name="test_insert_partition" />'
        '<testcase classname="tests.dialects.test_oracle.TestOracle" name="test_flashback">'
        '<failure message="ParseError">E</failure></testcase></testsuite></testsuites>'
    )

    def _write(self, body: str) -> str:
        d = tempfile.mkdtemp(prefix="dc-junit-")
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, "h.xml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def test_subtests_counted_from_suite_totals(self):
        from dc_eval.grade import junit_counts
        self.assertEqual(junit_counts(self._write(self.XML)), (37, 38))

    def test_missing_or_broken_file(self):
        from dc_eval.grade import junit_counts
        self.assertEqual(junit_counts("/nonexistent/x.xml"), (0, 0))
        self.assertEqual(junit_counts(self._write("<not xml")), (0, 0))

    def test_report_score_falls_back_to_resolved(self):
        from dc_eval.report import _mean_score
        rows = [{"resolved": True}, {"resolved": False}, {"resolved": False, "hidden_score": 0.5}]
        self.assertAlmostEqual(_mean_score(rows), 0.5)


class GradeBatchTests(unittest.TestCase):
    def test_grading_error_does_not_stop_batch(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-gerr-")
        repo = tempfile.mkdtemp(prefix="dc-eval-gerrrepo-")
        calls: list[str] = []
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(eval_dir, Task(id="aa-one", repo=repo, commit=sha, prompt="p"))
            save_task(eval_dir, Task(id="bb-two", repo=repo, commit=sha, prompt="p"))

            def fake_execute(task, arm, rep, **kwargs):
                calls.append(task.id)
                if task.id == "aa-one":
                    return {
                        "task": task.id, "arm": arm, "rep": rep,
                        "status": "grading_error",
                        "grading_error": "RuntimeError: Reversed patch detected",
                        "resolved": False,
                    }
                return {
                    "task": task.id, "arm": arm, "rep": rep,
                    "status": "ok", "resolved": True, "regressions": 0,
                }

            with patch("dc_eval.run.execute_run", fake_execute), patch(
                "dc_eval.run._require_api_key",
            ), patch("dc_eval.run._require_claude", return_value="claude"):
                code = run_eval(
                    eval_dir, dry_run=False, reps=1, arms=("baseline",), timeout_s=5,
                )
            self.assertEqual(code, 0)
            self.assertEqual(calls, ["aa-one", "bb-two"])
            with open(os.path.join(eval_dir, "results.jsonl"), encoding="utf-8") as fh:
                rows = [json.loads(ln) for ln in fh if ln.strip()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["status"], "grading_error")
            self.assertTrue(rows[1].get("resolved"))
            md = render_report(rows)
            self.assertIn("Grading errors", md)
            self.assertIn("Reversed patch", md)
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_execute_run_records_grading_error_instead_of_raising(self):
        src = tempfile.mkdtemp(prefix="dc-eval-exsrc-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-exout-")
        real_run = subprocess.run
        try:
            _init_git(src)
            _write(os.path.join(src, "app.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            task = Task(id="t", repo=src, commit=sha, prompt="p")

            fake_run = _eval_fake_run(real_run)

            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ), patch("dc_eval.grade.restore_hidden_tests", side_effect=RuntimeError("Reversed patch detected")):
                row = execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
            self.assertEqual(row.get("status"), "grading_error")
            self.assertIn("Reversed patch", row.get("grading_error") or "")
            self.assertFalse(row.get("resolved"))
            slot = os.path.join(eval_dir, "runs", "t", "baseline", "1")
            self.assertTrue(os.path.isfile(os.path.join(slot, "metrics.json")))
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_grade_regrades_without_calling_agent(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-regrade-")
        src = tempfile.mkdtemp(prefix="dc-eval-regradesrc-")
        try:
            _init_git(src)
            _write(os.path.join(src, "app.py"), "value = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "parent"], src)
            parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            _write(os.path.join(src, "app.py"), "value = 2\n")
            official = (
                "def test_hidden():\n"
                "    from app import value\n"
                "    assert value == 2\n"
            )
            _write(os.path.join(src, "test_hidden.py"), official)
            _git(["add", "."], src)
            _git(["commit", "-m", "fix"], src)
            fix = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            test_patch = subprocess.check_output(
                ["git", "diff", parent, fix, "--", "test_hidden.py"], cwd=src, text=True,
            )
            save_task(eval_dir, Task(
                id="t1", repo=src, commit=parent, prompt="p",
                hidden_tests=["test_hidden.py::test_hidden"],
                test_patch=test_patch, fix_commit=fix,
            ))
            slot = os.path.join(eval_dir, "runs", "t1", "baseline", "1")
            repo = os.path.join(slot, "repo")
            subprocess.check_call(
                ["git", "clone", "--quiet", src, repo],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            subprocess.check_call(
                ["git", "checkout", "--quiet", parent], cwd=repo,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            _write(os.path.join(repo, "app.py"), "value = 2\n")
            _write(
                os.path.join(repo, "test_hidden.py"),
                official + "\ndef test_agent_added():\n    assert True\n",
            )
            os.makedirs(slot, exist_ok=True)
            with open(os.path.join(slot, "stream.jsonl"), "w", encoding="utf-8") as fh:
                fh.write("{}\n")
            with open(os.path.join(slot, "metrics.json"), "w", encoding="utf-8") as fh:
                json.dump({
                    "task": "t1", "arm": "baseline", "rep": 1,
                    "status": "grading_error",
                    "grading_error": "RuntimeError: Reversed patch detected",
                    "resolved": False, "run_dir": slot,
                }, fh)
            with patch("dc_eval.run.execute_run") as ex:
                code = grade_runs(eval_dir)
            self.assertEqual(code, 0)
            ex.assert_not_called()
            with open(os.path.join(slot, "metrics.json"), encoding="utf-8") as fh:
                metrics = json.load(fh)
            self.assertEqual(metrics.get("status"), "ok")
            self.assertTrue(metrics.get("resolved"), metrics)
            with open(os.path.join(repo, "test_hidden.py"), encoding="utf-8") as fh:
                self.assertNotIn("test_agent_added", fh.read())
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(src, ignore_errors=True)

    def test_resume_does_not_rerun_finished_agent(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-res2-")
        repo = tempfile.mkdtemp(prefix="dc-eval-res2repo-")
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(eval_dir, Task(id="t1", repo=repo, commit=sha, prompt="p"))
            slot = os.path.join(eval_dir, "runs", "t1", "baseline", "1")
            os.makedirs(os.path.join(slot, "repo"))
            with open(os.path.join(slot, "stream.jsonl"), "w", encoding="utf-8") as fh:
                fh.write("{}\n")
            with open(os.path.join(slot, "metrics.json"), "w", encoding="utf-8") as fh:
                json.dump({
                    "task": "t1", "arm": "baseline", "rep": 1,
                    "status": "grading_error",
                    "grading_error": "RuntimeError: boom",
                    "resolved": False, "run_dir": slot,
                }, fh)

            def fake_regrade(task, slot, **kwargs):
                return {
                    "task": task.id, "arm": "baseline", "rep": 1,
                    "status": "ok", "resolved": True, "run_dir": slot,
                }

            with patch("dc_eval.run.execute_run") as ex, patch(
                "dc_eval.run.regrade_slot", fake_regrade,
            ), patch("dc_eval.run._require_api_key"), patch(
                "dc_eval.run._require_claude", return_value="claude",
            ):
                code = run_eval(
                    eval_dir, resume=True, dry_run=False, reps=1,
                    arms=("baseline",), timeout_s=5,
                )
            self.assertEqual(code, 0)
            ex.assert_not_called()
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)


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
            with patch("dc_eval.mine.create_run_venv", return_value="/nonexistent-venv"), patch(
                "dc_eval.mine.venv_python", return_value=sys.executable,
            ), patch("dc_eval.mine.venv_env", return_value=os.environ.copy()), patch(
                "dc_eval.mine.install_test_env",
            ):
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

    def test_regression_collection_is_capped(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-cap-")
        try:
            for i in range(MAX_REGRESSION_TESTS + 15):
                _write(
                    os.path.join(tmp, f"test_{i}.py"),
                    f"def test_{i}():\n    assert True\n",
                )
            ids = _regression_node_ids(tmp, skip_files=set(), limit=MAX_REGRESSION_TESTS)
            self.assertEqual(len(ids), MAX_REGRESSION_TESTS)
            self.assertTrue(all(x.startswith("test_") for x in ids))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


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
            with open(mcp, encoding="utf-8") as fh:
                mcp_data = json.load(fh)
            server = mcp_data["mcpServers"]["dc-engine"]
            self.assertEqual(server["command"], os.path.abspath(sys.executable))
            self.assertEqual(server["args"][:2], ["-m", "dc_engine.server"])
            with open(settings, encoding="utf-8") as fh:
                settings_data = json.load(fh)
            pre = settings_data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            self.assertIn("-m dc_engine hook pre-edit", pre)
            self.assertIn(os.path.abspath(sys.executable), pre.replace("\\", ""))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_layer_files_set_dc_probe_python(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-probe-")
        try:
            probe = os.path.join(tmp, "venv", "bin", "python")
            os.makedirs(os.path.dirname(probe), exist_ok=True)
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("#!/bin/sh\n")
            mcp, settings = write_layer_files(tmp, probe_python=probe)
            with open(mcp, encoding="utf-8") as fh:
                mcp_data = json.load(fh)
            server = mcp_data["mcpServers"]["dc-engine"]
            self.assertEqual(
                server["env"]["DC_PROBE_PYTHON"], os.path.abspath(probe),
            )
            with open(settings, encoding="utf-8") as fh:
                settings_data = json.load(fh)
            pre = settings_data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            post = settings_data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
            stop = settings_data["hooks"]["Stop"][0]["hooks"][0]["command"]
            for cmd in (pre, post, stop):
                self.assertIn("DC_PROBE_PYTHON=", cmd)
                self.assertIn(os.path.abspath(probe), cmd)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_interleaved_plan(self):
        t1 = Task(id="a", repo=".", commit="c", prompt="p")
        t2 = Task(id="b", repo=".", commit="c", prompt="p")
        plan = plan_runs([t1, t2], reps=2)
        order = [(t.id, arm, rep) for t, arm, rep in plan]
        self.assertEqual(
            [(tid, rep) for tid, _arm, rep in order],
            [
                ("a", 1), ("a", 1),
                ("a", 2), ("a", 2),
                ("b", 1), ("b", 1),
                ("b", 2), ("b", 2),
            ],
        )
        for i in range(0, len(order), 2):
            self.assertEqual({order[i][1], order[i + 1][1]}, {"baseline", "layer"})
        again = [(t.id, arm, rep) for t, arm, rep in plan_runs([t1, t2], reps=2, seed=0)]
        self.assertEqual(order, again)

    def test_dry_run_plan_text(self):
        t = Task(id="shop", repo=".", commit="abc1234ffff", prompt="p")
        text = format_plan(plan_runs([t], reps=1), model="sonnet", budget_usd=2.0, timeout_s=1200, eval_dir="eval")
        self.assertTrue(text.startswith("tasks: shop\n"), text[:80])
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
        repo = tempfile.mkdtemp(prefix="dc-eval-cli-repo-")
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(tmp, Task(
                id="t", repo=repo, commit=sha, prompt="fix it",
                hidden_tests=["test_x.py::test_x"],
            ))
            with self.assertRaises(SystemExit) as cm:
                eval_main(["run", "--dry-run", "--eval-dir", tmp, "--reps", "1"])
            self.assertEqual(cm.exception.code, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_cli_refuses_existing_run_dir_without_fresh_or_resume(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-cli-exist-")
        repo = tempfile.mkdtemp(prefix="dc-eval-cli-existrepo-")
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(tmp, Task(id="t", repo=repo, commit=sha, prompt="p"))
            os.makedirs(os.path.join(tmp, "runs", "t", "baseline", "1", "repo"))
            buf = io.StringIO()
            with redirect_stderr(buf), self.assertRaises(SystemExit) as cm:
                eval_main(["run", "--eval-dir", tmp, "--reps", "1", "--arm", "baseline"])
            self.assertEqual(cm.exception.code, 2)
            err = buf.getvalue()
            self.assertIn("--fresh", err)
            self.assertIn("--resume", err)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_cli_fresh_dry_run_does_not_archive(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-cli-fresh-")
        repo = tempfile.mkdtemp(prefix="dc-eval-cli-freshrepo-")
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(tmp, Task(id="t", repo=repo, commit=sha, prompt="p"))
            slot = os.path.join(tmp, "runs", "t", "baseline", "1")
            os.makedirs(os.path.join(slot, "repo"))
            marker = os.path.join(slot, "metrics.json")
            _write(marker, "{}\n")
            buf = io.StringIO()
            with redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
                eval_main([
                    "run", "--dry-run", "--fresh", "--eval-dir", tmp,
                    "--reps", "1", "--arm", "baseline",
                ])
            self.assertEqual(cm.exception.code, 0)
            self.assertTrue(os.path.isfile(marker))
            self.assertFalse(os.path.isdir(os.path.join(tmp, "runs_archive")))
            self.assertIn("would archive", buf.getvalue())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)


class TaskSelectTests(unittest.TestCase):
    IDS = [
        "aa-one",
        "bb-two",
        "aa-longer",
    ]

    def test_prefix_matches_one(self):
        self.assertEqual(match_task_id(self.IDS, "bb"), "bb-two")
        self.assertEqual(select_task_ids(self.IDS, include=["bb"]), ["bb-two"])

    def test_exact_id_wins_over_longer_prefix(self):
        self.assertEqual(match_task_id(self.IDS, "aa-one"), "aa-one")

    def test_ambiguous_prefix_errors(self):
        with self.assertRaises(TaskSelectError) as cm:
            match_task_id(self.IDS, "aa")
        msg = str(cm.exception)
        self.assertIn("more than one", msg)
        self.assertIn("aa-one", msg)
        self.assertIn("aa-longer", msg)

    def test_zero_match_errors(self):
        with self.assertRaises(TaskSelectError) as cm:
            match_task_id(self.IDS, "zz")
        self.assertIn("no task matches prefix 'zz'", str(cm.exception))

    def test_exclude_prefix(self):
        self.assertEqual(
            select_task_ids(self.IDS, exclude=["bb"]),
            ["aa-one", "aa-longer"],
        )

    def test_cli_dry_run_shows_selected_ids_and_rejects_bad_prefix(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-sel-")
        repo = tempfile.mkdtemp(prefix="dc-eval-selrepo-")
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(eval_dir, Task(id="aa-one", repo=repo, commit=sha, prompt="p"))
            save_task(eval_dir, Task(id="bb-two", repo=repo, commit=sha, prompt="p"))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    eval_main([
                        "run", "--dry-run", "--eval-dir", eval_dir,
                        "--reps", "1", "--tasks", "aa",
                    ])
            self.assertEqual(cm.exception.code, 0)
            text = out.getvalue()
            self.assertTrue(text.splitlines()[0].startswith("tasks: aa-one"), text[:200])
            self.assertIn("aa-one", text)
            self.assertNotIn("bb-two", text)

            err2 = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err2):
                with self.assertRaises(SystemExit) as cm:
                    eval_main([
                        "run", "--dry-run", "--eval-dir", eval_dir,
                        "--reps", "1", "--tasks", "nope",
                    ])
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("no task matches prefix 'nope'", err2.getvalue())

            err3 = io.StringIO()
            save_task(eval_dir, Task(id="aa-longer", repo=repo, commit=sha, prompt="p"))
            with redirect_stdout(io.StringIO()), redirect_stderr(err3):
                with self.assertRaises(SystemExit) as cm:
                    eval_main([
                        "run", "--dry-run", "--eval-dir", eval_dir,
                        "--reps", "1", "--tasks", "aa",
                    ])
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("more than one", err3.getvalue())
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_resume_only_considers_selected_task(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-resume-")
        repo = tempfile.mkdtemp(prefix="dc-eval-resrepo-")
        calls: list[tuple[str, str, int]] = []
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(eval_dir, Task(id="aa-one", repo=repo, commit=sha, prompt="p"))
            save_task(eval_dir, Task(id="bb-two", repo=repo, commit=sha, prompt="p"))
            done = os.path.join(eval_dir, "runs", "aa-one", "baseline", "1")
            os.makedirs(done)
            with open(os.path.join(done, "metrics.json"), "w", encoding="utf-8") as fh:
                fh.write("{}\n")

            def fake_execute(task, arm, rep, **kwargs):
                calls.append((task.id, arm, rep))
                return {"task": task.id, "arm": arm, "rep": rep, "resolved": True}

            with patch("dc_eval.run.execute_run", fake_execute), patch(
                "dc_eval.run._require_api_key",
            ), patch("dc_eval.run._require_claude", return_value="claude"):
                code = run_eval(
                    eval_dir, task_ids=["aa"], resume=True, dry_run=False,
                    reps=1, arms=("baseline",), timeout_s=5,
                )
            self.assertEqual(code, 0)
            self.assertEqual(calls, [])

            calls.clear()
            with patch("dc_eval.run.execute_run", fake_execute), patch(
                "dc_eval.run._require_api_key",
            ), patch("dc_eval.run._require_claude", return_value="claude"):
                code = run_eval(
                    eval_dir, task_ids=["bb"], resume=True, dry_run=False,
                    reps=1, arms=("baseline",), timeout_s=5,
                )
            self.assertEqual(code, 0)
            self.assertEqual(calls, [("bb-two", "baseline", 1)])
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_report_limits_to_selected_tasks(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-rep-")
        try:
            save_task(eval_dir, Task(id="aa-one", repo=".", commit="c", prompt="p"))
            save_task(eval_dir, Task(id="bb-two", repo=".", commit="c", prompt="p"))
            rows = [
                {"task": "aa-one", "arm": "baseline", "rep": 1, "resolved": True,
                 "regressions": 0, "input_tokens": 10, "output_tokens": 2,
                 "cost_usd": 0.1, "wall_time_s": 1, "read_chars": 1, "turns": 1},
                {"task": "aa-one", "arm": "layer", "rep": 1, "resolved": True,
                 "regressions": 0, "input_tokens": 8, "output_tokens": 2,
                 "cost_usd": 0.08, "wall_time_s": 1, "read_chars": 1, "turns": 1},
                {"task": "bb-two", "arm": "baseline", "rep": 1, "resolved": False,
                 "regressions": 0, "input_tokens": 10, "output_tokens": 2,
                 "cost_usd": 0.1, "wall_time_s": 1, "read_chars": 1, "turns": 1},
                {"task": "bb-two", "arm": "layer", "rep": 1, "resolved": False,
                 "regressions": 0, "input_tokens": 8, "output_tokens": 2,
                 "cost_usd": 0.08, "wall_time_s": 1, "read_chars": 1, "turns": 1},
            ]
            path = write_report(eval_dir, rows=rows, task_ids=["aa"])
            with open(path, encoding="utf-8") as fh:
                md = fh.read()
            self.assertIn("aa-one", md)
            self.assertNotIn("bb-two", md)
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)


class SafetyAndVenvTests(unittest.TestCase):
    def test_refuses_dc_engine_as_task_repo(self):
        engine_root = os.path.dirname(HERE)
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-self-")
        try:
            save_task(eval_dir, Task(
                id="bad", repo=engine_root, commit="HEAD", prompt="x",
            ))
            with self.assertRaises(SafetyError) as cm:
                run_eval(eval_dir, dry_run=True, reps=1)
            msg = str(cm.exception).lower()
            self.assertIn("dc-engine", msg)
            self.assertIn("source tree", msg)
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_refuses_repo_that_contains_dc_engine(self):
        engine_root = os.path.dirname(HERE)
        parent = os.path.dirname(engine_root)
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-parent-")
        try:
            save_task(eval_dir, Task(
                id="bad", repo=parent, commit="HEAD", prompt="x",
            ))
            with self.assertRaises(SafetyError) as cm:
                run_eval(eval_dir, dry_run=True, reps=1)
            self.assertIn("dc-engine", str(cm.exception).lower())
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_refuses_run_copy_with_eval_dir(self):
        src = tempfile.mkdtemp(prefix="dc-eval-haseval-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-out-")
        try:
            _init_git(src)
            os.makedirs(os.path.join(src, "eval"))
            _write(os.path.join(src, "eval", "note.txt"), "nope\n")
            _write(os.path.join(src, "app.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            task = Task(id="t", repo=src, commit=sha, prompt="p")
            with self.assertRaises(SafetyError) as cm:
                execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
            self.assertIn("eval/", str(cm.exception))
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_refuses_run_copy_with_dc_eval_dir(self):
        src = tempfile.mkdtemp(prefix="dc-eval-hasdce-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-out-")
        try:
            _init_git(src)
            os.makedirs(os.path.join(src, "dc_eval"))
            _write(os.path.join(src, "dc_eval", "x.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            task = Task(id="t", repo=src, commit=sha, prompt="p")
            with self.assertRaises(SafetyError) as cm:
                execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
            self.assertIn("dc_eval/", str(cm.exception))
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_refuses_engine_path_inside_runs(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-eng-")
        try:
            fake = os.path.join(eval_dir, "runs", "t", "dc_engine")
            os.makedirs(fake)
            with self.assertRaises(SafetyError) as cm:
                refuse_engine_inside_runs(eval_dir, fake)
            self.assertIn("eval/runs", str(cm.exception))
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_run_setup_uses_provided_env_path(self):
        repo = tempfile.mkdtemp(prefix="dc-eval-setup-")
        seen = {}

        def fake_run(*args, **kwargs):
            seen["env"] = kwargs.get("env")
            seen["cmd"] = args[0] if args else kwargs.get("args")
            return subprocess.CompletedProcess(seen["cmd"], 0, "", "")

        env = venv_env("/tmp/fake-venv", {"PATH": "/usr/bin", "HOME": os.environ.get("HOME", "")})
        try:
            with patch("dc_eval.run.subprocess.run", fake_run):
                run_setup(repo, "python -m pip install -e . -q", env=env)
            self.assertTrue(seen["env"]["PATH"].startswith(os.path.join("/tmp/fake-venv", "bin")))
            self.assertIn("python -m pip", seen["cmd"])
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_execute_run_venv_path_for_setup_grade_agent(self):
        src = tempfile.mkdtemp(prefix="dc-eval-venvsrc-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-venvout-")
        calls: list[tuple[str, object, dict | None]] = []

        real_run = subprocess.run
        fake_run = _eval_fake_run(real_run, calls)

        try:
            _init_git(src)
            _write(os.path.join(src, "app.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            task = Task(
                id="t", repo=src, commit=sha, prompt="p",
                setup="python -m pip install -e . pytest -q",
                hidden_tests=["test_x.py::test_x"],
            )
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ):
                row = execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
            self.assertEqual(row.get("dc_engine_version"), "0.1.0")
            self.assertIn("dc_engine", row.get("dc_engine_path") or "")
            self.assertTrue(row.get("dc_engine_git_commit"))
            self.assertIsNotNone(row.get("dc_engine_git_dirty"))
            slot = os.path.join(eval_dir, "runs", "t", "baseline", "1")
            with open(os.path.join(slot, "metrics.json"), encoding="utf-8") as fh:
                saved = json.load(fh)
            self.assertEqual(saved.get("dc_engine_git_commit"), row.get("dc_engine_git_commit"))
            self.assertEqual(saved.get("dc_engine_git_dirty"), row.get("dc_engine_git_dirty"))
            self.assertEqual(saved.get("dc_engine_path"), row.get("dc_engine_path"))
            kinds = [k for k, _, _ in calls]
            self.assertIn("venv", kinds)
            self.assertIn("pip", kinds)
            self.assertIn("setup", kinds)
            self.assertIn("agent", kinds)
            self.assertIn("pytest", kinds)
            self.assertLess(kinds.index("pip"), kinds.index("agent"))
            pip_cmds = [c for k, c, _ in calls if k == "pip"]
            self.assertTrue(any(c[-1] == "pytest" for c in pip_cmds), pip_cmds)
            venv_cmd = next(c for k, c, _ in calls if k == "venv")
            self.assertEqual(venv_cmd[:3], [sys.executable, "-m", "venv"])
            self.assertTrue(venv_cmd[3].endswith(os.path.join("runs", "t", "baseline", "1", "venv")))
            venv_bin = os.path.join(venv_cmd[3], "bin")
            setup_env = next(e for k, _, e in calls if k == "setup")
            self.assertTrue(setup_env["PATH"].startswith(venv_bin + os.pathsep))
            agent_env = next(e for k, _, e in calls if k == "agent")
            self.assertTrue(agent_env["PATH"].startswith(venv_bin + os.pathsep))
            pytest_cmd = next(c for k, c, _ in calls if k == "pytest")
            self.assertEqual(pytest_cmd[0], os.path.join(venv_bin, "python"))
            self.assertNotEqual(pytest_cmd[0], sys.executable)
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_execute_run_layer_sets_dc_probe_python(self):
        src = tempfile.mkdtemp(prefix="dc-eval-layerpy-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-layerout-")
        real_run = subprocess.run
        fake_run = _eval_fake_run(real_run)

        try:
            _init_git(src)
            _write(os.path.join(src, "app.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            task = Task(id="t", repo=src, commit=sha, prompt="p")
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ):
                execute_run(
                    task, "layer", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
            slot = os.path.join(eval_dir, "runs", "t", "layer", "1")
            probe = os.path.abspath(os.path.join(slot, "venv", "bin", "python"))
            with open(os.path.join(slot, "mcp.json"), encoding="utf-8") as fh:
                mcp = json.load(fh)
            self.assertEqual(mcp["mcpServers"]["dc-engine"]["env"]["DC_PROBE_PYTHON"], probe)
            with open(os.path.join(slot, "settings.json"), encoding="utf-8") as fh:
                settings = json.load(fh)
            pre = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            self.assertIn("DC_PROBE_PYTHON=", pre)
            self.assertIn(probe, pre)
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_make_shop_repo_two_commits_outside_engine(self):
        script = os.path.join(os.path.dirname(HERE), "eval", "fixtures", "make_shop_repo.py")
        dest = tempfile.mkdtemp(prefix="dc-eval-shopfix-")
        shutil.rmtree(dest)
        try:
            subprocess.check_call(
                [sys.executable, script, "--dest", dest, "--no-write-task"],
                stdout=subprocess.DEVNULL,
            )
            n = subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"], cwd=dest, text=True,
            ).strip()
            self.assertEqual(n, "2")
            log = subprocess.check_output(["git", "log", "--oneline"], cwd=dest, text=True)
            self.assertIn("zero", log.lower())
            parent = subprocess.check_output(
                ["git", "rev-parse", "HEAD^"], cwd=dest, text=True,
            ).strip()
            patch = subprocess.check_output(
                ["git", "diff", parent, "HEAD", "--", "tests/test_zero.py"],
                cwd=dest, text=True,
            )
            self.assertIn("test_zero_amount_rejected", patch)
            self.assertNotIn("validate_amount", patch)
            self.assertFalse(os.path.isdir(os.path.join(dest, "eval")))
            self.assertFalse(os.path.isdir(os.path.join(dest, "dc_eval")))
        finally:
            shutil.rmtree(dest, ignore_errors=True)


class VenvInstallTests(unittest.TestCase):
    def test_install_commands_pytest_editable_extras_and_requirements(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-inst-")
        try:
            _write(
                os.path.join(tmp, "pyproject.toml"),
                "[project]\nname = \"demo\"\n\n"
                "[project.optional-dependencies]\ntest = [\"pytest\"]\n"
                "dev = [\"ruff\"]\n",
            )
            _write(os.path.join(tmp, "requirements-dev.txt"), "coverage\n")
            cmds = install_command_argv("/venv/bin/python", tmp)
            joined = [" ".join(c) for c in cmds]
            self.assertEqual(cmds[0], ["/venv/bin/python", "-m", "pip", "install", "-q", "pytest"])
            self.assertTrue(any("-e" in c and ".[test,dev]" in c or ".[dev,test]" in c for c in joined) or any(
                c[-1].startswith(".[") for c in cmds
            ), joined)
            self.assertTrue(any("-r" in c and "requirements-dev.txt" in c for c in joined), joined)
            self.assertEqual(detect_import_name(tmp), "demo")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_install_commands_dependency_groups(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-grp-")
        try:
            _write(
                os.path.join(tmp, "pyproject.toml"),
                "[project]\nname = \"tomlkit\"\n\n[dependency-groups]\ntest = [\"pytest\"]\n",
            )
            cmds = install_command_argv("py", tmp)
            joined = [" ".join(c) for c in cmds]
            self.assertTrue(any(c[-2:] == ["-e", "."] for c in cmds), joined)
            self.assertTrue(any("--group" in c and "test" in c for c in joined), joined)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_preflight_pytest_missing_is_grading_error(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-pre-")
        try:
            _write(os.path.join(tmp, "app.py"), "x = 1\n")
            task = Task(id="t", repo=tmp, commit="HEAD", prompt="p", hidden_tests=["t.py::t"])

            def fake_run(cmd, **kwargs):
                argv = list(cmd)
                if argv[-2:] == ["pytest", "--version"] or (
                    len(argv) >= 3 and argv[1:3] == ["-m", "pytest"] and "--version" in argv
                ):
                    return subprocess.CompletedProcess(argv, 1, "", "No module named pytest")
                raise AssertionError(argv)

            with patch("dc_eval.grade.subprocess.run", fake_run):
                with self.assertRaises(GradingError) as cm:
                    grade_repo(task, tmp, run_dir=os.path.join(tmp, "run"))
            self.assertIn("pytest", str(cm.exception).lower())
            log = os.path.join(tmp, "run", "grading.log")
            self.assertTrue(os.path.isfile(log))
            with open(log, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("No module named pytest", body)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_preflight_unimportable_package_is_grading_error(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-imp-")
        try:
            _write(os.path.join(tmp, "pyproject.toml"), "[project]\nname = \"demo_pkg\"\n")
            os.makedirs(os.path.join(tmp, "demo_pkg"))
            _write(os.path.join(tmp, "demo_pkg", "__init__.py"), "")
            task = Task(id="t", repo=tmp, commit="HEAD", prompt="p")

            def fake_run(cmd, **kwargs):
                argv = list(cmd)
                if "--version" in argv:
                    return subprocess.CompletedProcess(argv, 0, "pytest 8.0.0\n", "")
                if "-c" in argv:
                    return subprocess.CompletedProcess(argv, 1, "", "ModuleNotFoundError: demo_pkg")
                raise AssertionError(argv)

            with patch("dc_eval.grade.subprocess.run", fake_run):
                with self.assertRaises(GradingError) as cm:
                    preflight_grade_env(tmp, "/venv/bin/python")
            self.assertIn("demo_pkg", str(cm.exception))
            self.assertIn("not importable", str(cm.exception).lower())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_grading_log_captures_hidden_and_regression_pytest(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-glog-")
        slot = os.path.join(tmp, "run")
        os.makedirs(slot)
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
                id="glog", repo=tmp, commit="HEAD", prompt="x",
                hidden_tests=["test_hidden.py::test_hidden"],
                test_patch=patch,
                regression_tests=["test_ok.py::test_ok"],
            )
            result = grade_repo(task, tmp, run_dir=slot)
            self.assertTrue(result["resolved"], result)
            log = os.path.join(slot, "grading.log")
            self.assertTrue(os.path.isfile(log))
            with open(log, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("hidden tests", body)
            self.assertIn("regression tests", body)
            self.assertIn("returncode=", body)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_execute_run_installs_editable_before_agent(self):
        src = tempfile.mkdtemp(prefix="dc-eval-editsrc-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-editout-")
        calls: list[tuple[str, object, dict | None]] = []
        fake_run = _eval_fake_run(subprocess.run, calls)
        try:
            _init_git(src)
            _write(os.path.join(src, "pyproject.toml"), "[project]\nname = \"demo\"\nversion = \"0\"\n")
            os.makedirs(os.path.join(src, "demo"))
            _write(os.path.join(src, "demo", "__init__.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            task = Task(id="t", repo=src, commit=sha, prompt="p")
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ):
                execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
            pip_cmds = [c for k, c, _ in calls if k == "pip"]
            self.assertTrue(any(c[-1] == "pytest" for c in pip_cmds), pip_cmds)
            self.assertTrue(any("-e" in c and c[-1] == "." for c in pip_cmds), pip_cmds)
            kinds = [k for k, _, _ in calls]
            self.assertLess(kinds.index("pip"), kinds.index("agent"))
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_mine_verify_uses_venv_install_recipe(self):
        repo = _build_mine_repo()
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-minevenv-")
        installs: list[tuple[str, str]] = []

        def fake_install(python, tree, **kwargs):
            installs.append((python, tree))

        try:
            with patch("dc_eval.mine.create_run_venv", return_value="/tmp/fake-venv"), patch(
                "dc_eval.mine.venv_python", return_value="/tmp/fake-venv/bin/python",
            ), patch("dc_eval.mine.venv_env", return_value={"PATH": "/tmp/fake-venv/bin"}), patch(
                "dc_eval.mine.install_test_env", fake_install,
            ), patch(
                "dc_eval.mine._pytest_pass_fail",
                side_effect=lambda root, nodes, python=None: (
                    self.assertEqual(python, "/tmp/fake-venv/bin/python"),
                    (set(nodes), set()),
                )[1],
            ):
                # verify=True but pytest results say nothing failed on base → no candidate
                found = mine_repo(repo, eval_dir, verify=True)
            self.assertEqual(found, [])
            self.assertTrue(installs)
            self.assertTrue(all(p == "/tmp/fake-venv/bin/python" for p, _ in installs))
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_offline_policy_merges_cli_json(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-off-")
        try:
            os.makedirs(os.path.join(tmp, ".cursor"))
            _write(
                os.path.join(tmp, ".cursor", "cli.json"),
                json.dumps({"permissions": {"allow": ["Shell(*)"], "deny": ["Other"]}}),
            )
            apply_cursor_offline_policy(tmp)
            with open(os.path.join(tmp, ".cursor", "cli.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertIn("WebFetch(*)", data["permissions"]["deny"])
            self.assertIn("Other", data["permissions"]["deny"])
            self.assertEqual(data["permissions"]["allow"], ["Shell(*)"])
            rule = os.path.join(tmp, ".cursor", "rules", "offline.mdc")
            self.assertTrue(os.path.isfile(rule))
            with open(rule, encoding="utf-8") as fh:
                text = fh.read().lower()
            self.assertIn("work offline", text)
            self.assertIn("do not search the web", text)
            self.assertIn("fetch", text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_execute_run_writes_offline_policy_both_arms(self):
        src = tempfile.mkdtemp(prefix="dc-eval-offsrc-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-offout-")
        fake_run = _eval_fake_run(subprocess.run)
        try:
            _init_git(src)
            _write(os.path.join(src, "app.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            task = Task(id="t", repo=src, commit=sha, prompt="p")
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ), patch("dc_eval.run._install_cursor_layer") as inst:
                execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="composer-1", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                    runner="cursor", agent_bin="agent",
                )
                execute_run(
                    task, "layer", 1,
                    eval_dir=eval_dir, model="composer-1", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                    runner="cursor", agent_bin="agent",
                )
            inst.assert_called_once()
            for arm in ("baseline", "layer"):
                repo = os.path.join(eval_dir, "runs", "t", arm, "1", "repo")
                with open(os.path.join(repo, ".cursor", "cli.json"), encoding="utf-8") as fh:
                    data = json.load(fh)
                self.assertEqual(data["permissions"]["deny"], ["WebFetch(*)"])
                self.assertEqual(data["permissions"]["allow"], [])
                rule = os.path.join(repo, ".cursor", "rules", "offline.mdc")
                self.assertTrue(os.path.isfile(rule), arm)
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_contaminated_status_and_report_exclusion(self):
        src = tempfile.mkdtemp(prefix="dc-eval-websrc-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-webout-")
        live = os.path.join(HERE, "data", "cursor_stream_read_live.jsonl")
        try:
            _init_git(src)
            _write(os.path.join(src, "app.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            task = Task(id="t", repo=src, commit=sha, prompt="p")
            slot = os.path.join(eval_dir, "runs", "t", "baseline", "1")
            repo = os.path.join(slot, "repo")
            os.makedirs(repo)
            shutil.copytree(src, repo, dirs_exist_ok=True)
            with open(live, encoding="utf-8") as fh:
                stream_text = fh.read()
            _write(os.path.join(slot, "stream.jsonl"), stream_text)
            with open(os.path.join(slot, "metrics.json"), "w", encoding="utf-8") as fh:
                json.dump({
                    "task": "t", "arm": "baseline", "rep": 1, "runner": "cursor",
                    "status": "ok", "run_dir": slot,
                }, fh)
            with patch("dc_eval.grade.subprocess.run", _eval_fake_run(subprocess.run)), patch(
                "dc_eval.run.install_test_env",
            ):
                row = regrade_slot(task, slot, src_repo=src)
            self.assertEqual(row.get("status"), "contaminated")
            self.assertTrue(row.get("contaminated"))
            self.assertEqual(row.get("web_search_count"), 1)
            self.assertEqual(row.get("web_fetch_count"), 1)
            self.assertGreater(row.get("read_chars") or 0, 0)
            md = render_report([row, {
                "task": "t", "arm": "layer", "rep": 1, "runner": "cursor",
                "status": "ok", "resolved": True, "regressions": 0,
                "input_tokens": 1, "output_tokens": 1,
                "cache_read_tokens": 0, "cache_write_tokens": 0,
                "tokens": 2, "cost_usd": 0.01, "wall_time_s": 1,
            }])
            self.assertIn("Contaminated runs", md)
            self.assertIn("excluded from the main comparison", md)
            summary = per_task_arm_summary([row, {
                "task": "t", "arm": "layer", "rep": 1, "status": "ok", "resolved": True,
            }])
            self.assertNotIn(("t", "baseline"), summary)
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)


class RunLifecycleTests(unittest.TestCase):
    def _tiny_task(self, src, tid="t"):
        _init_git(src)
        _write(os.path.join(src, "app.py"), "x = 1\n")
        _git(["add", "."], src)
        _git(["commit", "-m", "init"], src)
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
        return Task(id=tid, repo=src, commit=sha, prompt="p")

    def test_setup_failure_is_setup_error_not_unresolved(self):
        src = tempfile.mkdtemp(prefix="dc-eval-setuperr-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-setuperrout-")
        fake_run = _eval_fake_run(subprocess.run)
        try:
            task = self._tiny_task(src)
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ), patch("dc_eval.run.install_test_env", side_effect=RuntimeError("pip boom")):
                row = execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
            self.assertEqual(row.get("status"), "setup_error")
            self.assertFalse(row.get("resolved"))
            self.assertIn("pip boom", row.get("setup_error") or "")
            slot = os.path.join(eval_dir, "runs", "t", "baseline", "1")
            log = os.path.join(slot, "setup.log")
            self.assertTrue(os.path.isfile(log))
            with open(log, encoding="utf-8") as fh:
                self.assertIn("pip boom", fh.read())
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_stops_after_two_consecutive_setup_errors(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-consec-")
        repo = tempfile.mkdtemp(prefix="dc-eval-consecsrc-")
        calls: list[str] = []
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(eval_dir, Task(id="aa-one", repo=repo, commit=sha, prompt="p"))
            save_task(eval_dir, Task(id="bb-two", repo=repo, commit=sha, prompt="p"))
            save_task(eval_dir, Task(id="cc-three", repo=repo, commit=sha, prompt="p"))

            def fake_execute(task, arm, rep, **kwargs):
                calls.append(task.id)
                return {
                    "task": task.id, "arm": arm, "rep": rep,
                    "status": "setup_error",
                    "setup_error": "RuntimeError: pip boom",
                    "resolved": False,
                }

            with patch("dc_eval.run.execute_run", fake_execute), patch(
                "dc_eval.run._require_api_key",
            ), patch("dc_eval.run._require_claude", return_value="claude"):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = run_eval(
                        eval_dir, dry_run=False, reps=1, arms=("baseline",), timeout_s=5,
                    )
            self.assertEqual(code, 4)
            self.assertEqual(calls, ["aa-one", "bb-two"])
            self.assertIn("pip boom", buf.getvalue())
            self.assertIn("consecutive setup_error", buf.getvalue())
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_refuses_existing_run_dir_without_fresh_or_resume(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-refuse-")
        repo = tempfile.mkdtemp(prefix="dc-eval-refusesrc-")
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(eval_dir, Task(id="t1", repo=repo, commit=sha, prompt="p"))
            slot = os.path.join(eval_dir, "runs", "t1", "baseline", "1")
            os.makedirs(os.path.join(slot, "repo"))
            with patch("dc_eval.run._require_api_key"), patch(
                "dc_eval.run._require_claude", return_value="claude",
            ), patch("dc_eval.run.execute_run") as ex:
                with self.assertRaises(SafetyError) as cm:
                    run_eval(
                        eval_dir, dry_run=False, reps=1, arms=("baseline",), timeout_s=5,
                    )
            ex.assert_not_called()
            msg = str(cm.exception)
            self.assertIn("--fresh", msg)
            self.assertIn("--resume", msg)
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_fresh_archives_existing_run_dirs(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-fresh-")
        repo = tempfile.mkdtemp(prefix="dc-eval-freshsrc-")
        try:
            _init_git(repo)
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _git(["add", "."], repo)
            _git(["commit", "-m", "init"], repo)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            save_task(eval_dir, Task(id="t1", repo=repo, commit=sha, prompt="p"))
            slot = os.path.join(eval_dir, "runs", "t1", "baseline", "1")
            os.makedirs(os.path.join(slot, "repo"))
            _write(os.path.join(slot, "metrics.json"), "{}\n")

            def fake_execute(task, arm, rep, **kwargs):
                return {
                    "task": task.id, "arm": arm, "rep": rep,
                    "status": "ok", "resolved": True,
                }

            with patch("dc_eval.run.execute_run", fake_execute), patch(
                "dc_eval.run._require_api_key",
            ), patch("dc_eval.run._require_claude", return_value="claude"):
                code = run_eval(
                    eval_dir, dry_run=False, reps=1, arms=("baseline",),
                    timeout_s=5, fresh=True,
                )
            self.assertEqual(code, 0)
            self.assertFalse(os.path.isdir(os.path.join(slot, "repo")))
            archives = os.path.join(eval_dir, "runs_archive")
            found = []
            for dirpath, dirnames, filenames in os.walk(archives):
                if "metrics.json" in filenames:
                    found.append(dirpath)
            self.assertEqual(len(found), 1)
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_results_jsonl_keeps_completed_row_when_setup_error_appended(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-hist-")
        try:
            path = os.path.join(eval_dir, "results.jsonl")
            append_result(path, {
                "task": "t", "arm": "baseline", "rep": 1,
                "status": "ok", "resolved": True, "regressions": 0,
            })
            append_result(path, {
                "task": "t", "arm": "baseline", "rep": 1,
                "status": "setup_error", "setup_error": "boom", "resolved": False,
            })
            with open(path, encoding="utf-8") as fh:
                rows = [json.loads(ln) for ln in fh if ln.strip()]
            self.assertEqual(len(rows), 2)
            self.assertTrue(all("recorded_at" in r for r in rows))
            latest = latest_non_error_rows(rows)
            self.assertEqual(len(latest), 1)
            self.assertEqual(latest[0]["status"], "ok")
            self.assertTrue(latest[0]["resolved"])
            md = render_report(rows)
            self.assertIn("Setup errors", md)
            self.assertIn("boom", md)
            summary = per_task_arm_summary(latest_non_error_rows(rows))
            self.assertEqual(summary[("t", "baseline")]["resolved_rate"], 1.0)
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_agent_nonzero_without_result_is_agent_error(self):
        src = tempfile.mkdtemp(prefix="dc-eval-agerr-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-agerrout-")
        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            inner = _eval_fake_run(real_run)
            if kwargs.get("shell"):
                return inner(cmd, **kwargs)
            argv = list(cmd)
            base = os.path.basename(str(argv[0])) if argv else ""
            if base in ("claude", "agent") and "--list-models" not in argv and argv[-1] != "--version":
                err = kwargs.get("stderr")
                if err is not None and hasattr(err, "write"):
                    err.write("agent crashed\n")
                    if hasattr(err, "flush"):
                        err.flush()
                return subprocess.CompletedProcess(argv, 1, "", "agent crashed\n")
            return inner(cmd, **kwargs)

        try:
            task = self._tiny_task(src)
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ):
                row = execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
            self.assertEqual(row.get("status"), "agent_error")
            self.assertFalse(row.get("resolved"))
            self.assertIn("agent crashed", row.get("agent_error") or "")
            slot = os.path.join(eval_dir, "runs", "t", "baseline", "1")
            with open(os.path.join(slot, "stderr.txt"), encoding="utf-8") as fh:
                self.assertIn("agent crashed", fh.read())
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_execute_run_refuses_to_reuse_slot(self):
        src = tempfile.mkdtemp(prefix="dc-eval-reuse-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-reuseout-")
        fake_run = _eval_fake_run(subprocess.run)
        try:
            task = self._tiny_task(src)
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ):
                execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
                with self.assertRaises(SafetyError) as cm:
                    execute_run(
                        task, "baseline", 1,
                        eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                        timeout_s=5, claude_bin="claude", src_repo=src,
                    )
            self.assertIn("--fresh", str(cm.exception))
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_cursor_preflight_failure_is_setup_error(self):
        src = tempfile.mkdtemp(prefix="dc-eval-prefl-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-preflout-")
        real_run = subprocess.run
        agent_calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            argv = list(cmd) if not kwargs.get("shell") else []
            if argv and os.path.basename(str(argv[0])) == "agent" and "--list-models" in argv:
                agent_calls.append(argv)
                return subprocess.CompletedProcess(
                    argv, 1, "",
                    'Invalid project config: permissions.allow Required\n',
                )
            return _eval_fake_run(real_run)(cmd, **kwargs)

        try:
            task = self._tiny_task(src)
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ):
                row = execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="composer-1", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                    runner="cursor", agent_bin="agent",
                )
            self.assertEqual(row.get("status"), "setup_error")
            self.assertIn("permissions.allow", row.get("setup_error") or "")
            self.assertTrue(agent_calls)
            self.assertIn("--list-models", agent_calls[0])
            self.assertEqual(
                cursor_preflight_argv("/ws")[:4],
                ["agent", "--list-models", "--output-format", "stream-json"],
            )
            slot = os.path.join(eval_dir, "runs", "t", "baseline", "1")
            self.assertTrue(os.path.isfile(os.path.join(slot, "setup.log")))
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_offline_policy_always_writes_allow_list(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-allow-")
        try:
            apply_cursor_offline_policy(tmp)
            with open(os.path.join(tmp, ".cursor", "cli.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["permissions"]["allow"], [])
            self.assertEqual(data["permissions"]["deny"], ["WebFetch(*)"])
            apply_cursor_offline_policy(tmp)
            with open(os.path.join(tmp, ".cursor", "cli.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["permissions"]["deny"], ["WebFetch(*)"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_agent_zero_exit_without_result_is_agent_error(self):
        src = tempfile.mkdtemp(prefix="dc-eval-nores-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-noresout-")
        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            inner = _eval_fake_run(real_run)
            if kwargs.get("shell"):
                return inner(cmd, **kwargs)
            argv = list(cmd)
            base = os.path.basename(str(argv[0])) if argv else ""
            if base in ("claude", "agent") and "--list-models" not in argv and argv[-1] != "--version":
                return subprocess.CompletedProcess(argv, 0, "", "")
            return inner(cmd, **kwargs)

        try:
            task = self._tiny_task(src)
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ):
                row = execute_run(
                    task, "baseline", 1,
                    eval_dir=eval_dir, model="sonnet", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                )
            self.assertEqual(row.get("status"), "agent_error")
            self.assertFalse(row.get("resolved"))
            self.assertNotEqual(row.get("status"), "ok")
            self.assertIn("no result event", row.get("agent_error") or "")
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)

    def test_setup_error_excluded_from_metrics(self):
        rows = [
            {
                "task": "t", "arm": "baseline", "rep": 1, "status": "ok",
                "resolved": True, "regressions": 0, "wall_time_s": 40,
                "input_tokens": 10, "output_tokens": 2, "cost_usd": 0.1,
            },
            {
                "task": "u", "arm": "baseline", "rep": 1, "status": "setup_error",
                "setup_error": "boom", "resolved": False, "wall_time_s": 0,
            },
        ]
        md = render_report(rows)
        self.assertIn("Setup errors", md)
        self.assertIn("boom", md)
        summary = per_task_arm_summary(latest_non_error_rows(rows))
        self.assertIn(("t", "baseline"), summary)
        self.assertNotIn(("u", "baseline"), summary)
        self.assertIn("| baseline | 1 |", md)


class AblationTests(unittest.TestCase):
    def test_parse_arms_default_and_legacy(self):
        self.assertEqual(parse_arms(None, "both"), ("baseline", "layer"))
        self.assertEqual(parse_arms(None, None), ("baseline", "layer"))
        self.assertEqual(parse_arms(None, "baseline"), ("baseline",))
        self.assertEqual(
            parse_arms("baseline,tools,contracts,layer"),
            ("baseline", "tools", "contracts", "layer"),
        )
        self.assertEqual(parse_arms("tools", "both"), ("tools",))
        with self.assertRaises(ValueError):
            parse_arms("baseline,nope")
        with self.assertRaises(ValueError):
            parse_arms("baseline,baseline")

    def test_plan_shuffles_within_task_rep(self):
        t = Task(id="a", repo=".", commit="c", prompt="p")
        arms = ("baseline", "tools", "contracts", "layer")
        a = [(arm, rep) for _t, arm, rep in plan_runs([t], arms=arms, reps=2, seed=0)]
        b = [(arm, rep) for _t, arm, rep in plan_runs([t], arms=arms, reps=2, seed=0)]
        self.assertEqual(a, b)
        self.assertEqual([rep for _arm, rep in a], [1, 1, 1, 1, 2, 2, 2, 2])
        self.assertEqual({arm for arm, rep in a if rep == 1}, set(arms))
        default = [
            arm for _t, arm, _rep in plan_runs([t], arms=arms, reps=1, seed=0)
        ]
        self.assertEqual(sorted(default), sorted(arms))
        found_diff = False
        for s in range(1, 40):
            other = [
                arm for _t, arm, _rep in plan_runs([t], arms=arms, reps=1, seed=s)
            ]
            self.assertEqual(sorted(other), sorted(arms))
            if other != default:
                found_diff = True
                break
        self.assertTrue(found_diff, "arm shuffle should depend on --seed")

    def test_report_paired_each_arm_vs_baseline(self):
        rows = []
        for arm, tokens, reads, dcc, created, retries in (
            ("baseline", 1000, 8, 0, 0, 0),
            ("tools", 900, 6, 3, 0, 0),
            ("contracts", 850, 10, 2, 1, 1),
            ("layer", 800, 4, 5, 1, 2),
        ):
            rows.append({
                "task": "t1", "arm": arm, "rep": 1, "status": "ok",
                "resolved": True, "regressions": 0,
                "input_tokens": tokens, "output_tokens": 0,
                "cost_usd": 0.1, "wall_time_s": 10, "read_chars": 50,
                "turns": 3, "model_requests": 2, "tokens_per_request": tokens / 2,
                "read_calls": reads, "dc_engine_calls": dcc,
                "contracts_created": created, "contract_retries": retries,
            })
        md = render_report(rows)
        self.assertIn("Per-arm summary", md)
        self.assertIn("dc-engine calls", md)
        self.assertIn("contract retries", md)
        self.assertIn("tools − baseline", md)
        self.assertIn("contracts − baseline", md)
        self.assertIn("layer − baseline", md)
        summary = per_task_arm_summary(rows)
        diffs = paired_diffs(summary, "tokens", ["t1"], arm="tools")
        self.assertEqual(len(diffs), 1)
        self.assertAlmostEqual(diffs[0], -100.0)

    def _cursor_execute(self, arm: str):
        src = tempfile.mkdtemp(prefix="dc-eval-ablsrc-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-ablout-")
        fake_run = _eval_fake_run(subprocess.run)
        try:
            _init_git(src)
            _write(os.path.join(src, "app.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=src, text=True,
            ).strip()
            task = Task(id="t", repo=src, commit=sha, prompt="p")
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ):
                row = execute_run(
                    task, arm, 1,
                    eval_dir=eval_dir, model="composer-1", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                    runner="cursor", agent_bin="agent",
                )
            slot = os.path.join(eval_dir, "runs", "t", arm, "1")
            repo = os.path.join(slot, "repo")
            metrics_path = os.path.join(slot, "metrics.json")
            with open(metrics_path, encoding="utf-8") as fh:
                metrics = json.load(fh)
            mcp_path = os.path.join(repo, ".cursor", "mcp.json")
            hooks_path = os.path.join(repo, ".cursor", "hooks.json")
            return src, eval_dir, row, metrics, mcp_path, hooks_path, repo
        except Exception:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)
            raise

    def test_execute_run_tools_mcp_no_hooks(self):
        src = eval_dir = None
        try:
            src, eval_dir, row, metrics, mcp_path, hooks_path, repo = (
                self._cursor_execute("tools")
            )
            self.assertEqual(metrics.get("dc_engine_tools"), "slim")
            self.assertEqual(metrics.get("hook_mode"), "off")
            self.assertFalse(os.path.isfile(hooks_path))
            self.assertTrue(os.path.isfile(mcp_path))
            with open(mcp_path, encoding="utf-8") as fh:
                mcp = json.load(fh)
            args = mcp["mcpServers"]["dc-engine"]["args"]
            self.assertIn("--contracts", args)
            self.assertIn("optional", args)
            self.assertNotIn("--tools", args)
            self.assertFalse(os.path.isfile(os.path.join(repo, ".dc-engine", "config.json")))
            self.assertIn("read_calls", metrics)
            self.assertIn("dc_engine_calls", metrics)
            self.assertIn("contract_retries", metrics)
            self.assertEqual(row.get("dc_engine_tools"), "slim")
        finally:
            if src:
                shutil.rmtree(src, ignore_errors=True)
            if eval_dir:
                shutil.rmtree(eval_dir, ignore_errors=True)

    def test_execute_run_contracts_hooks_and_tools_flag(self):
        src = eval_dir = None
        try:
            src, eval_dir, row, metrics, mcp_path, hooks_path, _repo = (
                self._cursor_execute("contracts")
            )
            self.assertEqual(metrics.get("dc_engine_tools"), "contracts")
            self.assertEqual(metrics.get("hook_mode"), "block")
            self.assertTrue(os.path.isfile(hooks_path))
            with open(mcp_path, encoding="utf-8") as fh:
                mcp = json.load(fh)
            args = mcp["mcpServers"]["dc-engine"]["args"]
            self.assertEqual(args[:2], ["-m", "dc_engine.server"])
            self.assertIn("--tools", args)
            self.assertIn("contracts", args)
            self.assertNotIn("optional", args)
        finally:
            if src:
                shutil.rmtree(src, ignore_errors=True)
            if eval_dir:
                shutil.rmtree(eval_dir, ignore_errors=True)

    def test_execute_run_layer_slim_hooks(self):
        src = eval_dir = None
        try:
            src, eval_dir, row, metrics, mcp_path, hooks_path, _repo = (
                self._cursor_execute("layer")
            )
            self.assertEqual(metrics.get("dc_engine_tools"), "slim")
            self.assertEqual(metrics.get("hook_mode"), "block")
            self.assertTrue(os.path.isfile(hooks_path))
            with open(mcp_path, encoding="utf-8") as fh:
                mcp = json.load(fh)
            args = mcp["mcpServers"]["dc-engine"]["args"]
            self.assertNotIn("--tools", args)
            self.assertNotIn("optional", args)
        finally:
            if src:
                shutil.rmtree(src, ignore_errors=True)
            if eval_dir:
                shutil.rmtree(eval_dir, ignore_errors=True)

    def test_execute_run_baseline_no_engine(self):
        src = eval_dir = None
        try:
            src, eval_dir, row, metrics, mcp_path, hooks_path, _repo = (
                self._cursor_execute("baseline")
            )
            self.assertIsNone(metrics.get("dc_engine_tools"))
            self.assertEqual(metrics.get("hook_mode"), "off")
            self.assertFalse(os.path.isfile(hooks_path))
            self.assertFalse(os.path.isfile(mcp_path))
        finally:
            if src:
                shutil.rmtree(src, ignore_errors=True)
            if eval_dir:
                shutil.rmtree(eval_dir, ignore_errors=True)

    def test_tools_arm_does_not_call_install(self):
        src = tempfile.mkdtemp(prefix="dc-eval-noinst-")
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-noinstout-")
        fake_run = _eval_fake_run(subprocess.run)
        try:
            _init_git(src)
            _write(os.path.join(src, "app.py"), "x = 1\n")
            _git(["add", "."], src)
            _git(["commit", "-m", "init"], src)
            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=src, text=True,
            ).strip()
            task = Task(id="t", repo=src, commit=sha, prompt="p")
            with patch("dc_eval.run.subprocess.run", fake_run), patch(
                "dc_eval.grade.subprocess.run", fake_run,
            ), patch("dc_eval.run._install_cursor_layer") as inst:
                execute_run(
                    task, "tools", 1,
                    eval_dir=eval_dir, model="composer-1", budget_usd=2.0,
                    timeout_s=5, claude_bin="claude", src_repo=src,
                    runner="cursor", agent_bin="agent",
                )
            inst.assert_not_called()
        finally:
            shutil.rmtree(src, ignore_errors=True)
            shutil.rmtree(eval_dir, ignore_errors=True)


def _fake_engine_git(head="abc123", diff="", root=None):
    """Mock `dc_eval.gitutil.git` for engine-pin tests. Never the live agent."""

    def fake_git(args, cwd, check=True, timeout=120):
        a = list(args)
        h = head() if callable(head) else head
        d = diff() if callable(diff) else diff
        top = root or cwd
        if a[:2] == ["rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(["git", *a], 0, "true\n", "")
        if a[:2] == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(["git", *a], 0, str(top) + "\n", "")
        if a[:2] == ["rev-parse", "HEAD"] or a[:3] == ["log", "-1", "--format=%H"]:
            return subprocess.CompletedProcess(["git", *a], 0, str(h) + "\n", "")
        if a[:1] == ["diff"]:
            return subprocess.CompletedProcess(["git", *a], 0, d, "")
        raise AssertionError(f"unexpected git {a} cwd={cwd}")

    return fake_git


class EnginePinTests(unittest.TestCase):
    def test_capture_records_commit_dirty_hash_and_path(self):
        blob = "diff --git a/src/dc_engine/x.py b/src/dc_engine/x.py\n"
        expected_dirty = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        with patch("dc_eval.gitutil.git", _fake_engine_git(head="deadbeef", diff=blob)):
            pin = capture_engine_pin()
        self.assertEqual(pin.git_commit, "deadbeef")
        self.assertEqual(pin.git_dirty, expected_dirty)
        self.assertIn("dc_engine", pin.package_path)
        self.assertEqual(pin.version, "0.1.0")

    def _two_task_eval(self):
        eval_dir = tempfile.mkdtemp(prefix="dc-eval-pin-")
        repo = tempfile.mkdtemp(prefix="dc-eval-pinrepo-")
        _init_git(repo)
        _write(os.path.join(repo, "app.py"), "x = 1\n")
        _git(["add", "."], repo)
        _git(["commit", "-m", "init"], repo)
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True,
        ).strip()
        save_task(eval_dir, Task(id="aa-one", repo=repo, commit=sha, prompt="p"))
        save_task(eval_dir, Task(id="bb-two", repo=repo, commit=sha, prompt="p"))
        return eval_dir, repo

    def test_run_eval_stops_if_git_commit_changes(self):
        eval_dir, repo = self._two_task_eval()
        state = {"head": "aaa111"}
        executed: list[str] = []

        def fake_execute(task, arm, rep, **kwargs):
            executed.append(task.id)
            self.assertEqual(kwargs.get("engine_pin").git_commit, "aaa111")
            state["head"] = "bbb222"
            return {
                "task": task.id, "arm": arm, "rep": rep,
                "status": "ok", "resolved": True,
                **kwargs["engine_pin"].as_metrics(),
            }

        try:
            with patch("dc_eval.gitutil.git", _fake_engine_git(head=lambda: state["head"])), \
                 patch("dc_eval.run.execute_run", fake_execute), \
                 patch("dc_eval.run._require_api_key"), \
                 patch("dc_eval.run._require_claude", return_value="claude"):
                with self.assertRaises(SafetyError) as cm:
                    run_eval(
                        eval_dir, dry_run=False, reps=1, arms=("baseline",),
                        timeout_s=5,
                    )
            self.assertIn(ENGINE_CHANGED, str(cm.exception))
            self.assertEqual(executed, ["aa-one"])
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_run_eval_stops_if_dirty_diff_changes(self):
        eval_dir, repo = self._two_task_eval()
        state = {"diff": ""}
        executed: list[str] = []

        def fake_execute(task, arm, rep, **kwargs):
            executed.append(task.id)
            state["diff"] = "diff --git a/x b/x\n"
            return {
                "task": task.id, "arm": arm, "rep": rep,
                "status": "ok", "resolved": True,
            }

        try:
            with patch("dc_eval.gitutil.git", _fake_engine_git(diff=lambda: state["diff"])), \
                 patch("dc_eval.run.execute_run", fake_execute), \
                 patch("dc_eval.run._require_api_key"), \
                 patch("dc_eval.run._require_claude", return_value="claude"):
                with self.assertRaises(SafetyError) as cm:
                    run_eval(
                        eval_dir, dry_run=False, reps=1, arms=("baseline",),
                        timeout_s=5,
                    )
            self.assertIn("dc-engine changed since batch start", str(cm.exception))
            self.assertEqual(executed, ["aa-one"])
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)

    def test_run_eval_stops_if_package_path_changes(self):
        eval_dir, repo = self._two_task_eval()
        state = {"path": "/engine-a"}
        executed: list[str] = []

        def fake_pkg():
            return state["path"]

        def fake_execute(task, arm, rep, **kwargs):
            executed.append(task.id)
            state["path"] = "/engine-b"
            return {
                "task": task.id, "arm": arm, "rep": rep,
                "status": "ok", "resolved": True,
            }

        try:
            with patch("dc_eval.gitutil.git", _fake_engine_git(head="aaa111", diff="")), \
                 patch("dc_eval.run.dc_engine_package_dir", fake_pkg), \
                 patch("dc_eval.run.execute_run", fake_execute), \
                 patch("dc_eval.run._require_api_key"), \
                 patch("dc_eval.run._require_claude", return_value="claude"):
                with self.assertRaises(SafetyError) as cm:
                    run_eval(
                        eval_dir, dry_run=False, reps=1, arms=("baseline",),
                        timeout_s=5,
                    )
            self.assertIn("dc-engine changed since batch start", str(cm.exception))
            self.assertEqual(executed, ["aa-one"])
        finally:
            shutil.rmtree(eval_dir, ignore_errors=True)
            shutil.rmtree(repo, ignore_errors=True)


class OverheadProbeTests(unittest.TestCase):
    def test_mean_layer_minus_baseline(self):
        from dc_eval.probe import OVERHEAD_PROMPT, probe_overhead, render_overhead_report

        calls = []

        def fake_execute(task, arm, rep, **kwargs):
            self.assertEqual(task.prompt, OVERHEAD_PROMPT)
            self.assertFalse(kwargs.get("do_grade", True))
            calls.append((arm, rep))
            tokens = {"baseline": (1000, 1200), "layer": (1400, 1600)}[arm][rep - 1]
            return {
                "task": task.id, "arm": arm, "rep": rep, "status": "ok",
                "tokens": tokens, "input_tokens": tokens, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_write_tokens": 0,
                "model_requests": 1, "tokens_per_request": tokens,
            }

        tmp = tempfile.mkdtemp(prefix="dc-eval-oh-")
        try:
            with patch("dc_eval.probe.resolve_overhead_shop", return_value=(tmp, "abc")), \
                 patch("dc_eval.probe.load_catalogs", return_value={
                     "full": {
                         "mode": "full", "chars": 9000, "tokens": 2250,
                         "tool_count": 18, "instructions": "long",
                         "instructions_chars": 400, "instructions_tokens": 100,
                         "instructions_words": 80, "tools": [],
                     },
                     "slim": {
                         "mode": "slim", "chars": 3000, "tokens": 750,
                         "tool_count": 5, "instructions": "short",
                         "instructions_chars": 200, "instructions_tokens": 50,
                         "instructions_words": 40, "tools": [],
                     },
                 }), \
                 patch("dc_eval.probe.existing_run_slots", return_value=[]), \
                 patch("dc_eval.probe.archive_run_dirs"):
                payload = probe_overhead(
                    tmp, model="composer-1", runner="cursor", execute=fake_execute,
                )
            self.assertEqual(calls, [
                ("baseline", 1), ("layer", 1), ("baseline", 2), ("layer", 2),
            ])
            self.assertEqual(payload["mean_baseline_tokens"], 1100)
            self.assertEqual(payload["mean_layer_tokens"], 1500)
            self.assertEqual(payload["fixed_overhead_tokens"], 400)
            with open(os.path.join(tmp, "overhead.md"), encoding="utf-8") as fh:
                md = fh.read()
            self.assertIn("fixed overhead", md)
            self.assertIn("400", md)
            self.assertIn("Before (full)", md)
            self.assertIn("After (slim)", md)
            rendered = render_overhead_report(
                payload["rows"], model="composer-1", runner="cursor",
                shop=tmp, catalogs={},
            )
            self.assertIn(OVERHEAD_PROMPT, rendered)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cli_requires_model(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            with self.assertRaises(SystemExit):
                eval_main(["probe-overhead", "--eval-dir", "eval", "--runner", "cursor"])


if __name__ == "__main__":
    unittest.main()
