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

Optional: install KiCad for accurate SVG previews. The application uses `kicad-cli` on PATH first, then checks Windows installations under Program Files and the per-user `%LOCALAPPDATA%/Programs/KiCad` location. Without a PATH override, numeric version ordering selects the newest detected installation.

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

Changing the search provider does not change the active import source. Opening this dialog performs no network requests; only the explicit browser button opens the selected search URL. The loader does not scrape results, sign in, download files or use provider APIs. **Open ZIP…** loads files you have already downloaded. Site availability, login requirements and search results are handled by the website in your browser. Automated tests mock browser launching; a live browser search is a manual check.

Current real-world download and import validation focuses on SamacSys. LCSC remains available, with real-export validation and automatic EasyEDA conversion deferred.

After downloading:

1. For a ZIP containing native KiCad assets, use **Open ZIP…** as described below. Alternatively, extract it yourself into a dedicated folder. EasyEDA or legacy exports still need conversion with the appropriate CAD tool.
2. For already extracted files, click **Use export folder…** in the search dialog to use that folder for its selected provider, or use the same button in the main window for the active source. This saves the provider's input path and refreshes the asset lists. Other provider folders, output paths and categories are preserved. Cancel leaves the current plan and settings intact.
3. If you downloaded into the already configured input folder, click **Refresh** instead. New symbol entries, footprints and STEP filenames are reported in the log; existing selections are retained where possible. Detection happens on refresh, rather than through a background download watcher. Replacements under existing names are rescanned but are not labelled as newly added files.
4. Review the independent asset selections, previews and **Validate / review plan** before importing. Selecting a folder reads files; it does not import them or register anything in KiCad.

**Use export folder…** changes the configured input folder for that provider. It does not merge the folder with previous inputs or move/copy downloaded files. **Open ZIP…** is the separate action that extracts a downloaded archive into the local cache. You can restore a previous input through **Settings…**. Avoid choosing a general Downloads folder containing unrelated or partially downloaded files; use a dedicated, fully extracted export folder. Unsupported containers and formats are reported using the existing scanner.

## Downloads as an input source

Choose **Downloads** in the main **Source** selector to show a list of ZIP files inside the application, newest first. The initial folder is `~/Downloads`; **Folder…** selects another location and remembers it across sessions. The list reads only ZIP filenames directly in that folder. It does not recurse, scan archive contents in the background or include browser partial-download extensions.

Select a ZIP in the dropdown to load its assets, or use **Load ZIP** for the displayed entry. Merely opening Downloads mode or refreshing the list does not extract files. **Refresh** updates the list after another browser download; existing loaded assets still pass through the normal previews, naming, category and format selection, validation and explicit import. Both KiCad output formats remain available.

Downloads is an intake location rather than an online provider. Browser search still uses the current SamacSys or LCSC provider; no download API or automatic browser download is involved. A loaded ZIP uses the same local cache as **Open ZIP…** and replaces that provider's active input folder. Source paths for the other provider and the output library remain unchanged. Choose **SamacSys** or **LCSC** to return to their configured local input folders, or **Use export folder…** to restore a particular folder.

The last successfully loaded archive is retained across restarts so that an unrelated newer ZIP is not displayed as if it supplied the currently loaded component. A failed ZIP load leaves the preceding assets and reviewed plan intact and restores the corresponding selection. If an archive has been moved or removed, its extracted cache may still be used; refresh and choose an available ZIP to load a different component.

Asset dropdowns display symbol names and footprint/STEP filenames rather than complete relative paths. Duplicate names include a source path to distinguish them. Internally the full asset identities are preserved, including manual choices and intentionally empty footprint/model selections.

## Opening downloaded ZIP files

**Open ZIP…** is available in the main window and in **Search online…**. Select a downloaded archive, such as a SamacSys multi-CAD package. The loader extracts native `.kicad_sym`, `.kicad_mod`, `.stp` and `.step` assets while preserving their relative folder paths, plus `license.txt`, `licence.txt` and `part_info.txt` when present. Other CAD formats, PDFs, scripts and installers are not extracted or executed. The original ZIP is left unchanged.

