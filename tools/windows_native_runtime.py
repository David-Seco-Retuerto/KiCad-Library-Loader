"""Copy only the compiler's redistributable x64 CRT into the native SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def find_notice(visual):
    """Find an original notice in the selected VS edition, without downloading one."""
    visual = Path(visual)
    licenses = visual / "Licenses"
    paths = list(licenses.rglob("*")) if licenses.is_dir() else []
    paths.extend(visual.iterdir())
    candidates = [path for path in paths if path.is_file()
                  and path.suffix.casefold() in {".txt", ".rtf", ".html", ".htm"}
                  and re.sub(r"[^a-z]", "", path.stem.casefold()).startswith("thirdpartynotices")
                  and path.resolve().is_relative_to(visual.resolve())]
    if not candidates:
        raise RuntimeError(f"Microsoft's installed third-party runtime notice was not found under {licenses} or the installation root.")

    def preference(path):
        parts = tuple(part.casefold() for part in path.relative_to(visual).parts)
        return (visual.name.casefold() not in parts, "1033" not in parts,
                path.suffix.casefold() != ".txt", len(parts), path.as_posix().casefold())

    return min(candidates, key=preference)


def copy_runtime(sdk):
    sdk = Path(sdk)
    locator = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    installation = subprocess.check_output([str(locator), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip()
    if not installation:
        raise RuntimeError("Visual Studio redistributable runtime was not found.")
    visual = Path(installation)
    versions = [p for p in (visual / "VC/Redist/MSVC").iterdir() if p.is_dir() and re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", p.name)]
    if not versions:
        raise RuntimeError("No numbered Visual Studio redistributable runtime directory was found.")
    version = max(versions, key=lambda p: tuple(map(int, p.name.split("."))))
    runtime = version / "x64/Microsoft.VC143.CRT"
    files = sorted(runtime.glob("*.dll"))
    if not files:
        raise RuntimeError("The x64 release CRT was not found; debug/nonredistributable runtimes must not be substituted.")
    notice = find_notice(visual)
    notice_name = "MICROSOFT-THIRD-PARTY-NOTICES" + notice.suffix.lower()
    records = []
    for path in files:
        shutil.copyfile(path, sdk / "bin" / path.name)
        records.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    shutil.copyfile(notice, sdk / notice_name)
    record = {"compiler_redist_version": version.name, "family": "Microsoft.VC143.CRT x64 release",
              "origin": f"Visual Studio 2022 {visual.name} VC/Redist/MSVC", "files": records,
              "notice": {"file": notice_name, "installed_path": notice.relative_to(visual).as_posix(),
                         "sha256": hashlib.sha256(notice.read_bytes()).hexdigest()},
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
