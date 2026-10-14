"""Phase 3: checkpoints, auto-check, Claude Code hooks, installer."""

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

from dc_engine import Engine
from dc_engine import active, install
from dc_engine.contracts import CheckReport
from dc_engine.hooks import handle

FIXTURE = os.path.join(HERE, "fixtures", "shop")
ZERO_PROBE = {
    "id": "zero",
    "setup": ("from decimal import Decimal\nfrom shop.models import User\n"
              "from shop.billing import charge\nuser = User('a', 'AU')\n"),
    "call": "charge(user, Decimal(0))",
    "expect_new": {"raises": "ValueError"},
}
PREVIEW_PROBE = {
    "id": "preview",
    "setup": "from decimal import Decimal\nfrom shop.api import preview\n",
    "call": "preview(Decimal('10'), 'AU')",
}
REJECT_ZERO = (
    "def validate_amount(amount: Decimal) -> None:\n"
    "    if amount <= 0:\n"
    "        raise ValueError('amount must be positive')\n"
)
REJECT_ZERO_TYPE = (
    "def validate_amount(amount: Decimal) -> None:\n"
    "    if amount == 0:\n"
    "        raise TypeError('zero')\n"
    "    if amount < 0:\n"
    "        raise ValueError('negative amount')\n"
)


def git_init(root: str) -> None:
    ident = ["-c", "user.name=t", "-c", "user.email=t@t.t"]
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", *ident, "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", *ident, "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


class Phase3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-p3-")
        self.root = os.path.join(self.tmp, "shop")
        shutil.copytree(FIXTURE, self.root)
        git_init(self.root)
        self.e = Engine(self.root, typecheck="off", refresh_interval=0, probe_timeout=1.0)

    def tearDown(self) -> None:
        self.e.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create(self, preserve=None):
        return self.e.create_contract(
            "charge zero should raise", ["billing.validate_amount"],
            [ZERO_PROBE], preserve if preserve is not None else [])

    def _billing(self) -> str:
        with open(os.path.join(self.root, "shop", "billing.py"), encoding="utf-8") as fh:
            return fh.read()

    def test_checkpoint_created_on_improvement_and_restored(self):
        r = self._create()
        first = self.e.check_contract(r.contract_id)
        self.assertIsInstance(first, CheckReport)
        self.assertEqual(first.score, 0.0)
        listed = self.e.list_checkpoints(r.contract_id)
        self.assertIn("1  ", listed)
        self.e.replace_symbol("billing.validate_amount", REJECT_ZERO)
        good = self._billing()
        second = self.e.check_contract(r.contract_id)
        self.assertEqual(second.score, 1.0)
        self.assertIn("2  ", self.e.list_checkpoints(r.contract_id))
        self.e.replace_symbol("billing.validate_amount", REJECT_ZERO_TYPE)
        dropped = self.e.check_contract(r.contract_id)
        self.assertLess(dropped.score, 1.0)
        self.assertIn("score dropped", str(dropped))
        self.assertIn("dc_restore_checkpoint", str(dropped))
        out = self.e.restore_checkpoint(r.contract_id, 2)
        self.assertTrue(out.startswith("✓ restored"), out)
        self.assertEqual(self._billing(), good)
        again = self.e.check_contract(r.contract_id)
        self.assertEqual(again.score, 1.0)

    def test_amend_validates_new_probes(self):
        r = self._create()
        bad = self.e.amend_contract(
            r.contract_id, add_must_change=[{
                "id": "already",
                "setup": ZERO_PROBE["setup"],
                "call": ZERO_PROBE["call"],
                "expect_new": {"returns": "Receipt"},
            }])
        self.assertFalse(bad.ok, bad.report)
        self.assertIn("nothing to change", bad.report)
        unknown = self.e.amend_contract(r.contract_id, add_targets=["nope_symbol"])
        self.assertFalse(unknown.ok)
        ok = self.e.amend_contract(
            r.contract_id, add_targets=["tax.compute"], add_must_preserve=[PREVIEW_PROBE])
        self.assertTrue(ok.ok, ok.report)
        shown = self.e.get_contract(r.contract_id)
        self.assertIn("preview", shown)
        self.assertIn("shop.tax.compute", shown)

    def test_auto_check_line_after_replace(self):
        r = self._create()
        out = self.e.replace_symbol("billing.validate_amount", REJECT_ZERO)
        self.assertTrue(out.startswith("✓ replaced"), out)
        self.assertIn(f"contract {r.contract_id}:", out)
        self.assertIn("1/1", out)

    def test_creating_sets_active_closing_clears(self):
        r = self._create()
        self.assertEqual(active.get_active_id(self.root), r.contract_id)
        self.e.close_contract(r.contract_id)
        self.assertIsNone(active.get_active_id(self.root))


class HookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-hook-")
        self.root = os.path.join(self.tmp, "shop")
        shutil.copytree(FIXTURE, self.root)
        git_init(self.root)
        self.e = Engine(self.root, typecheck="off", refresh_interval=0, probe_timeout=1.0)
        self.py = os.path.join(self.root, "shop", "billing.py")
        self.md = os.path.join(self.root, "README.md")
        with open(self.md, "w", encoding="utf-8") as fh:
            fh.write("# shop\n")

    def tearDown(self) -> None:
        self.e.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pre(self, **kw):
        payload = {"cwd": self.root, "hook_event_name": "PreToolUse",
                   "tool_name": "Edit",
                   "tool_input": {"file_path": self.py, "old_string": "a", "new_string": "b"}}
        payload.update(kw)
        return handle("pre-edit", payload, self.root)

    def test_deny_python_without_contract(self):
        out = self._pre()
        dec = out["hookSpecificOutput"]
        self.assertEqual(dec["permissionDecision"], "deny")
        self.assertEqual(dec["hookEventName"], "PreToolUse")
        self.assertIn("dc_create_contract", dec["permissionDecisionReason"])

    def test_allow_non_python(self):
        out = self._pre(tool_name="Write",
                        tool_input={"file_path": self.md, "content": "# x\n"})
        self.assertEqual(out, {})

    def test_allow_with_contract(self):
        self.e.create_contract("z", ["billing.validate_amount"], [ZERO_PROBE], [])
        out = self._pre()
        spec = out.get("hookSpecificOutput") or {}
        self.assertNotEqual(spec.get("permissionDecision"), "deny")

    def test_amend_note_for_non_target_file(self):
        self.e.create_contract("z", ["billing.validate_amount"], [ZERO_PROBE], [])
        api = os.path.join(self.root, "shop", "api.py")
        out = self._pre(tool_input={"file_path": api, "old_string": "a", "new_string": "b"})
        note = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("dc_amend_contract", note)

    def test_stop_blocks_when_unsatisfied(self):
        self.e.create_contract("z", ["billing.validate_amount"], [ZERO_PROBE], [])
        out = handle("stop", {"cwd": self.root, "hook_event_name": "Stop",
                              "stop_hook_active": False}, self.root)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("not changed", out.get("reason", ""))

    def test_loop_guard_releases(self):
        self.e.create_contract("z", ["billing.validate_amount"], [ZERO_PROBE], [])
        payload = {"cwd": self.root, "hook_event_name": "Stop", "stop_hook_active": False}
        self.assertEqual(handle("stop", payload, self.root).get("decision"), "block")
        self.assertEqual(handle("stop", payload, self.root).get("decision"), "block")
        third = handle("stop", payload, self.root)
        self.assertNotEqual(third.get("decision"), "block")
        self.assertIn("allowing stop", third["hookSpecificOutput"]["additionalContext"])

    def test_stop_hook_active_allows(self):
        self.e.create_contract("z", ["billing.validate_amount"], [ZERO_PROBE], [])
        out = handle("stop", {"cwd": self.root, "hook_event_name": "Stop",
                              "stop_hook_active": True}, self.root)
        self.assertNotEqual(out.get("decision"), "block")

    def test_warn_mode_never_denies(self):
        active.set_enforce(self.root, "warn")
        out = self._pre()
        spec = out["hookSpecificOutput"]
        self.assertNotEqual(spec.get("permissionDecision"), "deny")
        self.assertIn("dc_create_contract", spec["additionalContext"])
        self.e.create_contract("z", ["billing.validate_amount"], [ZERO_PROBE], [])
        stop = handle("stop", {"cwd": self.root, "stop_hook_active": False}, self.root)
        self.assertNotEqual(stop.get("decision"), "block")

    def test_off_mode_is_noop(self):
        active.set_enforce(self.root, "off")
        self.assertEqual(self._pre(), {})
        self.assertEqual(handle("stop", {"cwd": self.root}, self.root), {})

    def test_post_edit_adds_status(self):
        self.e.create_contract("z", ["billing.validate_amount"], [ZERO_PROBE], [])
        out = handle("post-edit", {
            "cwd": self.root, "hook_event_name": "PostToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": self.py},
        }, self.root)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("contract ", ctx)
        self.assertIn("0/1", ctx)


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-inst-")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read(self, rel):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as fh:
            return json.load(fh)

    def test_idempotent_and_preserves_keys(self):
        os.makedirs(os.path.join(self.tmp, ".claude"))
        existing = {
            "permissions": {"allow": ["Bash"]},
            "hooks": {
                "PreToolUse": [{
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo hi"}],
                }]
            },
        }
        with open(os.path.join(self.tmp, ".claude", "settings.json"), "w") as fh:
            json.dump(existing, fh)
        with open(os.path.join(self.tmp, ".mcp.json"), "w") as fh:
            json.dump({"mcpServers": {"other": {"command": "x"}}}, fh)
        first = install.install(self.tmp)
        self.assertIn("add PreToolUse", first)
        second = install.install(self.tmp)
        self.assertIn("keep PreToolUse", second)
        settings = self._read(".claude/settings.json")
        self.assertEqual(settings["permissions"], {"allow": ["Bash"]})
        pre = settings["hooks"]["PreToolUse"]
        commands = [h["command"] for g in pre for h in g["hooks"]]
        self.assertEqual(commands.count("echo hi"), 1)
        self.assertEqual(commands.count("dc-engine hook pre-edit"), 1)
        mcp = self._read(".mcp.json")
        self.assertIn("other", mcp["mcpServers"])
        self.assertIn("dc-engine", mcp["mcpServers"])
        gone = install.uninstall(self.tmp)
        self.assertIn("remove", gone)
        settings = self._read(".claude/settings.json")
        self.assertEqual(settings["permissions"], {"allow": ["Bash"]})
        pre = settings["hooks"]["PreToolUse"]
        commands = [h["command"] for g in pre for h in g["hooks"]]
        self.assertEqual(commands, ["echo hi"])
        self.assertNotIn("Stop", settings["hooks"])
        mcp = self._read(".mcp.json")
        self.assertIn("other", mcp["mcpServers"])
        self.assertNotIn("dc-engine", mcp["mcpServers"])


if __name__ == "__main__":
    unittest.main()
