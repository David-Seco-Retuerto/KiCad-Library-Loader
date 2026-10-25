"""Build the isolated OCCT STEP helper from pinned sources; never invoke Git."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("FoundationClasses", "ModelingData", "ModelingAlgorithms", "Visualization", "ApplicationFramework", "DataExchange", "DETools", "Draw")


def extract_source(archive, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as source:
        members = source.getmembers()
        for member in members:
            relative = Path(member.name)
            target = (destination / relative).resolve()
            if relative.is_absolute() or ".." in relative.parts or not target.is_relative_to(destination):
                raise ValueError("Invalid upstream source path: " + member.name)
            if not (member.isfile() or member.isdir()):
                raise ValueError("Unsupported upstream source entry: " + member.name)
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as stream, target.open("wb") as output:
                    shutil.copyfileobj(stream, output)
    roots = list(destination.iterdir())
    if len(roots) != 1 or not (roots[0] / "CMakeLists.txt").is_file():
        raise ValueError("Unexpected OCCT source archive layout.")
    return roots[0]


def run_stage(command, folder, index, count, progress_interval=15):
    log = folder / f"stage-{index}.log"
    print(f"Stage {index + 1}/{count}: {log}", flush=True)
    if progress_interval <= 0:
        raise ValueError("The progress interval must be positive.")
    started = last_output = time.monotonic()
    previous_size = 0
    with log.open("w", encoding="utf-8") as output:
        with subprocess.Popen(command, cwd=folder, stdout=output, stderr=subprocess.STDOUT) as process:
            try:
                while True:
                    try:
                        process.wait(timeout=progress_interval)
                        break
                    except subprocess.TimeoutExpired:
                        now = time.monotonic()
                        size = log.stat().st_size
                        if size != previous_size:
                            previous_size, last_output = size, now
                        with log.open("rb") as stream:
                            stream.seek(max(0, size - 8000))
                            lines = stream.read().decode("utf-8", errors="replace").splitlines()
                        latest = next((line for line in reversed(lines) if line.strip()), "No compiler output yet.")
                        print(f"Stage {index + 1}/{count}: running {now - started:.0f}s; "
                              f"no new log bytes for {now - last_output:.0f}s. Last output: {latest[-2000:]}", flush=True)
            except BaseException:
                process.kill()
                process.wait()
                raise
            result_code = process.returncode
    print(f"Stage {index + 1}/{count}: finished in {time.monotonic() - started:.1f}s (exit {result_code}).", flush=True)
    if result_code:
        # Hosted CI runners disappear after the job; show the actual compiler
        # diagnostic in the console as well as preserving the complete log.
        with log.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 24000))
            tail = stream.read().decode("utf-8", errors="replace")
        print("Native build failure — last 80 log lines:", flush=True)
        print("\n".join(tail.splitlines()[-80:]), flush=True)
        raise RuntimeError(f"Native build failed at stage {index + 1} (exit {result_code}); inspect {log}.")


def build(build_root=None, jobs=2, generator=None, resume=None):
    lock = json.loads((ROOT / "native/occt-source.json").read_text(encoding="utf-8"))
    target = ("windows" if os.name == "nt" else "linux") + "-" + platform.machine().lower().replace("amd64", "x86_64")
    default_root = ROOT / ".native-build" if os.name == "nt" else Path.home() / ".cache/kicad-library-loader/native"
    base = Path(build_root or default_root).resolve()
    downloads = ROOT / ".native-build/downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / lock["archive"]
    if not archive.exists():
        temporary = archive.with_suffix(".download")
        try:
            with urllib.request.urlopen(lock["url"], timeout=120) as source, temporary.open("xb") as output:
                shutil.copyfileobj(source, output)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != lock["sha256"]:
                raise ValueError("OCCT source hash mismatch.")
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock["sha256"]:
        raise ValueError("OCCT source hash mismatch. Existing archive was not used.")
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    if resume:
        folder = Path(resume).resolve()
        source = folder / "source" / ("OCCT-" + lock["commit"])
        cache = folder / "occt-build/CMakeCache.txt"
        if not source.is_dir() or not cache.is_file() or folder.parent.name != target:
            raise ValueError("Resume requires an existing build for this platform and pinned source commit.")
        normalized = cache.read_text(encoding="utf-8").replace("\\", "/")
        if "CMAKE_HOME_DIRECTORY:INTERNAL=" + source.as_posix() not in normalized:
            raise ValueError("Resume cache does not belong to the pinned source directory.")
    else:
        folder = base / target / run
        folder.mkdir(parents=True, exist_ok=False)
        source = extract_source(archive, folder / "source")
    install = folder / "sdk"
    cmake = shutil.which("cmake")
    if not cmake:
        raise RuntimeError("CMake is required. On Windows use the installed Visual Studio C++ developer environment.")
    if generator is None:
        generator = "Ninja" if shutil.which("ninja") else "Unix Makefiles" if os.name != "nt" else "Ninja"
    configure = [cmake, "-S", str(source), "-B", str(folder / "occt-build"), "-G", generator,
                 "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_LIBRARY_TYPE=Shared", "-DCMAKE_DISABLE_FIND_PACKAGE_Git=ON",
                 "-DINSTALL_DIR=" + str(install), "-DINSTALL_DIR_BIN=bin", "-DINSTALL_DIR_LIB=lib",
                 "-DINSTALL_DIR_INCLUDE=include/opencascade", "-DINSTALL_DIR_CMAKE=lib/cmake/opencascade",
                 "-DBUILD_ADDITIONAL_TOOLKITS=TKDESTEP;TKMesh;TKPrim",
                 "-DUSE_FREEIMAGE=OFF", "-DUSE_FREETYPE=OFF", "-DUSE_FONTCONFIG=OFF", "-DUSE_TBB=OFF",
                 "-DUSE_VTK=OFF", "-DUSE_FFMPEG=OFF", "-DUSE_XLIB=OFF", "-DUSE_OPENGL=OFF", "-DUSE_RAPIDJSON=OFF"]
    configure += ["-DBUILD_MODULE_" + name + "=OFF" for name in MODULES]
    commands = [configure,
                [cmake, "--build", str(folder / "occt-build"), "--config", "Release", "--parallel", str(jobs)],
                [cmake, "--install", str(folder / "occt-build"), "--config", "Release"],
                [cmake, "-S", str(ROOT / "native"), "-B", str(folder / "helper-build"), "-G", generator,
                 "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + str(install), "-DCMAKE_INSTALL_PREFIX=" + str(install)],
                [cmake, "--build", str(folder / "helper-build"), "--config", "Release", "--parallel", str(jobs)],
                [cmake, "--install", str(folder / "helper-build"), "--config", "Release"]]
    print(json.dumps({"build": str(folder), "sdk": str(install)}), flush=True)
    for index, command in enumerate(commands):
        run_stage(command, folder, index, len(commands))
    if os.name == "nt":
        from windows_native_runtime import copy_runtime
        copy_runtime(install)
    executable = install / "bin" / ("kicad-step-mesher.exe" if os.name == "nt" else "kicad-step-mesher")
    subprocess.run([str(executable), "--self-test"], check=True)
    manifest = {"schema": 1, "target": target, "source": lock, "patches": [], "third_party_graphics_disabled": True,
                "source_archive_included": lock["archive"], "toolkits_requested": ["TKDESTEP", "TKMesh", "TKPrim"],
                "configure_options": [value for value in configure if value.startswith("-D") and "DIR=" not in value],
                "clean_machine_tested": False, "native_licence_review_complete": False}
    (install / "BUILD_PROVENANCE.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(archive, install / lock["archive"])
    for name in ("LICENSE_LGPL_21.txt", "OCCT_LGPL_EXCEPTION.txt"):
        shutil.copyfile(source / name, install / name)
    print(json.dumps({"sdk": str(install), "helper": str(executable)}), flush=True)
    return install


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--generator")
    parser.add_argument("--resume", type=Path, help="Reuse an owned build after helper changes; cached OCCT sources must remain unchanged")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error("Choose 1–16 build jobs.")
    build(args.build_root, args.jobs, args.generator, args.resume)


if __name__ == "__main__":
    main()
