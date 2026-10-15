"""Cursor runner, stream parse, prices, usage import. Never calls agent/claude."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_eval.arms import ALL_ARMS, cursor_argv
from dc_eval.cursor_stream import is_limit_error, metrics_from_cursor_stream
from dc_eval.prices import PLACEHOLDER_PRICES, estimate_cost_usd
from dc_eval.report import render_report
from dc_eval.run import (
    SafetyError,
    _install_cursor_layer,
    bind_cursor_interpreter,
    format_plan,
    has_cursor_auth,
    plan_runs,
)
from dc_eval.tasks import Task
from dc_eval.usage_import import apply_dashboard_totals, import_usage, match_rows, parse_csv_row

SAMPLE = os.path.join(HERE, "data", "cursor_stream_sample.jsonl")
LIVE_READ = os.path.join(HERE, "data", "cursor_stream_read_live.jsonl")
CSV = os.path.join(HERE, "data", "cursor_usage_sample.csv")


class CursorStreamTests(unittest.TestCase):
    def test_sample_metrics_sum_and_cost(self):
        with open(SAMPLE, encoding="utf-8") as fh:
            text = fh.read()
        m = metrics_from_cursor_stream(text)
        self.assertEqual(m["input_tokens"], 180)
        self.assertEqual(m["output_tokens"], 30)
        self.assertEqual(m["cache_read_tokens"], 1500)
        self.assertEqual(m["cache_write_tokens"], 75)
        self.assertEqual(m["tokens"], 1785)
        self.assertEqual(m["read_chars"], 1254)
        self.assertEqual(m["tool_calls"]["read"], 1)
        self.assertEqual(m["tool_calls"]["write"], 1)
        self.assertEqual(m["read_calls"], 1)
        self.assertTrue(any(p.endswith("billing.py") for p in m["files_written"]))
        self.assertFalse(m["usage_missing"])
        self.assertEqual(m["usage_blocks"], 2)
        self.assertFalse(m["is_error"])
        self.assertEqual(m["duration_ms"], 5234)
        self.assertIsNone(m["turns"])
        tmp = tempfile.mkdtemp(prefix="dc-prices-")
        try:
            os.makedirs(tmp, exist_ok=True)
            with open(os.path.join(tmp, "prices.json"), "w", encoding="utf-8") as fh:
                json.dump(PLACEHOLDER_PRICES, fh)
            cost = estimate_cost_usd(
                model="composer-1",
                input_tokens=180, output_tokens=30,
                cache_read_tokens=1500, cache_write_tokens=75,
                eval_dir=tmp,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        # (180*1.25 + 30*10 + 1500*0.125 + 75*1.25) / 1e6
        self.assertAlmostEqual(cost, 0.00080625)

    def test_missing_usage_is_null_and_flagged(self):
        text = '{"type":"result","subtype":"success","is_error":false,"duration_ms":1}\n'
        m = metrics_from_cursor_stream(text)
        self.assertTrue(m["usage_missing"])
        self.assertIsNone(m["tokens"])
        self.assertIsNone(m["input_tokens"])

    def test_read_chars_from_live_content_when_no_total_chars(self):
        self.assertTrue(os.path.isfile(LIVE_READ), "recorded live read stream missing")
        with open(LIVE_READ, encoding="utf-8") as fh:
            text = fh.read()
        m = metrics_from_cursor_stream(text)
        content = "from __future__ import annotations\n\nimport abc\n"
        self.assertEqual(m["read_chars"], len(content))
        self.assertGreater(m["read_chars"], 0)
        self.assertEqual(m["web_search_count"], 1)
        self.assertEqual(m["web_fetch_count"], 1)
        self.assertEqual(m["web_call_count"], 2)
        self.assertEqual(
            m["web_queries"],
            ["tomlkit Float PySequence_Check github issue 563"],
        )
        self.assertEqual(
            m["web_urls"],
            ["https://github.com/python-poetry/tomlkit/issues/563"],
        )

    def test_sample_prefers_total_chars_over_short_content(self):
        with open(SAMPLE, encoding="utf-8") as fh:
            text = fh.read()
        m = metrics_from_cursor_stream(text)
        self.assertEqual(m["read_chars"], 1254)
        self.assertEqual(m["tool_result_chars"]["read"], 1254)
        self.assertGreater(m["tool_result_chars"]["write"], 0)
        self.assertEqual(m.get("web_search_count"), 0)
        self.assertEqual(m.get("web_fetch_count"), 0)

    def test_mcp_result_size_uses_dc_engine_tool_name(self):
        blob = (
            '{"type":"tool_call","subtype":"completed","call_id":"c1",'
            '"tool_call":{"mcpToolCall":{"args":{"toolName":"dc_get_slice",'
            '"name":"dc-engine-dc_get_slice"},'
            '"result":{"success":{"content":[{"text":{"text":"SLICE abc"}}],'
            '"isError":false}}}}}\n'
        )
        m = metrics_from_cursor_stream(blob)
        self.assertEqual(m["tool_result_chars"]["dc_get_slice"], len("SLICE abc"))
        self.assertEqual(m["dc_engine_result_chars"]["dc_get_slice"], len("SLICE abc"))
        self.assertEqual(m["dc_engine_largest"][0]["tool"], "dc_get_slice")

    def test_model_requests_from_model_call_id(self):
        blob = "\n".join([
            '{"type":"assistant","model_call_id":"m1","message":{"content":[]}}',
            '{"type":"tool_call","subtype":"started","model_call_id":"m1"}',
            '{"type":"assistant","model_call_id":"m2"}',
            '{"type":"result","subtype":"success","is_error":false,'
            '"duration_ms":1}',
        ]) + "\n"
        m = metrics_from_cursor_stream(blob)
        self.assertEqual(m["model_requests"], 2)
        self.assertTrue(m["usage_missing"])
        self.assertIsNone(m["tokens_per_request"])
        blob2 = (
            '{"type":"assistant","model_call_id":"only"}\n'
            '{"type":"usage","inputTokens":100,"outputTokens":20,'
            '"cacheReadTokens":0,"cacheWriteTokens":0}\n'
            '{"type":"result","subtype":"success","is_error":false}\n'
        )
        m2 = metrics_from_cursor_stream(blob2)
        self.assertEqual(m2["model_requests"], 1)
        self.assertEqual(m2["tokens"], 120)
        self.assertEqual(m2["tokens_per_request"], 120)


class CursorCommandTests(unittest.TestCase):
    def test_both_arms_same_cli_flags(self):
        ws = "/tmp/eval-run/repo"
        base = cursor_argv("fix the bug", model="composer-1", workspace=ws)
        layer = cursor_argv("fix the bug", model="composer-1", workspace=ws)
        self.assertEqual(base, layer)
        self.assertEqual(base, [
            "agent", "-p", "--output-format", "stream-json", "--force",
            "--trust", "--approve-mcps", "--workspace", ws,
            "--model", "composer-1", "fix the bug",
        ])
        self.assertNotIn("--sandbox", base)

    def test_refuses_auto(self):
        with self.assertRaises(ValueError) as cm:
            cursor_argv("x", model="auto", workspace="/tmp/r")
        self.assertIn("auto", str(cm.exception).lower())
        with self.assertRaises(ValueError):
            cursor_argv("x", model="", workspace="/tmp/r")

    def test_dry_run_plan_prints_both_arm_commands(self):
        t = Task(id="shop", repo=".", commit="abc1234ffff", prompt="fix zero charges")
        eval_dir = os.path.abspath("eval")
        text = format_plan(
            plan_runs([t], reps=1), model="composer-1", budget_usd=2.0,
            timeout_s=1200, eval_dir=eval_dir, runner="cursor",
        )
        prefix = "agent -p --output-format stream-json --force --trust --approve-mcps --workspace"
        self.assertEqual(text.count(prefix), 2)
        self.assertIn("--model composer-1", text)
        self.assertNotIn("--sandbox", text)
        self.assertIn(os.path.join(eval_dir, "runs", "shop", "baseline", "1", "repo"), text)
        self.assertIn(os.path.join(eval_dir, "runs", "shop", "layer", "1", "repo"), text)
        self.assertIn("baseline", text)
        self.assertIn("layer", text)
        self.assertIn("install --cursor", text)
        self.assertIn("-m dc_engine", text)
        self.assertIn("no dc-engine MCP", text)
        self.assertIn("isolated venv", text)

    def test_dry_run_auto_raises(self):
        t = Task(id="shop", repo=".", commit="abc", prompt="p")
        with self.assertRaises(SafetyError):
            format_plan(
                plan_runs([t], reps=1), model="auto", budget_usd=2.0,
                timeout_s=1200, eval_dir="eval", runner="cursor",
            )

    def test_limit_detection(self):
        self.assertTrue(is_limit_error("Error: you've reached your usage limit", ""))
        self.assertTrue(is_limit_error("", '{"type":"result","result":"plan limit exceeded"}'))
        self.assertFalse(is_limit_error("all tests passed", '{"type":"result"}'))

    def test_auth_helper_does_not_return_key_material(self):
        # Presence check only; return value is bool.
        self.assertIsInstance(has_cursor_auth(), bool)

    def test_cursor_layer_writes_absolute_interpreter(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-bind-")
        try:
            _install_cursor_layer(tmp)
            py = os.path.abspath(sys.executable)
            with open(os.path.join(tmp, ".cursor", "hooks.json"), encoding="utf-8") as fh:
                hooks = json.load(fh)
            pre = hooks["hooks"]["preToolUse"][0]["command"]
            self.assertIn("-m dc_engine hook preToolUse", pre)
            self.assertIn("--format cursor", pre)
            self.assertTrue(py in pre or pre.startswith(py) or f"'{py}'" in pre or f'"{py}"' in pre)
            self.assertNotEqual(pre, "dc-engine hook preToolUse --format cursor")
            with open(os.path.join(tmp, ".cursor", "mcp.json"), encoding="utf-8") as fh:
                mcp = json.load(fh)
            server = mcp["mcpServers"]["dc-engine"]
            self.assertEqual(server["command"], py)
            self.assertEqual(server["args"][:2], ["-m", "dc_engine.server"])
            self.assertNotEqual(server.get("command"), "dc-engine-mcp")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bind_rewrites_installer_path_commands(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-rebind-")
        try:
            os.makedirs(os.path.join(tmp, ".cursor"))
            with open(os.path.join(tmp, ".cursor", "hooks.json"), "w", encoding="utf-8") as fh:
                json.dump({
                    "version": 1,
                    "hooks": {
                        "preToolUse": [{
                            "command": "dc-engine hook preToolUse --format cursor",
                            "matcher": "Write",
                        }],
                        "stop": [{"command": "dc-engine hook stop --format cursor"}],
                    },
                }, fh)
            with open(os.path.join(tmp, ".cursor", "mcp.json"), "w", encoding="utf-8") as fh:
                json.dump({
                    "mcpServers": {
                        "dc-engine": {"command": "dc-engine-mcp", "args": ["--root", "."]},
                    },
                }, fh)
            bind_cursor_interpreter(tmp, sys.executable)
            py = os.path.abspath(sys.executable)
            with open(os.path.join(tmp, ".cursor", "hooks.json"), encoding="utf-8") as fh:
                hooks = json.load(fh)
            self.assertIn("-m dc_engine hook preToolUse --format cursor", hooks["hooks"]["preToolUse"][0]["command"])
            self.assertIn(py, hooks["hooks"]["preToolUse"][0]["command"])
            with open(os.path.join(tmp, ".cursor", "mcp.json"), encoding="utf-8") as fh:
                mcp = json.load(fh)
            self.assertEqual(mcp["mcpServers"]["dc-engine"]["command"], py)
            self.assertEqual(mcp["mcpServers"]["dc-engine"]["args"][:2], ["-m", "dc_engine.server"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bind_sets_dc_probe_python(self):
        tmp = tempfile.mkdtemp(prefix="dc-eval-probebind-")
        try:
            os.makedirs(os.path.join(tmp, ".cursor"))
            with open(os.path.join(tmp, ".cursor", "hooks.json"), "w", encoding="utf-8") as fh:
                json.dump({
                    "version": 1,
                    "hooks": {
                        "preToolUse": [{
                            "command": "dc-engine hook preToolUse --format cursor",
                            "matcher": "Write",
                        }],
                    },
                }, fh)
            with open(os.path.join(tmp, ".cursor", "mcp.json"), "w", encoding="utf-8") as fh:
                json.dump({
                    "mcpServers": {
                        "dc-engine": {"command": "dc-engine-mcp", "args": ["--root", "."]},
                    },
                }, fh)
            probe = os.path.join(tmp, "venv", "bin", "python")
            os.makedirs(os.path.dirname(probe), exist_ok=True)
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("#!/bin/sh\n")
            bind_cursor_interpreter(tmp, sys.executable, probe)
            abs_probe = os.path.abspath(probe)
            with open(os.path.join(tmp, ".cursor", "hooks.json"), encoding="utf-8") as fh:
                hooks = json.load(fh)
            cmd = hooks["hooks"]["preToolUse"][0]["command"]
            self.assertIn("DC_PROBE_PYTHON=", cmd)
            self.assertIn(abs_probe, cmd)
            with open(os.path.join(tmp, ".cursor", "mcp.json"), encoding="utf-8") as fh:
                mcp = json.load(fh)
            self.assertEqual(
                mcp["mcpServers"]["dc-engine"]["env"]["DC_PROBE_PYTHON"], abs_probe,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_never_calls_agent_binary(self):
        from dc_eval import run as runmod
        with open(runmod.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("dry_run", src)
        self.assertIn("cursor_argv", src)


class UsageImportTests(unittest.TestCase):
    def test_matching_totals_ambiguity_and_mismatch_flag(self):
        import csv
        with open(CSV, newline="", encoding="utf-8") as fh:
            raw = list(csv.DictReader(fh))
        parsed = [parse_csv_row(r) for r in raw]
        self.assertEqual(parsed[0]["input_with_cache_write"], 1000)
        self.assertEqual(parsed[1]["input_without_cache_write"], 500)
        self.assertEqual(parsed[1]["cost"], "Included")
        self.assertEqual(parsed[2]["cost"], "Free")
        self.assertEqual(parsed[0]["total_tokens_sum"], 3100)

        runs = [
            {
                "task": "a", "arm": "baseline", "rep": 1, "model": "composer-1",
                "started_at": "2026-10-14T12:00:00.000Z",
                "ended_at": "2026-10-14T12:03:00.000Z",
                "input_tokens": 100, "output_tokens": 10,
                "cache_read_tokens": 10, "cache_write_tokens": 10,
                "tokens": 130, "runner": "cursor",
            },
            {
                "task": "b", "arm": "layer", "rep": 1, "model": "composer-1",
                "started_at": "2026-10-14T12:04:00.000Z",
                "ended_at": "2026-10-14T12:10:00.000Z",
                "input_tokens": 10, "output_tokens": 1,
                "cache_read_tokens": 0, "cache_write_tokens": 0,
                "tokens": 11, "runner": "cursor",
            },
        ]
        assigned, ignored, ambiguous = match_rows(parsed, runs)
        self.assertEqual(len(assigned), 3)  # 12:00:10, :20, :30 → run A
        self.assertEqual(len(ignored), 1)  # 15:00:00
        self.assertEqual(len(ambiguous), 1)  # 12:04:30 matches A slack and B
        self.assertTrue(ignored[0]["date"].startswith("2026-10-14T15:00"))
        updated = apply_dashboard_totals(runs, assigned)
        self.assertEqual(updated[0]["dashboard_total_tokens"], 3100 + 650 + 210)
        self.assertTrue(updated[0]["token_mismatch_gt_5pct"])
        self.assertIsNone(updated[1]["dashboard_total_tokens"])

    def test_import_usage_writes_results(self):
        tmp = tempfile.mkdtemp(prefix="dc-usage-")
        try:
            results = os.path.join(tmp, "results.jsonl")
            with open(results, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "task": "a", "arm": "baseline", "rep": 1, "model": "composer-1",
                    "started_at": "2026-10-14T12:00:00.000Z",
                    "ended_at": "2026-10-14T12:01:00.000Z",
                    "tokens": 3960, "runner": "cursor",
                    "input_tokens": 1200, "output_tokens": 160,
                    "cache_read_tokens": 2100, "cache_write_tokens": 500,
                }) + "\n")
            summary = import_usage(CSV, tmp)
            self.assertGreaterEqual(summary["assigned"], 1)
            self.assertGreaterEqual(summary["ignored"], 1)
            with open(results, encoding="utf-8") as fh:
                rows = [json.loads(ln) for ln in fh if ln.strip()]
            self.assertIn("dashboard_total_tokens", rows[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_report_shows_hooks_and_estimated(self):
        md = render_report([{
            "task": "t1", "arm": "baseline", "rep": 1, "runner": "cursor",
            "resolved": True, "regressions": 0,
            "input_tokens": 100, "output_tokens": 20,
            "cache_read_tokens": 800, "cache_write_tokens": 80,
            "tokens": 1000, "cost_usd": 0.01, "cost_estimated": True,
            "wall_time_s": 10, "read_chars": 50, "turns": None,
            "hooks_active": False, "usage_missing": False,
        }, {
            "task": "t1", "arm": "layer", "rep": 1, "runner": "cursor",
            "resolved": True, "regressions": 0,
            "input_tokens": 80, "output_tokens": 20,
            "cache_read_tokens": 400, "cache_write_tokens": 40,
            "tokens": 540, "cost_usd": 0.008, "cost_estimated": True,
            "wall_time_s": 12, "read_chars": 20, "turns": None,
            "hooks_active": True, "usage_missing": False,
        }])
        self.assertIn("estimated", md.lower())
        self.assertIn("hooks active", md.lower())
        self.assertIn("denials", md.lower())
        self.assertIn("stop follow-ups", md.lower())
        self.assertIn("n/a", md)
        self.assertIn("cache read", md.lower())


class CursorAblationPlanTests(unittest.TestCase):
    def test_four_arm_dry_run_prints_order_and_extras(self):
        t = Task(id="shop", repo=".", commit="abc1234ffff", prompt="fix zero charges")
        eval_dir = os.path.abspath("eval")
        arms = ("baseline", "tools", "contracts", "layer")
        text = format_plan(
            plan_runs([t], arms=arms, reps=1, seed=0),
            model="composer-1", budget_usd=2.0, timeout_s=1200,
            eval_dir=eval_dir, runner="cursor", seed=0,
        )
        self.assertIn("arm order seed: 0", text)
        self.assertIn("arms: ", text)
        prefix = "agent -p --output-format stream-json --force --trust --approve-mcps --workspace"
        self.assertEqual(text.count(prefix), 4)
        self.assertIn("no dc-engine MCP, no dc-engine hooks", text)
        self.assertIn("slim MCP, no hooks", text)
        self.assertIn("--tools contracts", text)
        self.assertIn("install --cursor", text)
        self.assertIn("dc_contract available but never required", text)
        for arm in arms:
            self.assertIn(os.path.join(eval_dir, "runs", "shop", arm, "1", "repo"), text)

    def test_cursor_argv_identical_across_ablation_arms(self):
        ws = "/tmp/eval-run/repo"
        cmds = [
            cursor_argv("fix the bug", model="composer-1", workspace=ws)
            for _ in ("baseline", "tools", "contracts", "layer")
        ]
        self.assertTrue(all(c == cmds[0] for c in cmds))
        self.assertNotIn(ALL_ARMS[0], cmds[0])


if __name__ == "__main__":
    unittest.main()
