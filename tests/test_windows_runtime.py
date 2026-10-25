"""Synthetic Visual Studio edition layouts and release-only CRT collection."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("windows_runtime_tests", Path(__file__).resolve().parents[1] / "tools/windows_native_runtime.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class WindowsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def installation(self, edition, notice_path=None):
        visual = self.root / edition
        crt = visual / "VC/Redist/MSVC/14.44.35112/x64/Microsoft.VC143.CRT"
        crt.mkdir(parents=True)
        (crt / "vcruntime140.dll").write_bytes(b"synthetic release runtime")
        debug = visual / "VC/Redist/MSVC/14.44.35112/debug_nonredist/x64/Microsoft.VC143.DebugCRT"
        debug.mkdir(parents=True)
        (debug / "vcruntime140d.dll").write_bytes(b"must never be shipped")
        sdk = self.root / (edition + "-sdk")
        (sdk / "bin").mkdir(parents=True)
        if notice_path:
            notice = visual / notice_path
            notice.parent.mkdir(parents=True, exist_ok=True)
            notice.write_bytes(b"Synthetic original notice.\r\nPreserve these bytes.\r\n")
        return visual, sdk

    def collect(self, visual, sdk):
        with patch.object(runtime.subprocess, "check_output", return_value=str(visual) + "\n"):
            return runtime.copy_runtime(sdk)

    def test_build_tools_and_enterprise_original_notices_are_preserved(self):
        for edition in ("BuildTools", "Enterprise", "Professional", "Community"):
            with self.subTest(edition=edition):
                relative = f"Licenses/{edition}/1033/ThirdPartyNotices.txt"
                visual, sdk = self.installation(edition, relative)
                record = self.collect(visual, sdk)
                self.assertEqual((sdk / "MICROSOFT-THIRD-PARTY-NOTICES.txt").read_bytes(), (visual / relative).read_bytes())
                self.assertEqual(record["notice"]["installed_path"], relative)
                self.assertEqual(record["notice"]["sha256"], hashlib.sha256((visual / relative).read_bytes()).hexdigest())
                self.assertIn(edition, record["origin"])
                self.assertEqual([item["file"] for item in record["files"]], ["vcruntime140.dll"])
                self.assertFalse((sdk / "bin/vcruntime140d.dll").exists())
                self.assertEqual(json.loads((sdk / "WINDOWS-RUNTIME.json").read_text()), record)

    def test_matching_edition_and_english_notice_are_preferred(self):
        visual, sdk = self.installation("Enterprise", "Licenses/Enterprise/1033/ThirdPartyNotices.txt")
        for relative in ("Licenses/BuildTools/1033/ThirdPartyNotices.txt", "Licenses/Enterprise/3082/ThirdPartyNotices.txt"):
            other = visual / relative
            other.parent.mkdir(parents=True)
            other.write_bytes(b"other installed notice")
        record = self.collect(visual, sdk)
        self.assertEqual(record["notice"]["installed_path"], "Licenses/Enterprise/1033/ThirdPartyNotices.txt")

    def test_rtf_notice_keeps_its_format_and_bytes(self):
        visual, sdk = self.installation("Enterprise", "Licenses/Enterprise/1033/ThirdPartyNotices.rtf")
        record = self.collect(visual, sdk)
        self.assertEqual(record["notice"]["file"], "MICROSOFT-THIRD-PARTY-NOTICES.rtf")
        self.assertEqual((sdk / record["notice"]["file"]).read_bytes(), (visual / record["notice"]["installed_path"]).read_bytes())
        self.assertFalse((sdk / "MICROSOFT-THIRD-PARTY-NOTICES.txt").exists())

    def test_root_notice_and_localized_notice_layouts_are_supported(self):
        for edition, relative in (("Enterprise", "ThirdPartyNotices.txt"), ("BuildTools", "Licenses/BuildTools/3082/ThirdPartyNotices.txt")):
            with self.subTest(relative=relative):
                visual, sdk = self.installation(edition, relative)
                self.assertEqual(self.collect(visual, sdk)["notice"]["installed_path"], relative)

    def test_missing_notice_fails_before_any_runtime_is_copied(self):
        visual, sdk = self.installation("Enterprise")
        with self.assertRaisesRegex(RuntimeError, "notice was not found"):
            self.collect(visual, sdk)
        self.assertEqual(list((sdk / "bin").iterdir()), [])
        self.assertFalse((sdk / "WINDOWS-RUNTIME.json").exists())

    def test_debug_runtime_is_not_used_when_release_runtime_is_absent(self):
        visual, sdk = self.installation("BuildTools", "Licenses/BuildTools/1033/ThirdPartyNotices.txt")
        (visual / "VC/Redist/MSVC/14.44.35112/x64/Microsoft.VC143.CRT/vcruntime140.dll").unlink()
        with self.assertRaisesRegex(RuntimeError, "x64 release CRT was not found"):
            self.collect(visual, sdk)
        self.assertEqual(list((sdk / "bin").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
