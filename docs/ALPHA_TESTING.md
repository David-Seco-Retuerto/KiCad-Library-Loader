# Alpha acceptance checks

Use a disposable library/output folder and a new test KiCad project. Never use a production project to test update, move, removal or restore. Record the archive SHA-256, OS version, KiCad version and results. Do not include provider CAD files or personal settings in public reports.

## Portable startup

1. Extract the whole package into a writable directory containing spaces. Keep the helper and `_internal` together.
2. Start the main executable from the desktop. Confirm there is no dependency on the development Python environment.
3. Confirm preferences are created under the portable's `data` folder. Choose separate test inputs/output in Settings, save and restart; verify that the choices persist.
4. Open the symbol, footprint and STEP previews. Resize the window and open/close each combobox twice; the left panel should not jump.
5. Switch between Downloads and SamacSys; verify that the Downloads selector disappears without leaving an empty block. Refresh should select the newest ZIP. Automatic ZIP intake must not import to the library.

## Acquisition and native import

1. Open a native SamacSys ZIP obtained by the tester. Confirm independent symbol, footprint and STEP selection and a readable suggested name.
2. Search online and verify the preferred SamacSys portal opens. Browser login/download remains manual.
3. Download one exact LCSC code, such as C2040. Confirm the result is loaded for review, not silently imported. Cancel a second acquisition and verify the GUI remains usable and no library files were written by that cancelled action.
4. Review the plan, acknowledge any explained warnings and import to the disposable output. Repeating the import must not overwrite a conflicting component.
5. In KiCad 9, register the packed symbol file and footprint folder with the reported nickname. In KiCad 10+, repeat using a separate output and the genuine `.kicad_symdir` directory. Register only one symbol format per nickname.
6. Configure the model path variable to the output root when using variable mode. Place the symbol, update a test PCB from the schematic, and open KiCad's 3D viewer. Confirm pins/pads/package and model alignment against the component datasheet.

## Managed changes

1. With a disposable input copy, make a small visible footprint edit and use Review update. Confirm the diff and apply it; verify an update record and backup appear.
2. In Import history, restore that update. Confirm the original component returns and unrelated symbols stay intact.
3. Move a tracked component to another category. Verify the destination reference and history; existing placed schematic/PCB instances are not automatically rewritten.
4. Remove that tracked component, then recover it from history. Verify the recovered assets in KiCad.
5. Change one generated file manually and attempt a managed operation that would replace it. Confirm the tool refuses the unsafe replacement.

## Current evidence and limits

Windows and Ubuntu 24.04 WSLg are the available development/test systems. Tests with a reduced environment on the same machine are relocation/dependency checks, not independent clean-machine tests. No separate clean Windows or Linux desktop system has been validated. Treat that result as pending; never infer it from automated smoke tests.

Portable publication also requires closing the native dependency review in [NATIVE_DEPENDENCIES.md](NATIVE_DEPENDENCIES.md). A source-only alpha does not ship those DLL/shared-library bundles.

## Unattended regression failures

Portable packaging runs `tools/run_regressions.py` with fail-fast discovery, a 600-second subprocess limit and stack dumps every 120 seconds. `build/<platform>/<run>/regression.log` retains the complete output and is included in CI build diagnostics. Windows also runs a ten-minute regression preflight before the expensive native build; the packaging pass after SDK compilation additionally enables the native-helper cases. Normal full local discovery remains `python -m unittest discover -s tests -v`.

Temporary workspaces are resolved before comparing paths so Windows 8.3 aliases such as `RUNNER~1` do not differ from their canonical spelling. Update staging must also resolve its temporary root before translating generated assets to their final output paths.
