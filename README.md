# KiCad Library Loader

A Python/Tkinter application for importing native KiCad symbols, footprints and STEP models from local SamacSys or LCSC folders, downloaded ZIPs, or integrated LCSC acquisition through easyeda2kicad. Select each asset independently, review the plan and import without overwriting existing components. Source files are never modified.

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

Changing the search provider does not change the active import source. Opening this dialog performs no network requests; only the explicit browser button opens the selected search URL. The browser-search action does not scrape results, sign in or download files. The separate **Download LCSC…** action can invoke a converter installed with the loader as described below. **Open ZIP…** loads files you have already downloaded. Site availability, login requirements and search results are handled by the website in your browser. Automated tests mock browser launching; a live browser search is a manual check.

SamacSys native ZIP imports and a single LCSC/EasyEDA component (RP2040, C2040) have been checked. This is limited sample coverage; it does not establish availability or correctness for every component.

After downloading:

1. For a ZIP containing native KiCad assets, use **Open ZIP…** as described below. Alternatively, extract it yourself into a dedicated folder. EasyEDA or legacy exports still need conversion with the appropriate CAD tool.
2. For already extracted files, click **Use export folder…** in the search dialog to use that folder for its selected provider, or use the same button in the main window for the active source. This saves the provider's input path and refreshes the asset lists. Other provider folders, output paths and categories are preserved. Cancel leaves the current plan and settings intact.
3. If you downloaded into the already configured input folder, click **Refresh** instead. New symbol entries, footprints and STEP filenames are reported in the log; existing selections are retained where possible. Export-folder detection happens on Refresh. Replacements under existing names are rescanned but are not labelled as newly added files. Downloads mode also offers the optional passive Auto-refresh list described below.
4. Review the independent asset selections, previews and **Validate / review plan** before importing. Selecting a folder reads files; it does not import them or register anything in KiCad.

**Use export folder…** changes the configured input folder for that provider. It does not merge the folder with previous inputs or move/copy downloaded files. **Open ZIP…** is the separate action that extracts a downloaded archive into the local cache. You can restore a previous input through **Settings…**. Avoid choosing a general Downloads folder containing unrelated or partially downloaded files; use a dedicated, fully extracted export folder. Unsupported containers and formats are reported using the existing scanner.

## Downloading one LCSC component

**Download LCSC…** in the main window obtains one exact LCSC part using **easyeda2kicad 1.0.1**, installed automatically with the loader requirements. It is also available in **Search online…** when LCSC is selected. Browser search remains permanently available for choosing manufacturer/package variants.

No separate converter environment or executable selection is required. Existing installations can update the loader environment from the repository root:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

1. Click **Download LCSC…**. By default the loader resolves the converter from the same Python environment as the running application, without searching PATH or personal folders. Old saved external executable paths do not activate an override automatically.
2. Enter one exact part code, such as `C2040`. MPN searches, arbitrary URLs, multiple-part requests and command arguments are not accepted here. Use **Search online…** to find the correct code/package first.
3. Click **Download and load for review**. This explicitly starts the loader-installed converter (or your enabled advanced override) with `--full --lcsc_id <code> --output <unique-cache-prefix>` without a shell or overwrite flag. The GUI remains responsive and offers cancellation; progress indicates activity, not a measured percentage.
4. On success, the LCSC input switches to the new native assets. Other provider folders, output root, categories and chosen KiCad format are preserved. Review the component, symbol/pin/pad mapping, footprint dimensions and STEP alignment, then use the normal validation and **Import**. Downloading never imports automatically.

**Use an external converter (advanced)** is available for testing another installation. Enable it explicitly, then choose its executable; the mode and path are remembered locally. This setting is normally off. A missing default dependency reports the command to update loader requirements; the application does not install software or access the network merely by opening the dialog. The converter runs as a separate process to keep cancellation and the GUI responsive; users do not need to manage a second venv.

