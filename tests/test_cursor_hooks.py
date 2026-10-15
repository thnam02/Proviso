"""Cursor hook adapter + installer. Does not call the agent or claude CLIs."""

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

from dc_engine import Engine, active, install
from dc_engine.contracts import CheckReport
from dc_engine.hooks import (
    MSG_NO_CONTRACT_EDIT,
    MSG_NO_CONTRACT_SHELL,
    handle,
    handle_cursor,
)

FIXTURE = os.path.join(HERE, "fixtures", "shop")
ZERO_PROBE = {
    "id": "zero",
    "setup": ("from decimal import Decimal\nfrom shop.models import User\n"
              "from shop.billing import charge\nuser = User('a', 'AU')\n"),
    "call": "charge(user, Decimal(0))",
    "expect_new": {"raises": "ValueError"},
}
REJECT_ZERO = (
    "def validate_amount(amount: Decimal) -> None:\n"
    "    if amount <= 0:\n"
    "        raise ValueError('amount must be positive')\n"
)


def git_init(root: str) -> None:
    ident = ["-c", "user.name=t", "-c", "user.email=t@t.t"]
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", *ident, "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", *ident, "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


class CursorHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-cur-")
        self.root = os.path.join(self.tmp, "shop")
        shutil.copytree(FIXTURE, self.root)
        git_init(self.root)
        self.e = Engine(self.root, typecheck="off", refresh_interval=0, probe_timeout=1.0)
        self.py = os.path.join(self.root, "shop", "billing.py")

    def tearDown(self) -> None:
        self.e.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_payload(self, path=None):
        return {
            "tool_name": "Write",
            "tool_input": {"path": path or self.py},
            "cwd": self.root,
            "hook_event_name": "preToolUse",
        }

    def test_pretool_write_without_contract_denies(self):
        out = handle_cursor("preToolUse", self._write_payload(), self.root)
        self.assertEqual(out, {
            "permission": "deny",
            "agent_message": MSG_NO_CONTRACT_EDIT,
        })

    def test_pretool_write_with_contract_allows(self):
        self.e.create_contract(
            "charge zero should raise", ["billing.validate_amount"], [ZERO_PROBE], [])
        out = handle_cursor("preToolUse", self._write_payload(), self.root)
        self.assertEqual(out, {"permission": "allow"})

    def test_shell_py_write_without_contract_denies(self):
        out = handle_cursor("beforeShellExecution", {
            "command": "echo x > shop/billing.py",
            "cwd": self.root,
        }, self.root)
        self.assertEqual(out, {
            "permission": "deny",
            "agent_message": MSG_NO_CONTRACT_SHELL,
        })

    def test_non_python_edit_allows(self):
        md = os.path.join(self.root, "README.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("hi\n")
        out = handle_cursor("preToolUse", self._write_payload(md), self.root)
        self.assertEqual(out, {"permission": "allow"})

    def test_before_mcp_always_allows(self):
        out = handle_cursor("beforeMCPExecution", {
            "tool_name": "dc_create_contract",
            "tool_input": "{}",
            "mcp_server_name": "dc-engine",
            "cwd": self.root,
        }, self.root)
        self.assertEqual(out, {"permission": "allow"})

    def test_after_file_edit_records_path(self):
        out = handle_cursor("afterFileEdit", {
            "file_path": self.py,
            "edits": [{"old_string": "a", "new_string": "b"}],
            "cwd": self.root,
        }, self.root)
        self.assertEqual(out, {})
        sess = active.load_session(self.root)
        self.assertTrue(any(str(p).endswith("billing.py") for p in sess.get("edited_paths") or []))

    def test_stop_score_below_one_followup(self):
        self.e.create_contract(
            "charge zero should raise", ["billing.validate_amount"], [ZERO_PROBE], [])
        out = handle_cursor("stop", {
            "cwd": self.root, "status": "completed", "loop_count": 0,
        }, self.root)
        self.assertIn("followup_message", out)
        self.assertIn("contract ", out["followup_message"])
        self.assertIn("Fix every", out["followup_message"])
        self.assertEqual(set(out), {"followup_message"})

    def test_stop_score_one_empty(self):
        r = self.e.create_contract(
            "charge zero should raise", ["billing.validate_amount"], [ZERO_PROBE], [])
        self.e.replace_symbol("billing.validate_amount", REJECT_ZERO, check=False)
        report = self.e.check_contract(r.contract_id)
        self.assertIsInstance(report, CheckReport)
        self.assertGreaterEqual(report.score, 1.0 - 1e-12)
        out = handle_cursor("stop", {
            "cwd": self.root, "status": "completed", "loop_count": 0,
        }, self.root)
        self.assertEqual(out, {})

    def test_loop_release_after_three_same_scores(self):
        self.e.create_contract(
            "charge zero should raise", ["billing.validate_amount"], [ZERO_PROBE], [])
        payload = {"cwd": self.root, "status": "completed", "loop_count": 0}
        self.assertIn("followup_message", handle_cursor("stop", payload, self.root))
        payload["loop_count"] = 1
        self.assertIn("followup_message", handle_cursor("stop", payload, self.root))
        payload["loop_count"] = 2
        third = handle_cursor("stop", payload, self.root)
        self.assertEqual(third, {})
        with open(os.path.join(self.root, ".dc-engine", "hooks.log"), encoding="utf-8") as fh:
            log = fh.read()
        self.assertIn("STOP-RELEASE", log)

    def test_loop_count_three_releases(self):
        self.e.create_contract(
            "charge zero should raise", ["billing.validate_amount"], [ZERO_PROBE], [])
        out = handle_cursor("stop", {
            "cwd": self.root, "status": "completed", "loop_count": 3,
        }, self.root)
        self.assertEqual(out, {})

    def test_warn_never_denies_or_followups(self):
        active.set_enforce(self.root, "warn")
        self.assertEqual(
            handle_cursor("preToolUse", self._write_payload(), self.root),
            {"permission": "allow"},
        )
        self.assertEqual(
            handle_cursor("beforeShellExecution", {
                "command": "tee shop/x.py", "cwd": self.root,
            }, self.root),
            {"permission": "allow"},
        )
        self.e.create_contract(
            "charge zero should raise", ["billing.validate_amount"], [ZERO_PROBE], [])
        self.assertEqual(
            handle_cursor("stop", {"cwd": self.root, "loop_count": 0}, self.root),
            {},
        )
        with open(os.path.join(self.root, ".dc-engine", "hooks.log"), encoding="utf-8") as fh:
            log = fh.read()
        self.assertIn("WARN", log)

    def test_off_is_allow_or_empty(self):
        active.set_enforce(self.root, "off")
        self.assertEqual(
            handle_cursor("preToolUse", self._write_payload(), self.root),
            {"permission": "allow"},
        )
        self.assertEqual(handle_cursor("stop", {"cwd": self.root, "loop_count": 0}, self.root), {})

    def test_claude_format_unchanged(self):
        out = handle("pre-edit", {
            "tool_name": "Write",
            "tool_input": {"file_path": self.py},
            "cwd": self.root,
        }, self.root)
        self.assertEqual(
            out["hookSpecificOutput"]["permissionDecision"], "deny",
        )
        self.assertNotIn("permission", out)


class CursorInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-cur-inst-")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read(self, rel):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as fh:
            return json.load(fh)

    def test_merges_without_losing_other_keys_idempotent_uninstall(self):
        os.makedirs(os.path.join(self.tmp, ".cursor"))
        existing_hooks = {
            "version": 1,
            "hooks": {
                "sessionStart": [{"command": "echo hi"}],
            },
            "extra": True,
        }
        with open(os.path.join(self.tmp, ".cursor", "hooks.json"), "w") as fh:
            json.dump(existing_hooks, fh)
        with open(os.path.join(self.tmp, ".cursor", "mcp.json"), "w") as fh:
            json.dump({"mcpServers": {"other": {"command": "x"}}}, fh)
        first = install.install(self.tmp, claude_code=False, cursor=True)
        self.assertIn("add preToolUse", first)
        second = install.install(self.tmp, claude_code=False, cursor=True)
        self.assertIn("keep preToolUse", second)
        hooks = self._read(".cursor/hooks.json")
        self.assertEqual(hooks["version"], 1)
        self.assertTrue(hooks["extra"])
        self.assertEqual(hooks["hooks"]["sessionStart"], [{"command": "echo hi"}])
        pre = hooks["hooks"]["preToolUse"]
        self.assertEqual(pre[0]["matcher"], "Write")
        self.assertEqual(pre[0]["command"], "dc-engine hook preToolUse --format cursor")
        self.assertEqual(len(pre), 1)
        mcp = self._read(".cursor/mcp.json")
        self.assertIn("other", mcp["mcpServers"])
        self.assertIn("dc-engine", mcp["mcpServers"])
        gone = install.uninstall(self.tmp, claude_code=False, cursor=True)
        self.assertIn("remove", gone)
        hooks = self._read(".cursor/hooks.json")
        self.assertEqual(hooks["hooks"]["sessionStart"], [{"command": "echo hi"}])
        self.assertNotIn("preToolUse", hooks["hooks"])
        self.assertNotIn("stop", hooks["hooks"])
        mcp = self._read(".cursor/mcp.json")
        self.assertIn("other", mcp["mcpServers"])
        self.assertNotIn("dc-engine", mcp["mcpServers"])


if __name__ == "__main__":
    unittest.main()
