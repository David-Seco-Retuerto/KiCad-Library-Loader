"""Assemble a small paired release from verified candidates, without rebuilding or Git."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import tarfile
import zipfile

PROJECT = "KiCad-Library-Loader"
REPOSITORY = "https://github.com/David-Seco-Retuerto/" + PROJECT
ROOT = PROJECT
PRIVATE = {".git", ".venv", "__pycache__", "data", ".kicad-importer-cache",
           ".kicad-loader-history", ".kicad-loader-backups", "AGENTS.md", ".kicad-importer.json"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(name):
    path = PurePosixPath(name)
    if not name or name.startswith("/") or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe archive path: " + name)
    return path


class Candidate:
    def __init__(self, path, platform, version):
        self.path, self.platform, self.version = Path(path), platform, version
        self.archive = zipfile.ZipFile(path) if platform == "windows-x86_64" else tarfile.open(path, "r:gz")
        try:
            self._load(platform, version)
        except BaseException:
            self.archive.close()
            raise

    def _load(self, platform, version):
        self.entries = {}
        members = self.archive.infolist() if platform == "windows-x86_64" else self.archive.getmembers()
        for member in members:
            name = member.filename.rstrip("/") if isinstance(member, zipfile.ZipInfo) else member.name.rstrip("/")
            parts = safe_path(name).parts
            if parts[0] != ROOT or any(part in PRIVATE for part in parts[1:]):
                raise ValueError("Unexpected/private candidate path: " + name)
            if len(parts) == 1:
                continue
            relative = PurePosixPath(*parts[1:]).as_posix()
            if relative in self.entries:
                raise ValueError("Duplicate archive entry: " + name)
            if isinstance(member, zipfile.ZipInfo):
                if member.is_dir():
                    continue
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unexpected Windows symlink")
            elif member.isdir():
                continue
            elif member.issym():
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), member.linkname))
                if member.linkname.startswith("/") or not target.startswith(ROOT + "/"):
                    raise ValueError("Candidate link escapes its root: " + name)
            elif not member.isfile():
                raise ValueError("Unsupported candidate entry: " + name)
            self.entries[relative] = member
        required = ["LICENSE", "AUTHORS.md", "THIRD_PARTY_NOTICES.md", "DEPENDENCIES.json",
                    "NATIVE_DEPENDENCIES.json", f"{PROJECT}-{version}-source.tar.gz",
                    PROJECT + (".exe" if platform == "windows-x86_64" else ""),
                    "kicad-loader-worker" + (".exe" if platform == "windows-x86_64" else ""),
                    "licenses/native-step/BUILD_PROVENANCE.json"]
        if any(name not in self.entries for name in required):
            raise ValueError("Incomplete candidate archive")

    def close(self):
        self.archive.close()

    def read(self, name):
        member = self.entries[name]
        if isinstance(member, zipfile.ZipInfo):
            return self.archive.read(member)
        if not member.isfile():
            raise ValueError("Expected a regular file: " + name)
        with self.archive.extractfile(member) as stream:
            return stream.read()

    def runtime(self):
        suffix = ".exe" if self.platform == "windows-x86_64" else ""
        return [name for name in self.entries if name.startswith("_internal/")
                or name in {PROJECT + suffix, "kicad-loader-worker" + suffix}]


def dependency_sources(candidate):
    records = json.loads(candidate.read("dependency-sources/SOURCE.json"))["sources"]
    native = json.loads(candidate.read("licenses/native-step/BUILD_PROVENANCE.json"))["source"]
    records.append({"filename": native["archive"], "sha256": native["sha256"]})
    sources = {}
    for record in records:
        name = record["filename"]
        if safe_path(name).name != name:
            raise ValueError("Invalid dependency source filename")
        data = candidate.read("dependency-sources/" + name)
        if digest(data) != record["sha256"]:
            raise ValueError("Dependency source hash mismatch: " + name)
        sources[name] = data
    return sources


def short_licences(candidate):
    mapping = {}
    used = set()
    for name in sorted(candidate.entries):
        if not name.startswith("licenses/"):
            continue
        parts = PurePosixPath(name).parts
        target = name
        if len(parts) > 3 and parts[1] == "runtime":
            target = "/".join((*parts[:3], parts[-1]))
            if target in used:
                base = PurePosixPath(parts[-1])
                target = "/".join((*parts[:3], base.stem + "-" + digest(candidate.read(name))[:12] + base.suffix))
        if target in used:
            raise ValueError("Licence destination collision")
        used.add(target)
        mapping[name] = target
    return mapping


def generated_files(candidate):
    version = candidate.version
    sources_name = f"{PROJECT}-{version}-source-complete.tar.gz"
    source_url = f"{REPOSITORY}/releases/download/v{version}/{sources_name}"
    mapping = short_licences(candidate)
    files = {mapping[name]: candidate.read(name) for name in mapping}
    files["licenses/PATHS.json"] = (json.dumps(mapping, indent=2) + "\n").encode()
    for name in ("DEPENDENCIES.json", "NATIVE_DEPENDENCIES.json", "WINDOWS-PYTHON-RUNTIME.json"):
        if name not in candidate.entries:
            continue
        data = json.loads(candidate.read(name))
        def rewrite(value):
            if isinstance(value, dict): return {key: rewrite(item) for key, item in value.items()}
            if isinstance(value, list): return [rewrite(item) for item in value]
            return mapping.get(value, value) if isinstance(value, str) else value
        files["metadata/" + name] = (json.dumps(rewrite(data), indent=2) + "\n").encode()
    files["LICENSE"] = candidate.read("LICENSE")
    files["AUTHORS.md"] = candidate.read("AUTHORS.md")
    files["THIRD_PARTY_NOTICES.md"] = ("# Portable distribution layout\n\n"
        "Application and dependency sources are offered separately in the complete source archive:\n\n"
        + source_url + "\n\n"
        "Original component notices follow unchanged. References to dependency-sources and docs below refer to the complete source archive (dependency-sources/ and app/docs/). "
        "Runtime licence files are retained; licenses/PATHS.json maps original build paths to their shorter packaged locations.\n\n---\n\n").encode() + candidate.read("THIRD_PARTY_NOTICES.md")
    command = PROJECT + (".exe" if candidate.platform == "windows-x86_64" else "")
    files["README.txt"] = (f"KiCad Library Loader {version}\n\n"
        f"Extract this complete folder and run {command}. Keep the worker and _internal folder together.\n"
        "No separate Python installation is needed. Install KiCad separately.\n"
        "Choose your input and output folders in Settings. Preferences and cache are stored in data next to the application.\n"
        "This is an alpha: try a temporary library/project and check pin mapping, footprint dimensions and 3D alignment in KiCad.\n"
        "Linux x86_64 was tested on Ubuntu 24.04; other distributions are not yet validated. Compatible glibc and C++ system runtimes are required.\n\n"
        "Source code, build instructions and developer documentation: see SOURCE.txt.\n"
        "Licence and third-party terms: LICENSE, THIRD_PARTY_NOTICES.md and licenses/.\n").encode()
    files["SOURCE.txt"] = (f"Matching complete source: {sources_name}\n{source_url}\n\n"
        "Available without an additional charge alongside the portable downloads. You do not need the source archive to run the application.\n"
        "It contains the exact application source from the validated builds, the included upstream source archives, original provenance and the release layout recipe.\n"
        "app/ contains application code and build recipes. release-tools/ contains the packaging-only reorganization recipe.\n").encode()
    return files


def write_portable(candidate, destination):
    generated = generated_files(candidate)
    if candidate.platform == "windows-x86_64":
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for name in sorted(candidate.runtime()):
                member = copy.copy(candidate.entries[name])
                output.writestr(member, candidate.read(name), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
            for name, data in sorted(generated.items()):
                output.writestr(ROOT + "/" + name, data)
    else:
        with tarfile.open(destination, "w:gz") as output:
            for name in sorted(candidate.runtime()):
                member = copy.copy(candidate.entries[name])
                output.addfile(member, io.BytesIO(candidate.read(name)) if member.isfile() else None)
            for name, data in sorted(generated.items()):
                member = tarfile.TarInfo(ROOT + "/" + name)
                member.size, member.mode = len(data), 0o644
                output.addfile(member, io.BytesIO(data))
    # All runtime files and symlink targets/modes must remain exactly the same.
    if candidate.platform == "windows-x86_64":
        with zipfile.ZipFile(destination) as archive:
            for name in candidate.runtime():
                if digest(archive.read(ROOT + "/" + name)) != digest(candidate.read(name)):
                    raise ValueError("Runtime changed: " + name)
    else:
        with tarfile.open(destination, "r:gz") as archive:
            for name in candidate.runtime():
                new, old = archive.getmember(ROOT + "/" + name), candidate.entries[name]
                if (new.mode, new.type, new.linkname) != (old.mode, old.type, old.linkname):
                    raise ValueError("Runtime permissions/link changed: " + name)
                if old.isfile():
                    with archive.extractfile(new) as stream:
                        if digest(stream.read()) != digest(candidate.read(name)):
                            raise ValueError("Runtime changed: " + name)
    return {"runtime_entries_verified": len(candidate.runtime()), "runtime_unchanged": True,
            "original_sha256": digest(candidate.path.read_bytes()), "sha256": digest(Path(destination).read_bytes()),
            "original_bytes": candidate.path.stat().st_size, "bytes": Path(destination).stat().st_size}


def prepare(windows, linux, destination):
    match = re.fullmatch(r"KiCad-Library-Loader-([0-9A-Za-z.+-]+)-windows-x86_64\.zip", Path(windows).name)
    if not match:
        raise ValueError("Select the final Windows portable ZIP, not an Actions artifact container")
    version = match[1]
    if Path(linux).name != f"{PROJECT}-{version}-linux-x86_64.tar.gz":
        raise ValueError("Windows/Linux versions do not match")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    assets = destination / "assets"
    assets.mkdir()
    candidates = []
    try:
        for path, platform in ((windows, "windows-x86_64"), (linux, "linux-x86_64")):
            candidates.append(Candidate(path, platform, version))
        application = candidates[0].read(f"{PROJECT}-{version}-source.tar.gz")
        if application != candidates[1].read(f"{PROJECT}-{version}-source.tar.gz"):
            raise ValueError("Application source archives differ between platforms")
        upstream = dependency_sources(candidates[0])
        if upstream != dependency_sources(candidates[1]):
            raise ValueError("Dependency sources differ between platforms")
        receipts = {}
        for candidate in candidates:
            receipts[candidate.platform] = write_portable(candidate, assets / candidate.path.name)
        source = assets / f"{PROJECT}-{version}-source-complete.tar.gz"
        source_root = f"{PROJECT}-{version}-source-complete"
        with tarfile.open(source, "w:gz") as output:
            def add(name, data, mode=0o644):
                info = tarfile.TarInfo(source_root + "/" + name)
                info.size, info.mode = len(data), mode
                output.addfile(info, io.BytesIO(data))
            with tarfile.open(fileobj=io.BytesIO(application), mode="r:gz") as original:
                for member in original:
                    parts = safe_path(member.name).parts
                    if member.isdir(): continue
                    if not member.isfile() or len(parts) < 2 or parts[0] != f"{PROJECT}-{version}" or any(x in PRIVATE for x in parts[1:]):
                        raise ValueError("Unsafe application source entry")
                    relative = PurePosixPath(*parts[1:]).as_posix()
                    with original.extractfile(member) as stream:
                        data = stream.read()
                    add("app/" + relative, data, member.mode)
                    if relative == "LICENSE": add("LICENSE", data)
            for name, data in sorted(upstream.items()):
                add("dependency-sources/" + name, data)
            for candidate in candidates:
                for name in sorted(candidate.entries):
                    if name.startswith("licenses/") or name == "dependency-sources/SOURCE.json":
                        add("provenance/" + candidate.platform + "/" + name, candidate.read(name))
                for name in ("THIRD_PARTY_NOTICES.md", "RELEASE_STATUS.txt", "DEPENDENCIES.json", "NATIVE_DEPENDENCIES.json", "WINDOWS-PYTHON-RUNTIME.json"):
                    if name in candidate.entries: add("provenance/" + candidate.platform + "/" + name, candidate.read(name))
            add("release-tools/prepare_release.py", Path(__file__).read_bytes())
            tests = Path(__file__).resolve().parents[1] / "tests/test_release_assembly.py"
            if tests.is_file(): add("release-tools/tests/test_release_assembly.py", tests.read_bytes())
            add("provenance/INPUTS.json", (json.dumps(receipts, indent=2) + "\n").encode())
            add("README.md", (f"# {PROJECT} {version}: complete corresponding source\n\n"
                "app/ is the exact application source from the validated Windows/Linux builds. dependency-sources/ contains the matching unchanged upstream archives. "
                "provenance/ retains original build/component records and the binary-preservation receipt. release-tools/ contains the packaging-only layout recipe.\n\n"
                "Follow app/README.md and app/docs/NATIVE_BUILD.md for dependencies, source execution and compilation. "
                "To reproduce the release layout, run release-tools/prepare_release.py against the two original portable candidates identified in provenance/INPUTS.json. "
                "The layout recipe does not recompile or modify executables. App code is AGPL-3.0-only; upstream components retain their own licences.\n").encode())
        hashes = {path.name: digest(path.read_bytes()) for path in sorted(assets.iterdir())}
        (assets / "SHA256SUMS").write_bytes("".join(f"{sha}  {name}\n" for name, sha in hashes.items()).encode())
        review = {"version": version, "runtime_unchanged": True, "published": False,
                  "application_source_sha256": digest(application), "packages": receipts, "sha256": hashes}
        (destination / "ASSEMBLY_REVIEW.json").write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        return review
    finally:
        for candidate in candidates: candidate.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--linux", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.windows, args.linux, args.output), indent=2))


if __name__ == "__main__":
    main()
