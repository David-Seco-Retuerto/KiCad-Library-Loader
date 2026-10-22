"""Explicit single-part acquisition via the loader-installed easyeda2kicad CLI or an explicit override."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time

from archive_import import cache_directory, MAX_ENTRIES, MAX_FILE_BYTES, MAX_TOTAL_BYTES
from import_history import ACQUISITION_FILE, file_hash
from library_core import associate, prop, scan_directory


class DownloadCancelled(ValueError):
    pass


@dataclass(frozen=True)
class DownloadResult:
    folder: Path
    lcsc_id: str
    notices: tuple = ()


def lcsc_code(value):
    if not isinstance(value, str) or not re.fullmatch(r"C[1-9][0-9]{0,11}", value.strip(), re.IGNORECASE):
        raise ValueError("Enter one LCSC part code, such as C2040. Choose the exact package on LCSC first.")
    return value.strip().upper()


def converter_path(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Select a valid easyeda2kicad executable for the external override.")
    path = Path(value.strip()).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Choose an existing absolute path to the easyeda2kicad executable.")
    path = path.resolve()
    if os.name == "nt" and path.suffix.lower() != ".exe":
        raise ValueError("On Windows, select Scripts/easyeda2kicad.exe from its environment.")
    return path


def installed_converter(scripts_folder=None):
    """Resolve only the active Python environment, never an unrelated PATH tool."""
    folder = Path(scripts_folder if scripts_folder is not None else sysconfig.get_path("scripts"))
    name = "easyeda2kicad.exe" if os.name == "nt" else "easyeda2kicad"
    path = folder / name
    if not path.is_file():
        raise ValueError("The loader's easyeda2kicad dependency is missing. Update this application's dependencies with:\n"
                         f'"{sys.executable}" -m pip install -r requirements.txt')
    return converter_path(str(path))


def discard_download(folder, workspace):
    """Remove only an owned, unique download run directly under the managed cache."""
    folder = Path(folder)
    run = folder.parent
    cache = cache_directory(workspace)
    if (folder.name != "assets" or run.parent != cache or not run.name.startswith("lcsc-")
            or run.is_symlink() or run.resolve() != run or folder.resolve() != folder):
        raise ValueError("Refusing to remove files outside the managed LCSC cache.")
    shutil.rmtree(run)


def check_run(folder):
    total, count = 0, 0
    for current, directories, names in os.walk(folder, followlinks=False):
        for name in (*directories, *names):
            path = Path(current) / name
            count += 1
            if path.is_symlink() or path.resolve() != path:
                raise ValueError("Converter output contains linked files or folders.")
            if count > MAX_ENTRIES:
                raise ValueError("Converter output contains too many entries.")
            if path.is_file():
                size = path.stat().st_size
                total += size
                if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    raise ValueError("Converter output exceeds the local size limits.")


def stop_process(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def log_tail(path):
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 4096))
        return stream.read().decode("utf-8", errors="replace").strip()


def download_lcsc(workspace, executable, part_code, cancelled=None, timeout=180):
    """Run without a shell or library-output access; return native assets for review.

    The selected executable is trusted external software, not a sandboxed converter.
    Limits bound our waiting and accepted cache output, not the remote HTTP transport.
    """
    code, executable = lcsc_code(part_code), converter_path(executable)
    cancelled = cancelled if cancelled is not None else threading.Event()
    if cancelled.is_set():
        raise DownloadCancelled("Download cancelled. No component was loaded or imported.")
    cache = cache_directory(workspace)
    cache.mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="lcsc-", dir=cache))
    assets = run / "assets"
    assets.mkdir()
    log = run / "converter.log"
    process = None
    try:
        command = [str(executable), "--full", "--lcsc_id", code, "--output", str(assets / "component")]
        deadline = time.monotonic() + timeout
        with log.open("wb") as output:
            process = subprocess.Popen(command, cwd=run, stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=subprocess.STDOUT, shell=False,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            while process.poll() is None:
                if cancelled.is_set():
                    raise DownloadCancelled("Download cancelled. No component was loaded or imported.")
                if time.monotonic() >= deadline:
                    raise ValueError("Download timed out. Check the connection or use Search online and a local export.")
                check_run(run)
                cancelled.wait(0.1)
        if cancelled.is_set():
            raise DownloadCancelled("Download cancelled. No component was loaded or imported.")
        check_run(run)
        if process.returncode != 0:
            raise ValueError("easyeda2kicad failed. Check the part code, network and tool version.\n" + log_tail(log))
        inventory = scan_directory(assets)
        if len(inventory.symbols) != 1 or inventory.notices:
            raise ValueError("The converter did not produce one readable native symbol. " + " ".join(inventory.notices[:5]))
        symbol = next(iter(inventory.symbols.values()))
        if str(prop(symbol.node, "LCSC Part")).upper() != code:
            raise ValueError("The generated symbol does not identify the requested LCSC part. Nothing was loaded.")
        footprint, model = associate(inventory, symbol)
        if not footprint:
            raise ValueError("No unambiguous associated native footprint was generated. Nothing was loaded.")
        notices = () if model else ("No unambiguous STEP model was generated. Review the 3D selection before importing.",)
        version = re.search(r"easyeda2kicad(?:\.py)? v([0-9]+(?:\.[0-9]+){1,3})", log_tail(log))
        metadata = {"schema_version": 1, "provider": "LCSC", "lcsc_id": code,
                    "method": "easyeda2kicad", "tool_version": version.group(1) if version else "unknown",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "files": []}
        for path in sorted(assets.rglob("*")):
            if path.is_file():
                metadata["files"].append({"relative_path": path.relative_to(assets).as_posix(), "sha256": file_hash(path)})
        (assets / ACQUISITION_FILE).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        if cancelled.is_set():
            raise DownloadCancelled("Download cancelled. No component was loaded or imported.")
        return DownloadResult(assets, code, notices)
    except BaseException:
        stop_process(process)
        discard_download(assets, workspace)
        raise
