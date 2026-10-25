"""SDK packaging checks bind source hashes/platform and exclude build files."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("native_sdk_tests", Path(__file__).resolve().parents[1] / "tools/native_sdk.py")
sdk_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sdk_module)


class NativeSdkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "native").mkdir()
        self.sdk = self.root / "sdk"
        (self.sdk / "bin").mkdir(parents=True)
        (self.sdk / "lib").mkdir()
        data = b"synthetic upstream source archive"
        self.lock = {"archive":"occt.tar.gz", "sha256":hashlib.sha256(data).hexdigest()}
        (self.root / "native/occt-source.json").write_text(json.dumps(self.lock))
        (self.sdk / "occt.tar.gz").write_bytes(data)
        target = ("windows" if os.name == "nt" else "linux") + "-" + platform.machine().lower().replace("amd64", "x86_64")
        self.provenance = {"target":target,"source":self.lock}
        self.save_manifest()
        self.helper = "kicad-step-mesher.exe" if os.name == "nt" else "kicad-step-mesher"
        (self.sdk / "bin" / self.helper).write_bytes(b"synthetic helper")
        (self.sdk / "lib/unused.lib").write_bytes(b"build only")
        (self.sdk / "lib/libTKExample.so.7.9").write_bytes(b"synthetic runtime")
        for name in ("LICENSE_LGPL_21.txt", "OCCT_LGPL_EXCEPTION.txt"):
            (self.sdk / name).write_text("synthetic licence")
        self.bundle = self.root / "bundle"
        (self.bundle / "dependency-sources").mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.object(sdk_module, "ROOT", self.root).start()

    def save_manifest(self):
        (self.sdk / "BUILD_PROVENANCE.json").write_text(json.dumps(self.provenance))

    def test_runtime_source_and_licences_are_copied_without_static_build_libraries(self):
        sdk_module.copy_sdk(self.sdk, self.bundle)
        self.assertTrue((self.bundle / "_internal/step-reader/bin" / self.helper).is_file())
        self.assertTrue((self.bundle / "_internal/step-reader/lib/libTKExample.so.7.9").is_file())
        self.assertFalse((self.bundle / "_internal/step-reader/lib/unused.lib").exists())
        self.assertEqual((self.bundle / "dependency-sources/occt.tar.gz").read_bytes(), b"synthetic upstream source archive")
        self.assertTrue((self.bundle / "licenses/native-step/OCCT_LGPL_EXCEPTION.txt").is_file())

    def test_original_microsoft_notice_format_and_provenance_are_packaged(self):
        data = b"{\\rtf1 Synthetic original notice}"
        (self.sdk / "MICROSOFT-THIRD-PARTY-NOTICES.rtf").write_bytes(data)
        (self.sdk / "WINDOWS-RUNTIME.json").write_text('{"synthetic":true}')
        sdk_module.copy_sdk(self.sdk, self.bundle)
        notices = self.bundle / "licenses/native-step"
        self.assertEqual((notices / "MICROSOFT-THIRD-PARTY-NOTICES.rtf").read_bytes(), data)
        self.assertTrue((notices / "WINDOWS-RUNTIME.json").is_file())
        self.assertFalse((notices / "MICROSOFT-THIRD-PARTY-NOTICES.txt").exists())

    def test_wrong_source_hash_is_rejected_before_runtime_copy(self):
        (self.sdk / "occt.tar.gz").write_bytes(b"changed source")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            sdk_module.copy_sdk(self.sdk, self.bundle)
        self.assertFalse((self.bundle / "_internal").exists())

    def test_wrong_platform_is_rejected_before_runtime_copy(self):
        self.provenance["target"] = "other-platform"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "platform/source"):
            sdk_module.copy_sdk(self.sdk, self.bundle)
        self.assertFalse((self.bundle / "_internal").exists())
