# Portable dependency preparation

## Minimal STEP SDK delivery

The release path uses the small native STEP helper and a locally compiled OCCT SDK. Source/notice preparation is implemented and locally tested. Independent-runner validation and owner acceptance remain required before publication; this is not a claim that a separate clean target system has already passed.

| Component | Included evidence and delivery |
| --- | --- |
| Loader Python/C++ code | AGPL-3.0-only; complete loader source/build/test archive accompanies each binary. |
| OCCT 7.9.3 | Exact commit `a016080bf6738d6aeae020badee4e888ad1540a5`, archive SHA-256 pinned in `native/occt-source.json`, no source patches; full source archive, LGPL 2.1, exception and configuration provenance included. Shared libraries can be rebuilt/replaced. |
| easyeda2kicad 1.0.1 | Upstream AGPL notice and exact PyPI sdist, hash-verified before inclusion. |
| PyInstaller / hooks | Bootloader exception and hook licences retained; exact PyPI sdists and installed metadata/notices included. |
| Windows CPython 3.11.9 and dependencies | Runtime versions checked at build time; official CPython dependency commits, notice URLs and byte hashes pinned in `native/windows-python-notices.json`; original Python/Tcl/Tk notices retained. |
| Windows C++ CRT | Unmodified release x64 CRT from the compiler's redistributable directory, with version/file hashes and original third-party notices. No debug runtime or Visual Studio installation is shipped. [Microsoft distributable-code list](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution). |
| Linux runtime | Exact installed Ubuntu binary/source package versions, original file hashes, copyright texts and common licences under `licenses/linux-system`. FreeType uses FTL with attribution in THIRD_PARTY_NOTICES.md; preserve the additional permissive notices. |
| Target OS | Windows 10+ x86_64 or Ubuntu 24.04 x86_64 baseline. Linux glibc/libgcc/libstdc++ remain system prerequisites; their shared libraries are not bundled by the minimal mode. |

OCCT is configured without FreeImage, FreeType, VTK, TBB, FFmpeg or Xlib. Recursively required OCCT toolkits may still include OCCT visualization interfaces; this is not a claim that the build consists of a single toolkit. The C++ helper only exposes STEP-to-mesh and synthetic test-fixture generation. The frozen worker retains explicit LCSC acquisition separately.

The full OCCT source is included rather than relying on a changing default branch or a future written offer. Rebuilding instructions, CMake files and the helper source accompany the loader source. See [NATIVE_BUILD.md](NATIVE_BUILD.md).

## Verification

`NATIVE_DEPENDENCIES.json` records shipped native file hashes with family hints. Those hints are not automatic licence approval. `DEPENDENCIES.json`, `BUILD_PROVENANCE.json`, `WINDOWS-RUNTIME.json` / `WINDOWS-PYTHON-RUNTIME.json` and `SYSTEM_PACKAGES.json` provide separate origin/notice evidence. Archive content checks reject local settings, caches and assistant instructions from source delivery. Source line endings/order are fixed so native platforms can ship identical application source bytes.

Local tests check box bounds/winding, non-ASCII paths, invalid STEP rejection, curved-shape agreement, real SamacSys mesh agreement, frozen GUI/STEP operation, native KiCad formats and explicit LCSC acquisition. Separate GitHub Actions launch jobs are prepared but must actually run before their result is claimed. Manual schematic/PCB acceptance remains an owner task; neither a mesh preview nor a passing test suite establishes electrical correctness.

## Legacy OCP candidates

Source installations and the development-only `--legacy-ocp` path still use `cadquery-ocp-novtk` 7.9.3.1.1. Its wheel includes an image/codec stack with incomplete immutable transitive provenance. Those legacy portable candidates remain unapproved for publication. The minimal SDK path avoids distributing that stack rather than guessing its versions or copying only generic notices.
