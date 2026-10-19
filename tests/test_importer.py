"""Synthetic fixtures only. Real vendor libraries must never be committed."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from library_core import (ImportErrorDetail, associate, build_plan, child, children,
                          commit_plan, dump, load_preferences, parse, prop,
                          read_tree, safe_name, save_preferences, scan)

SYMBOL = '''(kicad_symbol_lib (version 20220914) (generator test)
 (symbol "TEST123" (in_bom yes) (on_board yes)
  (property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27))))
  (property "Value" "TEST123" (at 0 0 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "Vendor:GEOM" (at 0 0 0) (effects (font (size 1.27 1.27))))
  (property "Manufacturer_Part_Number" "TEST123")
  (symbol "TEST123_0_1" (rectangle (start -2 -2) (end 2 2) (stroke (width 0) (type default)) (fill (type background))))
  (symbol "TEST123_1_1" (pin passive line (at 0 0 0) (length 2.54) (name "IN" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27))))))
 ))'''
FOOTPRINT = '''(footprint "GEOM" (version 20221018) (generator test) (layer "F.Cu")
 (descr "SOIC 1-pin test")
 (fp_text value "GEOM" (at 0 0) (layer "F.Fab") (effects (font (size 1 1))))
 (pad "1" smd rect (at 0 0 90) (size 1 2) (layers "F.Cu" "F.Paste" "F.Mask"))
 (model "C:\\\\vendor\\\\TEST123.stp" (offset (xyz 1 2 3)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 90))))'''
STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.source = self.repo / "Imports" / "SamacSys"
        self.source.mkdir(parents=True)
        (self.repo / "Imports" / "LCSC").mkdir()
        self.sym = self.source / "parts.kicad_sym"
        self.sym.write_text(SYMBOL, encoding="utf-8")
        self.fp = self.source / "GEOM.kicad_mod"
        self.fp.write_text(FOOTPRINT, encoding="utf-8")
        (self.source / "TEST123.stp").write_bytes(STEP)
        self.refresh()

    def refresh(self):
        self.inv = scan(self.repo, "SamacSys")
        self.key = next(iter(self.inv.symbols))
        self.fkey, self.mkey = associate(self.inv, self.inv.symbols[self.key])

    def plan(self, mode="Suggestion", custom="", **kwargs):
        values = dict(repo=self.repo, inv=self.inv, symbol_key=self.key,
                      fp_key=self.fkey, model_key=self.mkey, category="ICs", mode=mode, custom=custom, symbol_format="packed")
        values.update(kwargs)
        return build_plan(**values)

    def test_round_trip_escaping_and_unknown_attributes(self):
        tree = parse('(root "a\\\\b\\\"c" (unknown yes) "á")')
        self.assertEqual(tree, parse(dump(tree)))
        for invalid in ('(root "oops)', '(root))', '(root) (other)', '"oops', '(root "bad) trailing'):
            with self.assertRaises(ImportErrorDetail):
                parse(invalid)

    def test_association_and_native_import_references(self):
        self.assertEqual((self.fkey, self.mkey), ("GEOM.kicad_mod", "TEST123.stp"))
        before = {p: p.read_bytes() for p in self.source.iterdir()}
        plan = self.plan()
        self.assertFalse(plan.warnings)
        commit_plan(self.repo, plan)
        library = read_tree(self.repo / "Symbols/DVL_ICs.kicad_sym")
        symbol = children(library, "symbol")[0]
        reference = prop(symbol, "Footprint")
        self.assertTrue(reference.startswith("DVL_ICs:TEST123_GEOM_"))
        fp = read_tree(self.repo / "Footprints/DVL_ICs.pretty" / (reference.split(":")[1] + ".kicad_mod"))
        model = child(fp, "model")
        self.assertEqual(child(model, "offset"), parse('(offset (xyz 1 2 3))'))
        self.assertTrue(model[1].startswith("${DVL_LIB_ROOT}/3DModels/ICs/"))
        self.assertEqual(before, {p: p.read_bytes() for p in self.source.iterdir()})
        self.assertFalse(list((self.repo / "Symbols").glob("*.kicad_symdir")))
        with self.assertRaisesRegex(ImportErrorDetail, "already exists"):
            self.plan()

    def test_original_custom_and_bad_windows_names(self):
        self.assertTrue(any(p.name == "GEOM.kicad_mod" for p in self.plan("Original").files))
        self.assertTrue(any(p.name == "My Part.kicad_mod" for p in self.plan("Custom", "My Part").files))
        for name in ("", "../bad", "CON", "NUL.foo", "COM1", "bad:", "bad.", " spaces "):
            with self.assertRaises(ImportErrorDetail):
                safe_name(name)

    def test_no_overwrite_and_identical_reuse(self):
        plan = self.plan()
        target = next(p for p in plan.files if p.suffix == ".stp")
        target.parent.mkdir(parents=True)
        target.write_bytes(b"different")
        with self.assertRaisesRegex(ImportErrorDetail, "Already exists"):
            self.plan()
        target.write_bytes(STEP)
        self.assertNotIn(target, self.plan().files)

    def test_library_append_preserves_previous_symbol(self):
        commit_plan(self.repo, self.plan())
        self.sym.write_text(SYMBOL.replace("TEST123", "TEST456"), encoding="utf-8")
        self.refresh()
        commit_plan(self.repo, self.plan(model_key=""))
        lib = read_tree(self.repo / "Symbols/DVL_ICs.kicad_sym")
        self.assertEqual([n[1] for n in children(lib, "symbol")], ["TEST123", "TEST456"])

    def test_changed_destinations_and_lock(self):
        plan = self.plan()
        path = next(iter(plan.files))
        path.parent.mkdir(parents=True)
        path.write_bytes(b"concurrent")
        with self.assertRaisesRegex(ImportErrorDetail, "changed"):
            commit_plan(self.repo, plan)
        self.assertEqual(path.read_bytes(), b"concurrent")
        (self.repo / ".kicad-importer.lock").write_text("test")
        with self.assertRaisesRegex(ImportErrorDetail, "blocked"):
            commit_plan(self.repo, plan)

    def test_rollback_on_io_error(self):
        plan = self.plan()
        original = Path.open
        def failing_open(path, *args, **kwargs):
            if path.suffix == ".kicad_mod" and args and args[0] == "xb":
                raise OSError("simulated disk failure")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", failing_open):
            with self.assertRaises(OSError):
                commit_plan(self.repo, plan)
        self.assertTrue(all(not p.exists() for p in plan.files))
        self.assertFalse((self.repo / ".kicad-importer.lock").exists())
        self.assertFalse(list(self.repo.rglob("*.import-tmp")))

    def test_empty_lcsc_legacy_and_foreign_formats(self):
        root = self.repo / "Imports/LCSC"
        (root / "legacy.lib").write_text("EESchema-LIBRARY")
        (root / "easyeda.json").write_text("{}")
        inv = scan(self.repo, "LCSC")
        self.assertFalse(inv.symbols)
        self.assertTrue(any("legacy" in n for n in inv.notices))
        self.assertTrue(any("unsupported" in n for n in inv.notices))

    def test_ambiguous_names_do_not_autoassociate(self):
        folder = self.source / "another"
        folder.mkdir()
        (folder / self.fp.name).write_text(FOOTPRINT)
        self.refresh()
        self.assertEqual(self.fkey, "")

    def test_unsupported_inheritance_and_bad_step(self):
        self.sym.write_text(SYMBOL.replace('(in_bom yes)', '(extends "BASE") (in_bom yes)'), encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorDetail, "Inherited"):
            self.plan()
        self.sym.write_text(SYMBOL, encoding="utf-8")
        (self.source / "TEST123.stp").write_bytes(b"not really STEP")
        with self.assertRaisesRegex(ImportErrorDetail, "STEP"):
            self.plan()

    def test_missing_parts_and_pin_mismatch_warn(self):
        plan = self.plan(fp_key="", model_key="")
        self.assertTrue(plan.warnings)
        library = parse(next(iter(plan.files.values())).decode())
        self.assertEqual(prop(children(library, "symbol")[0], "Footprint"), "")
        self.fp.write_text(FOOTPRINT.replace('(pad "1"', '(pad "2"'), encoding="utf-8")
        self.assertTrue(any("Pin/pad" in w for w in self.plan().warnings))

    def test_preferences_round_trip_and_corrupt(self):
        path = self.repo / ".kicad-importer.json"
        prefs = {"mode": "Custom", "custom": "User_name", "source": "LCSC", "category": "Misc"}
        save_preferences(path, prefs)
        self.assertEqual(load_preferences(path), prefs)
        path.write_text("{broken")
        self.assertEqual(load_preferences(path), {})


if __name__ == "__main__":
    unittest.main()
