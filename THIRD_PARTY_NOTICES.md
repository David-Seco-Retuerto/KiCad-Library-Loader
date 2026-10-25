# Third-party software notices

Copyright (C) 2026 David-Seco-Retuerto applies to the loader's own code under AGPL-3.0-only. Third-party components retain their own copyrights, licences and applicable exceptions. The loader does not relicense those components. KiCad and provider CAD assets are not bundled as application code.

## easyeda2kicad 1.0.1

- Project: [easyeda2kicad.py](https://github.com/uPesy/easyeda2kicad.py), by uPesy and upstream contributors.
- Release: [PyPI 1.0.1](https://pypi.org/project/easyeda2kicad/1.0.1/), declaring AGPL-3.0.
- Original licence: `licenses/easyeda2kicad-AGPL-3.0.txt`.

The loader calls the unmodified converter entry point in a separate worker for explicit single-part LCSC acquisition. Its implementation has not been copied into the loader's own modules or modified. Each release provides the exact upstream source distribution, verified against PyPI SHA-256, in the complete source download linked from the portables. Downloaded CAD assets remain in the user's cache and have separate provider terms; they are not application source/release fixtures.

## Source-installation STEP dependency

Source installations/tests use cadquery-ocp-novtk 7.9.3.1.1 and cadquery-ocp-proxy 7.9.3.1.1, declaring Apache-2.0 for the bindings. Their native dependencies have separate terms. Matching OCP/build-system notice evidence is under `licenses/upstream`; Python package metadata alone does not establish every bundled DLL/shared-library licence or source obligation.

## Minimal STEP portable mode

Release builds use `--native-sdk` to ship the loader's C++ STEP helper and dynamically linked Open CASCADE Technology 7.9.3 built from the exact commit/archive in `native/occt-source.json`. The complete unmodified OCCT source archive is provided under `dependency-sources` in the separate complete source download, linked alongside the portable on the same release page. The LGPL 2.1 licence, OCCT exception and build provenance remain in each portable under `licenses/native-step`. The helper/build recipes are part of the AGPL loader source archive. The OCCT libraries may be modified/rebuilt/replaced under their applicable terms; the loader does not impose additional restrictions on those rights.

The OCP Python bindings remain a source-installation/test dependency. They and their FreeImage/codec dependency stack are not included in minimal STEP portables. The legacy `--legacy-ocp` development bundle still has unresolved transitive provenance and must not be published.

Windows packages retain the CPython licence, Tcl/Tk terms and the pinned third-party notices recorded in `native/windows-python-notices.json`, including OpenSSL, libffi, bzip2, XZ/liblzma and zlib. Microsoft release CRT files are copied unmodified from the installed Visual Studio redistributable folder; their identity/hashes and original third-party notices are retained. They remain subject to Microsoft's terms, not the loader's AGPL licence. See the [Microsoft redistribution reference](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution).

Linux packages retain exact Ubuntu package identities, original file hashes, complete package copyright texts and common licence texts under `licenses/linux-system`. These cover CPython, Tcl/Tk/BLT, X.Org, Fontconfig, FreeType, OpenSSL, compression and support libraries. Where FreeType offers a choice, this distribution uses the FreeType Licence (FTL) for the font engine and retains the other applicable permissive component notices. Portions of this software are copyright (C) 1996–2023 The FreeType Project (https://freetype.org/). All rights reserved. The font engine comes from Tk's system dependencies, not the minimal STEP SDK.

The GNU C/C++ runtime libraries (`libstdc++.so.6`, `libgcc_s.so.1`) and glibc are target-system prerequisites for minimal Linux portables and are not bundled. The supported baseline remains Ubuntu 24.04 x86_64/glibc 2.39; a portable does not contain the operating system.

PyInstaller bootloader/runtime exceptions and hook notices are preserved. Exact PyPI source distributions for PyInstaller and pyinstaller-hooks-contrib accompany the converter sdist in the complete source download. All available runtime licence texts remain accessible in the package. See `docs/NATIVE_DEPENDENCIES.md` and the generated dependency/package inventories for scope and verification evidence.
