"""Optional portable STEP backend; source installations retain Python/OCP."""
import json
import os
from pathlib import Path
import subprocess
import sys


def bundled_reader():
    if not getattr(sys, "frozen", False):
        return None
    runtime = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent / "_internal"))
    executable = runtime / "step-reader/bin" / ("kicad-step-mesher.exe" if os.name == "nt" else "kicad-step-mesher")
    return executable if executable.is_file() else None


def run_reader(args, timeout=55):
    executable = bundled_reader()
    if executable is None:
        raise RuntimeError("The native STEP helper is missing from this portable package.")
    env = os.environ.copy()
    resources = executable.parent.parent / "resources"
    for name, folder in (("CSF_STEPDefaults", "XSTEPResource"), ("CSF_XSMessage", "XSMessage"), ("CSF_SHMessage", "SHMessage")):
        if (resources / folder).is_dir():
            env[name] = str(resources / folder)
    result = subprocess.run([str(executable), *map(str, args)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout, env=env,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Native STEP reader failed.")[-2000:])
    return result


def reader_version():
    return json.loads(run_reader(["--self-test"], timeout=10).stdout)["version"]
