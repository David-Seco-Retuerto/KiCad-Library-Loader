"""Release-content boundary checks use synthetic archives, never provider files."""
import hashlib
import io
import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location("release_audit_tests", Path(__file__).resolve().parents[1] / "tools/release_audit.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class ReleaseAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()

    def zip(self, files):
        path = self.folder / "release.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            for name, value in files.items():
                bundle.writestr(name, value)
        return path

    def test_source_with_licence_is_checked_without_claiming_binary_readiness(self):
        report = audit.inspect_archive(self.zip({"Loader/LICENSE": "synthetic licence", "Loader/scripts/main.py": "print(1)"}), source=True)
        self.assertTrue(report["content_checks_passed"])
        self.assertFalse(report["release_ready"])
        self.assertIsNone(report["native_licence_review_complete"])

    def test_native_hash_and_family_are_evidence_not_licence_approval(self):
        data = b"MZsynthetic native file"
        report = audit.inspect_archive(self.zip({"Loader/_internal/cadquery_ocp_novtk.libs/TKMesh-abcd.dll": data}))
        record, = report["native_files"]
        self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(record["component_hint"], "Open CASCADE Technology")
        self.assertEqual(record["review_status"], "unverified")
        self.assertFalse(report["native_licence_review_complete"])

    def test_private_preferences_and_vendor_output_fail_content_checks(self):
        for name in (".kicad-importer.json", "AGENTS.md", ".git/config", "Imports/example.kicad_sym", "data/settings"):
            with self.subTest(name=name):
                report = audit.inspect_archive(self.zip({"Loader/LICENSE": "licence", "Loader/" + name: "private"}), source=True)
                self.assertFalse(report["content_checks_passed"])
                self.assertIn("Loader/" + name, report["private_paths"])

    def test_unsafe_archive_paths_are_rejected_without_extraction(self):
        for name in ("../outside", "/absolute", "Loader/../outside", "C:/absolute", "Loader\\outside"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.safe_name(name)
        self.assertFalse((self.folder / "outside").exists())

    def test_native_file_in_source_is_rejected_regardless_of_extension(self):
        report = audit.inspect_archive(self.zip({"Loader/LICENSE": "licence", "Loader/scripts/disguised.txt": b"\x7fELFfake"}), source=True)
        self.assertFalse(report["content_checks_passed"])
        self.assertEqual(len(report["native_files"]), 1)

    def test_multiple_roots_and_missing_licence_are_rejected(self):
        report = audit.inspect_archive(self.zip({"one/script.py": "", "two/script.py": ""}), source=True)
        self.assertFalse(report["content_checks_passed"])
        self.assertEqual(len(report["errors"]), 2)

    def test_tar_links_are_recorded_and_rejected_for_source(self):
        path = self.folder / "source.tar.gz"
        with tarfile.open(path, "w:gz") as bundle:
            info = tarfile.TarInfo("Loader/LICENSE")
            info.size = 7
            bundle.addfile(info, io.BytesIO(b"licence"))
            info = tarfile.TarInfo("Loader/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "../../private"
            bundle.addfile(info)
        report = audit.inspect_archive(path, source=True)
        self.assertFalse(report["content_checks_passed"])
        self.assertEqual(report["link_members"], ["Loader/link"])

    def test_linux_runtime_and_binding_families_are_distinguished(self):
        for name, expected in (("_internal/libtk8.6.so", "Tcl / Tk / BLT"),
                               ("_internal/libTKMesh-a.so.7.9.3", "Open CASCADE Technology"),
                               ("_internal/OCP/OCP.so", "OCP bindings (including statically linked code)"),
                               ("_internal/libunknown.so", "Unidentified native component")):
            self.assertEqual(audit.component_hint(name), expected)

    def test_source_delivery_refuses_to_replace_an_existing_directory(self):
        import sys
        tools = str(Path(__file__).resolve().parents[1] / "tools")
        sys.path.insert(0, tools)
        import source_release
        with self.assertRaises(FileExistsError):
            source_release.prepare(self.folder)

    def test_source_delivery_records_audit_and_matching_checksum(self):
        import sys
        from unittest.mock import patch
        tools = str(Path(__file__).resolve().parents[1] / "tools")
        sys.path.insert(0, tools)
        import source_release
        def archive(path):
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr("Loader/LICENSE", "synthetic licence")
                bundle.writestr("Loader/scripts/app.py", "# synthetic source")
        with patch.object(source_release, "source_archive", side_effect=archive):
            result = source_release.prepare(self.folder / "delivery")
        digest = hashlib.sha256(result.read_bytes()).hexdigest()
        self.assertEqual((result.parent / "SHA256SUMS").read_text(), digest + "  " + result.name + "\n")
        import json
        self.assertTrue(json.loads((result.parent / "source-content-audit.json").read_text())["content_checks_passed"])

    def test_failed_source_delivery_does_not_emit_success_checksums(self):
        import sys
        from unittest.mock import patch
        tools = str(Path(__file__).resolve().parents[1] / "tools")
        sys.path.insert(0, tools)
        import source_release
        def archive(path):
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr("Loader/.kicad-importer.json", "private")
        with patch.object(source_release, "source_archive", side_effect=archive), self.assertRaises(ValueError):
            source_release.prepare(self.folder / "failed-delivery")
        self.assertFalse((self.folder / "failed-delivery/SHA256SUMS").exists())

    def test_source_member_order_uses_portable_case_sensitive_names(self):
        import sys
        from unittest.mock import patch
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        import build_portable
        (self.folder / "licenses").mkdir()
        for name in ("OCCT-exception.txt", "OCCT-LGPL.txt", "OCP.txt", "ocp-build.txt"):
            (self.folder / "licenses" / name).write_text("synthetic notice")
        with patch.object(build_portable, "ROOT", self.folder), patch.object(build_portable, "SOURCE_DIRS", ("licenses",)), patch.object(build_portable, "SOURCE_FILES", ()):
            names = [p.name for p in build_portable.source_files()]
        self.assertEqual(names, ["OCCT-LGPL.txt", "OCCT-exception.txt", "OCP.txt", "ocp-build.txt"])