The assets are stored in a unique folder under `<settings-workspace>/.kicad-importer-cache/`. This local vendor cache is excluded from this application's Git source tree and persists across restarts. Opening a ZIP sets that folder as the input for the active source (or the provider selected in the search dialog), saves preferences and refreshes the asset lists. Other source paths, output settings and categories are preserved. Previous cache folders are retained; loading another ZIP does not overwrite them or merge the downloads. To return to a SamacSys Library Loader folder, use **Use export folder…** or **Settings…**.

Opening a ZIP does not write to the output libraries. Review the associations and previews, select a category and choose the symbol format before **Validate / review plan → Import**:

- **KiCad 10+ — Unpacked** writes a genuine `.kicad_symdir` with one `.kicad_sym` file per symbol.
- **KiCad 9 — Packed** writes a grouped `.kicad_sym` library.

The current format choice is preserved when opening an archive. Existing collision and source-protection checks apply to subsequent imports. No SamacSys Library Loader installation is required when the archive already contains these native assets. Archives containing only legacy or other CAD formats are reported as requiring conversion; Open ZIP does not provide that conversion.

Extraction rejects unsafe or duplicate paths, archive links, encrypted selected assets, damaged ZIPs and archives with more than 5,000 entries. Selected assets are limited to 100 MB per file and 250 MB total. Failed extractions are removed. Cancel leaves the active settings and plan unchanged. Cache folders are retained after successful loading so saved input paths remain usable; they can be removed manually once no longer used as an input. Never publish the cache or third-party assets without the appropriate rights.

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

1. Choose **Downloads** to load a ZIP from the download list, or configure folders using **Settings…** and select **SamacSys** or **LCSC**. **Refresh** rescans that source without restarting, preserving valid selections within the same source folder, including intentionally empty selections.
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

## Updating an imported component

Use **Review update…** for an existing component with matching import history. The normal **Import** action still refuses to replace an existing symbol.

1. Load the updated export folder or ZIP and select its symbol, footprint and STEP independently.
2. Choose the same category and symbol output format as the tracked import.
3. Click **Review update…**. The report shows changed files, old/new content hashes and text diffs for symbols and footprints. STEP changes are identified by size/hash; **Existing STEP…** and **Incoming STEP…** open the raw models without footprint transforms.
4. Review the changes and warnings, including pin/pad mapping, package dimensions and 3D alignment. Tick the review checkbox, then **Back up and apply update**. Merely opening or cancelling the review writes no backups or output changes.

The first update workflow keeps the component's existing library nickname, category, symbol format, asset names, model extension and symbol/footprint/model set. A new source geometry name does not rename the existing footprint. Naming choices in the main window do not rename assets during an update. Adding/removing assets, relocating categories, adopting an untracked component, format conversion and applying shared-asset changes remain separate future workflows.

Before an update, recorded destination hashes must match. Missing files, changed MPNs and manual edits are blocked. Packed updates replace only the selected symbol and preserve other symbol definitions. New history records also store a per-symbol fingerprint so a later recorded append does not prevent verifying that symbol. Older packed records without this fingerprint can only be used if the entire library still matches their recorded state; otherwise automatic update is blocked rather than inferred.

Changed footprints/models are blocked if another component or symbol format has used them in the local history. The checker also scans symbol references and model references in the generated output root, including files without import history. Unreadable dependencies or ambiguous ownership stop the update. These conservative checks may require a future separate-copy or migration workflow even if you no longer use a historical reference. They do not inspect every external project, library outside the output root or already placed PCB instance. Both symbol formats are not synchronised automatically.

Applying rechecks the incoming files, destination snapshots, history and dependency folders. If the reviewed plan changes, confirmation is cleared and the refreshed plan must be reviewed again. File/directory changes are rechecked under the existing output lock before writing.

Backups of every changed destination file are written first to `<output-root>/.kicad-loader-backups/<update-id>/`, retaining their paths relative to the output root. A manifest contains the original hashes. A packed symbol backup contains the complete preceding library. Backups, replacements and the new history event participate in the existing rollback mechanism: an I/O failure restores the previous assets and removes newly written transaction files. A power-loss crash is still not atomic across files.

