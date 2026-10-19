"""Extract native assets from local ZIP downloads into a persistent local cache."""
from pathlib import Path, PurePosixPath
import shutil
import json
from import_history import ORIGIN_FILE, file_hash
import stat
import tempfile
import zipfile

from library_layout import validate_segment

MAX_ENTRIES = 5000
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_TOTAL_BYTES = 250 * 1024 * 1024
NATIVE_SUFFIXES = {".kicad_sym", ".kicad_mod", ".stp", ".step"}
METADATA_NAMES = {"license.txt", "licence.txt", "part_info.txt"}


def member_path(info):
    name = info.filename.replace("\\", "/")
    parts = name.rstrip("/").split("/")
    if name.startswith("/") or not all(parts):
        raise ValueError(f"Unsafe archive path: {info.filename}")
    try:
        for part in parts:
            validate_segment(part, maximum=255)
    except ValueError as exc:
        raise ValueError(f"Unsafe archive path: {info.filename}") from exc
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError(f"Archive links are unsupported: {info.filename}")
    return PurePosixPath(*parts)


def cache_directory(workspace):
    workspace = Path(workspace).resolve()
    cache = workspace / ".kicad-importer-cache"
    if cache.is_symlink() or cache.resolve() != cache or not cache.resolve().is_relative_to(workspace):
        raise ValueError("The ZIP cache must be a regular folder inside the settings workspace.")
    if cache.exists() and not cache.is_dir():
        raise ValueError("The ZIP cache path is a file.")
    return cache


def discard_extraction(folder, workspace):
    """Only remove an extraction created directly inside our managed cache."""
    folder = Path(folder)
    cache = cache_directory(workspace)
    if (folder.is_symlink() or folder.parent != cache or not folder.name.startswith("zip-")
            or folder.resolve().parent != cache):
        raise ValueError("Refusing to remove a folder outside the managed ZIP cache.")
    shutil.rmtree(folder)


def extract_native_zip(archive_path, workspace):
    """Never overwrite outputs or execute archive contents. Keep relative asset paths."""
    destination = None
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise ValueError(f"Archive has too many entries (maximum {MAX_ENTRIES}).")
            selected, seen, total = [], set(), 0
            for info in entries:
                path = member_path(info)
                if info.is_dir():
                    continue
                if path.suffix.lower() not in NATIVE_SUFFIXES and path.name.lower() not in METADATA_NAMES:
                    continue
                key = str(path).casefold()
                if key in seen:
                    raise ValueError(f"Duplicate archive asset path: {path}")
                seen.add(key)
                if info.flag_bits & 1:
                    raise ValueError("Encrypted ZIP downloads are unsupported.")
                total += info.file_size
                if info.file_size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    raise ValueError("ZIP assets exceed the extraction size limit (100 MB/file, 250 MB total).")
                selected.append((info, path))
            if not any(path.suffix.lower() == ".kicad_sym" for _, path in selected):
                raise ValueError("No native .kicad_sym symbols found in this ZIP. Legacy .lib and other CAD formats need conversion before loading.")
            cache = cache_directory(workspace)
            cache.mkdir(exist_ok=True)
            destination = Path(tempfile.mkdtemp(prefix="zip-", dir=cache))
            for info, path in selected:
                target = destination.joinpath(*path.parts)
                if not target.resolve().is_relative_to(destination):
                    raise ValueError(f"Archive asset escapes the extraction folder: {path}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    remaining = min(info.file_size, MAX_FILE_BYTES)
                    while True:
                        block = source.read(min(1024 * 1024, remaining + 1))
                        if not block:
                            break
                        remaining -= len(block)
                        if remaining < 0:
                            raise ValueError("An archive asset exceeded its declared size.")
                        output.write(block)
            from library_core import scan_directory
            inventory = scan_directory(destination)
            if not inventory.symbols:
                raise ValueError("No readable native KiCad symbols found. " + "\n".join(inventory.notices[:5]))
            origin = {"archive_path": str(Path(archive_path).resolve()), "archive_sha256": file_hash(archive_path)}
            with (destination / ORIGIN_FILE).open("x", encoding="utf-8") as handle:
                json.dump(origin, handle, ensure_ascii=False, indent=2)
        return destination
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, RuntimeError) as exc:
        if destination is not None:
            discard_extraction(destination, workspace)
        raise ValueError(f"Cannot read ZIP download: {exc}") from exc
    except Exception:
        if destination is not None:
            discard_extraction(destination, workspace)
        raise
