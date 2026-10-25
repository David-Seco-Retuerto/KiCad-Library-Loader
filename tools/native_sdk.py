"""Validate and copy a locally built STEP SDK into a new portable bundle."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil

ROOT = Path(__file__).resolve().parents[1]


def copy_sdk(sdk, bundle):
    sdk, bundle = Path(sdk).resolve(), Path(bundle)
    lock = json.loads((ROOT / "native/occt-source.json").read_text(encoding="utf-8"))
    provenance = json.loads((sdk / "BUILD_PROVENANCE.json").read_text(encoding="utf-8"))
    expected = ("windows" if os.name == "nt" else "linux") + "-" + platform.machine().lower().replace("amd64", "x86_64")
    if provenance["target"] != expected or provenance["source"] != lock:
        raise ValueError("The native SDK platform/source does not match this release build.")
    archive = sdk / lock["archive"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock["sha256"]:
        raise ValueError("Native SDK source archive hash mismatch.")
    executable = sdk / "bin" / ("kicad-step-mesher.exe" if os.name == "nt" else "kicad-step-mesher")
    if not executable.is_file():
        raise ValueError("Native SDK helper is missing.")
    destination = bundle / "_internal/step-reader"
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("bin", "lib"):
        folder = sdk / name
        if not folder.is_dir():
            continue
        target = destination / name
        target.mkdir()
        for path in sorted(folder.iterdir()):
            if path.is_file() and (path == executable or path.suffix.lower() == ".dll" or ".so" in path.name):
                if path.is_symlink():
                    if not path.resolve().is_relative_to(sdk):
                        raise ValueError("Native SDK link escapes its directory.")
                    target.joinpath(path.name).symlink_to(os.readlink(path))
                else:
                    shutil.copyfile(path, target / path.name)
                    shutil.copymode(path, target / path.name)
    for folder in ("XSMessage", "SHMessage", "UnitsAPI", "XSTEPResource", "StdResource"):
        found = [p for p in sdk.rglob(folder) if p.is_dir()]
        if found:
            target = destination / "resources" / folder
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(found[0], target)
    notices = bundle / "licenses/native-step"
    notices.mkdir(parents=True)
    for name in ("LICENSE_LGPL_21.txt", "OCCT_LGPL_EXCEPTION.txt", "BUILD_PROVENANCE.json"):
        shutil.copyfile(sdk / name, notices / name)
    microsoft_notices = [path for path in sdk.glob("MICROSOFT-THIRD-PARTY-NOTICES.*")
                         if path.is_file() and path.suffix.lower() in {".txt", ".rtf", ".html", ".htm"}]
    for path in microsoft_notices + [sdk / "WINDOWS-RUNTIME.json"]:
        if path.is_file():
            shutil.copyfile(path, notices / path.name)
    sources = bundle / "dependency-sources"
    shutil.copyfile(archive, sources / archive.name)
    return provenance