The new history event links to the previous import/update and records its backup folder. Backups persist after success and are excluded by this application's and the original library workspace's ignore rules; configure other output repositories yourself. They contain vendor library data. There is no automatic backup cleanup or restore button yet. Manual restoration requires reviewing later imports first, especially when restoring a whole packed library. Existing schematic/PCB instances must be reviewed and updated through KiCad separately.

## Import history

Click **Import history…** at the bottom of the main window to review imports into the current output library root. Records appear newest first and can be filtered by component, MPN, category, nickname or provider. Select a row to see its source files, original ZIP when recorded, selected symbol format, naming mode, destination files and acknowledged warnings. **Copy details** copies this summary for troubleshooting; **Refresh** rereads the local records.

History starts with successful imports made by this version. It does not reconstruct earlier imports or infer their original provider/download. Changing the output root displays that library's history, independently of the current source folder or workspace preferences.

Each event is stored as a separate JSON file in `<output-root>/.kicad-loader-history/`. It distinguishes newly created files, reused identical footprints/models, and packed symbol libraries updated by appending a new symbol. Output paths are stored relative to the library root with SHA-256 hashes of the contents at import time. Previous hashes are included for existing files. The records contain metadata, not copies of the components or complete backup data.

A history record is included in the same application write plan and lock as its assets. An I/O failure while writing the record triggers the usual rollback, including restoration of a packed library that was just extended. Imports remain non-crash-atomic across multiple files; a power loss can leave incomplete assets or history. The existing recovery cautions still apply.

New **Open ZIP…** extractions retain a local `.loader-archive-origin.json` with the original archive path and SHA-256. Imports from those caches include that provenance in the history. Folder inputs and older caches without this metadata report the original ZIP as unknown. The archive does not need to remain available to browse the record. The GUI also records the chosen provider and input mode; direct core imports retain the source file/folder information without assuming a provider.

History is an import-time snapshot. Files may subsequently be changed, moved, deleted or extended by later packed imports; viewing a record does not verify their current state. Reviewed in-place updates are now available as described above. Component removal, automatic undo/restore, unattended updates and category migration are not implemented.

History is local and excluded by the application's ignore rules and the original library workspace's ignore rules. If you choose another output Git repository, add `.kicad-loader-history/` to its ignore rules if desired; the application does not edit arbitrary repositories. Its records can contain personal source paths. Do not assume it is a transferable package or a backup of your library.

## Checking your KiCad setup

Click **Check KiCad setup…** beside the symbol output controls. Select the KiCad version settings folder, for example `%APPDATA%/kicad/10.0` on Windows. Detected version folders are listed newest first; **Browse…** handles custom locations. Select the current category or **All categories**, then **Run checks**.

Optionally select a **Project folder** to include that project's `sym-lib-table` and `fp-lib-table`. Entries in the project tables override global entries with the same nickname. Without a project selection, only global registrations are checked. Linked `Table` entries are inspected, with cycle and nesting protection.

The report checks:

- Category nicknames and registered symbol/footprint library locations, including a packed/unpacked path mismatch or a disabled entry.
- A folder registered under another nickname, such as `DVL_uCs` when the imported references require `uCs`, with the expected nickname and destination to configure in KiCad.
- The existence of generated library paths and the footprints referenced by their symbols.
- Saved path variables from `kicad_common.json`, overridden by the loader's inherited environment where present; `${KIPRJMOD}` requires a selected project folder.
- Whether the configured portable model variable targets the output root, and whether the actual model references in generated footprints resolve to existing files.
- Unpacked output used with an explicitly selected KiCad version profile older than 10.

**Copy report** copies the findings for troubleshooting. Correct registrations in KiCad using **Preferences → Manage Symbol Libraries**, **Manage Footprint Libraries** or **Configure Paths**, then run checks again. This feature reads configuration and library files; it does not add, rename, register or delete libraries, and does not edit KiCad settings or PCB/schematic files.

An OK result means the inspected saved paths and references match. It does not test native CAD loading, component geometry, electrical correctness, all project instances or pin-to-pad alignment. Unreadable/linked tables are reported; entries in those tables cannot be confirmed. A running KiCad session may have unsaved settings or a different inherited environment. Choose the relevant project and profile to get a useful result. The output format is captured from the main window when the report dialog is opened.

## Supported inputs and limits

