"""Check pinned Windows CPython runtime notices against the build interpreter."""
import hashlib
import json
from pathlib import Path
import platform
import ssl
import tkinter
import zlib

ROOT = Path(__file__).resolve().parents[1]


def verify():
    path = ROOT / "native/windows-python-notices.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    actual = {"openssl": ssl.OPENSSL_VERSION, "zlib": zlib.ZLIB_VERSION, "tcl": tkinter.Tcl().eval("info patchlevel")}
    if platform.python_version() != record["python_version"] or actual != record["runtime"]:
        raise ValueError("Windows Python runtime changed; review and repin its notices before releasing.")
    for component in record["components"]:
        for notice in component["notice_files"]:
            path = ROOT / notice["file"]
            if not path.resolve().is_relative_to(ROOT / "licenses") or hashlib.sha256(path.read_bytes()).hexdigest() != notice["sha256"]:
                raise ValueError("Pinned Windows runtime notice is missing or changed: " + notice["file"])
    return record
