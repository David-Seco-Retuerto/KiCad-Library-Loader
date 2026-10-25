"""Collect exact Debian/Ubuntu runtime package identities and copyright texts.

Analysis files are parsed as literals, never executed. This evidence collector
records provenance without inferring licence approval from package names.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def binary_entries(analyses):
    found = set()
    def visit(value):
        if isinstance(value, (list, tuple)):
            if len(value) == 3 and all(isinstance(v, str) for v in value) and value[2] in {"BINARY", "EXTENSION"}:
                found.add((value[0], value[1]))
            else:
                for item in value:
                    visit(item)
    for path in analyses:
        visit(ast.literal_eval(Path(path).read_text(encoding="utf-8")))
    return sorted(found)


def owner(path):
    path = Path(path)
    variants = [path, path.resolve()]
    if str(path).startswith("/usr/lib/"):
        variants.append(Path(str(path)[4:]))
    elif str(path).startswith("/lib/"):
        variants.append(Path("/usr" + str(path)))
    for candidate in dict.fromkeys(variants):
        result = subprocess.run(["dpkg-query", "-S", str(candidate)], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if ": " in line and not line.startswith(("diversion", "local diversion")):
                    return line.rsplit(": ", 1)[0]
    return None


def collect(analyses, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    packages, unidentified = {}, []
    for destination, original in binary_entries(analyses):
        path = Path(original)
        if not path.is_file():
            continue
        # Locally compiled OCCT and pip wheels have separate source/notice flows.
        if not str(path).startswith(("/lib/", "/usr/lib/")):
            continue
        package = owner(path)
        if not package:
            unidentified.append(destination)
            continue
        if package not in packages:
            fmt = "${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n"
            values = subprocess.check_output(["dpkg-query", "-W", "-f=" + fmt, package], text=True).strip().split("\t")
            binary_name, version, source, source_version = values
            copyright = Path("/usr/share/doc") / binary_name.split(":")[0] / "copyright"
            target = output / (binary_name.replace(":", "_") + "-copyright.txt")
            if copyright.is_file():
                shutil.copyfile(copyright, target)
            packages[package] = {"binary_package": binary_name, "binary_version": version,
                "source_package": source or binary_name.split(":")[0], "source_version": source_version or version,
                "notice": target.name if target.is_file() else None, "binary_files": [],
                "review_status": "unreviewed"}
        packages[package]["binary_files"].append({"path": destination, "sha256_original": hashlib.sha256(path.read_bytes()).hexdigest()})
    common = Path("/usr/share/common-licenses")
    if common.is_dir():
        target = output / "common-licenses"
        target.mkdir()
        for path in sorted(common.iterdir()):
            if path.is_file():
                shutil.copyfile(path, target / path.name)
    report = {"schema": 1, "distribution": Path("/etc/os-release").read_text(encoding="utf-8"),
              "packages": sorted(packages.values(), key=lambda item: item["binary_package"]),
              "unidentified_system_binaries": unidentified, "licence_review_complete": False,
              "note": "Exact installed package identities and original file hashes; source delivery/licence choices require review."}
    (output / "SYSTEM_PACKAGES.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.analysis, args.output)
    print(json.dumps({"packages": len(report["packages"]), "unidentified": report["unidentified_system_binaries"]}))


if __name__ == "__main__":
    main()