- Native `.kicad_sym` libraries, `.kicad_mod` files with a `module` or `footprint` root, and `.stp`/`.step` models are supported in either source folder.
- The available SamacSys files for AD7190BRUZ and NE555DR have been tested. NE555DR's footprint filename differs from its internal name; the component-name fallback handles this case.
- LCSC was empty during development. Native KiCad exports use the same importer; compatibility with unavailable EasyEDA formats is not claimed.
- Legacy `.lib`/`.dcm` files are not automatically converted. When a matching `.kicad_sym` is available, it is used. Otherwise, convert the library with KiCad first.
- EasyEDA JSON, `.epro` and `.elib` are unsupported. ZIP downloads containing native KiCad assets can be loaded with **Open ZIP…**. Folder scanning does not automatically expand ZIPs; it reports them for explicit loading or extraction.
- Symbols using `extends` are blocked to avoid broken dependencies. Export a standalone symbol with KiCad first. Libraries with different format versions must be normalised with KiCad before merging.

## Validation and write safety

Validation checks native syntax, filenames, collisions, references, pin/pad numbers and STEP header/end markers. OpenCascade also checks that previewed STEP models can be read and contain renderable surfaces. Pin/pad mismatches and missing assets require explicit review.

The standard Import action never replaces existing symbols. Duplicate names in the selected library block standard imports, including duplicates in differently named files inside a symdir. Adding a new symbol preserves previous symbols in both layouts. A byte-identical footprint or STEP is reused; different content under the same name blocks a standard import. The separate **Review update…** workflow permits controlled replacement only after the history, reference and backup checks above. Original names can share assets when content and references match; suggested names create component-specific copies.

Writes use an exclusive application lock, destination-change checks, temporary files and rollback on I/O failures. Multi-file imports are not crash-atomic against power loss, and external editors may ignore the lock. Avoid editing destination libraries during import. After a crash, inspect outputs before retrying. Remove a stale `.kicad-importer.lock` only after confirming no other importer is running. Stale `.import-tmp` files are not silently deleted.

Plans are tied to their selected output root, and writing rechecks the destination boundaries and all configured input roots. Input folders may be outside the workspace; they remain read-only. The loader rejects output asset folders that overlap an input and never uses an input folder as temporary workspace.

## Git and third-party licensing

The application ignores local preferences, environments, locks, temporary files, `.kicad-loader-history/` metadata, `.kicad-loader-backups/` and the vendor ZIP cache `.kicad-importer-cache/`. Entire `Imports/`, `Symbols/`, `Footprints/` and `3DModels/` trees at the application root are ignored, including custom category names. Tests use synthetic fixtures; no SamacSys or LCSC models are distributed.

Libraries saved outside this application folder belong to their own workspace. The loader does not change their Git configuration or ignore rules. Review vendor assets and their licences before staging or publishing; version control remains user-managed.

Ignore rules do not untrack previously committed files. Review `git ls-files` and the applicable vendor licences before publishing. Dependencies are installed from their packages rather than vendored into this repository; their own licences continue to apply. Choose a licence for your application code before publishing it.

## Future expansion

Independent input/output paths, configurable categories/library names and explicit folder preparation are implemented. The next steps are:

1. Complete a repeatable manual schematic-to-PCB/3D workflow check. Native KiCad 10.0.7 symdir loading and KiCad 9.0.7 packed loading have passed CLI verification; standalone extraction is implemented.
2. Browser search and explicit downloaded-export folder selection are implemented. Next, check the complete browser/download workflow manually with real exports, using SamacSys; real LCSC validation remains deferred.
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

For native KiCad 10 validation, require the version explicitly:

```powershell
.venv\Scripts\python.exe scripts\verify_local.py --repo C:\path\KiCad-Libraries --require-kicad-major 10
# Override automatic detection, for example with a per-user Windows installation:
.venv\Scripts\python.exe scripts\verify_local.py --repo C:\path\KiCad-Libraries --kicad-cli "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\kicad-cli.exe" --require-kicad-major 10
```

The verifier prints the actual executable and version. Required-version checks fail before importing if the selected executable is absent, unrecognised or too old, and fail if no native symbols are available. Native KiCad 10 checks include loading the entire symdir, rather than only its individual symbol files. Footprint checks request every item by name from its library and require actual SVG output; destination folders are created before invoking KiCad. Synthetic tests exercise these conditions with mocks; the real CLI runs above provide the native validation evidence.

