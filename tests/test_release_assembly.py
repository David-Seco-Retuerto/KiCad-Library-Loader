"""Release assembly preserves runtime bytes, source coverage and Linux links."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

RECIPE = Path(__file__).resolve().parents[1] / "tools/prepare_release.py"
if not RECIPE.is_file(): RECIPE = Path(__file__).resolve().parents[1] / "prepare_release.py"
SPEC = importlib.util.spec_from_file_location("release_assembly_test", RECIPE)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
VERSION = "0.1.0-alpha.1"
PREFIX = "KiCad-Library-Loader"


def source_archive(extra=None):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, data in {"LICENSE": b"synthetic application licence", "scripts/app.py": b"print('synthetic source')", **(extra or {})}.items():
            info = tarfile.TarInfo(PREFIX + "-" + VERSION + "/" + name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return stream.getvalue()


class ReleaseAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.application = source_archive()
        self.windows = self.root / f"{PREFIX}-{VERSION}-windows-x86_64.zip"
        self.linux = self.root / f"{PREFIX}-{VERSION}-linux-x86_64.tar.gz"
        self.output = self.root / "release"
        self.candidate(self.windows, True)
        self.candidate(self.linux, False)

    def candidate(self, path, windows, app=None, invalid_hash=False, extra=None, unsafe_link=False):
        native, converter = b"synthetic OCCT source archive", b"synthetic converter source archive"
        notice = "licenses/runtime/converter/converter-1.0.dist-info/licenses/LICENSE"
        source = {"archive": "occt.tar.gz", "sha256": hashlib.sha256(native).hexdigest()}
        record = {"filename": "converter.tar.gz", "sha256": "0"*64 if invalid_hash else hashlib.sha256(converter).hexdigest()}
        files = {"LICENSE": b"synthetic application licence", "AUTHORS.md": b"Synthetic author",
                 "README.md": b"Developer instructions", "THIRD_PARTY_NOTICES.md": b"Original attribution\r\n",
                 "RELEASE_STATUS.txt": b"old candidate status", "docs/development.md": b"developer document",
                 f"{PREFIX}-{VERSION}-source.tar.gz": self.application if app is None else app,
                 "dependency-sources/SOURCE.json": json.dumps({"sources": [record]}).encode(),
                 "dependency-sources/occt.tar.gz": native, "dependency-sources/converter.tar.gz": converter,
                 "licenses/native-step/BUILD_PROVENANCE.json": json.dumps({"source": source}).encode(),
                 notice: b"original licence bytes\r\n", "licenses/upstream/LICENSE": b"upstream no-extension notice",
                 "DEPENDENCIES.json": json.dumps([{"notice_files": [notice]}]).encode(),
                 "NATIVE_DEPENDENCIES.json": b"{}", "_internal/library.bin": b"synthetic dependency bytes",
                 PREFIX + (".exe" if windows else ""): b"synthetic main executable",
                 "kicad-loader-worker" + (".exe" if windows else ""): b"synthetic worker", **(extra or {})}
        if windows:
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in files.items(): archive.writestr(PREFIX + "/" + name, data)
        else:
            with tarfile.open(path, "w:gz") as archive:
                for name, data in files.items():
                    info = tarfile.TarInfo(PREFIX + "/" + name)
                    info.size, info.mode = len(data), 0o755 if name in (PREFIX, "kicad-loader-worker") else 0o644
                    archive.addfile(info, io.BytesIO(data))
                link = tarfile.TarInfo(PREFIX + "/_internal/library.so")
                link.type, link.linkname = tarfile.SYMTYPE, "/outside" if unsafe_link else "library.bin"
                archive.addfile(link)

    def test_clean_pair_has_four_assets_and_preserves_runtime_sources_licences_and_links(self):
        review = release.prepare(self.windows, self.linux, self.output)
        self.assertTrue(review["runtime_unchanged"])
        assets = self.output / "assets"
        self.assertEqual(len(list(assets.iterdir())), 4)
        with zipfile.ZipFile(assets / self.windows.name) as archive:
            names = archive.namelist()
            self.assertEqual(archive.read(PREFIX + "/" + PREFIX + ".exe"), b"synthetic main executable")
            self.assertFalse(any("dependency-sources/" in name or "/docs/" in name or "-source.tar.gz" in name or "dist-info" in name for name in names))
            notice = PREFIX + "/licenses/runtime/converter/LICENSE"
            self.assertEqual(archive.read(notice), b"original licence bytes\r\n")
            metadata = json.loads(archive.read(PREFIX + "/metadata/DEPENDENCIES.json"))
            self.assertEqual(metadata[0]["notice_files"], ["licenses/runtime/converter/LICENSE"])
            self.assertIn("source-complete.tar.gz", archive.read(PREFIX + "/SOURCE.txt").decode())
        with tarfile.open(assets / self.linux.name) as archive:
            self.assertEqual(archive.getmember(PREFIX + "/" + PREFIX).mode, 0o755)
            self.assertEqual(archive.getmember(PREFIX + "/_internal/library.so").linkname, "library.bin")
        with tarfile.open(next(assets.glob('*source-complete.tar.gz'))) as archive:
            names = archive.getnames()
            root = names[0].split('/')[0]
            self.assertIn(root + "/app/scripts/app.py", names)
            self.assertIn(root + "/provenance/windows-x86_64/licenses/upstream/LICENSE", names)
            self.assertIn(root + "/release-tools/prepare_release.py", names)
            self.assertEqual(len([n for n in names if n.endswith('/occt.tar.gz')]), 1)
        for line in (assets / "SHA256SUMS").read_text().splitlines():
            expected, name = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((assets / name).read_bytes()).hexdigest(), expected)

    def test_existing_destination_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(FileExistsError): release.prepare(self.windows, self.linux, self.output)
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_mismatched_application_sources_cannot_produce_checksums(self):
        self.candidate(self.linux, False, app=source_archive({"extra.py": b"different"}))
        with self.assertRaisesRegex(ValueError, "source archives differ"):
            release.prepare(self.windows, self.linux, self.output)
        self.assertFalse((self.output / "assets/SHA256SUMS").exists())

    def test_dependency_hash_mismatch_cannot_produce_checksums(self):
        self.candidate(self.windows, True, invalid_hash=True)
        with self.assertRaisesRegex(ValueError, "source hash mismatch"):
            release.prepare(self.windows, self.linux, self.output)
        self.assertFalse((self.output / "assets/SHA256SUMS").exists())

    def test_private_inputs_are_rejected(self):
        self.candidate(self.windows, True, extra={"data/settings.json": b"private"})
        with self.assertRaisesRegex(ValueError, "private candidate path"):
            release.prepare(self.windows, self.linux, self.output)

    def test_unsafe_linux_link_is_rejected(self):
        self.candidate(self.linux, False, unsafe_link=True)
        with self.assertRaisesRegex(ValueError, "link escapes"):
            release.prepare(self.windows, self.linux, self.output)

    def test_private_application_source_is_rejected(self):
        bad = source_archive({"AGENTS.md": b"private instruction"})
        self.candidate(self.windows, True, app=bad)
        self.candidate(self.linux, False, app=bad)
        with self.assertRaisesRegex(ValueError, "Unsafe application source"):
            release.prepare(self.windows, self.linux, self.output)
        self.assertFalse((self.output / "assets/SHA256SUMS").exists())
