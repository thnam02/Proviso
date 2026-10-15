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
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from dc_engine import Engine
from dc_engine.contracts import (
    CREATE_CONTRACT_DESCRIPTION, CREATE_CONTRACT_EXAMPLE, CheckReport, CreateResult,
    Probe, allocate_id, apply_auto_imports, already_imported, load_contract,
    split_import_target,
)
from dc_engine.probes import probe_python, run_probe, venv_python
from dc_engine.server import INSTRUCTIONS

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
        closed = self.e.close_contract(r.contract_id, reason="test done")
        self.assertTrue(closed.startswith("✓ closed"), closed)
        self.assertFalse(os.path.isdir(
            os.path.join(self.root, ".dc-engine", "baseline", r.contract_id)))


class AutoImportAndIdTests(unittest.TestCase):
    def test_auto_import_function(self):
        pair = split_import_target("shop.billing.charge", "function")
        self.assertEqual(pair, ("shop.billing", "charge"))
        setup, added = apply_auto_imports("user = User('a', 'AU')\n", [pair])
        self.assertEqual(added, ["from shop.billing import charge"])
        self.assertTrue(setup.startswith("from shop.billing import charge\n"))
        self.assertIn("user = User", setup)

    def test_auto_import_method_imports_class(self):
        pair = split_import_target(
            "shop.billing.Receipt.total", "method", "shop.billing.Receipt")
        self.assertEqual(pair, ("shop.billing", "Receipt"))
        setup, added = apply_auto_imports("", [pair])
        self.assertEqual(added, ["from shop.billing import Receipt"])

    def test_auto_import_skips_if_already_imported(self):
        setup = "from shop.billing import charge, Receipt\n"
        self.assertTrue(already_imported(setup, "shop.billing", "charge"))
        new, added = apply_auto_imports(setup, [("shop.billing", "charge")])
        self.assertEqual(added, [])
        self.assertEqual(new, setup)

    def test_create_prepends_target_import_and_reports_it(self):
        tmp = tempfile.mkdtemp(prefix="dc-auto-")
        root = os.path.join(tmp, "shop")
        try:
            shutil.copytree(FIXTURE, root)
            git_init(root)
            e = Engine(root, typecheck="off", refresh_interval=0, probe_timeout=1.0)
            probe = {
                "id": "zero",
                "setup": (
                    "from decimal import Decimal\n"
                    "from shop.models import User\n"
                    "user = User('a', 'AU')\n"
                ),
                "call": "validate_amount(Decimal(0))",
                "expect_new": {"raises": "ValueError"},
            }
            r = e.create_contract(
                "Reject zero charges", ["billing.validate_amount"], [probe], [])
            self.assertTrue(r.ok, r.report)
            self.assertIn("from shop.billing import validate_amount", r.report)
            self.assertIn("auto-imported:", r.report)
            setup = r.contract.must_change[0].setup
            self.assertTrue(setup.startswith("from shop.billing import validate_amount\n"))
            e.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_short_ids_three_words_plus_hash(self):
        cid = allocate_id("/tmp/dc-no-contracts-xyz", "Reject zero-dollar charges in shop billing")
        parts = cid.split("-")
        self.assertRegex(parts[-1], r"^[a-f0-9]{4}$")
        self.assertEqual(len(parts[-1]), 4)
        self.assertLessEqual(len(parts) - 1, 3)
        self.assertTrue(cid.startswith("reject-zero"))

    def test_create_description_has_complete_example(self):
        from dc_engine.catalog import word_count
        self.assertIn("must_change", CREATE_CONTRACT_DESCRIPTION)
        self.assertIn("must_preserve", CREATE_CONTRACT_DESCRIPTION)
        self.assertIn("expect_old", CREATE_CONTRACT_DESCRIPTION)
        self.assertIn("expect_new", CREATE_CONTRACT_DESCRIPTION)
        self.assertIn('"raises"', CREATE_CONTRACT_DESCRIPTION)
        self.assertIn('"returns"', CREATE_CONTRACT_DESCRIPTION)
        self.assertNotIn("shop.billing.validate_amount", CREATE_CONTRACT_DESCRIPTION)
        self.assertEqual(CREATE_CONTRACT_EXAMPLE["targets"][0], "shop.billing.validate_amount")
        self.assertIn("task", CREATE_CONTRACT_EXAMPLE)
        self.assertIn("targets", CREATE_CONTRACT_EXAMPLE)
        self.assertIn("dc_start", INSTRUCTIONS)
        self.assertIn("FIRST", INSTRUCTIONS)
        self.assertIn("exact current source", INSTRUCTIONS)
        self.assertIn("contract status", INSTRUCTIONS)
        self.assertLessEqual(word_count(INSTRUCTIONS), 120)

    def test_rejected_contract_includes_corrected_example(self):
        tmp = tempfile.mkdtemp(prefix="dc-ex-")
        root = os.path.join(tmp, "shop")
        try:
            shutil.copytree(FIXTURE, root)
            git_init(root)
            e = Engine(root, typecheck="off", refresh_interval=0, probe_timeout=1.0)
            r = e.create_contract("x", ["charg"], [ZERO_PROBE], [])
            self.assertFalse(r.ok)
            self.assertIn("Corrected example", r.report)
            self.assertIn('"task"', r.report)
            self.assertIn("expect_new", r.report)
            e.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


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


