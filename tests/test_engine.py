"""Unit tests for dc-engine phase 1.  Run:  python -m unittest discover tests"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_engine import Engine
from dc_engine.parser import module_name, parse_source
from dc_engine.views import (
    DEFAULT_REPO_MAP_TOKENS, DEFAULT_SLICE_TOKENS, DEFAULT_START_TOKENS,
    GET_SYMBOL_MAX_TOKENS, SMALL_REPO_TOKENS, est_tokens,
)
from unittest.mock import patch

FIXTURE = os.path.join(HERE, "fixtures", "shop")


class FixtureCase(unittest.TestCase):
    typecheck = "off"  # pyright is slow; enabled only in the dedicated test below

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-test-")
        self.root = os.path.join(self.tmp, "shop")
        shutil.copytree(FIXTURE, self.root)
        self.e = Engine(self.root, typecheck=self.typecheck, refresh_interval=0)

    def tearDown(self) -> None:
        self.e.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def read(self, rel: str) -> str:
        with open(os.path.join(self.root, rel), encoding="utf-8") as fh:
            return fh.read()

    def callees(self, caller: str) -> set[str]:
        self.e.ensure_fresh()
        return {r["callee"] for r in self.e.store.callees_of(caller) if r["callee"]}


class ParserTests(unittest.TestCase):
    def test_module_names(self):
        self.assertEqual(module_name("src/pkg/mod.py"), "pkg.mod")
        self.assertEqual(module_name("pkg/__init__.py"), "pkg")
        self.assertEqual(module_name("setup.py"), "setup")

    def test_symbols_ranges_and_signatures(self):
        pf = parse_source(open(os.path.join(FIXTURE, "shop", "billing.py")).read(), "shop/billing.py")
        by = {s.qualname: s for s in pf.symbols}
        total = by["shop.billing.Receipt.total"]
        self.assertEqual(total.kind, "method")
        self.assertIn("@property", total.signature)
        self.assertLess(total.start_line, total.def_line)  # decorator included
        self.assertEqual(by["shop.billing.Receipt"].kind, "class")
        self.assertEqual(by["shop.billing.charge"].docstring, "Charge a user and return a receipt.")

    def test_syntax_error_is_recorded_not_raised(self):
        pf = parse_source("def broken(:\n    pass\n", "x.py")
        self.assertIsNotNone(pf.error)
        self.assertEqual(pf.symbols, [])


class CallGraphTests(FixtureCase):
    def test_local_and_constructor_calls(self):
        self.assertEqual(self.callees("shop.billing.charge"),
                         {"shop.billing.validate_amount", "shop.billing.Receipt"})

    def test_relative_module_import(self):  # from . import tax ; tax.compute()
        self.assertEqual(self.callees("shop.billing.Receipt.total"), {"shop.tax.compute"})

    def test_aliased_module_import(self):  # import shop.tax as t ; t.compute()
        self.assertEqual(self.callees("shop.api.preview"), {"shop.tax.compute"})

    def test_package_reexport(self):  # from shop import charge  (re-exported in __init__)
        self.assertEqual(self.callees("shop.api.checkout"), {"shop.billing.charge"})

    def test_self_and_super(self):
        self.assertEqual(self.callees("shop.api.Service.run"), {"shop.api.Service.helper"})
        self.assertEqual(self.callees("shop.models.Admin.notify"),
                         {"shop.models.User.notify", "shop.models.Admin.log"})

    def test_unknown_receiver_stays_unresolved(self):
        self.e.ensure_fresh()
        rows = self.e.store.callees_of("shop.billing.charge")
        notify = [r for r in rows if r["expr"] == "user.notify"]
        self.assertEqual(len(notify), 1)
        self.assertIsNone(notify[0]["callee"])

    def test_external_and_builtin_calls(self):
        self.e.ensure_fresh()
        rows = {r["expr"]: r for r in self.e.store.callees_of("shop.tax.compute")}
        self.assertEqual(rows["Decimal"]["external"], "decimal.Decimal")
        self.assertNotIn("print", {r["expr"] for r in self.e.store.callees_of("shop.models.Admin.log")})


class ViewTests(FixtureCase):
    def test_repo_map_full_and_compressed(self):
        full = self.e.repo_map(max_tokens=5000)
        self.assertIn("def charge(user: User, amount: Decimal) -> Receipt", full)
        small = self.e.repo_map(max_tokens=60)
        self.assertLessEqual(est_tokens(small), 60)

    def test_find_symbol_ranks_exact_name_first(self):
        self.assertTrue(self.e.find_symbol("charge").startswith("shop.billing.charge"))

    def test_get_symbol_lists_calls_and_callers(self):
        out = self.e.get_symbol("billing.charge")
        self.assertIn("calls: shop.billing.Receipt, shop.billing.validate_amount", out)
        self.assertIn("called by: shop.api.checkout", out)
        self.assertNotIn("validate_amount(amount)\n", out)  # no body unless asked
        self.assertLessEqual(est_tokens(out), GET_SYMBOL_MAX_TOKENS)
        self.assertIn("validate_amount(amount)", self.e.get_symbol("billing.charge", include_body=True))

    def test_default_budgets(self):
        self.assertEqual(DEFAULT_REPO_MAP_TOKENS, 800)
        self.assertEqual(DEFAULT_SLICE_TOKENS, 1500)
        self.assertEqual(DEFAULT_START_TOKENS, 2500)
        mapped = self.e.repo_map()
        self.assertLessEqual(est_tokens(mapped), DEFAULT_REPO_MAP_TOKENS)
        sliced = self.e.get_slice(["billing.charge"])
        self.assertLessEqual(est_tokens(sliced), DEFAULT_SLICE_TOKENS + 80)
        old_map = self.e.repo_map(max_tokens=2000)
        self.assertGreaterEqual(est_tokens(old_map), est_tokens(mapped))

    def test_duplicate_names_need_line(self):
        self.assertIn("pick one", self.e.get_symbol("Admin.label"))
        self.assertIn("@label.setter", self.e.get_symbol("Admin.label@L32"))

    def test_references_include_possible_matches(self):
        out = self.e.find_references("User.notify")
        self.assertIn("in shop.models.Admin.notify", out)
        self.assertIn("in shop.billing.charge  (user.notify)", out)  # name match, flagged as possible

    def test_slice_contents(self):
        out = self.e.get_slice(["billing.charge"])
        self.assertIn("== TARGET shop.billing.charge", out)
        self.assertIn("receipt = Receipt(user, amount)", out)
        self.assertIn("shop.billing.validate_amount", out)
        self.assertIn("shop.api.checkout", out)
        self.assertIn("possibly shop.models.User.notify", out)

    def test_slice_respects_budget_by_dropping_bodies(self):
        out = self.e.get_slice(["billing.charge"], max_tokens=150)
        self.assertIn("omitted: budget", out)
        self.assertNotIn("receipt = Receipt(user, amount)", out)

    def test_method_slice_has_class_context(self):
        out = self.e.get_slice(["Receipt.total"])
        self.assertIn("is in class Receipt", out)

    def test_slice_include_tests(self):
        path = os.path.join(self.root, "tests", "test_charge.py")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                "from decimal import Decimal\n"
                "from shop.billing import charge\n"
                "from shop.models import User\n"
                "\n"
                "def test_charge_positive():\n"
                "    charge(User('a', 'US'), Decimal('1'))\n"
            )
        out = self.e.get_slice(["billing.charge"], include_tests=True)
        self.assertIn("== TEST", out)
        self.assertIn("test_charge_positive", out)
        self.assertNotIn("charge(User('a', 'US')", out)
        with_bodies = self.e.get_slice(
            ["billing.charge"], include_tests=True, include_test_bodies=True,
        )
        self.assertIn("charge(User('a', 'US')", with_bodies)
        without = self.e.get_slice(["billing.charge"], include_tests=False)
        self.assertNotIn("== TEST", without)


class EditTests(FixtureCase):
    def test_replace_method_reindents(self):
        out = self.e.replace_symbol("Service.helper", "def helper(self) -> int:\n    return 42\n")
        self.assertTrue(out.startswith("✓ replaced"), out)
        self.assertIn("    def helper(self) -> int:\n        return 42\n", self.read("shop/api.py"))

    def test_replace_keeps_decorator_handling(self):
        new = '@property\ndef total(self) -> Decimal:\n    return self.amount\n'
        self.e.replace_symbol("Receipt.total", new)
        src = self.read("shop/billing.py")
        self.assertEqual(src.count("@property"), 1)
        self.assertIn("    @property\n    def total(self) -> Decimal:\n        return self.amount\n", src)

    def test_syntax_error_rejected_and_file_unchanged(self):
        before = self.read("shop/billing.py")
        out = self.e.replace_symbol("billing.charge", "def charge(user, amount:\n    return 1\n")
        self.assertTrue(out.startswith("✗ rejected"), out)
        self.assertEqual(before, self.read("shop/billing.py"))

    def test_must_be_single_definition(self):
        out = self.e.replace_symbol("billing.charge", "x = 1\ndef charge():\n    pass\n")
        self.assertIn("exactly one def/class", out)

    def test_new_lint_errors_reported_and_old_ones_not(self):
        out = self.e.replace_symbol(
            "billing.validate_amount",
            "def validate_amount(amount: Decimal) -> None:\n    if amount < 0:\n        raise ValueError(msg)\n")
        if "ruff: skipped" in out:
            self.skipTest("ruff not installed")
        self.assertIn("ruff: 1 new", out)
        self.assertIn("F821", out)

    def test_signature_change_warns_about_callers(self):
        out = self.e.replace_symbol(
            "billing.validate_amount",
            "def validate_amount(amount: Decimal, limit: Decimal) -> None:\n    pass\n")
        self.assertIn("⚠ signature changed", out)
        self.assertIn("shop.billing.charge", out)

    def test_index_updates_after_edit(self):
        self.e.replace_symbol("tax.compute",
                              "def compute(amount: Decimal, region: str, exempt: bool = False) -> Decimal:\n"
                              "    return Decimal('0') if exempt else amount\n")
        self.assertIn("exempt: bool=False", self.e.get_symbol("tax.compute"))

    def test_insert_after_symbol_and_append(self):
        out = self.e.insert_symbol("def audit(self) -> str:\n    return 'ok'\n", after="Service.helper")
        self.assertTrue(out.startswith("✓ inserted audit"), out)
        self.assertIn("shop.api.Service.audit", self.e.find_symbol("audit"))
        self.e.insert_symbol("def new_fn() -> int:\n    return 1\n", path="shop/extra.py")
        self.assertIn("shop.extra.new_fn", self.e.find_symbol("new_fn"))

    def test_crlf_files_keep_line_endings(self):
        path = os.path.join(self.root, "shop", "crlf.py")
        with open(path, "w", newline="") as fh:
            fh.write("def a():\r\n    return 1\r\n")
        self.e.ensure_fresh(force=True)
        self.e.replace_symbol("crlf.a", "def a():\n    return 2\n")
        with open(path, newline="") as fh:
            self.assertEqual(fh.read(), "def a():\r\n    return 2\r\n")


class IncrementalTests(FixtureCase):
    def test_only_changed_files_are_reparsed(self):
        self.e.ensure_fresh(force=True)
        time.sleep(0.01)
        path = os.path.join(self.root, "shop", "tax.py")
        with open(path, "a") as fh:
            fh.write("\n\ndef vat(x):\n    return compute(x, 'AU')\n")
        stats = self.e.ensure_fresh()
        self.assertEqual(stats["parsed"], 1)
        self.assertEqual(self.callees("shop.tax.vat"), {"shop.tax.compute"})

    def test_deleted_file_removed(self):
        self.e.ensure_fresh()
        os.remove(os.path.join(self.root, "shop", "api.py"))
        self.e.ensure_fresh()
        self.assertIn("no symbol", self.e.get_symbol("checkout"))


@unittest.skipUnless(shutil.which("pyright"), "pyright not installed")
class TypeCheckTests(FixtureCase):
    typecheck = "pyright"

    def test_pyright_reports_broken_caller(self):
        out = self.e.replace_symbol(
            "billing.validate_amount",
            "def validate_amount(amount: Decimal, limit: Decimal) -> None:\n    pass\n")
        self.assertIn("pyright: 1 new", out)
        self.assertIn("reportCallIssue", out)

    def test_signature_change_checks_callers_in_other_files(self):
        out = self.e.replace_symbol(
            "tax.compute",
            "def compute(amount: Decimal, region: str, year: int) -> Decimal:\n    return amount\n")
        self.assertIn("✗ breaks", out)
        self.assertIn("shop/billing.py", out)   # resolved caller (Receipt.total)
        self.assertIn("shop/api.py", out)       # resolved caller via alias (preview)


class StartTests(FixtureCase):
    def test_small_repo_mode_threshold(self):
        self.assertEqual(SMALL_REPO_TOKENS, 8000)
        out = self.e.start("Reject zero-dollar charges in shop billing")
        self.assertIn("== REPO", out)
        self.assertIn("small", out.lower())
        self.assertIn(str(SMALL_REPO_TOKENS), out)
        self.assertIn("Read files directly", out)
        self.assertNotIn("== MAP", out)
        self.assertNotIn("== SLICES", out)
        self.assertIn("== CONTRACT TEMPLATE", out)
        self.assertIn("== CONTRACT EXAMPLE", out)
        self.assertIn("dc_contract", out)
        self.assertIn("shop.billing.validate_amount", out)

    def test_start_sections_and_budget_when_large(self):
        real = self.e.store.stats()
        big = dict(real)
        big["chars"] = (SMALL_REPO_TOKENS + 100) * 4
        with patch.object(self.e.store, "stats", return_value=big):
            out = self.e.start(
                "charge user receipt",
                hint_symbols=["billing.charge"],
                max_tokens=2000,
            )
        self.assertIn("== REPO", out)
        self.assertIn("== MAP", out)
        self.assertIn("== SLICES", out)
        self.assertIn("== CONTRACT TEMPLATE", out)
        self.assertIn("== CONTRACT EXAMPLE", out)
        self.assertNotIn("Read files directly", out)
        self.assertLessEqual(est_tokens(out), 2500)

    def test_start_template_uses_hint_symbols(self):
        out = self.e.start("fix billing", hint_symbols=["billing.validate_amount"])
        self.assertIn("shop.billing.validate_amount", out)
        self.assertIn("from shop.billing import validate_amount", out)


if __name__ == "__main__":
    unittest.main()
