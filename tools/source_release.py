"""Prepare source-only alpha delivery; never publish or invoke Git."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_portable import ROOT, VERSION, source_archive
from release_audit import inspect_archive


def prepare(destination):
    destination = Path(destination)
    # Keep each reviewed delivery intact; do not replace older archives/reports.
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / f"KiCad-Library-Loader-{VERSION}-source.tar.gz"
    source_archive(archive)
    audit = inspect_archive(archive, source=True)
    (destination / "source-content-audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    if not audit["content_checks_passed"]:
        raise ValueError("Source delivery failed content checks: " + str(audit["errors"]))
    (destination / "SHA256SUMS").write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n", encoding="utf-8")
    (destination / "READ-ME-FIRST.txt").write_text(
        "SOURCE-ONLY ALPHA DELIVERY — OWNER PUBLICATION IS MANUAL\n"
        "Follow README.md to install Python/Tk and requirements on Windows or Linux.\n"
        "This archive includes application source, tests, build tools and notices. It does not bundle Python/native dependencies.\n"
        "The content audit checks archive boundaries; it does not replace regression tests or a licence review of portable binaries.\n"
        "Portable candidates remain separate and have open native-source/notice review and clean-machine checks.\n", encoding="utf-8")
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/source-release" / VERSION)
    args = parser.parse_args()
    print(prepare(args.output))


if __name__ == "__main__":
    main()
