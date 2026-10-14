"""Phase 2: delta contracts and the old-vs-new probe runner.

Run:  python -m unittest tests.test_contracts
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_engine import Engine
from dc_engine.contracts import CheckReport, CreateResult

FIXTURE = os.path.join(HERE, "fixtures", "shop")

ZERO_SETUP = (
    "from decimal import Decimal\n"
    "from shop.models import User\n"
    "from shop.billing import charge\n"
    "user = User('a', 'AU')\n"
)
ZERO_CALL = "charge(user, Decimal(0))"
ZERO_PROBE = {
    "id": "zero",
    "setup": ZERO_SETUP,
    "call": ZERO_CALL,
    "expect_new": {"raises": "ValueError"},
}
PREVIEW_PROBE = {
    "id": "preview",
    "setup": "from decimal import Decimal\nfrom shop.api import preview\n",
    "call": "preview(Decimal('10'), 'AU')",
}
REJECT_ZERO = (
    "def validate_amount(amount: Decimal) -> None:\n"
    "    \"\"\"Reject non-positive amounts.\"\"\"\n"
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
TAX_ZERO = (
    "def compute(amount: Decimal, region: str) -> Decimal:\n"
    "    return amount * 0\n"
)


def git_init(root: str) -> None:
    ident = ["-c", "user.name=t", "-c", "user.email=t@t.t"]
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", *ident, "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", *ident, "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


class GitContractTests(unittest.TestCase):
    typecheck = "off"

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-contract-")
        self.root = os.path.join(self.tmp, "shop")
        shutil.copytree(FIXTURE, self.root)
        git_init(self.root)
        self.e = Engine(self.root, typecheck=self.typecheck, refresh_interval=0,
                        probe_timeout=1.0)

    def tearDown(self) -> None:
        self.e.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create(self, preserve=None, **extra) -> CreateResult:
        return self.e.create_contract(
            extra.get("task", "charge(user, Decimal(0)) should raise ValueError"),
            extra.get("targets", ["billing.validate_amount"]),
            extra.get("must_change", [ZERO_PROBE]),
            preserve if preserve is not None else extra.get("must_preserve", [PREVIEW_PROBE]),
        )

    def test_expect_old_mismatch_rejected_with_real_result(self):
        probe = dict(ZERO_PROBE, expect_old={"raises": "ValueError"})
        r = self.e.create_contract(
            "zero should raise", ["billing.validate_amount"], [probe], [])
        self.assertIsInstance(r, CreateResult)
        self.assertFalse(r.ok, r.report)
        self.assertIn("your understanding of the current behaviour is wrong", r.report)
        self.assertIn("Receipt", r.report)

    def test_already_matches_expect_new_rejected(self):
        probe = dict(ZERO_PROBE, expect_new={"returns": "Receipt"})
        r = self.e.create_contract(
            "noop", ["billing.validate_amount"], [probe], [])
        self.assertFalse(r.ok, r.report)
        self.assertIn("nothing to change", r.report)

    def test_unknown_target_suggests(self):
        r = self.e.create_contract("x", ["charg"], [ZERO_PROBE], [])
        self.assertFalse(r.ok)
        self.assertIn("no symbol", r.report)
        self.assertIn("charge", r.report)

    def test_valid_contract_then_intended_edit_scores_one(self):
        r = self._create()
        self.assertTrue(r.ok, r.report)
        self.assertIsNotNone(r.contract_id)
        out = self.e.replace_symbol("billing.validate_amount", REJECT_ZERO)
        self.assertTrue(out.startswith("✓ replaced"), out)
        report = self.e.check_contract(r.contract_id)
        self.assertIsInstance(report, CheckReport)
        self.assertEqual(report.score, 1.0)
        text = str(report)
        self.assertIn("✓", text)
        self.assertIn("1.0", text)
        self.assertIn("ValueError", text)

    def test_unintended_change_on_preserve_probe(self):
        r = self._create()
        self.assertTrue(r.ok, r.report)
        self.e.replace_symbol("billing.validate_amount", REJECT_ZERO)
        self.e.replace_symbol("tax.compute", TAX_ZERO)
        report = self.e.check_contract(r.contract_id)
        text = str(report)
        self.assertIn("unintended", text)
        self.assertIn("preview", text)
        self.assertLess(report.score, 1.0)

    def test_no_edit_is_not_changed(self):
        r = self._create(preserve=[])
        report = self.e.check_contract(r.contract_id)
        text = str(report)
        self.assertIn("not changed", text)
        self.assertEqual(report.score, 0.0)

    def test_wrong_edit_is_changed_wrongly(self):
        r = self._create(preserve=[])
        self.e.replace_symbol("billing.validate_amount", REJECT_ZERO_TYPE)
        report = self.e.check_contract(r.contract_id)
        text = str(report)
        self.assertIn("changed wrongly", text)
        self.assertIn("TypeError", text)
        self.assertEqual(report.score, 0.0)

    def test_random_without_seed_is_deterministic(self):
        # Preserve probe: two baseline runs must agree even though the call
        # never seeds random itself (the runner does).
        r = self.e.create_contract(
            "random is seeded", ["billing.charge"], [ZERO_PROBE],
            [{"id": "rnd", "call": "__import__('random').random()"}])
        self.assertTrue(r.ok, r.report)
        self.assertNotIn("rnd", r.contract.flaky)
        report = self.e.check_contract(r.contract_id)
        self.assertIn("preserved: rnd", str(report))

    def test_sleep_is_timeout_not_crash(self):
        r = self.e.create_contract(
            "timeout", ["billing.charge"],
            [{"id": "sleep", "call": "__import__('time').sleep(5)",
              "expect_new": {"returns": "None"}}],
            [])
        self.assertTrue(r.ok, r.report)
        report = self.e.check_contract(r.contract_id)
        text = str(report)
        self.assertIn("timeout", text.lower())
        self.assertNotIn("Traceback", text)

    def test_uncommitted_changes_are_in_git_baseline(self):
        path = os.path.join(self.root, "shop", "tax.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src.replace(
                'return amount * RATES.get(region, Decimal("0"))',
                "return Decimal('0')",
            ))
        probe = {
            "id": "tax0",
            "setup": "from decimal import Decimal\nfrom shop.tax import compute\n",
            "call": "compute(Decimal('10'), 'AU')",
            "expect_old": {"returns": "Decimal('0')"},
            "expect_new": {"returns": "Decimal('1')"},
        }
        r = self.e.create_contract("uncommitted tax", ["tax.compute"], [probe], [])
        self.assertTrue(r.ok, r.report)

    def test_get_list_close(self):
        r = self._create(preserve=[])
        listed = self.e.list_contracts()
        self.assertIn(r.contract_id, listed)
        shown = self.e.get_contract(r.contract_id)
        self.assertIn("must_change", shown)
        closed = self.e.close_contract(r.contract_id)
        self.assertTrue(closed.startswith("✓ closed"), closed)
        self.assertFalse(os.path.isdir(
            os.path.join(self.root, ".dc-engine", "baseline", r.contract_id)))


class CopyContractTests(unittest.TestCase):
    """Non-git repo uses a copied baseline."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-copy-")
        self.root = os.path.join(self.tmp, "shop")
        shutil.copytree(FIXTURE, self.root)
        self.e = Engine(self.root, typecheck="off", refresh_interval=0, probe_timeout=1.0)

    def tearDown(self) -> None:
        self.e.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_copy_baseline_roundtrip(self):
        r = self.e.create_contract(
            "zero charge", ["billing.validate_amount"], [ZERO_PROBE], [])
        self.assertTrue(r.ok, r.report)
        self.assertEqual(r.contract.baseline_ref, "copy")
        self.e.replace_symbol("billing.validate_amount", REJECT_ZERO)
        report = self.e.check_contract(r.contract_id)
        self.assertEqual(report.score, 1.0)


if __name__ == "__main__":
    unittest.main()
