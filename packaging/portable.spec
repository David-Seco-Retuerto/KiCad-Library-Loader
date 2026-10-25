# Native builds only: run through tools/build_portable.py on each target OS.
from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_delvewheel_libs_directory, copy_metadata

root = Path(SPECPATH).parent
sources = str(root / "scripts")
datas, binaries, hidden = [], [], []
native_step = bool(os.environ.get("KICAD_LOADER_NATIVE_SDK"))
for package in (("easyeda2kicad",) if native_step else ("OCP", "cadquery_ocp_proxy", "easyeda2kicad")):
    package_data, package_bins, package_hidden = collect_all(package)
    datas += package_data
    binaries += package_bins
    hidden += package_hidden
for package in (("easyeda2kicad",) if native_step else ("cadquery-ocp-novtk", "cadquery-ocp-proxy", "easyeda2kicad")):
    datas += copy_metadata(package)
if sys.platform == "win32" and not native_step:
    datas, binaries = collect_delvewheel_libs_directory("OCP", "cadquery_ocp_novtk.libs", datas=datas, binaries=binaries)
common = dict(pathex=[sources], binaries=binaries, datas=datas, hiddenimports=hidden,
              hookspath=[], runtime_hooks=[], excludes=["pytest", "unittest", "pip", "setuptools"] + (["OCP", "cadquery_ocp_proxy"] if native_step else []))
gui = Analysis([str(root / "scripts/portable_entry.py")], **common)
worker = Analysis([str(root / "scripts/portable_worker.py")], **common)
if native_step and sys.platform == "linux":
    # These remain target-system prerequisites, like glibc; do not redistribute them.
    for analysis in (gui, worker):
        analysis.binaries = [entry for entry in analysis.binaries if Path(entry[0]).name not in {"libstdc++.so.6", "libgcc_s.so.1"}]
gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True,
              name="KiCad-Library-Loader", console=False, upx=False)
worker_exe = EXE(PYZ(worker.pure), worker.scripts, [], exclude_binaries=True,
                 name="kicad-loader-worker", console=True, upx=False)
COLLECT(gui_exe, worker_exe, gui.binaries, gui.datas, worker.binaries, worker.datas,
        name="KiCad-Library-Loader", upx=False)
