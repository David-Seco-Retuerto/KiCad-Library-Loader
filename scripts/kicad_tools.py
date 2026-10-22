"""Find installed KiCad CLIs and verify the executable's actual version."""
import os
from pathlib import Path
import re
import shutil
import subprocess


def find_cli(environment=None):
    environment = dict(os.environ if environment is None else environment)
    found = shutil.which("kicad-cli", path=environment.get("PATH", ""))
    if found:
        return found
    bases = [Path(environment[key]) / "KiCad" for key in ("ProgramFiles", "ProgramFiles(x86)") if environment.get(key)]
    if environment.get("LOCALAPPDATA"):
        bases.append(Path(environment["LOCALAPPDATA"]) / "Programs/KiCad")
    candidates = [path for base in bases for path in base.glob("*/bin/kicad-cli.exe") if path.is_file()]
    def rank(path):
        match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", path.parent.parent.name)
        return (tuple(int(value or 0) for value in match.groups()) if match else (), str(path))
    return str(max(candidates, key=rank)) if candidates else None


def cli_version(executable):
    result = subprocess.run([str(executable), "version"], capture_output=True, text=True, timeout=15,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    version = result.stdout.strip()
    match = re.match(r"(\d+)\.", version)
    if result.returncode or not match:
        raise RuntimeError(f"Cannot determine KiCad CLI version: {result.stderr.strip() or version or 'empty response'}")
    return version, int(match.group(1))
