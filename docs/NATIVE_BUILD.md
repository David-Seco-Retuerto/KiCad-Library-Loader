# Building the native STEP helper

Minimal portable builds use a small C++ helper linked dynamically to locally built Open CASCADE 7.9.3. Source installations retain the Python/OCP preview. Both produce the same mesh format for the existing Tk viewer.

The full OCCT source archive is pinned by commit and SHA-256 in `native/occt-source.json`; it is downloaded into the ignored `.native-build/downloads/` directory. No Git command is used. The build requests STEP, meshing and a primitive generator for synthetic checks, with recursively required OCCT toolkits. FreeImage, FreeType, VTK, TBB, FFmpeg and Xlib are disabled. Do not infer that other runtime obligations are closed solely from those options.

## Windows compiler prerequisites

`packaging/native-build.vsconfig` selects MSVC x64/x86, Windows 11 SDK 26100 and Visual Studio CMake tools. `tools/install_native_build_tools.ps1` downloads the official Visual Studio 2022 Build Tools bootstrapper, verifies a valid Microsoft signature, and asks Windows for administrator approval. It never restarts the computer automatically and does not change Git. This installs machine-level development tools; the portable's end users will not need them.

Run the script interactively and accept the Microsoft installer/UAC prompts. Then use a new x64 Visual Studio developer environment so CMake, Ninja and MSVC are available. The builder accepts an explicit generator if needed.

## Linux build

With a C++17 compiler and CMake available:

```sh
python3 tools/build_native_step.py --jobs 4
```

Each invocation creates a new build directory; failures leave logs and outputs available for inspection. The resulting `sdk` contains a helper, shared libraries, provenance and the full unchanged OCCT source archive and licence texts. That SDK is a build input, not a complete portable release.

To test the compiled helper:

```sh
KICAD_LOADER_TEST_STEP_HELPER=/absolute/sdk/bin/kicad-step-mesher .venv/bin/python -m unittest discover -s tests -p test_native_step.py -v
```

Checks cover synthetic box size and face winding, non-ASCII paths, invalid inputs and curved-shape agreement with the existing Python reader. Real STEP comparisons, frozen/relocation checks and the runtime notice inventory are part of portable release verification. Independent-runner and owner acceptance remain before publication.

Linux defaults to `~/.cache/kicad-library-loader/native`, a persistent native filesystem location. Keep the build Python environment there as well; `/tmp` was cleared between WSL invocations during verification and must not hold the only copy of completed builds.

On Windows, `powershell -File tools/build_native_step.ps1 -Jobs 4` discovers the installed x64 compiler environment automatically. After changes to only the helper, `-Resume /absolute/existing/build` reuses the owned OCCT build; cached upstream sources must remain unchanged. Normal invocations create a fresh build directory. Logs record each configure/build/install stage. SDKs retain the compiler redistributable identity/hashes on Windows and the complete pinned OCCT archive on both platforms.

## Windows build path length

MSVC can reject a relative OCCT include when its full spelling reaches the Windows path limit, even if the normalized path is shorter and the header exists. The hosted workflow builds under `RUNNER_TEMP/kll-native` instead of the longer checkout directory, and collects diagnostics from that location. The upstream sources are unchanged.

For a deeply nested local checkout, select a short build root explicitly:

```powershell
powershell -File tools/build_native_step.ps1 -Jobs 2 -BuildRoot C:\kll-build
```

The root holds generated compiler outputs; it does not change the application workspace or library output. The resulting SDK is under `<build-root>/windows-x86_64/<run>/sdk`. Supply that SDK path to `tools/build_portable.py --native-sdk` when packaging manually.

## Visual Studio runtime notices

The runtime collector discovers the installed third-party notice inside the selected Visual Studio installation, including Build Tools and Enterprise layouts. It prefers the matching edition and English (1033) when available, preserves the original file bytes and extension, and records its relative installed path and SHA-256 in `WINDOWS-RUNTIME.json`. It does not download a substitute notice or continue without one. Only the x64 release CRT from `VC/Redist/MSVC/<version>/x64/Microsoft.VC143.CRT` is copied; debug and nonredistributable directories remain excluded.
