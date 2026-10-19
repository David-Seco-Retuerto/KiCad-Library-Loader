# KiCad Library Loader

A Python/Tkinter application for importing native KiCad symbols, footprints and STEP models from local SamacSys or LCSC folders. Select each asset independently, review the plan and import without overwriting existing components. Source files are never modified.

This is the standalone application. Your KiCad libraries and provider downloads can live in separate folders; no library repository or vendor assets are bundled. The source remains in `scripts/`, with tests in `tests/`. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the code map and remaining work.

## Installation

Python 3.10 or newer with Tcl/Tk is required. On Windows, enable Tcl/Tk in the Python installer.

Run all commands in this document from the **repository root**, not from `scripts/`. Dependencies are listed in [`requirements.txt`](requirements.txt), and regression tests live in [`tests/`](tests/).

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\import_gui.py
```

If `.venv` already exists, run only the last two commands. The importer and 2D previews use the standard library. The integrated STEP preview uses `cadquery-ocp-novtk`, the OpenCascade Python bindings without VTK. No external CAD viewer, STEP file association, internet connection or browser is needed for 3D preview after installation.

Optional: install KiCad and expose `kicad-cli` on PATH for accurate SVG previews. The application also checks the usual Windows installation directory under `Program Files/KiCad`.

Alternatively, run `powershell -File .\start_gui.ps1`; it prefers the application's virtual environment. The older `scripts/start_gui.ps1` entry point also works. To use another settings workspace:

```powershell
.venv\Scripts\python.exe scripts\import_gui.py --workspace C:\path\loader-settings
```

`--workspace` (or its compatibility alias `--repo`) selects the existing folder that holds local preferences and supplies the initial default paths. It does not have to contain `Imports/`: open **Settings…** to select exports and a library elsewhere. No Git repository is required at the selected output location.

## Moving from the embedded loader

Create a fresh virtual environment using the installation commands above. Do not copy the old `.venv`. Before launching for the first time, optionally copy your existing preferences:

```powershell
.venv\Scripts\python.exe scripts\migrate_workspace.py --from-workspace C:\path\KiCad-Libraries
powershell -File .\start_gui.ps1
```

The migration copies only `.kicad-importer.json` into this application folder, resolves relative paths against the old workspace and keeps your selected category, naming mode, output format and custom categories. Inputs, output libraries and the original settings stay in place. It refuses to replace existing destination preferences. If the old workspace has no saved preferences, configure **Settings…** in the new application instead.

The default settings workspace is the application folder, independently of the directory from which you launch it. On a fresh installation, choose your library output root in **Settings…** before importing. Migrated settings continue to target the existing library. A different `--workspace` must already exist; it stores its own preferences. The PowerShell launcher also accepts `-Workspace C:\path\loader-settings`.

## Folder settings

Click **Settings…** next to the source controls to configure:

| Setting | Initial default | Meaning |
| --- | --- | --- |
| SamacSys input | `<workspace>/Imports/SamacSys` | Read-only folder containing native exports |
| LCSC input | `<workspace>/Imports/LCSC` | Independent read-only export folder |
| Library output root | `<workspace>` | Parent folder for generated `Symbols/`, `Footprints/` and `3DModels/` |
| 3D model paths | KiCad path variable | Portable variable-based references or absolute file paths |
| KiCad path variable | `DVL_LIB_ROOT` | Custom variable used in portable mode |

Use **Browse…** to choose an existing folder, or type a new folder path. Relative paths are resolved against the settings workspace. Missing input folders are allowed and reported during scanning, which lets you configure an unused provider before downloading any exports. Output folders are created during import or explicitly with **Prepare library folders…**. Files and overlapping input/output asset folders are rejected, including paths resolved through directory links.

**Save settings** stores the paths in the workspace's `.kicad-importer.json`, rescans the active source and invalidates any previous import plan. It does not move, convert or copy existing libraries, register them in KiCad, or create missing input/output folders. **Cancel** leaves the active configuration unchanged. **Restore defaults** fills the dialog with the original layout; changes only take effect when saved.

Existing preferences without a `paths` section retain the original layout and their previous naming mode, custom name, source, category and output format. Invalid saved path settings are reported and block imports until corrected; the loader does not silently overwrite them with defaults.

The main window displays the active input folder and output root. Always review the destination shown by **Validate / review plan**, especially after changing folders. Categories, library names and category-specific 3D folder names are configured separately under **Categories…**. The three top-level output subfolders remain `Symbols/`, `Footprints/` and `3DModels/`.

## Browser search and downloaded exports

Click **Search online…** to enter a manufacturer part number or keyword. The current symbol's MPN is suggested when available. Choose a provider, review the URL and click **Open search in browser**:

- **SamacSys** opens the [SamacSys / Mouser Component Search portal](https://ms.componentsearchengine.com/) using `search.html?searchString=...`. This is the preferred portal for the current manual download workflow. Sign in on that portal first; if login clears a search, click **Open search in browser** again to repeat it.
- **LCSC** opens [LCSC search](https://www.lcsc.com/).

Changing the search provider does not change the active import source. Opening this dialog performs no network requests; only the explicit browser button opens the selected search URL. The loader does not scrape results, sign in, download files or use provider APIs. Site availability, login requirements and search results are handled by the website in your browser. Automated tests mock browser launching; a live browser search is a manual check.

Current real-world download and import validation focuses on SamacSys. LCSC remains available, with real-export validation and automatic EasyEDA conversion deferred.

After downloading:

1. Extract any ZIP archive yourself into a dedicated folder. Use native `.kicad_sym`, `.kicad_mod` and STEP exports. EasyEDA or legacy exports still need conversion with the appropriate CAD tool.
2. Click **Use export folder…** in the search dialog to use that folder for its selected provider, or use the same button in the main window for the active source. This saves the provider's input path and refreshes the asset lists. Other provider folders, output paths and categories are preserved. Cancel leaves the current plan and settings intact.
3. If you downloaded into the already configured input folder, click **Refresh** instead. New symbol entries, footprints and STEP filenames are reported in the log; existing selections are retained where possible. Detection happens on refresh, rather than through a background download watcher. Replacements under existing names are rescanned but are not labelled as newly added files.
4. Review the independent asset selections, previews and **Validate / review plan** before importing. Selecting a folder reads files; it does not import them or register anything in KiCad.

**Use export folder…** changes the configured input folder for that provider. It does not merge the folder with previous inputs or move/copy downloaded files. You can restore a previous input through **Settings…**. Avoid choosing a general Downloads folder containing unrelated or partially downloaded files; use a dedicated, fully extracted export folder. Unsupported containers and formats are reported using the existing scanner.

## Categories and automatic library folders

Open **Categories…** to add, edit or remove categories. The initial categories preserve the original DVL layout:

| Category | Library base name / KiCad nickname | 3D folder |
| --- | --- | --- |
| ICs | DVL_ICs | ICs |
| Connectors | DVL_Connectors | Connectors |
| Power | DVL_Power | Power |
| Misc | DVL_Misc | Misc |

For a custom library, enter for example:

```text
Category: Analog
Library base name: MyLib_Analog
3D folder: Analog_Models
```

Use **New** to clear the editor, then **Add category** to add a row. To change a row, select it, edit the fields and click **Update selected**. For a new category, blank library/3D fields use the category name. **Save categories** saves the table and updates the main category dropdown. Edited fields must be added/updated before saving, so uncommitted edits are not silently lost. **Cancel** discards the dialog changes. At least one category must remain.

Enter **base names only**, without `.pretty`, `.kicad_symdir` or `.kicad_sym`. The loader adds the correct suffixes. It rejects invalid Windows/KiCad characters, path separators, reserved device names, manually entered KiCad suffixes, and duplicate category, library or 3D-folder names, ignoring case. Each field is limited to 100 characters. The library base name is used as the nickname for both symbols and footprints; there is no mandatory `DVL_` prefix.

Categories are saved in `.kicad-importer.json` alongside the path and naming preferences. Older preferences without categories retain the four DVL categories. Editing/removing a category or restoring defaults changes future imports only: existing libraries, symbols, footprints, models and KiCad registrations are never renamed, moved or deleted automatically.

### Preparing folders before importing

After saving categories and selecting **Symbol output** in the main window, click **Prepare library folders…**. The preview lists the output root, all configured categories, exact paths to create/reuse, and existing-library warnings. No folders are created until you click **Create library folders**. A warning acknowledgement is required when another symbol format is already present.

For the example above:

| Asset | Automatically generated destination |
| --- | --- |
| KiCad 10+ symbols | `Symbols/MyLib_Analog.kicad_symdir/` |
| KiCad 9 symbols | `Symbols/MyLib_Analog.kicad_sym` — a file, not a folder |
| Footprints | `Footprints/MyLib_Analog.pretty/` |
| Models | `3DModels/Analog_Models/` |

Preparation creates the unpacked symbol folder in KiCad 10+ mode, the footprint folder, and the normal 3D folder. In KiCad 9 mode it creates only the `Symbols/` parent; the actual `.kicad_sym` file is generated when the first symbol is imported. No fake `.kicad_sym` directories or placeholder symbol files are produced. Imported components also create their required folders automatically, so preparation is optional.

Existing valid folders and file contents are reused without overwriting. A file occupying a required folder path or an invalid existing symbol library blocks preparation. Settings and relevant library contents are checked again before creating folders, and preparation uses the same per-output-root lock as imports. I/O failures may leave empty newly created folders; existing contents remain untouched. Folder preparation does not register the libraries in KiCad.

## Repository layout

```text
Imports/
  SamacSys/
    SamacSys_Parts.kicad_sym
    SamacSys_Parts.pretty/*.kicad_mod
    SamacSys_Parts.3dshapes/*.stp
  LCSC/
Symbols/
Footprints/
3DModels/
scripts/
tests/
```

This is the initial default layout. Each provider's actual input folder and the output root may live elsewhere. Both input folders are scanned recursively. Filenames do not have to match symbol names. This repository ignores imported assets at the default paths; external output folders have their own version-control rules.

## Import workflow

1. Configure folders using **Settings…** if needed, then select **SamacSys** or **LCSC**. **Refresh** rescans that source without restarting, preserving valid selections within the same source folder, including intentionally empty selections.
2. Select a symbol. The importer first matches its Footprint property against available filenames, then tries an exact component name/MPN match. STEP association first uses the footprint's model references, then the component name/MPN. Ambiguous matches remain empty.
3. Select or change the footprint and STEP independently. Switching the symbol or footprint recalculates associations, so review the selections afterwards. Empty means skip that asset. Symbol-only imports are supported; a STEP model requires a footprint.
4. Select a configured destination category. The initial choices are **ICs**, **Connectors**, **Power** and **Misc**; use **Categories…** to define others.
5. Choose **Symbol output**: **KiCad 10+ — Unpacked** (default) or **KiCad 9 — Packed**. Only the selected format is written. The choice persists across components and sessions, and switching it invalidates any previous plan.
6. Choose a naming mode: **Original** uses the footprint's internal name, **Suggestion** (default) combines the MPN with the existing geometry code and description, and **Custom** enables a free-text field. Unknown dimensions are never invented. Naming mode, custom text, source, category and symbol output persist in `.kicad-importer.json`.
7. Review the previews and click **Validate / review plan**. Review the selected format, exact symbol destination, registration instructions and warnings. When warnings are present, check **I have reviewed the warnings and associations** to enable **Import**. Changes to the selection or name invalidate the plan. Inputs and destinations are checked again before writing.

The selected name applies to the footprint and copied STEP model. The symbol's name and Value remain unchanged. For example, the available AD7190 input produces `AD7190BRUZ_SOP65P640X120-24N_RU-24_TSSOP`. Names are limited to 140 characters and must be valid on Windows.

## Previews

### Symbol and footprint

The embedded canvas offers simplified 2D previews. Pin names appear towards the symbol body; pin numbers appear above horizontal pin lines or beside vertical pin lines. Active-low signal marks are retained. Labels adapt to pin spacing and support all four pin directions.

The canvas supports common rectangles, lines, polygons, circles, pins and pads. Symbol units overlap, pads are simplified polygons, and some arcs, text and special shapes are omitted. Use **Symbol SVG (KiCad)** or **Footprint SVG (KiCad)** for an accurate rendering from KiCad. These buttons run `kicad-cli` in the background and open the resulting SVG files in the browser. Preview files live in temporary `dvl-preview-*` folders, which can be removed after closing the browser view.

### STEP models

**Preview STEP in 3D** opens a local, shaded preview window:

- Drag with the left mouse button to rotate.
- Scroll to zoom.
- Use **Isometric**, **Top**, **Front** or **Side** to reset the view.
- The status line reports model dimensions in millimetres and triangle count.

STEP parsing and tessellation run in a separate process with a timeout. Invalid files and missing dependencies produce an English error in the preview window. Models above the lightweight viewer's size limit require a full CAD viewer. Temporary meshes are deleted after loading.

The preview shows the source model's geometry with a neutral material. It does not show original STEP colours or placement on a footprint/PCB. Check final placement, orientation and assembly alignment in KiCad after importing. None of the previews certify a component for manufacture.

## KiCad outputs and configuration

The two symbol output options are shown below using the default ICs category. Custom categories use their configured library base name instead of `DVL_ICs`:

| Symbol output | Destination | Register in KiCad |
| --- | --- | --- |
| **KiCad 10+ — Unpacked** (default) | `Symbols/DVL_ICs.kicad_symdir/<symbol-name>.kicad_sym` | The `DVL_ICs.kicad_symdir` **folder** |
| **KiCad 9 — Packed** | `Symbols/DVL_ICs.kicad_sym` | The `DVL_ICs.kicad_sym` **file** |

Each new unpacked file is a complete native `kicad_symbol_lib` with the original format header and exactly one top-level symbol, including its nested units and graphics. Additional imports create additional files without rewriting existing ones. Existing native files containing multiple symbols can be read when checking duplicates. This follows the [official KiCad 10 unpacked-library structure](https://docs.kicad.org/10.0/en/eeschema/eeschema.html#_unpacked_libraries); it is not an extension rename.

Packed mode appends new symbols to a single category library, preserving the existing symbols. Packing/unpacking does not downgrade the source file's format version. KiCad 9 mode rejects source symbol/footprint versions newer than its supported format; use compatible exports or choose KiCad 10+ instead.

Footprints and STEP models use the same destinations in both modes:

```text
Footprints/DVL_ICs.pretty/<selected-name>.kicad_mod
3DModels/ICs/<selected-name>.stp
```

The same structure applies to the other categories. Existing packed libraries and unpacked directories are preserved. There is no automatic migration, deletion or synchronisation of existing symbol libraries.

These relative paths are created under the **Library output root** selected in Settings, independently of the input folders and the settings workspace. The plan uses a lock in that output root, so two loader instances targeting the same library cannot import simultaneously. Changing the output root affects future imports only; existing libraries stay in place.

In KiCad's **Preferences → Manage Symbol Libraries**, register the selected **folder** (KiCad 10+) or **file** (KiCad 9). In **Preferences → Manage Footprint Libraries**, register the `.pretty` directory. Use the configured **Library base name** as the nickname in both tables: for example `MyLib_Analog`, or `DVL_ICs` for the initial ICs category. The import plan reports both paths and the nickname.

Register only one symbol format under each nickname in a given KiCad library table. If both formats have contents, the plan warns about this. When the same symbol exists in the other format, it reports whether the symbol definitions match or differ, and requires warning acknowledgement. The other format is never updated. Different imports over time can leave the two libraries out of sync; the warning compares symbol definitions, not a full CAD or asset-history comparison. Changing the selector affects future imports only; converting complete existing libraries is a separate, unimplemented operation.

In portable mode, model references use `${DVL_LIB_ROOT}/3DModels/...` by default, or the custom variable chosen in Settings. Set that variable in KiCad to the selected **output root**, not to the loader's installation folder or input folder. In absolute mode, references use the full destination STEP path and do not require a KiCad variable. Absolute paths must be updated if the library is moved to a different location or computer.

KiCad loads the linked STEP automatically when its reference resolves; models do not need their own library-table registration or manual reassignment to each footprint. If the model already appears correctly, no additional model setup is needed in that environment. This application does not create path variables or edit KiCad's library tables or preferences automatically.

If you change output roots and want to keep using an older library, choose **absolute paths** or a **different custom variable** for the new output. Repointing a shared variable such as `DVL_LIB_ROOT` also redirects model references in every older library using it. Switching reference style within an existing output folder does not overwrite conflicting footprint files; the normal collision checks still apply.

The symbol's Footprint property becomes `<library-base-name>:<selected-name>`. The footprint's internal name and value are updated, and its model path points to the copied STEP under the configured 3D folder. Existing model offset/at, scale and rotation are preserved when an association is found. A manually selected model triggers an alignment warning; ambiguous multiple-model transforms block the import. Omitting STEP removes 3D references from the footprint copy to avoid stale links to Imports.

### Adding a generated library to KiCad

Prepare the library folders or import a component first. Packed `.kicad_sym` files require the first import before registration. The examples below use the default **ICs** category; use the nickname and paths shown by the plan for a custom category.

1. Open the **Schematic Editor → Preferences → Manage Symbol Libraries**.
2. Select **Global Libraries** to make the library available in all projects, or **Project Specific Libraries** for the current project only.
3. Add a row and set **Nickname** to `DVL_ICs`, with **Library Format** set to `KiCad`.
4. Set **Library Path** to the appropriate output:
   - **KiCad 10+ — Unpacked:** `<output-root>/Symbols/DVL_ICs.kicad_symdir` (the folder).
   - **KiCad 9 — Packed:** `<output-root>/Symbols/DVL_ICs.kicad_sym` (the file).
5. Confirm with **OK**.

Then open the **PCB Editor → Preferences → Manage Footprint Libraries**, choose the same scope, and add the following row:

| Field | Value |
| --- | --- |
| Nickname | `DVL_ICs` |
| Library Path | `<output-root>/Footprints/DVL_ICs.pretty` |
| Library Format | `KiCad` |

Replace `<output-root>` with the selected Library output root; it is a placeholder, not a KiCad variable. Both library tables use the same nickname. For a given symbol nickname, register only one library location and one symbol format in the active table.

### Checking an import in KiCad

Use a new test project to check the complete chain:

1. Place the imported symbol from `DVL_ICs` in the schematic and check that its **Footprint** field points to `DVL_ICs:<selected-name>`.
2. Save and annotate the schematic, then use **Tools → Update PCB from Schematic** (`F8`). The assigned footprint should load without manual reassignment or missing-library errors.
3. Open **View → 3D Viewer** (`Alt+3`) in the PCB Editor. The linked model should appear automatically. Check its orientation, height and terminal alignment against the pads.
4. Compare pin numbering, pin 1, pad pitch and package dimensions with the component datasheet before using the library in a production design.

A user manual smoke check has confirmed that the import workflow generally works in KiCad and that the linked 3D model loads automatically. This is separate from the automated checks below; it does not establish exhaustive validation of every component or KiCad version.

## Supported inputs and limits

- Native `.kicad_sym` libraries, `.kicad_mod` files with a `module` or `footprint` root, and `.stp`/`.step` models are supported in either source folder.
- The available SamacSys files for AD7190BRUZ and NE555DR have been tested. NE555DR's footprint filename differs from its internal name; the component-name fallback handles this case.
- LCSC was empty during development. Native KiCad exports use the same importer; compatibility with unavailable EasyEDA formats is not claimed.
- Legacy `.lib`/`.dcm` files are not automatically converted. When a matching `.kicad_sym` is available, it is used. Otherwise, convert the library with KiCad first.
- EasyEDA JSON, `.epro`, `.elib` and ZIP containers are detected as unsupported. Export or extract native KiCad files first.
- Symbols using `extends` are blocked to avoid broken dependencies. Export a standalone symbol with KiCad first. Libraries with different format versions must be normalised with KiCad before merging.

## Validation and write safety

Validation checks native syntax, filenames, collisions, references, pin/pad numbers and STEP header/end markers. OpenCascade also checks that previewed STEP models can be read and contain renderable surfaces. Pin/pad mismatches and missing assets require explicit review.

Existing symbols are never replaced. Duplicate names in the selected library block imports, including duplicates in differently named files inside a symdir. Adding a new symbol preserves previous symbols in both layouts. A byte-identical footprint or STEP is reused; different content under the same name blocks the import. Original names can share assets when content and references match; suggested names create component-specific copies.

Writes use an exclusive application lock, destination-change checks, temporary files and rollback on I/O failures. Multi-file imports are not crash-atomic against power loss, and external editors may ignore the lock. Avoid editing destination libraries during import. After a crash, inspect outputs before retrying. Remove a stale `.kicad-importer.lock` only after confirming no other importer is running. Stale `.import-tmp` files are not silently deleted.

Plans are tied to their selected output root, and writing rechecks the destination boundaries and all configured input roots. Input folders may be outside the workspace; they remain read-only. The loader rejects output asset folders that overlap an input and never uses an input folder as temporary workspace.

## Git and third-party licensing

The application ignores local preferences, environments, locks and temporary files. Entire `Imports/`, `Symbols/`, `Footprints/` and `3DModels/` trees at the application root are ignored, including custom category names. Tests use synthetic fixtures; no SamacSys or LCSC models are distributed.

Libraries saved outside this application folder belong to their own workspace. The loader does not change their Git configuration or ignore rules. Review vendor assets and their licences before staging or publishing; version control remains user-managed.

Ignore rules do not untrack previously committed files. Review `git ls-files` and the applicable vendor licences before publishing. Dependencies are installed from their packages rather than vendored into this repository; their own licences continue to apply. Choose a licence for your application code before publishing it.

## Future expansion

Independent input/output paths, configurable categories/library names and explicit folder preparation are implemented. The next steps are:

1. Complete independent-installation smoke checks and native KiCad 10 directory verification. The standalone folder extraction is implemented; repository creation remains user-managed.
2. Browser search and explicit downloaded-export folder selection are implemented. Next, check the complete browser/download workflow manually with real exports, including LCSC.
3. Standalone publication, followed by KiCad plugin packaging.
4. Provider-specific API search and downloads, subject to available access.

`providers.py` contains the local source adapters, with stable identifiers and a shared native-file scanning contract. It separates provider selection from the GUI and output settings. These adapters build browser search links and scan local exports. They perform no HTTP requests or downloads; native KiCad exports remain required.

## Testing

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
# Optional: read local vendor files; import and render only in a temporary directory:
.venv\Scripts\python.exe scripts\verify_local.py --repo C:\path\KiCad-Libraries
# Test only one layout:
.venv\Scripts\python.exe scripts\verify_local.py --repo C:\path\KiCad-Libraries --format unpacked
# Use native exports outside the workspace (output still goes only to a temporary folder):
.venv\Scripts\python.exe scripts\verify_local.py --repo C:\path\KiCad-Libraries --samacsys-dir C:\exports\SamacSys --lcsc-dir C:\exports\LCSC
# Verify custom category paths, folder preparation and imports (temporary output only):
.venv\Scripts\python.exe scripts\verify_local.py --repo C:\path\KiCad-Libraries --category Analog --library-name MyLib_Analog --model-folder Analog_Models
```

Tests cover associations, naming, references, unchanged sources, collisions, duplicate symbols, identical-file reuse, concurrent changes, rollback, unsupported formats, preferences and the Tk import workflow. Preview regressions cover pin label placement in all four orientations, active-low marks, internal-viewer routing, STEP tessellation, model bounds, rotation and rendering through the subprocess loader. STEP tests require the dependency in `requirements.txt`; GUI tests require Tcl/Tk and a display.

Symbol-layout regressions also cover one-symbol unpacked files, preserving nested units, appending without touching other files, duplicates across filenames, matching/differing copies in the other format, directory changes since validation and rejecting fake downgrades. The Tk test imports into both formats and verifies that the selection persists.

Folder-setting tests cover migration of existing preferences, independent external inputs/outputs, absolute and variable STEP references, source protection, overlap rejection, changing the output after validation, invalid configuration, Cancel/Save behaviour, and persistence across restarts. The directory-link test is skipped on systems where the current user cannot create directory symlinks.

Category tests additionally cover default migration, custom symbol/footprint/model references in both formats, invalid/duplicate names and suffixes, editor persistence, preserving custom categories when changing paths, preview cancellation, preparation without symbol imports, existing-file preservation, conflicts added after preview and preventing a `.kicad_sym` folder in packed mode.

The local verifier defaults to testing **both** layouts, reuses common footprint/STEP outputs, and verifies that original sources are unchanged. KiCad 9.0.7 has validated the packed library and the individual files within the unpacked directory by exporting them to SVG. Native `.kicad_symdir` directory loading requires KiCad 10+, which was not installed in the development environment. If a KiCad 10+ CLI is found, the verifier additionally tests loading the directory as a library; otherwise it explicitly reports that this check was not run.

Workspace-extraction tests cover relative and legacy path migration, custom categories and preferences, source preservation, refusal to replace settings, invalid/missing preferences, and launching the CLI from an unrelated directory.

Browser-search tests cover URL encoding, explicit browser launching, invalid/empty queries and browser errors. Download-handoff tests cover provider-specific path persistence, cancellation, overlap rejection, save failures, unchanged inputs, subsequent validated import, refresh discovery and unsupported ZIP-only folders. They use mocked browser/file-picker calls and synthetic exports.
