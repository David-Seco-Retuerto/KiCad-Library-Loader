# Preparing a portable alpha

Version: 0.1.0-alpha.1. Loader licence: AGPL-3.0-only. Copyright (C) 2026 David-Seco-Retuerto.

## Native builds

Build separately on Windows and Linux; PyInstaller is not a cross-compiler. Install `requirements-build.txt` in a dedicated environment. Windows release notices are pinned to Python 3.11.9; Linux uses Ubuntu 24.04 system Python 3.12 with Tk/venv, a C++ compiler and CMake. See [NATIVE_BUILD.md](NATIVE_BUILD.md).

1. Build the SDK using `powershell -File tools/build_native_step.ps1` on Windows or `python tools/build_native_step.py --jobs 4` on Linux. Use persistent native Linux storage, not `/tmp` for the only copy of completed builds.
2. Run `python tools/build_portable.py --native-sdk /absolute/path/to/sdk --online-smoke`. The Windows SDK path is printed by its builder. The normal release path requires `--native-sdk`; `--legacy-ocp` creates development-only candidates with unresolved wheel provenance and must not be published.
3. Review regression, worker, frozen GUI/STEP, native-format and content reports. `--skip-tests` is development-only and remains recorded. The live smoke downloads C2040 through the frozen helper and imports only into temporary libraries.
4. Check SHA256SUMS and extract the complete archive into a writable folder containing spaces. Keep `_internal`, the worker and the native reader together. Verify initial `data` preferences and restart with saved settings. Do not ship personal `data`, input exports, history or backups.

Each portable build uses a unique build/dist directory. No Git command, tag, push or publication is executed. The whitelisted loader source archive includes Python/C++ sources, tests, recipes, docs, licence texts and CI configuration. It excludes assistant instructions, settings, environments, caches and real provider CAD assets. Source ordering and checkout line endings are controlled for matching source bytes across native platforms.

Minimal packages include complete pinned OCCT source, licences/exception and provenance, plus exact PyPI converter/PyInstaller/hooks sdists. Windows runtime notice pins and Ubuntu system-package identities/copyrights are preserved. See [NATIVE_DEPENDENCIES.md](NATIVE_DEPENDENCIES.md). Native filename hints are not automatic legal approval; review actual source/notice evidence.

## Independent validation before publication

The manual `Portable validation` GitHub Actions workflow builds both OS packages and starts them on separate fresh runners. It publishes no release.

1. The owner reviews staging/history for private data and commits/pushes the reviewed code. A private repository is sufficient for this preparation.
2. In GitHub, open Actions, select Portable validation and Run workflow. Its optional live-download checkbox acquires C2040 only for temporary testing.
3. Review both build jobs and both separate launch jobs. Download the two portable artifacts and their evidence. The workflow has been linted locally; it must actually run before its result is claimed.
4. Follow [ALPHA_TESTING.md](ALPHA_TESTING.md) with a disposable KiCad project/output, including schematic-to-PCB/3D checks. Native symbol/footprint CLI exports and mesh tests do not establish electrical correctness.
5. Record tested systems and known limits in the alpha release notes. Hosted runners are fresh development images, not a promise of compatibility with every minimal desktop system. Local WSLg checks do not establish broader Linux desktop coverage.

The supported local baseline is Windows x86_64 and Ubuntu 24.04 x86_64/WSLg with glibc 2.39. Minimal Linux bundles rely on the target OS for glibc, libgcc and libstdc++. ARM, macOS, older glibc and musl/Alpine are unvalidated.

Builds retain `RELEASE_STATUS.txt` and `release_ready=false` while independent-runner/owner acceptance is pending. Do not change flags to manufacture evidence. First publication remains both platforms together as 0.1.0-alpha.1. The owner performs all final Git/tag/release actions.

## Source-only utility

`python tools/source_release.py` can prepare a separate source archive/content report/checksum without distributing native runtime libraries. This utility does not change the agreed first-publication plan for both portables.
