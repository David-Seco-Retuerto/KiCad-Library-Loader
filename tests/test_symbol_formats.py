"""Output-layout, coexistence and compatibility regressions (synthetic inputs)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from library_core import (ImportErrorDetail, build_plan, child, children, commit_plan,
                          dump, prop, read_tree, set_prop)
import test_importer as fixtures
from test_importer import SYMBOL, FOOTPRINT


class SymbolFormatTests(unittest.TestCase):
    setUp = fixtures.ImportTests.setUp
    refresh = fixtures.ImportTests.refresh
    plan = fixtures.ImportTests.plan

    @property
    def packed(self):
        return self.repo / "Symbols/DVL_ICs.kicad_sym"

    @property
    def unpacked(self):
        return self.repo / "Symbols/DVL_ICs.kicad_symdir"

    def test_default_is_genuine_single_symbol_unpacked_library(self):
        plan = build_plan(self.repo, self.inv, self.key, self.fkey, self.mkey, "ICs", "Suggestion")
        commit_plan(self.repo, plan)
        self.assertFalse(self.packed.exists())
        files = list(self.unpacked.glob("*.kicad_sym"))
        self.assertEqual([p.name for p in files], ["TEST123.kicad_sym"])
        tree = read_tree(files[0])
        self.assertEqual(tree[0], "kicad_symbol_lib")
        self.assertEqual(child(tree, "version"), child(read_tree(self.sym), "version"))
        symbols = children(tree, "symbol")
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0][1], "TEST123")
        self.assertEqual(children(symbols[0], "symbol"), children(self.inv.symbols[self.key].node, "symbol"))
        self.assertTrue(prop(symbols[0], "Footprint").startswith("DVL_ICs:"))
        self.assertTrue(any(f"Register symbol folder in KiCad: {self.unpacked}" == item for item in plan.info))

    def test_add_unpacked_symbol_leaves_previous_file_untouched(self):
        commit_plan(self.repo, self.plan(symbol_format="unpacked"))
        first = self.unpacked / "TEST123.kicad_sym"
        old = first.read_bytes()
        self.sym.write_text(SYMBOL.replace("TEST123", "TEST456"), encoding="utf-8")
        self.refresh()
        commit_plan(self.repo, self.plan(symbol_format="unpacked"))
        self.assertEqual(first.read_bytes(), old)
        self.assertTrue((self.unpacked / "TEST456.kicad_sym").exists())
        self.assertEqual(len(list(self.unpacked.glob("*.kicad_sym"))), 2)

    def test_duplicate_in_another_filename_is_blocked(self):
        commit_plan(self.repo, self.plan(symbol_format="unpacked"))
        (self.unpacked / "TEST123.kicad_sym").rename(self.unpacked / "other_filename.kicad_sym")
        with self.assertRaisesRegex(ImportErrorDetail, "already exists"):
            self.plan(symbol_format="unpacked")

    def test_unpacking_selection_warns_and_never_updates_packed_counterpart(self):
        commit_plan(self.repo, self.plan(symbol_format="packed"))
        old = self.packed.read_bytes()
        plan = self.plan(symbol_format="unpacked")
        self.assertTrue(any("matching content" in w for w in plan.warnings))
        self.assertTrue(any("Register only one" in w for w in plan.warnings))
        self.assertNotIn(self.packed, plan.files)
        commit_plan(self.repo, plan)
        self.assertEqual(self.packed.read_bytes(), old)

    def test_packing_selection_warns_and_never_updates_unpacked_counterpart(self):
        commit_plan(self.repo, self.plan(symbol_format="unpacked"))
        path = self.unpacked / "TEST123.kicad_sym"
        old = path.read_bytes()
        plan = self.plan(symbol_format="packed")
        self.assertTrue(any("matching content" in w for w in plan.warnings))
        self.assertNotIn(path, plan.files)
        commit_plan(self.repo, plan)
        self.assertEqual(path.read_bytes(), old)
        self.assertTrue(self.packed.is_file())

    def test_different_counterpart_content_is_explicit(self):
        commit_plan(self.repo, self.plan(symbol_format="packed"))
        tree = read_tree(self.packed)
        set_prop(children(tree, "symbol")[0], "Value", "Different metadata")
        self.packed.write_text(dump(tree), encoding="utf-8")
        old = self.packed.read_bytes()
        plan = self.plan(symbol_format="unpacked")
        self.assertTrue(any("different content" in w and "out of sync" in w for w in plan.warnings))
        commit_plan(self.repo, plan)
        self.assertEqual(self.packed.read_bytes(), old)

    def test_unpacked_folder_changes_invalidate_a_plan(self):
        plan = self.plan(symbol_format="unpacked")
        self.unpacked.mkdir(parents=True)
        (self.unpacked / "other.kicad_sym").write_text(SYMBOL.replace("TEST123", "OTHER"), encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "folder changed"):
            commit_plan(self.repo, plan)
        self.assertFalse((self.unpacked / "TEST123.kicad_sym").exists())

    def test_counterpart_added_after_validation_invalidates_plan(self):
        plan = self.plan(symbol_format="unpacked")
        self.packed.parent.mkdir(parents=True)
        self.packed.write_text(SYMBOL, encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "changed since validation"):
            commit_plan(self.repo, plan)

    def test_invalid_format_and_corrupt_selected_library_are_blocked(self):
        with self.assertRaisesRegex(ImportErrorDetail, "output format"):
            self.plan(symbol_format="typo")
        self.unpacked.mkdir(parents=True)
        (self.unpacked / "bad.kicad_sym").write_text("not a library")
        with self.assertRaises(ImportErrorDetail):
            self.plan(symbol_format="unpacked")

    def test_corrupt_counterpart_requires_review_and_is_not_changed(self):
        self.packed.parent.mkdir(parents=True)
        self.packed.write_text("not a library")
        plan = self.plan(symbol_format="unpacked")
        self.assertTrue(any("Could not check the other output format" in w for w in plan.warnings))
        commit_plan(self.repo, plan)
        self.assertEqual(self.packed.read_text(), "not a library")

    def test_future_format_is_not_falsely_downgraded_for_kicad9(self):
        self.sym.write_text(SYMBOL.replace("20220914", "20260101"), encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "no downgrade"):
            self.plan(symbol_format="packed")
        plan = self.plan(symbol_format="unpacked")
        serialized = next(data for p, data in plan.files.items() if p.suffix == ".kicad_sym")
        self.assertIn(b"20260101", serialized)
        self.sym.write_text(SYMBOL, encoding="utf-8")
        self.fp.write_text(FOOTPRINT.replace("20221018", "20260101"), encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "source footprint.*newer"):
            self.plan(symbol_format="packed")


if __name__ == "__main__":
    unittest.main()
