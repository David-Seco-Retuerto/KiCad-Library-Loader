"""Windowed executable entry point, with an explicit isolated build smoke mode."""
import json
from pathlib import Path
import sys


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        output = Path(sys.argv[2]).resolve()
        try:
            from portable_smoke import gui_smoke
            result = gui_smoke()
        except Exception as exc:
            output.write_text(json.dumps({"passed": False, "error": str(exc)}), encoding="utf-8")
            return 1
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0
    from import_gui import main as gui
    gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
