"""Inspect release contents without extracting or executing them.

Component names are investigation hints, not verified licence determinations.
The tool never promotes a binary to release-ready based on filename matching.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import zipfile

PRIVATE_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                 ".native-build", ".kicad-importer-cache", ".kicad-loader-history", ".kicad-loader-backups", "data"}
PRIVATE_NAMES = {"AGENTS.md", ".kicad-importer.json", ".kicad-importer.json.tmp", ".kicad-importer.lock"}


def safe_name(name):
    # A release archive must contain a single relative, portable path per member.
    path = PurePosixPath(name)
    if not name or name.startswith("/") or "\\" in name or ":" in name or ".." in path.parts:
        raise ValueError("Unsafe archive member: " + name)
    return path


def component_hint(name):
    lower = name.lower()
    base = PurePosixPath(lower).name
    if (base.startswith("tk") and len(base) > 2 and base[2].isalpha()) or (base.startswith("libtk") and "8.6" not in base):
        return "Open CASCADE Technology"
    if "/ocp/" in lower:
        return "OCP bindings (including statically linked code)"
    if base.startswith(("python", "libpython")) or "/lib-dynload/" in lower or base.endswith(".pyd"):
        return "CPython and extension dependencies"
    families = (
        (("freeimage", "libfreeimage"), "FreeImage and image codecs"),
        (("raw-", "libraw"), "LibRaw"),
        (("jbig", "libjbig"), "JBIG-KIT"),
        (("freetype", "libfreetype"), "FreeType"),
        (("fontconfig", "libfontconfig"), "Fontconfig"),
        (("openexr", "iex", "ilmthread", "imath", "libhalf", "libiex", "libilm"), "OpenEXR / Imath"),
        (("tcl", "tk86", "libtcl", "libtk8", "libblt"), "Tcl / Tk / BLT"),
        (("libssl", "libcrypto"), "OpenSSL"),
        (("api-ms-", "ucrtbase", "vcruntime", "vccorlib", "concrt", "msvcp", "vcomp"), "Microsoft runtime"),
        (("libstdc++", "libgcc", "libgomp"), "GCC runtime"),
        (("libx11", "libxau", "libxdmcp", "libxext", "libxft", "libxrender", "libxss"), "X.Org libraries"),
        (("deflate", "libdeflate", "zlib", "libz.", "zstd", "libzstd", "liblzma", "libbz2", "libbrotli"), "Compression libraries"),
        (("jpeg", "libjpeg", "libjxr", "libpng", "lcms", "liblcms", "lerc", "openjp", "libopenjp", "tiff", "libtiff", "libwebp", "libsharpyuv"), "Image codecs"),
        (("libffi", "libexpat", "libbsd", "libmd", "libuuid"), "Other native runtime libraries"),
    )
    for prefixes, label in families:
        if base.startswith(prefixes):
            return label
    if base in {"kicad-step-mesher", "kicad-step-mesher.exe"}:
        return "Loader native STEP helper"
    if base in {"kicad-library-loader", "kicad-library-loader.exe", "kicad-loader-worker", "kicad-loader-worker.exe"}:
        return "Loader and PyInstaller bootloader"
    return "Unidentified native component"


def native_record(name, stream):
    digest = hashlib.sha256()
    prefix = stream.read(4)
    digest.update(prefix)
    size = len(prefix)
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        size += len(block)
        digest.update(block)
    if prefix[:2] != b"MZ" and prefix != b"\x7fELF":
        return None
    return {"path": name, "size": size, "sha256": digest.hexdigest(),
            "component_hint": component_hint(name), "review_status": "unverified"}


def inspect_archive(archive, source=False):
    archive = Path(archive)
    records, private, notices, names, links = [], [], [], [], []
    def inspect(name, stream=None, link=False):
        path = safe_name(name)
        names.append(name)
        relative = path.parts[1:]
        if any(part in PRIVATE_PARTS or part in PRIVATE_NAMES for part in relative):
            private.append(name)
        if source and relative and relative[0] in {"Imports", "Symbols", "Footprints", "3DModels", "build", "dist"}:
            private.append(name)
        if link:
            links.append(name)
        if any(word in path.name.lower() for word in ("license", "copying", "notice", "copyright")):
            notices.append(name)
        if stream is not None:
            record = native_record(name, stream)
            if record:
                records.append(record)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                # Unix symlinks have a special mode in ZIP external attributes.
                link = (member.external_attr >> 16) & 0o170000 == 0o120000
                with bundle.open(member) as stream:
                    inspect(member.filename, stream if not member.is_dir() and not link else None, link)
    else:
        with tarfile.open(archive, "r:*") as bundle:
            for member in bundle:
                if member.isfile():
                    with bundle.extractfile(member) as stream:
                        inspect(member.name, stream)
                elif member.isdir() or member.issym() or member.islnk():
                    inspect(member.name, link=not member.isdir())
                else:
                    raise ValueError("Unsupported archive member: " + member.name)
    roots = {PurePosixPath(name).parts[0] for name in names}
    duplicate_names = [name for name, count in Counter(names).items() if count > 1]
    errors = []
    if len(roots) != 1 or not names:
        errors.append("Expected a single top-level archive directory.")
    if private:
        errors.append("Local/private paths are present.")
    if duplicate_names:
        errors.append("Duplicate archive members are present.")
    if source and (records or links):
        errors.append("Source delivery must not contain native executables or links.")
    if source and not any(name == next(iter(roots), "") + "/LICENSE" for name in names):
        errors.append("Application licence is missing.")
    return {"schema": 1, "archive": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "kind": "application-source" if source else "portable-binary", "content_checks_passed": not errors,
            "errors": errors, "private_paths": sorted(set(private)), "duplicate_members": duplicate_names,
            "native_files": records, "native_families": dict(sorted(Counter(r["component_hint"] for r in records).items())),
            "notice_files": sorted(notices), "link_members": links,
            "native_licence_review_complete": False if records else None,
            "clean_machine_tested": False, "release_ready": False}


def inspect_bundle(folder):
    """Record files as shipped; resolving links must stay inside the bundle."""
    folder = Path(folder).resolve()
    records = []
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            resolved = path.resolve()
            if not resolved.is_relative_to(folder):
                raise ValueError("Bundle link escapes its directory: " + path.name)
            with path.open("rb") as stream:
                record = native_record(path.relative_to(folder).as_posix(), stream)
            if record:
                records.append(record)
    return {"schema": 1, "native_files": records,
            "native_families": dict(sorted(Counter(r["component_hint"] for r in records).items())),
            "native_licence_review_complete": False,
            "note": "Filename-based hints do not establish versions, licences or corresponding-source coverage."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or args.report.resolve() == args.archive.resolve():
        parser.error("Choose a new report path; existing files are never replaced.")
    report = inspect_archive(args.archive, args.source)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.report), "content_checks_passed": report["content_checks_passed"],
                      "native_files": len(report["native_files"]), "release_ready": False}))
    return 0 if report["content_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
