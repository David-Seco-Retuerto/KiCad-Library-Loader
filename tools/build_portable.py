"""Build an isolated native portable candidate; never publish or invoke Git."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from app_version import VERSION
# Also support importlib-based tests, without relying on the current directory.
sys.path.insert(0, str(ROOT / "tools"))
from release_audit import inspect_bundle, inspect_archive

SOURCE_FILES = ("README.md", "PROJECT_STATUS.md", "LICENSE", "AUTHORS.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md",
                "requirements.txt", "requirements-build.txt", "start_gui.ps1", "start_gui.sh", ".gitignore", ".gitattributes")
SOURCE_DIRS = ("scripts", "tests", "docs", "tools", "packaging", "licenses", "native", ".github")


def source_files():
    for name in SOURCE_FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for name in SOURCE_DIRS:
        for path in sorted((ROOT / name).rglob("*"), key=lambda item: item.relative_to(ROOT).as_posix()):
            if (path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
                    and path.suffix not in {".pyc", ".pyo"} and path.name != "AGENTS.md"):
                yield path


def source_archive(destination):
    # Stable metadata and gzip headers yield the same source artifact on both OSes.
    with Path(destination).open("wb") as stream, gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for path in source_files():
                info = archive.gettarinfo(path, arcname=f"KiCad-Library-Loader-{VERSION}/" + path.relative_to(ROOT).as_posix())
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                info.mode = 0o755 if path.name == "start_gui.sh" else 0o644
                with path.open("rb") as source:
                    archive.addfile(info, source)


def dependency_sources(bundle):
    """Ship exact upstream converter and bootloader/tool sources, hash-verified."""
    folder = bundle / "dependency-sources"
    folder.mkdir()
    records = []
    for name in ("easyeda2kicad", "pyinstaller", "pyinstaller-hooks-contrib"):
        version = metadata.version(name)
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
            release = json.load(response)
        source = next(item for item in release["urls"] if item["packagetype"] == "sdist")
        if not source["url"].startswith("https://files.pythonhosted.org/") or Path(source["filename"]).name != source["filename"]:
            raise ValueError("Unexpected upstream source location.")
        with urllib.request.urlopen(source["url"], timeout=60) as response:
            data = response.read(50_000_001)
        if len(data) > 50_000_000 or hashlib.sha256(data).hexdigest() != source["digests"]["sha256"]:
            raise ValueError("Upstream source archive hash/size check failed.")
        (folder / source["filename"]).write_bytes(data)
        records.append({"name": name, "version": version, "filename": source["filename"],
                        "sha256": source["digests"]["sha256"], "url": source["url"]})
    (folder / "SOURCE.json").write_text(json.dumps({"schema": 1, "sources": records}, indent=2), encoding="utf-8")


def notices(bundle, native=False):
    folder = bundle / "licenses" / "runtime"
    folder.mkdir(parents=True)
    inventory = []
    packages = ("easyeda2kicad", "pyinstaller", "pyinstaller-hooks-contrib")
    if not native:
        packages += ("cadquery-ocp-novtk", "cadquery-ocp-proxy")
    for name in packages:
        dist = metadata.distribution(name)
        item = {"name": dist.metadata["Name"], "version": dist.version,
                "declared_license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                "project_urls": dist.metadata.get_all("Project-URL") or [], "notice_files": []}
        for relative in dist.files or []:
            if any(term in str(relative).casefold() for term in ("license", "copying", "notice")):
                source = Path(dist.locate_file(relative))
                if source.is_file() and source.stat().st_size < 5_000_000:
                    target = folder / name / str(relative).replace("..", "_")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    item["notice_files"].append(target.relative_to(bundle).as_posix())
        inventory.append(item)
    # CPython, Tcl and Tk are runtime components, not pip distributions.
    candidates = [Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE",
                  Path(sys.base_prefix) / "tcl/tcl8.6/license.terms", Path(sys.base_prefix) / "tcl/tk8.6/license.terms",
                  Path("/usr/share/doc/python3.12/copyright"), Path("/usr/share/doc/libtcl8.6/copyright"), Path("/usr/share/doc/libtk8.6/copyright")]
    for index, source in enumerate(candidates):
        if source.is_file():
            shutil.copyfile(source, folder / f"system-{index}-{source.name}")
    (bundle / "DEPENDENCIES.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    # The native wheel bundles additional DLL/.so components whose licences are
    # not fully represented by pip metadata. Candidates remain explicitly gated.
    (bundle / "RELEASE_STATUS.txt").write_text(
        "LOCAL ALPHA CANDIDATE — NOT A PUBLISHED RELEASE\n"
        + ("Minimal OCCT source and runtime notices are included. Independent-runner and owner acceptance checks remain before publication.\n" if native else "Legacy OCP dependency notice/source inventory is unresolved. Do not publish this binary.\n")
        + "See docs/RELEASING.md. No provider component assets or personal settings are included.\n", encoding="utf-8")


def make_archive(bundle, destination):
    if os.name == "nt":
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(bundle.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=bundle.name + "/" + path.relative_to(bundle).as_posix())
    else:
        # Tar preserves executable bits and any native shared-library links.
        with tarfile.open(destination, "w:gz") as archive:
            archive.add(bundle, arcname=bundle.name)


def run_regression_tests(work, environment, timeout=600):
    log = Path(work) / "regression.log"
    print(f"Running fail-fast regressions (timeout: {timeout}s). Full log: {log}", flush=True)
    failure = None
    with log.open("w", encoding="utf-8") as stream:
        try:
            result = subprocess.run([sys.executable, "-u", str(ROOT / "tools/run_regressions.py")],
                                    cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                    env=environment, timeout=timeout)
            if result.returncode:
                failure = f"Regression tests failed (exit {result.returncode})."
        except subprocess.TimeoutExpired:
            failure = f"Regression tests timed out after {timeout}s. Inspect the last test and stack dumps."
    with log.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - 32000))
        tail = stream.read().decode("utf-8", errors="replace")
    print(tail, flush=True)
    if failure:
        raise RuntimeError(f"{failure} Full log: {log}")


def build():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true", help="Development only; report records that regression tests were not run")
    parser.add_argument("--online-smoke", action="store_true", help="Explicitly acquire C2040 into a temporary folder through the frozen helper")
    backend = parser.add_mutually_exclusive_group(required=True)
    backend.add_argument("--native-sdk", type=Path, help="Use the reviewed-source minimal STEP SDK")
    backend.add_argument("--legacy-ocp", action="store_true", help="Development only: bundle the legacy OCP wheel; native provenance remains unresolved")
    args = parser.parse_args()
    if sys.platform not in {"win32", "linux"}:
        parser.error("Only Windows and Linux candidates are supported.")
    target = ("windows" if os.name == "nt" else "linux") + "-" + platform.machine().lower().replace("amd64", "x86_64")
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    work = ROOT / "build" / target / run
    result = ROOT / "dist" / target / run
    work.mkdir(parents=True)
    result.mkdir(parents=True)
    if not args.skip_tests:
        test_environment = os.environ.copy()
        if args.native_sdk:
            test_environment["KICAD_LOADER_TEST_STEP_HELPER"] = str(args.native_sdk / "bin" / ("kicad-step-mesher.exe" if os.name == "nt" else "kicad-step-mesher"))
        run_regression_tests(work, test_environment)
    log = work / "pyinstaller.log"
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--distpath", str(result), "--workpath", str(work / "pyinstaller"),
                        str(ROOT / "packaging/portable.spec")], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True,
                       env={**os.environ, "KICAD_LOADER_NATIVE_SDK": str(args.native_sdk.resolve()) if args.native_sdk else ""})
    bundle = result / "KiCad-Library-Loader"
    for name in ("README.md", "AUTHORS.md", "LICENSE", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(ROOT / name, bundle / name)
    shutil.copytree(ROOT / "licenses", bundle / "licenses")
    shutil.copytree(ROOT / "docs", bundle / "docs")
    if os.name == "nt":
        from windows_python_notices import verify
        windows_runtime = verify()
        (bundle / "WINDOWS-PYTHON-RUNTIME.json").write_text(json.dumps(windows_runtime, indent=2) + "\n", encoding="utf-8")
    notices(bundle, native=bool(args.native_sdk))
    dependency_sources(bundle)
    if args.native_sdk:
        from native_sdk import copy_sdk
        copy_sdk(args.native_sdk, bundle)
    if sys.platform == "linux":
        from linux_runtime_notices import collect
        collect(sorted((work / "pyinstaller").rglob("Analysis-*.toc")), bundle / "licenses/linux-system")
    native_inventory = inspect_bundle(bundle)
    (bundle / "NATIVE_DEPENDENCIES.json").write_text(json.dumps(native_inventory, indent=2) + "\n", encoding="utf-8")
    suffix = ".exe" if os.name == "nt" else ""
    worker = bundle / ("kicad-loader-worker" + suffix)
    app = bundle / ("KiCad-Library-Loader" + suffix)
    check = subprocess.run([str(worker), "--self-test"], check=True, capture_output=True, text=True, timeout=90)
    converter = subprocess.run([str(worker), "--help"], check=True, capture_output=True, text=True, timeout=60)
    if "--lcsc_id" not in converter.stdout:
        raise RuntimeError("Frozen converter help did not load.")
    # Run from another working directory, not the build/source tree.
    with tempfile.TemporaryDirectory(prefix="loader-frozen-check-") as temporary:
        gui_report = Path(temporary) / "gui.json"
        subprocess.run([str(app), "--smoke-test", str(gui_report)], cwd=temporary, check=True, timeout=120)
        gui = json.loads(gui_report.read_text(encoding="utf-8"))
        if not gui.get("passed"):
            raise RuntimeError(gui)
    if args.online_smoke:
        from lcsc_download import download_lcsc
        from library_core import scan_directory, associate, build_plan, commit_plan
        with tempfile.TemporaryDirectory(prefix="loader-frozen-acquisition-") as temporary:
            workspace = Path(temporary).resolve()
            acquired = download_lcsc(workspace, str(worker), "C2040")
            inventory = scan_directory(acquired.folder)
            key = next(iter(inventory.symbols))
            fp, model = associate(inventory, inventory.symbols[key])
            for mode in ("packed", "unpacked"):
                output = workspace / mode
                plan = build_plan(workspace, inventory, key, fp, model, "ICs", "Suggestion", symbol_format=mode, output_root=output)
                commit_plan(output, plan)
    report = {"version": VERSION, "target": target, "python": platform.python_version(), "platform": platform.platform(),
              "libc": platform.libc_ver(), "regression_tests_run": not args.skip_tests,
              "worker": json.loads(check.stdout), "converter_help": True, "gui": gui,
              "live_download": args.online_smoke, "native_step_sdk": bool(args.native_sdk), "clean_machine": False, "release_ready": False}
    (result / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Source whitelist prevents settings, vendor caches, AGENTS and Git data leaks.
    source = result / f"KiCad-Library-Loader-{VERSION}-source.tar.gz"
    source_archive(source)
    shutil.copyfile(source, bundle / source.name)
    archive = result / (f"KiCad-Library-Loader-{VERSION}-{target}" + (".zip" if os.name == "nt" else ".tar.gz"))
    make_archive(bundle, archive)
    for artifact, is_source in ((archive, False), (source, True)):
        audit = inspect_archive(artifact, source=is_source)
        (result / ("source-content-audit.json" if is_source else "binary-content-audit.json")).write_text(
            json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        if not audit["content_checks_passed"]:
            raise RuntimeError("Release content checks failed: " + str(audit["errors"]))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, source)}
    (result / "SHA256SUMS").write_text("".join(f"{value}  {name}\n" for name, value in hashes.items()), encoding="utf-8")
    print(json.dumps({"candidate": str(archive), "source": str(source), "verification": str(result / "verification.json")}, indent=2), flush=True)


if __name__ == "__main__":
    build()
