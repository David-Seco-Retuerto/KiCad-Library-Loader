"""Console helper for the portable GUI's isolated CAD/converter processes."""
import json
import platform
from pathlib import Path
import sys

from app_version import VERSION
from native_step import bundled_reader, run_reader, reader_version


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--self-test"]:
        import _tkinter
        native_version = reader_version() if bundled_reader() else None
        if native_version is None:
            import OCP.Standard
        from easyeda2kicad._version import __version__
        print(json.dumps({"version": VERSION, "system": platform.system(), "architecture": platform.machine(),
                          "tk": _tkinter.TK_VERSION, "converter": __version__, "native_reader": "OCCT" if native_version else "OCP", "occt_version": native_version}))
        return 0
    if args and args[0] == "--mesh":
        if len(args) != 3:
            print("Usage: kicad-loader-worker --mesh STEP JSON", file=sys.stderr)
            return 2
        from step_preview import mesh_step
        try:
            if bundled_reader():
                run_reader(args)
                return 0
            Path(args[2]).write_text(json.dumps(mesh_step(args[1])), encoding="utf-8")
            return 0
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
    # Call the installed upstream entry point unchanged, with an explicit argv.
    from easyeda2kicad.__main__ import main as convert
    return convert(args)


if __name__ == "__main__":
    raise SystemExit(main())
