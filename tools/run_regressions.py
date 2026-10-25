"""Run fail-fast regressions with periodic stack dumps for unattended builds."""
import faulthandler
from pathlib import Path
import unittest


def main():
    faulthandler.enable()
    faulthandler.dump_traceback_later(120, repeat=True)
    try:
        result = unittest.main(module=None, argv=[__file__, "discover", "-s",
                               str(Path(__file__).resolve().parents[1] / "tests"), "-v", "-f"], exit=False)
        return 0 if result.result.wasSuccessful() else 1
    finally:
        faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    raise SystemExit(main())
