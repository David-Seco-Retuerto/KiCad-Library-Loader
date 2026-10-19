"""Saved KiCad configuration checks use synthetic assets and never edit tables."""
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kicad_diagnostics import diagnose, resolve_uri
from library_core import Atom, build_plan, commit_plan, dump, scan
from loader_settings import LoaderSettings
from import_gui import App
from test_importer import SYMBOL, FOOTPRINT, STEP


def entry(name, uri, kind="KiCad", disabled=False):
    result = [Atom("lib"), [Atom("name"), name], [Atom("type"), kind], [Atom("uri"), str(uri)]]
    if disabled:
        result.append([Atom("disabled")])
    return result


def table(path, kind, entries):
    path.write_text(dump([Atom("sym_lib_table" if kind == "symbol" else "fp_lib_table"), *entries]), encoding="utf-8")


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "library"
        self.workspace.mkdir()
        self.config = self.base / "config/10.0"
        self.config.mkdir(parents=True)
        self.settings = LoaderSettings.defaults(self.workspace)
        self.layout = self.settings.categories[0]
        source = self.settings.sources["SamacSys"]
        source.mkdir(parents=True)
        (source / "parts.kicad_sym").write_text(SYMBOL, encoding="utf-8")
        (source / "GEOM.kicad_mod").write_text(FOOTPRINT, encoding="utf-8")
        (source / "TEST123.stp").write_bytes(STEP)
        inventory = scan(self.workspace, "SamacSys")
        key = next(iter(inventory.symbols))
        plan = build_plan(self.workspace, inventory, key, "GEOM.kicad_mod", "TEST123.stp", "ICs", "Suggestion")
        commit_plan(self.workspace, plan)
        (self.config / "kicad_common.json").write_text(json.dumps({"environment": {"vars": {"DVL_LIB_ROOT": str(self.workspace)}}}), encoding="utf-8")
        table(self.config / "sym-lib-table", "symbol", [entry("DVL_ICs", self.layout.symbol_library(self.workspace, "unpacked"))])
        table(self.config / "fp-lib-table", "footprint", [entry("DVL_ICs", "${DVL_LIB_ROOT}/Footprints/DVL_ICs.pretty")])

    def findings(self, **kwargs):
        return diagnose(self.settings, kwargs.pop("symbol_format", "unpacked"), self.config,
                        category_name="ICs", environment=kwargs.pop("environment", {}), **kwargs)

    def errors(self, **kwargs):
        return [f.detail for f in self.findings(**kwargs) if f.level == "ERROR"]

    def test_valid_registration_references_and_models_leave_all_files_unchanged(self):
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        findings = self.findings()
        self.assertFalse([f for f in findings if f.level == "ERROR"])
        self.assertTrue(any("Assigned footprint exists" in f.detail for f in findings))
        self.assertTrue(any("3D model exists" in f.detail for f in findings))
        self.assertEqual({p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}, before)

    def test_nickname_mismatch_reports_registered_alias_and_missing_reference(self):
        table(self.config / "fp-lib-table", "footprint", [entry("OtherName", self.layout.footprint_library(self.workspace))])
        errors = self.errors()
        self.assertTrue(any("registered as OtherName" in text for text in errors))
        self.assertTrue(any("unregistered nickname" in text for text in errors))
        self.assertTrue(any("DVL_ICs" in text and "Manage" in text for text in errors))

    def test_wrong_registered_path_is_reported(self):
        table(self.config / "fp-lib-table", "footprint", [entry("DVL_ICs", self.base / "wrong.pretty")])
        self.assertTrue(any("Registered path" in text for text in self.errors()))

    def test_missing_and_overridden_model_variable_are_reported(self):
        (self.config / "kicad_common.json").write_text('{"environment":{"vars":null}}', encoding="utf-8")
        self.assertTrue(any("DVL_LIB_ROOT is undefined" in text for text in self.errors()))
        (self.config / "kicad_common.json").write_text(json.dumps({"environment": {"vars": {"DVL_LIB_ROOT": str(self.workspace)}}}), encoding="utf-8")
        self.assertTrue(any("future imports expect" in text for text in self.errors(environment={"DVL_LIB_ROOT": str(self.base / "other")})))

    def test_project_table_overrides_global_and_resolves_kiprjmod(self):
        table(self.config / "fp-lib-table", "footprint", [entry("DVL_ICs", self.base / "wrong.pretty")])
        table(self.workspace / "fp-lib-table", "footprint", [entry("DVL_ICs", "${KIPRJMOD}/Footprints/DVL_ICs.pretty")])
        self.assertFalse(self.errors(project=self.workspace))
        self.assertTrue(self.errors())

    def test_disabled_project_entry_does_not_fall_back_to_global(self):
        table(self.workspace / "fp-lib-table", "footprint", [entry("DVL_ICs", self.layout.footprint_library(self.workspace), disabled=True)])
        self.assertTrue(any("disabled" in text for text in self.errors(project=self.workspace)))

    def test_linked_tables_are_read_and_cycles_are_reported(self):
        linked = self.config / "linked-table"
        table(linked, "footprint", [entry("DVL_ICs", self.layout.footprint_library(self.workspace))])
        table(self.config / "fp-lib-table", "footprint", [entry("Nested", linked, kind="Table")])
        self.assertFalse(self.errors())
        table(linked, "footprint", [entry("Cycle", self.config / "fp-lib-table", kind="Table")])
        self.assertTrue(any("Cyclic" in text for text in self.errors()))

    def test_missing_model_file_and_footprint_file_are_reported(self):
        model = next((self.workspace / "3DModels").rglob("*.stp"))
        model.unlink()
        self.assertTrue(any("3D file not found" in text for text in self.errors()))
        footprint = next(self.layout.footprint_library(self.workspace).glob("*.kicad_mod"))
        footprint.unlink()
        self.assertTrue(any("Footprint" in text and "not found" in text for text in self.errors()))

    def test_wrong_symbol_layout_and_old_kicad_profile_are_reported(self):
        self.assertTrue(any("Registered path" in text for text in self.errors(symbol_format="packed")))
        old = self.config.with_name("9.0")
        self.config.rename(old)
        self.config = old
        self.assertTrue(any("needs KiCad 10+" in text for text in self.errors()))

    def test_malformed_table_and_duplicate_nicknames_are_reported(self):
        (self.config / "fp-lib-table").write_text("broken", encoding="utf-8")
        self.assertTrue(any("Cannot read" in text for text in self.errors()))
        row = entry("DVL_ICs", self.layout.footprint_library(self.workspace))
        table(self.config / "fp-lib-table", "footprint", [row, row])
        self.assertTrue(any("Duplicate nickname" in text for text in self.errors()))

    def test_unresolved_cycles_and_relative_paths_are_not_guessed(self):
        for uri, variables in (("${A}", {"A": "${B}", "B": "${A}"}), ("relative/path", {}), ("${KIPRJMOD}/file", {})):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                resolve_uri(uri, variables)

    def test_gui_reports_selected_category_without_editing_kicad_tables(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            app = App(root, self.workspace)
            before = {p: p.read_bytes() for p in self.config.iterdir() if p.is_file()}
            with patch("diagnostics_dialog.config_folders", return_value=[self.config]):
                dialog = app.check_kicad_setup()
            report = dialog.report.get("1.0", "end")
            self.assertIn("Category: ICs", report)
            self.assertIn("0 error(s)", report)
            self.assertEqual({p: p.read_bytes() for p in self.config.iterdir() if p.is_file()}, before)
            dialog.window.destroy()
        finally:
            root.destroy()
