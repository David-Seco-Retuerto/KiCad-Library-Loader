"""Source/frozen paths and worker commands; never resolve a helper through PATH."""
from pathlib import Path
import os
import sys


def frozen():
    return bool(getattr(sys, "frozen", False))


def application_folder():
    return Path(sys.executable).resolve().parent if frozen() else Path(__file__).resolve().parents[1]


def default_workspace():
    return application_folder() / "data" if frozen() else application_folder()


def bundled_worker():
    name = "kicad-loader-worker.exe" if os.name == "nt" else "kicad-loader-worker"
    path = application_folder() / name
    if not path.is_file():
        raise RuntimeError("The portable worker is missing. Extract the complete release archive, including its _internal folder, into a writable directory.")
    return path


def mesh_command(source, output):
    prefix = [str(bundled_worker())] if frozen() else [sys.executable, str(Path(__file__).with_name("step_preview.py"))]
    return [*prefix, "--mesh", str(source), str(output)]
