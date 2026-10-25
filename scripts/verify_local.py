"""Opt-in integration: read vendor inputs, import ONLY into a temporary directory.

Run: python scripts/verify_local.py --repo C:/path/KiCad-Libraries
No vendor fixture/output is added to this repository.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

from kicad_tools import find_cli, cli_version
from library_core import SYMBOL_FORMATS, associate, build_folder_plan, build_plan, children, commit_plan, read_tree, scan
from step_preview import mesh_step
from providers import PROVIDERS
from library_layout import LibraryCategory
from loader_settings import LoaderSettings


def digest_files(root):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--kicad-cli", type=Path, help="Use this KiCad CLI executable instead of automatic detection")
    parser.add_argument("--require-kicad-major", type=int, help="Fail unless the native checks use at least this KiCad major version")
    parser.add_argument("--format", choices=["both", *SYMBOL_FORMATS], default="both")
    parser.add_argument("--category", default="ICs")
    parser.add_argument("--library-name", default="DVL_ICs")
    parser.add_argument("--model-folder", default="ICs")
    for key in PROVIDERS:
        parser.add_argument(f"--{key.lower()}-dir", type=Path, help=f"Override the {key} native-export input folder")
    args = parser.parse_args()
    category = LibraryCategory(args.category, args.library_name, args.model_folder).validated()
    roots = {key: getattr(args, f"{key.lower()}_dir") or provider.default_folder(args.repo)
             for key, provider in PROVIDERS.items()}
    before = {key: digest_files(path) for key, path in roots.items()}
    if args.require_kicad_major is not None and args.require_kicad_major < 1:
        parser.error("--require-kicad-major must be positive")
    cli = str(args.kicad_cli.expanduser().resolve()) if args.kicad_cli else find_cli()
    version, major = "unavailable", 0
    if cli:
        try:
            version, major = cli_version(cli)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            parser.error(str(exc))
        print(f"Native validation CLI: {cli} (KiCad {version})")
    if args.require_kicad_major and major < args.require_kicad_major:
        parser.error(f"KiCad {args.require_kicad_major}+ is required for this validation; found {version}.")
    imported = 0
    formats = list(SYMBOL_FORMATS) if args.format == "both" else [args.format]
    with tempfile.TemporaryDirectory(prefix="dvl-integration-") as directory:
        target = Path(directory).resolve() / "separate-output-library"
        settings = LoaderSettings(roots, target, "absolute", categories=(category,)).validated(args.repo)
        for output_format in formats:
            commit_plan(target, build_folder_plan(args.repo, settings, output_format))
        print(f"Prepared temporary library folders for {category.library_name}")
        for source in PROVIDERS:
            inv = scan(args.repo, source, input_root=roots[source])
            print(f"{source}: {len(inv.symbols)} symbols, {len(inv.footprints)} footprints, {len(inv.models)} STEP")
            for notice in inv.notices:
                print("  " + notice)
            for key, symbol in inv.symbols.items():
                fp, model = associate(inv, symbol)
                for output_format in formats:
                    plan = build_plan(args.repo, inv, key, fp, model, category.name, "Suggestion", symbol_format=output_format,
                                      output_root=target, input_roots=roots.values(), model_path_mode="absolute", category_config=category)
                    for warning in plan.warnings:
                        print("  WARNING: " + warning)
                    commit_plan(target, plan)
                    print(f"  Imported {symbol.name} into temporary {output_format} library")
                    imported += 1
            for path in inv.models.values():
                try:
                    mesh = mesh_step(path)
                    print(f"  STEP preview OK: {path.name}, {len(mesh['triangles'])} triangles, {mesh['size_mm']} mm")
                except RuntimeError as exc:
                    if "needs OpenCascade" not in str(exc):
                        raise
                    print("  STEP preview check skipped: install requirements.txt")
                    break
        if args.require_kicad_major and not imported:
            raise RuntimeError("No native symbols were imported; the required native validation was not performed.")
        if cli and imported:
            def run_export(command, folder, expected):
                folder.mkdir(parents=True, exist_ok=True)
                result = subprocess.run(command, capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                print(result.stdout.strip())
                if result.returncode:
                    raise RuntimeError(result.stderr)
                if len(list(folder.glob("*.svg"))) < expected:
                    raise RuntimeError(f"Missing SVG output from {command[-1]}")

            packed = category.symbol_library(target, "packed")
            unpacked = category.symbol_library(target, "unpacked")
            inputs = ([packed] if packed.exists() else []) + list(unpacked.glob("*.kicad_sym"))
            for index, path in enumerate(inputs):
                output = target / f"svg_symbols_{index}"
                expected = len(children(read_tree(path), "symbol"))
                run_export([cli, "sym", "export", "svg", "--output", str(output), str(path)], output, expected)
            if unpacked.exists():
                if major >= 10:
                    output = target / "svg_unpacked_directory"
                    expected = sum(len(children(read_tree(p), "symbol")) for p in unpacked.glob("*.kicad_sym"))
                    run_export([cli, "sym", "export", "svg", "--output", str(output), str(unpacked)], output, expected)
                    print("KiCad 10+ unpacked-directory loading OK")
                else:
                    print(f"KiCad {version or 'unknown'}: unpacked files validated individually; native directory loading requires KiCad 10+ and was not tested.")
            footprints = category.footprint_library(target)
            if footprints.exists():
                # Request every library item explicitly: a successful bulk command
                # is not sufficient evidence that all footprints were loaded.
                for index, footprint in enumerate(sorted(footprints.glob("*.kicad_mod"))):
                    output = target / f"svg_footprints_{index}"
                    run_export([cli, "fp", "export", "svg", "--footprint", footprint.stem,
                                "--output", str(output), str(footprints)], output, 1)
            print("KiCad SVG exports OK")
        elif not cli:
            print("kicad-cli unavailable: native KiCad validation skipped")
    if before != {key: digest_files(path) for key, path in roots.items()}:
        raise RuntimeError("Source files changed during verification")
    print(f"OK: {imported} temporary imports; original source folders unchanged")


if __name__ == "__main__":
    main()