[easyeda2kicad](https://github.com/uPesy/easyeda2kicad.py) is third-party software developed by uPesy and contributors, declared AGPL-3.0 by release 1.0.1. It is installed as a normal pinned dependency, with its licence and attribution retained in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [the included licence text](licenses/easyeda2kicad-AGPL-3.0.txt). No converter implementation has been copied into the loader scripts. Full installer packaging, application licensing and matching source distribution remain release-preparation work.

The dependency's provider interface and service access remain distinct from native import support. No provider credentials or browser cookies are requested or stored by the loader. The sample worked without a credential prompt; availability and account requirements may differ for other parts or service versions.

Each run creates `<settings-workspace>/.kicad-importer-cache/lcsc-<unique-id>/`, with `assets/` and a converter log. The child process runs in that directory. Successful caches persist so review and import can continue later. Failed/cancelled runs are cleaned within that bounded cache, and the previously loaded input/reviewed plan remains unchanged. A timeout stops a slow converter. Size/entry checks reject excessive local output; these checks do not sandbox an arbitrary executable or control its HTTP transport. Closing the download dialog during a run requests cancellation; closing the application also cancels the worker.

Before loading, native symbols/footprints must parse and the generated symbol's `LCSC Part` field must match the requested code. A missing or ambiguous STEP is reported, not fabricated. A WRL model reference can auto-select a unique STEP with the same basename; duplicates leave the selection empty for explicit review. The importer uses STEP, retains the selected reference transform and does not convert WRL geometry into STEP. Check alignment, since equivalent model filenames do not guarantee identical coordinate systems.

A local `.loader-acquisition.json` records the code, converter version when reported, retrieval time and original generated file hashes. Successful imports include that provenance in history, separately from ZIP provenance. These are acquisition-time hashes, not a certificate that source files have never changed afterwards. Caches and vendor assets remain excluded from source control. Existing download/update/restore protections still apply.

This first integration is an explicit single-code workflow. It does not provide an in-app online results catalog, unattended polling, bulk downloads, automatic authentication or direct SamacSys downloading. It relies on the external tool's provider interfaces, which are not claimed to be an official supported standalone API. See the roadmap and provider-specific feasibility notes for the remaining work.

## Downloads as an input source

Enable **Auto-refresh** in Downloads mode to check the selected folder every three seconds while the application is open. The option is off initially and remembered between sessions. It updates only the ZIP list and a separate status message; it preserves the selected ZIP when available, loaded assets and any reviewed import plan. If the selected ZIP disappears, the dropdown becomes empty; already extracted assets remain available. Polling pauses outside Downloads mode and during a busy preview operation. Missing or temporarily unreadable folders show a status message and are retried.

**Auto-refresh alone** does not extract or import anything, open a browser, or certify download completion. The separate session-only **Auto-load new ZIPs** option can extract and load new arrivals for review, as described below. A `.zip` may still be downloading; incomplete extensions such as `.crdownload` are excluded. Select a ZIP or click **Load ZIP** to read it through the normal archive validation. The main **Refresh** button in Downloads mode explicitly loads the newest ZIP, even when another component is loaded. With Auto-refresh alone, replacing a ZIP under the same name does not reload its assets automatically. The watcher stops when the application closes.

Choose **Downloads** in the main **Source** selector to show a list of ZIP files inside the application, newest first. The initial folder is `~/Downloads`; **Folder…** selects another location and remembers it across sessions. The list reads only ZIP filenames directly in that folder. It does not recurse, scan archive contents in the background or include browser partial-download extensions.

Select a ZIP in the dropdown to load its assets, or use **Load ZIP** for the displayed entry. Merely opening Downloads mode or a passive list refresh does not extract files. Clicking the main **Refresh** button explicitly requests loading the newest ZIP. **Refresh** orders ZIPs by file modification time (newest first) and loads the first ZIP; existing loaded assets still pass through the normal previews, naming, category and format selection, validation and explicit import. Both KiCad output formats remain available.

Downloads is an intake location rather than an online provider. Browser search still uses the current SamacSys or LCSC provider; listing Downloads does not invoke a download API or start a browser download. Direct LCSC acquisition is a separate explicit action. A loaded ZIP uses the same local cache as **Open ZIP…** and replaces that provider's active input folder. Source paths for the other provider and the output library remain unchanged. Choose **SamacSys** or **LCSC** to return to their configured local input folders, or **Use export folder…** to restore a particular folder.

The last successfully loaded archive is retained across restarts so that an unrelated newer ZIP is not displayed as if it supplied the currently loaded component. A failed ZIP load leaves the preceding assets and reviewed plan intact and restores the corresponding selection. If an archive has been moved or removed, its extracted cache may still be used; refresh and choose an available ZIP to load a different component.

Asset dropdowns display symbol names and footprint/STEP filenames rather than complete relative paths. Duplicate names include a source path to distinguish them. Internally the full asset identities are preserved, including manual choices and intentionally empty footprint/model selections.

## Automatically loading new browser downloads

For the SamacSys browser workflow, open **Search online…**, open the preferred search in your browser, then click **Watch Downloads for new ZIPs**. This selects Downloads for that provider, closes the search dialog and arms **Auto-load new ZIPs**. Alternatively, select Downloads and tick **Auto-load new ZIPs** in the main window. Use **Folder…** to choose the browser's download folder.

This option is off at every application start and is not persisted. Enabling it also enables Auto-refresh. ZIPs already present when watching starts are a baseline and are skipped. New ZIP filenames or replacements observed afterwards are candidates. Selecting another source/folder, manual ZIP loading, or disabling/rearming the option resets pending arrivals; existing files are baselined again rather than unexpectedly loaded. Disabling Auto-refresh also disables automatic loading.

A candidate must have a nonzero size and unchanged size/modification time for at least six seconds across the normal three-second polls. Browser sidecars such as `.zip.crdownload`, `.zip.part` and `.zip.download` defer loading. This is a completion heuristic, not a browser completion event: ZIP/native-content validation and before/after file-hash/stat checks are also required. Automatic loading rejects ZIPs over 250 MB; manual Open ZIP retains its existing selected-asset limits.

Extraction and hashing run in a background thread. Current ZIP-cache boundaries, selected-file limits and path protections apply. Only native symbols, footprints, STEP and supported notices/metadata are extracted; ZIPs with no readable native symbol are skipped. No requests are made to SamacSys by this watcher, and no account credentials or browser cookies are accessed.

When valid, the new assets become the active provider input and the ZIP provenance is retained. This replaces the main-window component selection and invalidates the previous import review/acknowledgement. It **does not import into your library**: inspect the symbol, footprint and model, validate the plan, then explicitly Import. If several candidates are ready together, the newest by modification time is chosen; older pending candidates are dropped after a successful load rather than cycling through components. Further newer arrivals can still be processed.

Automatic loading waits while another loader dialog is open or the app is busy. Source/option changes and application closure cancel or discard an in-flight result. Unsupported/broken ZIPs and failed preference saves leave the preceding component/review intact; a separate status message explains the failure without repeated modal errors. A rejected unchanged ZIP is not retried continuously; use Load ZIP manually or replace the file to retry.

**Manual Refresh is separate:** in Downloads mode it attempts the newest listed ZIP immediately, even if it predates this watching session. If it is incomplete or invalid, an error is shown and the previously loaded component/review is retained. Outside Downloads, Refresh continues to rescan the selected export folder.

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

The first update workflow keeps the component's existing library nickname, category, symbol format, asset names, model extension and symbol/footprint/model set. A new source geometry name does not rename the existing footprint. Naming choices in the main window do not rename assets during an update. Adding/removing assets, adopting an untracked component, format conversion and applying shared-asset changes remain separate future workflows. Moving a tracked component to another category uses the separate history workflow below.

Before an update, recorded destination hashes must match. Missing files, changed MPNs and manual edits are blocked. Packed updates replace only the selected symbol and preserve other symbol definitions. New history records also store a per-symbol fingerprint so a later recorded append does not prevent verifying that symbol. Older packed records without this fingerprint can only be used if the entire library still matches their recorded state; otherwise automatic update is blocked rather than inferred.

Changed footprints/models are blocked if another component or symbol format has used them in the local history. The checker also scans symbol references and model references in the generated output root, including files without import history. Unreadable dependencies or ambiguous ownership stop the update. These conservative checks may require a future separate-copy or migration workflow even if you no longer use a historical reference. They do not inspect every external project, library outside the output root or already placed PCB instance. Both symbol formats are not synchronised automatically.

Applying rechecks the incoming files, destination snapshots, history and dependency folders. If the reviewed plan changes, confirmation is cleared and the refreshed plan must be reviewed again. File/directory changes are rechecked under the existing output lock before writing.

Backups of every changed destination file are written first to `<output-root>/.kicad-loader-backups/<update-id>/`, retaining their paths relative to the output root. A manifest contains the original hashes. A packed symbol backup contains the complete preceding library. Backups, replacements and the new history event participate in the existing rollback mechanism: an I/O failure restores the previous assets and removes newly written transaction files. A power-loss crash is still not atomic across files.

The new history event links to the previous import/update and records its backup folder. Backups persist after success and are excluded by this application's and the original library workspace's ignore rules; configure other output repositories yourself. They contain vendor library data. Use the reviewed restoration workflow below to revert the latest component update. There is no automatic backup cleanup. Do not replace a whole packed library from a backup without accounting for later imports. Existing schematic/PCB instances must be reviewed and updated through KiCad separately.

## Restoring the previous component version

1. Open **Import history…** and select the update you want to revert.
2. Click **Restore…**. Only the latest recorded operation for that component may be an update to restore; initial imports, an already restored update and older superseded updates are blocked.
3. Review the file diffs, model hashes and warnings. **Existing STEP…** and **Restored STEP…** preview raw models without footprint transforms. The restored model is read from its verified backup, so the original download is not required.
4. Tick the review checkbox, then **Back up and restore**. Opening or cancelling the review does not change assets, history or backups.

Restoration verifies the selected update, previous version, backup manifest and file hashes. Manual edits, missing files, modified backups, ambiguous history or shared changed footprints/models block the operation. It keeps the same asset set, names, locations and symbol format. Checks use history and references under the selected output root; they do not inspect external libraries/projects or already placed instances.

For packed `.kicad_sym` libraries, only the selected symbol definition is restored into the current library. Other symbols, including ones appended after the update, are preserved. The entire current library must match its latest recorded file hash and the selected symbol must match its fingerprint. Older insufficient history is blocked rather than guessed. Unpacked `.kicad_symdir` output restores the tracked symbol file.

Applying rebuilds the plan and clears confirmation if the reviewed state changes. File snapshots, backup data, history and dependency folders are checked again under the output lock. Current changed files are backed up before restoration, and a new `restore` history event links the reverted update and restored version. Original history and backups remain available; restoring does not delete any component. An I/O failure rolls back the transaction; an abrupt power loss is not atomic across files. Empty transaction folders may remain after a failed write.

This restoration workflow does not offer redo, multiple-step undo, removal, undoing a category move or format conversion. After a restore, a new **Review update…** can update the component again using a selected export. Library restoration does not change already placed schematic or PCB instances; review and update those separately in KiCad.

## Move a component to another category

1. Open **Import history…** for the output root containing the component.
2. Select its latest active record and click **Move to category…**.
3. Choose a configured destination category, then **Review move…**.
4. Review destination paths, source removals, retained shared assets, diffs and warnings. Tick the review checkbox and click **Back up and move**. Choosing a category or cancelling the review writes nothing.
5. Register the destination symbol and footprint libraries in KiCad under the displayed nickname if needed. Review and reassign existing schematic/PCB library references separately; the loader does not rewrite projects.

A move preserves component/footprint/model names and the current native symbol layout: packed `.kicad_sym` stays packed; genuine `.kicad_symdir` stays unpacked. The destination symbol's Footprint property and the copied footprint's STEP path are adjusted. STEP bytes, footprint geometry and model transforms are preserved. The current output settings determine whether the new STEP reference uses the configured path variable or an absolute path. No format conversion or synchronisation of other copies occurs.

Only verified, currently tracked components can move. Missing files, manual edits, insufficient older packed history, unreadable dependencies and symbols with inherited dependants block the move. The destination category must use distinct library and model-folder names. An existing destination symbol blocks the move; footprint/STEP files are reused only if their complete contents match. Other packed-library symbols are preserved. Moving the last packed symbol leaves a valid empty source library; empty folders are retained.

Shared source footprints/models are retained using active history and references within the output root. Unshared source files are removed after backup; a packed source symbol is removed from its library rather than deleting that library. External projects, libraries outside the output root and already placed instances are not inspected. They may still use the old symbol nickname or retained assets, so review those assignments before moving a component used in a design.

Changed or removed files are backed up first under `.kicad-loader-backups/`. A linked `move` event records both categories and source-file changes; original ZIP/acquisition provenance is retained without requiring the original download. Apply rebuilds and rechecks the plan, history, files and dependency folders under the application lock. I/O failures roll back writes and removals; power loss is not atomic across files. Backups contain vendor data and have no automatic cleanup.

The current **Restore…** action reverts updates only, not moves. You can select the new active history record and review a move back if its validation and collision checks pass. Automatic move undo and adopting untracked components remain future work. Reviewed removal and recovery are available below.

## Remove and recover a component

1. Open **Import history…** and select the latest active record for the component.
2. Click **Remove component…**. Review the files to remove, shared resources to retain, diffs and warnings.
3. Tick the review checkbox and click **Back up and remove**. Opening or cancelling the review changes nothing.
4. To recover it, select its removal event and click **Recover removed…**, review the recovery plan, tick the checkbox and click **Recover component**.

Removal supports both packed KiCad 9 libraries and genuine KiCad 10+ symdir libraries. It removes only the chosen symbol/definition, preserving other symbols and empty libraries/folders. Footprint/STEP files are removed only if active history and references within the selected output root do not identify another user. Shared assets stay in place. Missing/manual changes, insufficient older packed history, unreadable dependencies or inherited dependants block the operation. The loader does not adopt untracked components.

Every removed/changed file is backed up before modification under `.kicad-loader-backups/`; a removal event retires the component in local history and records retained/changed/removed paths. Keep both the history and backups. They contain vendor data and may contain personal paths; the application's ignore rules exclude them, but other output repositories need their own ignore rules. No original downloaded export is needed for removal or recovery.

Recovery verifies the latest removal, its preceding component version, manifest and backup hashes, retained resources, destination names and current recorded packed-library contents. It restores only the selected packed symbol, preserving later recorded sibling imports. An existing symbol or different footprint/STEP file blocks recovery; byte-identical footprint/STEP files may be reused. Missing or edited retained resources and modified/missing backups also block recovery. A recovered or reimported component cannot be recovered again from an older removal event. Recovery adds a new active history event and keeps the removal event/backups.

Both actions rebuild the reviewed plan before applying and check history, files and relevant directories again under the application lock. Recovery backs up a current packed library before adding the recovered symbol. I/O failures roll back asset, metadata and removal changes. Power loss is not atomic across files; empty transaction folders may remain after failures. Backup cleanup is manual.

Existing projects, libraries outside the output root and already placed schematic/PCB instances are not inspected or rewritten. They may still reference a removed symbol or resource. Review affected designs in KiCad before removal, and check their assignments after recovery. Other symbol-format copies are not synchronised. This workflow recovers a tracked removal; it is not a general multi-step undo, move undo or disaster-recovery wizard.

## Import history

Click **Import history…** at the bottom of the main window to review imports into the current output library root. Records appear newest first and can be filtered by component, MPN, category, nickname or provider. Select a row to see its source files, original ZIP when recorded, selected symbol format, naming mode, destination files and acknowledged warnings. **Copy details** copies this summary for troubleshooting; **Refresh** rereads the local records.

History starts with successful imports made by this version. It does not reconstruct earlier imports or infer their original provider/download. Changing the output root displays that library's history, independently of the current source folder or workspace preferences.

Each event is stored as a separate JSON file in `<output-root>/.kicad-loader-history/`. It distinguishes newly created files, reused identical footprints/models, and packed symbol libraries updated by appending a new symbol. Output paths are stored relative to the library root with SHA-256 hashes of the contents at import time. Previous hashes are included for existing files. The records contain metadata, not copies of the components or complete backup data.

A history record is included in the same application write plan and lock as its assets. An I/O failure while writing the record triggers the usual rollback, including restoration of a packed library that was just extended. Imports remain non-crash-atomic across multiple files; a power loss can leave incomplete assets or history. The existing recovery cautions still apply.

New **Open ZIP…** extractions retain a local `.loader-archive-origin.json` with the original archive path and SHA-256. Imports from those caches include that provenance in the history. Folder inputs and older caches without this metadata report the original ZIP as unknown. The archive does not need to remain available to browse the record. The GUI also records the chosen provider and input mode; direct core imports retain the source file/folder information without assuming a provider.

History is an import-time snapshot. Files may subsequently be changed, moved, deleted or extended by later packed imports; viewing a record does not verify their current state. Reviewed in-place updates are now available as described above. Reviewed restoration of the latest component update is described above. Reviewed category moves are also available above. Reviewed removal and recovery are also available above. Unattended updates and automatic adoption of untracked components are not implemented.

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
2. Browser search and explicit downloaded-export folder selection are implemented. Next, check the complete browser/download workflow manually with real exports, using SamacSys. Optional automatic native ZIP intake is implemented, with the browser retaining control of website downloads. The first LCSC C2040 acquisition/GUI/native-output check has passed; broader real-part coverage is still needed.
3. Standalone publication, followed by KiCad plugin packaging.
4. Provider-specific API search and downloads, subject to available access.

`providers.py` contains the local source adapters, with stable identifiers and a shared native-file scanning contract. It separates provider selection from the GUI and output settings. These adapters build browser search links and scan local exports. They perform no HTTP requests or downloads; native KiCad assets remain required at the import boundary. The separate acquisition module can obtain those assets through an external converter.

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

## Roadmap: direct online acquisition

See the dated [SamacSys feasibility review](docs/SAMACSYS_INTEGRATION.md) for official sources, confirmed findings and open access questions. No self-service download API contract was located in the inspected public documentation; provider confirmation is the next prerequisite. This does not mean no API exists. The published website terms also include automation restrictions, so the browser account is not treated as sufficient integration permission.

An initial explicit LCSC-code download through easyeda2kicad installed with the loader is implemented above. Broader integrated online search/direct acquisition remains planned, separate from browser search and the passive Downloads list. The intended flow is: search by MPN, choose the exact manufacturer/package/variant, download the available native symbol/footprint/STEP assets into the local cache, then review and explicitly import them through the existing validation pipeline.

- Start by investigating a supported SamacSys integration, including available provider interfaces, authentication, access and redistribution conditions. API availability or download permission is not assumed.
- Add explicit download progress, cancellation, partial-download handling, archive validation and provenance. Downloads must never import silently or include provider assets in this source repository.
- Broaden the initial LCSC/easyeda2kicad integration with more real-part coverage and provider-access clarification, then evaluate other providers where supported. SamacSys direct acquisition remains unimplemented.
- Keep **Search online…** permanently, including after direct downloads are implemented, so users can browse alternative packages and variants manually. A supported browser/download handoff remains useful where a provider has no suitable integration.

Direct acquisition and provider feasibility are explicit milestones alongside release preparation. A future KiCad plugin can expose the same importer and acquisition workflow; it does not replace the standalone application.

Category-move verification (2026-10-23): 230 regression tests ran, 229 passed and the existing Windows directory-symlink privilege test was skipped. Sixteen new tests cover both native layouts, sharing, collisions/manual edits, inherited dependants, source/destination races, backup/write/deletion rollback, subsequent updates/restoration, move-back and explicit GUI confirmation. A real NUP2105LT1G ZIP was extracted/imported/moved only in temporary libraries: KiCad 9.0.7 packed and KiCad 10.0.7 native-directory symbol/footprint SVG exports passed, and the moved STEP rendered with OpenCascade (612 triangles). Exact backups matched; the original ZIP and extracted input bytes were unchanged. A full interactive schematic/PCB/3D workflow remains a manual check.

Removal/recovery verification (2026-10-23): 247 tests ran, 246 passed and one existing Windows directory-symlink privilege test was skipped. Seventeen new synthetic regressions cover both layouts, exact backups/recovery, sharing, inherited dependants, collisions/manual edits, history/dependency races, backup/write/deletion rollback, later packed appends, subsequent move/update/restore workflows, source-independent provenance and explicit GUI confirmation. Real NUP2105LT1G temporary import → removal → recovery returned all asset bytes exactly; KiCad 9.0.7 packed and KiCad 10.0.7 native-directory symbol/footprint SVG exports and STEP tessellation (612 triangles) passed. Original ZIP/input bytes, production libraries and user preferences were unchanged.