Tests cover associations, naming, references, unchanged sources, collisions, duplicate symbols, identical-file reuse, concurrent changes, rollback, unsupported formats, preferences and the Tk import workflow. Preview regressions cover pin label placement in all four orientations, active-low marks, internal-viewer routing, STEP tessellation, model bounds, rotation and rendering through the subprocess loader. STEP tests require the dependency in `requirements.txt`; GUI tests require Tcl/Tk and a display.

Symbol-layout regressions also cover one-symbol unpacked files, preserving nested units, appending without touching other files, duplicates across filenames, matching/differing copies in the other format, directory changes since validation and rejecting fake downgrades. The Tk test imports into both formats and verifies that the selection persists.

Folder-setting tests cover migration of existing preferences, independent external inputs/outputs, absolute and variable STEP references, source protection, overlap rejection, changing the output after validation, invalid configuration, Cancel/Save behaviour, and persistence across restarts. The directory-link test is skipped on systems where the current user cannot create directory symlinks.

Category tests additionally cover default migration, custom symbol/footprint/model references in both formats, invalid/duplicate names and suffixes, editor persistence, preserving custom categories when changing paths, preview cancellation, preparation without symbol imports, existing-file preservation, conflicts added after preview and preventing a `.kicad_sym` folder in packed mode.

The local verifier defaults to testing **both** layouts, reuses common footprint/STEP outputs, and verifies that original sources are unchanged. KiCad 9.0.7 has validated the packed library and the individual files within the unpacked directory by exporting them to SVG. Native `.kicad_symdir` directory loading was additionally verified with KiCad 10.0.7 on 2026-10-22 using AD7190BRUZ, ESP32-S3-WROOM-1-N4R8 and NE555DR. The verifier tested both symbol layouts, all three footprint library items and OpenCascade STEP previews in temporary outputs; source hashes were unchanged. KiCad 9.0.7 separately passed the packed-only verification. This establishes those CLI checks, rather than a complete GUI placement/PCB update/3D viewer test or exhaustive compatibility.

Workspace-extraction tests cover relative and legacy path migration, custom categories and preferences, source preservation, refusal to replace settings, invalid/missing preferences, and launching the CLI from an unrelated directory.

Browser-search tests cover URL encoding, explicit browser launching, invalid/empty queries and browser errors. Download-handoff tests cover provider-specific path persistence, cancellation, overlap rejection, save failures, unchanged inputs, subsequent validated import, refresh discovery and unsupported ZIP-only folders. They use mocked browser/file-picker calls and synthetic exports.

ZIP regression tests use synthetic multi-CAD archives and cover selective extraction, retained licence metadata, traversal/absolute/device paths, symlinks, duplicate paths, size/count limits, damaged or legacy-only archives, cleanup, Cancel/Save failure behaviour, provider handoff and validated imports in both KiCad output formats. A real NUP2105LT1G SamacSys ZIP was also tested using temporary extraction and output: both layouts, STEP preview and KiCad 9 SVG exports passed. Native directory loading has subsequently passed the KiCad 10.0.7 checks described above.

Downloads and display-label regressions cover shallow ZIP listing, date ordering, partial files, refresh, folder preference persistence, save failures, missing archives, failed-load recovery, restart selection, exact duplicate asset selection and imports in both output formats.

KiCad setup diagnostics tests cover matching and mismatched nicknames/paths, saved and inherited variables, project overrides, disabled libraries, nested and cyclic tables, missing referenced files, malformed/duplicate registrations, symbol layout/version mismatches, the report GUI and read-only behaviour.

History regressions cover import-time destination hashes, created/updated/reused classifications, packed append history, symbol-only records, rollback after metadata write failures, retry without duplicate events, ZIP provenance, older caches, corrupt records and the read-only filtered history browser.

Update regressions cover both symbol formats, exact backups, packed sibling preservation, manual edits, fresh MPN identity, older history limits, recorded/untracked shared assets, other-format sharing, changed dependencies after review, write-failure rollback, stable names/absolute paths and explicit GUI confirmation with re-review on changes.
