"""Copy only the compiler's redistributable x64 CRT into the native SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def copy_runtime(sdk):
    sdk = Path(sdk)
    locator = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    installation = subprocess.check_output([str(locator), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip()
    if not installation:
        raise RuntimeError("Visual Studio redistributable runtime was not found.")
    visual = Path(installation)
    versions = [p for p in (visual / "VC/Redist/MSVC").iterdir() if p.is_dir() and re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", p.name)]
    version = max(versions, key=lambda p: tuple(map(int, p.name.split("."))))
    runtime = version / "x64/Microsoft.VC143.CRT"
    files = sorted(runtime.glob("*.dll"))
    if not files:
        raise RuntimeError("The x64 release CRT was not found; debug/nonredistributable runtimes must not be substituted.")
    records = []
    for path in files:
        shutil.copyfile(path, sdk / "bin" / path.name)
        records.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    notice = visual / "Licenses/BuildTools/1033/ThirdPartyNotices.txt"
    if not notice.is_file():
        raise RuntimeError("Microsoft's installed third-party runtime notice was not found.")
    shutil.copyfile(notice, sdk / "MICROSOFT-THIRD-PARTY-NOTICES.txt")
    record = {"compiler_redist_version": version.name, "family": "Microsoft.VC143.CRT x64 release",
              "origin": "Visual Studio 2022 Build Tools VC/Redist/MSVC", "files": records,
              "redistribution_reference": "https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files"}
    (sdk / "WINDOWS-RUNTIME.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdk", type=Path)
    args = parser.parse_args()
    print(json.dumps(copy_runtime(args.sdk)))


if __name__ == "__main__":
    main()
