"""Concurrent JSON state writes and per-invocation hooks.log JSONL."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_engine.hooks import handle, handle_cursor
from dc_engine.jsonio import exclusive_lock, read_json, write_json_atomic
from dc_eval.cursor_stream import summarize_hooks_log

WORKER = r"""
import sys
from dc_engine.jsonio import exclusive_lock, read_json, write_json_atomic
path = sys.argv[1]
with exclusive_lock(path):
    data = read_json(path)
    data["n"] = int(data.get("n") or 0) + 1
    write_json_atomic(path, data)
"""


def _parse_log(root: str) -> list[dict]:
    path = os.path.join(root, ".dc-engine", "hooks.log")
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            out.append(json.loads(ln))
    return out


class ConcurrentSessionWriteTests(unittest.TestCase):
    def test_twenty_processes_rmw_session_json(self):
        tmp = tempfile.mkdtemp(prefix="dc-lock-")
        try:
            path = os.path.join(tmp, ".dc-engine", "session.json")
            os.makedirs(os.path.dirname(path))
            write_json_atomic(path, {"n": 0})
            src = os.path.join(os.path.dirname(HERE), "src")
            env = os.environ.copy()
            env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
            procs = [
                subprocess.Popen(
                    [sys.executable, "-c", WORKER, path],
                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                for _ in range(20)
            ]
            errors = []
            for p in procs:
                _out, err = p.communicate(timeout=30)
                if p.returncode != 0:
                    errors.append(err.strip() or f"exit {p.returncode}")
            self.assertEqual(errors, [], msg=errors[:3])
            self.assertEqual(read_json(path).get("n"), 20)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class HookLogJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-hlog-")
        os.makedirs(os.path.join(self.tmp, ".dc-engine"))
        self.py = os.path.join(self.tmp, "app.py")
        with open(self.py, "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cursor_and_claude_each_append_one_json_line(self):
        handle_cursor("preToolUse", {
            "tool_name": "Write",
            "tool_input": {"path": self.py},
            "cwd": self.tmp,
        }, self.tmp)
        handle("pre-edit", {
            "tool_name": "Write",
            "tool_input": {"file_path": self.py},
            "cwd": self.tmp,
        }, self.tmp)
        recs = _parse_log(self.tmp)
        self.assertEqual(len(recs), 2)
        cur, claude = recs[0], recs[1]
        self.assertEqual(cur["format"], "cursor")
        self.assertEqual(cur["event"], "preToolUse")
        self.assertEqual(cur["decision"], "deny")
        self.assertEqual(cur["tool"], "Write")
        self.assertIn("timestamp", cur)
        self.assertIn("duration_ms", cur)
        self.assertIsInstance(cur["duration_ms"], int)
        self.assertNotIn("error", cur)
        self.assertEqual(claude["format"], "claude")
        self.assertEqual(claude["event"], "pre-edit")
        self.assertEqual(claude["decision"], "deny")

    def test_error_keeps_traceback_as_field(self):
        with patch("dc_engine.hooks.active.enforce_mode", side_effect=RuntimeError("boom")):
            out = handle_cursor("preToolUse", {
                "tool_name": "Write",
                "tool_input": {"path": self.py},
                "cwd": self.tmp,
            }, self.tmp)
        self.assertEqual(out, {"permission": "allow"})
        recs = _parse_log(self.tmp)
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertIn("boom", rec.get("error") or "")
        self.assertIn("Traceback", rec.get("traceback") or "")
        self.assertIn("RuntimeError", rec.get("traceback") or "")

    def test_summarize_counts_events_denials_and_active(self):
        handle_cursor("preToolUse", {
            "tool_name": "Write",
            "tool_input": {"path": self.py},
            "cwd": self.tmp,
        }, self.tmp)
        handle_cursor("beforeMCPExecution", {"cwd": self.tmp}, self.tmp)
        with patch("dc_engine.hooks.active.enforce_mode", side_effect=RuntimeError("x")):
            handle_cursor("stop", {"cwd": self.tmp, "loop_count": 0}, self.tmp)
        path = os.path.join(self.tmp, ".dc-engine", "hooks.log")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        s = summarize_hooks_log(text)
        self.assertEqual(s["hook_calls"], 3)
        self.assertEqual(s["hook_denials"], 1)
        self.assertEqual(s["hook_errors"], 1)
        self.assertEqual(s["hook_calls_by_event"]["preToolUse"], 1)
        self.assertEqual(s["hook_calls_by_event"]["beforeMCPExecution"], 1)
        self.assertEqual(s["hook_calls_by_event"]["stop"], 1)
        self.assertTrue(s["hooks_active"])  # at least one call without error

    def test_hooks_active_false_when_only_errors(self):
        with patch("dc_engine.hooks.active.enforce_mode", side_effect=RuntimeError("x")):
            handle("stop", {"cwd": self.tmp}, self.tmp)
        path = os.path.join(self.tmp, ".dc-engine", "hooks.log")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        s = summarize_hooks_log(text)
        self.assertEqual(s["hook_errors"], 1)
        self.assertFalse(s["hooks_active"])


if __name__ == "__main__":
    unittest.main()