def _clean_probe_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("DC_PROBE_PYTHON", "VIRTUAL_ENV")}
    env.update(extra)
    return env


def _fake_venv(path: str) -> str:
    if os.name == "nt":
        bindir = os.path.join(path, "Scripts")
        py = os.path.join(bindir, "python.exe")
    else:
        bindir = os.path.join(path, "bin")
        py = os.path.join(bindir, "python")
    os.makedirs(bindir, exist_ok=True)
    with open(py, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\n")
    os.chmod(py, 0o755)
    return py


class ProbePythonTests(unittest.TestCase):
    def test_dc_probe_python_wins(self):
        tmp = tempfile.mkdtemp(prefix="dc-py-env-")
        try:
            chosen = _fake_venv(os.path.join(tmp, "chosen"))
            other = _fake_venv(os.path.join(tmp, "other"))
            root = os.path.join(tmp, "repo")
            _fake_venv(os.path.join(root, ".venv"))
            got = probe_python(root, env=_clean_probe_env(
                DC_PROBE_PYTHON=chosen, VIRTUAL_ENV=os.path.join(tmp, "other"),
            ))
            self.assertEqual(got, chosen)
            self.assertNotEqual(got, other)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_virtual_env_wins_over_repo_venv(self):
        tmp = tempfile.mkdtemp(prefix="dc-py-venv-")
        try:
            active = _fake_venv(os.path.join(tmp, "active"))
            root = os.path.join(tmp, "repo")
            _fake_venv(os.path.join(root, ".venv"))
            got = probe_python(root, env=_clean_probe_env(
                VIRTUAL_ENV=os.path.join(tmp, "active"),
            ))
            self.assertEqual(got, active)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_repo_dot_venv_before_venv(self):
        tmp = tempfile.mkdtemp(prefix="dc-py-dot-")
        try:
            root = os.path.join(tmp, "repo")
            dot = _fake_venv(os.path.join(root, ".venv"))
            _fake_venv(os.path.join(root, "venv"))
            got = probe_python(root, env=_clean_probe_env())
            self.assertEqual(got, dot)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_repo_venv_directory(self):
        tmp = tempfile.mkdtemp(prefix="dc-py-plain-")
        try:
            root = os.path.join(tmp, "repo")
            plain = _fake_venv(os.path.join(root, "venv"))
            got = probe_python(root, env=_clean_probe_env())
            self.assertEqual(got, plain)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sys_executable_fallback(self):
        tmp = tempfile.mkdtemp(prefix="dc-py-sys-")
        try:
            got = probe_python(tmp, env=_clean_probe_env())
            self.assertEqual(got, sys.executable)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_create_records_probe_python(self):
        tmp = tempfile.mkdtemp(prefix="dc-py-rec-")
        root = os.path.join(tmp, "shop")
        try:
            shutil.copytree(FIXTURE, root)
            git_init(root)
            e = Engine(root, typecheck="off", refresh_interval=0, probe_timeout=1.0)
            r = e.create_contract(
                "zero charge", ["billing.validate_amount"], [ZERO_PROBE], [])
            self.assertTrue(r.ok, r.report)
            py = probe_python(root)
            self.assertIn("probe python:", r.report)
            self.assertIn(py, r.report)
            saved = load_contract(root, r.contract_id)
            self.assertIsNotNone(saved)
            self.assertEqual(saved.probe_python, py)
            e.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_probe_imports_package_only_in_temp_venv(self):
        tmp = tempfile.mkdtemp(prefix="dc-py-pkg-")
        try:
            venv = os.path.join(tmp, "venv")
            subprocess.run(
                [sys.executable, "-m", "venv", venv],
                check=True, capture_output=True, timeout=60,
            )
            py = venv_python(venv)
            self.assertTrue(py and os.path.isfile(py), py)
            loc = subprocess.run(
                [py, "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                check=True, capture_output=True, text=True, timeout=15,
            )
            site = loc.stdout.strip()
            self.assertTrue(os.path.isdir(site), site)
            with open(os.path.join(site, "dc_probe_only_pkg.py"), "w", encoding="utf-8") as fh:
                fh.write("MARKER = 'from-venv'\n")
            missing = subprocess.run(
                [sys.executable, "-c", "import dc_probe_only_pkg"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(missing.returncode, 0)
            tree = os.path.join(tmp, "tree")
            os.makedirs(tree)
            probe = Probe(
                id="pkg",
                setup="import dc_probe_only_pkg",
                call="dc_probe_only_pkg.MARKER",
            )
            with patch.dict(os.environ, {"DC_PROBE_PYTHON": py}):
                result = run_probe(tree, probe, timeout=5)
            self.assertEqual(result.kind, "return", result.display())
            self.assertEqual(result.value, "'from-venv'")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class SlimToolTests(unittest.TestCase):
    typecheck = "off"

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dc-slim-")
        self.root = os.path.join(self.tmp, "shop")
        shutil.copytree(FIXTURE, self.root)
        git_init(self.root)
        self.e = Engine(self.root, typecheck=self.typecheck, refresh_interval=0,
                        probe_timeout=1.0)

    def tearDown(self) -> None:
        self.e.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_slim_names_and_full_superset(self):
        from dc_engine.catalog import SLIM_NAMES
        from dc_engine.server import dump_catalog, make_tool_functions
        slim = [f.__name__ for f in make_tool_functions(self.e, "slim")]
        self.assertEqual(slim, list(SLIM_NAMES))
        full = [f.__name__ for f in make_tool_functions(self.e, "full")]
        for name in SLIM_NAMES:
            self.assertIn(name, full)
        self.assertIn("dc_create_contract", full)
        self.assertIn("dc_get_slice", full)
        self.assertIn("dc_insert_symbol", full)
        slim_cat = dump_catalog("slim")
        full_cat = dump_catalog("full")
        self.assertEqual(slim_cat["tool_count"], 5)
        self.assertGreater(full_cat["tool_count"], 5)
        self.assertLess(slim_cat["chars"], full_cat["chars"])
        blob = "\n".join(t["description"] for t in slim_cat["tools"])
        self.assertNotIn("shop.billing.validate_amount", blob)
        self.assertLessEqual(slim_cat["instructions_words"], 120)
        names = [t["name"] for t in slim_cat["tools"]]
        self.assertEqual(names, list(SLIM_NAMES))
        schema = next(t["input_schema"] for t in slim_cat["tools"] if t["name"] == "dc_contract")
        self.assertIn("action", schema.get("required") or [])
        self.assertEqual(schema["properties"]["action"]["type"], "string")
        self.assertEqual(schema["properties"]["targets"]["type"], "array")
        start_s = next(t["input_schema"] for t in slim_cat["tools"] if t["name"] == "dc_start")
        self.assertEqual(start_s["properties"]["max_tokens"]["type"], "integer")
        self.assertEqual(start_s["properties"]["hint_symbols"]["type"], "array")
        from dc_engine.catalog import CONTRACTS_NAMES
        from dc_engine.server import INSTRUCTIONS_OPTIONAL
        contracts = [f.__name__ for f in make_tool_functions(self.e, "contracts")]
        self.assertEqual(contracts, list(CONTRACTS_NAMES))
        ccat = dump_catalog("contracts")
        self.assertEqual(ccat["tool_count"], 2)
        self.assertEqual([t["name"] for t in ccat["tools"]], list(CONTRACTS_NAMES))
        self.assertNotIn("dc_start", [t["name"] for t in ccat["tools"]])
        self.assertIn("Read and Grep", ccat["instructions"])
        self.assertIn("never required", INSTRUCTIONS_OPTIONAL)
        cdesc = next(t["description"] for t in ccat["tools"] if t["name"] == "dc_contract")
        self.assertIn("shop.billing.validate_amount", cdesc)
        self.assertIn('"action":"create"', cdesc)
        self.assertNotIn("dc_start", cdesc)
        self.assertNotIn("dc_start", ccat["instructions"])
        sdesc = next(t["description"] for t in slim_cat["tools"] if t["name"] == "dc_contract")
        self.assertIn("dc_start", sdesc)
        self.assertNotIn("shop.billing.validate_amount", sdesc)

    def test_mode_texts_only_name_exposed_tools(self):
        import re
        from dc_engine.catalog import TOOL_MODES
        from dc_engine.server import dump_catalog
        catalogs = {mode: dump_catalog(mode) for mode in TOOL_MODES}
        universe = set()
        for cat in catalogs.values():
            universe.update(t["name"] for t in cat["tools"])
        pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(n) for n in sorted(universe, key=len, reverse=True)) + r")\b"
        )
        for mode, cat in catalogs.items():
            exposed = {t["name"] for t in cat["tools"]}
            blobs = [cat.get("instructions") or ""]
            blobs.extend(t.get("description") or "" for t in cat["tools"])
            for blob in blobs:
                for name in pattern.findall(blob):
                    self.assertIn(
                        name, exposed,
                        f"{mode} text names {name!r} which is not in that mode's tools",
                    )

    def test_dc_contract_and_dc_find(self):
        from dc_engine.server import make_tool_functions
        fns = {f.__name__: f for f in make_tool_functions(self.e, "slim")}
        created = fns["dc_contract"](
            action="create",
            task="charge(user, Decimal(0)) should raise ValueError",
            targets=["billing.validate_amount"],
            must_change=[ZERO_PROBE],
            must_preserve=[PREVIEW_PROBE],
        )
        self.assertTrue(created.startswith("✓ contract created:"), created)
        cid = created.split(":", 1)[1].strip().split()[0]
        checked = fns["dc_contract"](action="check", contract_id=cid)
        self.assertIn("not changed", checked)
        self.assertIn("unknown action", fns["dc_contract"](action="nope"))
        hits = fns["dc_find"]("charge")
        self.assertIn("shop.billing.charge", hits)
        refs = fns["dc_find"]("billing.charge", mode="references")
        self.assertTrue(refs.strip(), refs)


if __name__ == "__main__":
    unittest.main()
