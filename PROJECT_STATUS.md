# Project status

The loader has been extracted from the library repository into an independent application folder. No Git repository is created by the extraction. The original embedded scripts remain a legacy snapshot until the owner removes them.

## Implemented

- Independent source and output folders; local SamacSys and LCSC provider adapters.
- Independent asset selection, naming preferences, validation and collision protection.
- Refreshed English main window: scrollable source/assets/destination cards, simultaneous symbol/footprint previews above a grouped/color-coded review report, expanded drawings, direct library tools and persistent import actions.
- Packed KiCad 9 and unpacked KiCad 10+ symbol output with rewritten references.
- Configurable categories and explicit folder preparation.
- Symbol/footprint previews and an integrated STEP viewer.
- Persistent local preferences and a non-overwriting settings migration utility.
- Browser search for SamacSys / Component Search Engine and LCSC, explicit export-folder selection and new-asset notices on refresh.
- Open ZIP for native KiCad downloads, selective extraction into an ignored persistent cache, and review/import through either output format.
- Downloads source with a newest-first ZIP list, main Refresh loading the newest ZIP, optional passive auto-refresh and session-only automatic loading of stable new native ZIP arrivals.
- Explicit single-code LCSC download through the easyeda2kicad dependency installed with the loader, with cancellable background work, isolated native cache, review handoff and acquisition provenance.
- Concise asset labels, with disambiguation for duplicate names and unchanged internal file identities.
- Read-only KiCad setup diagnostics: global/project/linked tables, nicknames, paths, footprint references and model variables/files.
- Import history browser with transactional per-import records, output hashes, file action classification and original ZIP provenance for new extractions.
- Controlled in-place updates with explicit diffs/confirmation, stable names, backup manifests, history linkage and manual-edit/shared-asset protection.
- Reviewed restoration of the latest component update, preserving packed-library siblings and backing up the current files before restoring.
- Reviewed category moves for tracked components, with reference changes, shared-resource retention, source-file backups/removal and linked history in both native symbol formats.
- Reviewed component removal and recovery, with shared-resource retention, verified backups, removal tombstones and source-independent recovery in both formats.

## Code map

- `scripts/import_gui.py`: Tk application and CLI entry point.
- `scripts/gui_layout.py`: shared ttk presentation and main workflow layout, independent of import planning.
- `scripts/report_text.py`: semantic report blocks and line colors; no import-plan mutations.
- `scripts/library_core.py`: scanning, syntax, associations, plans and writes.
- `scripts/library_layout.py`, `loader_settings.py`: categories, paths and validation.
- `scripts/providers.py`: local provider contract and encoded browser search URLs.
- `scripts/search_dialog.py`: browser search and download-folder handoff.
- `scripts/lcsc_download.py`, `lcsc_dialog.py`: external single-code acquisition, bounded cache handling and responsive download/review handoff.
- `scripts/input_choices.py`: asset display labels and shallow date-ordered download listing.
- `scripts/download_watch.py`: session arrival tracking and stable/hash-checked native ZIP preparation.
- `scripts/archive_import.py`: bounded native ZIP extraction and managed cache cleanup on failure.
- `scripts/step_preview.py`: OpenCascade tessellation and preview support.
- `scripts/kicad_diagnostics.py`, `diagnostics_dialog.py`: saved KiCad configuration and asset reference reports.
- `scripts/import_history.py`, `history_dialog.py`: provenance records and a history browser with reviewed restoration.
- `scripts/component_updates.py`, `update_dialog.py`: tracked replacement planning, dependency checks and review/apply UI.
- `scripts/component_restore.py`: verified backup restoration of the latest component update.
- `scripts/component_lifecycle.py`: shared tracked-component verification and local ownership/reference checks.
- `scripts/component_move.py`, `move_dialog.py`: tracked category relocation and destination selection.
- `scripts/component_remove.py`: reviewed removal and verified recovery of removed components.
- `scripts/verify_local.py`: optional real-export verification with temporary outputs.
- `tests/`: synthetic core and GUI regression tests.

## Next milestones

1. Try the refreshed main window with real Downloads/provider workflows and confirm the new grouping and minimum-window layout are comfortable. The first interface cleanup is implemented; gather feedback before expanding the visual redesign to secondary dialogs.
2. Complete a documented manual schematic/PCB/3D check, including updates, restoration, category moves and removal/recovery. Native KiCad 9.0.7 packed and KiCad 10.0.7 directory loading have passed CLI verification; broaden real-part coverage for SamacSys and LCSC.
3. Prepare a public alpha: choose an application licence, versioning, packaging and dependency/source notices; document the supported lifecycle and recovery limits.
4. **Direct online acquisition remains planned.** The initial explicit LCSC/easyeda2kicad download is implemented; broaden real-part coverage, clarify provider access and evaluate in-app result/package selection. For SamacSys, obtain confirmation of a supported interface, authentication, access and integration terms before implementing downloads. Findings and open questions are in [docs/SAMACSYS_INTEGRATION.md](docs/SAMACSYS_INTEGRATION.md). Downloaded assets must go through review and validation, without silent library imports.
5. **Keep manual Search online permanently**, including the preferred SamacSys portal and Downloads handoff, to choose alternative packages/variants. Check authenticated browser/download behaviour manually.
6. Evaluate KiCad plugin integration using the same core workflows; retain the standalone application.

KiCad 9 can validate packed symbols and individual unpacked symbol files, but cannot establish native KiCad 10 directory compatibility. Tests do not replace component datasheet checks. Multi-file imports use rollback for I/O failures but are not crash-atomic.

## Extraction verification (2026-10-19)

- A fresh Windows Python 3.11 virtual environment was created and requirements installed from binary packages.
- 78 regression tests ran: 77 passed; one directory-symlink test was skipped because Windows did not grant symlink creation privileges.
- The independent GUI started with migrated local preferences and retained the existing library/input paths and the custom UCs category. The original workspace settings were unchanged.
- Real AD7190BRUZ and NE555DR exports were imported in both formats into temporary custom-category output. STEP tessellation and KiCad 9.0.7 symbol/footprint SVG exports passed; input hashes were unchanged.
- No vendor input/output trees, virtual environment from the original workspace, or Git history were copied. The independent environment and local preferences are ignored.
- Native KiCad 10 directory loading and real LCSC exports remain unverified.

## Browser handoff verification (2026-10-19)

89 regression tests ran: 88 passed, with the existing Windows directory-symlink privilege skip. Eleven new tests exercise browser search and downloaded-export selection using mocked browser/file-picker calls and synthetic files, including a subsequent validated import into temporary output. No real download, account login or live browser result validation was performed. Browser search is an explicit handoff; provider APIs, automatic ZIP extraction and background watching are not implemented.

## Preferred SamacSys browser portal

Manual searches now use `https://ms.componentsearchengine.com/search.html?searchString=...`, matching the portal preferred by the user. Its public form and a public NE555DR results URL were checked. Queries use percent-encoded spaces because the portal decodes parameters with `decodeURIComponent`. Authenticated login/download behaviour remains a manual check; no user session was accessed. The application retains the query in the search dialog so it can be reopened after website login if necessary.

## Native ZIP intake verification

A real NUP2105LT1G SamacSys multi-CAD ZIP was opened using the new extractor in a temporary settings workspace. Only its native symbol, footprint, STEP and licence/part metadata were extracted. The normal import pipeline generated packed and unpacked outputs, rendered the STEP and exported symbol/footprint SVGs with KiCad 9.0.7. The original ZIP was unchanged and production libraries were not modified. KiCad 10 native directory loading remains pending.

Fourteen synthetic archive/GUI regression tests additionally cover extraction boundaries and failure handling, persisted input selection and preserving the chosen KiCad output format. Downloads and browsing remain manual; Open ZIP handles an already downloaded native archive without requiring SamacSys Library Loader.

## Next integration step

Check KiCad setup is now available as a read-only diagnostic. Automatic library-table registration and changes to KiCad preferences are not implemented. Native KiCad 10.0.7 directory loading has now passed CLI verification (2026-10-22); the configuration report itself does not perform or establish CAD loading. Import history is implemented. Controlled updates are implemented with additional current-file/reference checks. Reviewed restoration of the latest update is now implemented. Reviewed category migration is now implemented (2026-10-23); initial-import undo and removal remain future work.

## Import history implementation

Successful imports now commit a new local metadata record alongside their assets. New ZIP extractions retain archive path/hash provenance in the ignored cache. Existing pre-feature imports are not reconstructed. Records can be viewed and filtered for the current output root; no delete/undo/update action is provided yet. The history directory is excluded in both the application and original library workspace ignore files. No Git operations were performed.

## Native KiCad 9/10 validation — 2026-10-22

- Found KiCad 10.0.7 in a per-user Windows installation. CLI discovery now includes this location and compares numeric versions; PATH remains an explicit priority.
- Added `--kicad-cli` and `--require-kicad-major` to the local verifier. A required version cannot silently fall back to KiCad 9, and an empty input cannot pass the required native checks.
- Real SamacSys AD7190BRUZ, ESP32-S3-WROOM-1-N4R8 and NE555DR: six temporary imports (both formats), SVG export of the packed library, individual unpacked files and native symdir directory all passed with KiCad 10.0.7. Each of the three footprints was exported by name from the generated library. STEP surfaces were checked with OpenCascade. Source hashes were unchanged.
- A separate KiCad 9.0.7 run passed three packed imports, symbol/footprint SVGs and STEP preview checks.
- Fixed verifier SVG destination preparation: KiCad 10 footprint export needed an existing output directory. No component geometry change was required.
- 140 regression tests ran: 139 passed; the existing Windows directory-symlink privilege test was skipped. Eight new tests cover discovery and verifier preconditions/commands; mocked CLI tests are distinct from the real CAD runs.
- Existing production libraries, schematics and PCB files were not used as write targets. A full interactive schematic placement → PCB update → 3D viewer workflow remains a manual check. This supersedes earlier entries saying native directory loading was unverified.
- Controlled component updates are now implemented (see below). Next development candidates: managed category migration, safe restore/removal, and automatic download detection after further real-world update testing.

## Controlled component updates — 2026-10-22

- Review update keeps the tracked asset names, category, format and asset set. It requires matching history and protects recorded manual changes. New per-symbol fingerprints allow packed updates after recorded appends; older insufficient packed history is blocked explicitly.
- Shared changed assets are blocked using local history and reference scanning under the output root. The checker does not claim complete knowledge of external projects or already placed instances.
- Review shows text diffs and model hashes, with raw STEP preview controls. Apply requires explicit confirmation and rebuilds the plan; changes invalidate confirmation. Backups are committed before replacements under the existing lock, with dependency snapshots and I/O rollback.
- Backups are ignored in the independent application and original library workspace. No Git operations or production-library update were performed.
- 159 tests ran: 158 passed, one Windows symlink-privilege skip. Nineteen new update tests cover scope, identity, shared/manual changes, dependency races, backup/history write failures, preservation and GUI review behaviour.
- Real NUP2105LT1G ZIP validation modified only temporary extracted copies to simulate symbol/footprint/model revisions. Both formats updated successfully, exact original backups matched, history was linked, native symbols/footprints reloaded using KiCad 10.0.7 (unpacked directory) and 9.0.7 (packed), and updated STEP contents rendered with OpenCascade. The downloaded archive remained unchanged.
- Not included: shared-asset replacement, asset addition/removal, category migration, format conversion, automatic adoption of older untracked components or a restore/undo wizard.

## Passive Downloads auto-refresh — 2026-10-22

- Optional remembered Auto-refresh checks the Downloads ZIP list every three seconds while the application is open. It does not load, extract or import files and does not replace a reviewed plan or the selected component.
- Polling preserves available selections, clears a removed selection, detects size/timestamp changes, reports folder errors separately from the import report, and retries. It pauses outside Downloads mode or while the application is busy and cancels its callback on window destruction.
- Listing a ZIP does not guarantee download completion; explicit loading retains the existing archive validation. No new dependencies or provider assets are included.
- 164 regression tests ran: 163 passed, one existing Windows symlink-privilege skip. Five new GUI tests cover passive discovery/replacement, selection removal, opt-in/provider/busy behaviour, error recovery, preference persistence and callback cancellation. No production libraries were changed.

## Reviewed component restoration — 2026-10-22

- Import history now offers Restore for update records. Planning verifies the latest component operation, predecessor identity/MPN, native output layout, backup manifest and hashes, current file hashes and packed symbol fingerprints. Restoring already superseded/restored updates, initial imports, missing/corrupt backups, manual edits and shared changed assets is blocked.
- Packed restoration merges only the selected previous symbol into the current library, preserving subsequent appends. Unpacked restoration retains the native symbol file. Both retain asset names and paths; source exports are not needed and prior archive provenance is preserved.
- Explicit review uses text diffs/model hashes and existing/restored raw STEP previews. Apply rebuilds the plan and rechecks dependency snapshots; current changed files are backed up first, with a linked restore history event and I/O rollback. Existing designs and external references are not automatically updated/inspected.
- No redo, repeated undo, initial-import removal, automatic adoption or category migration is included. Empty transaction folders can remain after a write failure; multi-file writes remain non-crash-atomic.
- Direct online CAD acquisition is explicitly listed above, starting with SamacSys feasibility and retaining manual Search online permanently.
- 180 regression tests ran: 179 passed, one existing Windows symlink-privilege skip. Sixteen new restoration tests cover exact recovery in both formats, packed appends/manual changes, backup integrity and races, sharing, source-independent provenance, I/O rollback and explicit GUI confirmation/re-review.
- Real NUP2105LT1G verification used only a temporary extracted source and separate temporary output roots: import, simulated update and restore returned all asset bytes exactly; linked history, KiCad 9.0.7 packed and KiCad 10.0.7 native-directory symbol/footprint SVG loading, and STEP tessellation passed. The original ZIP hash was unchanged. Production libraries and Git were not modified.

## SamacSys acquisition feasibility — 2026-10-22

- Reviewed official Component Search Engine/Mouser portal documentation, published service terms, Supplyframe's SamacSys page and historical API/integration announcement. Findings and source links are in [docs/SAMACSYS_INTEGRATION.md](docs/SAMACSYS_INTEGRATION.md).
- No self-service native CAD-download API contract was located in the inspected public sources. This does not establish that no API exists. A normal account and free browser downloads do not by themselves establish API access.
- Published Component Search Engine terms contain automation restrictions. Next confirm a supported integration and applicable permission with SamacSys/Supplyframe; the report lists the concrete questions and official contact route. No enquiry was sent.
- Direct acquisition remains a planned feature. No network client, speculative endpoints, account handling or placeholder download controls were added. Browser search and explicit ZIP intake remain operational and are retained in the future design.
- Documentation-only change; no new code tests were needed. The preceding 180-test result applies to the unchanged application code. No vendor assets, credentials, personal paths, Git operations or production-library writes were involved in this review.

## First LCSC acquisition integration — 2026-10-22

- Download LCSC accepts one exact C-number and invokes a separately installed easyeda2kicad executable without a shell/overwrite flag, in a unique ignored cache. Executable configuration is local; no personal path is a source-code default and no new package dependency is bundled.
- Background work uses a queue to update Tk only on its main thread, with cancellation/timeout/process termination and application-close cancellation. Failed runs or failed input handoffs preserve the preceding settings/review; successful runs load native assets but never import automatically.
- Native symbol/footprint parsing and an exact generated LCSC Part field are required. Missing STEP is reported. A WRL reference can associate a unique STEP basename while ambiguous matches remain empty for review; transforms are preserved and must be checked.
- Local acquisition metadata records C-number, reported converter version, retrieval time and generated-file hashes; new history records include it separately from ZIP origin, and restoration preserves prior provenance.
- Browser search remains available permanently. This first integration provides no in-app online result catalog, bulk requests, automatic login or SamacSys downloader. The external tool's provider access and licensing remain distinct from native import support.
- Live C2040 (RP2040) download was exercised through the new Tk dialog using the separately installed easyeda2kicad 1.0.1. Symbol/footprint/STEP selections were automatic, no import occurred on download, and subsequent temporary imports retained acquisition history. KiCad 9.0.7 packed and KiCad 10.0.7 native symdir/footprint SVG loading passed; STEP tessellation produced 8,460 triangles. App preferences and production libraries were unchanged.
- Final regression suite: 198 tests, 197 passed and the existing Windows symlink-privilege test skipped. Eighteen new synthetic tests cover validation, external CLI arguments, cache/provenance, process failures, cancellation/timeout, native-output identity, size limits, WRL/STEP ambiguity and GUI handoff/persistence failures. A progress animation callback leak found during closure checks was removed; progress now uses the existing cancelled-on-close Tk polling callback. No Git operations were performed.

## Automatic local ZIP intake and newest Refresh — 2026-10-22

- Main Refresh in Downloads explicitly loads the newest ZIP by modification time, retaining the preceding component/review on load failure. Passive list refresh and internal rescans remain non-loading.
- Auto-load new ZIPs is opt-in per session, enabling list polling and baselining existing files. New/replaced ZIPs wait six stable seconds, known partial sidecars and native ZIP validation; before/after hash/stat checks reject changing input. Extraction runs off the Tk thread and retains original archives/provenance.
- Search online offers Watch Downloads for new ZIPs. The browser performs the website search/download; this adds no SamacSys HTTP client or login handling. Imported library writes still require explicit validation and Import.
- Mode/folder/manual-load changes reset pending arrivals; inactive or closed contexts discard in-flight extraction. Loader dialogs defer automatic handoff. Invalid ZIPs or preference errors report a status and preserve the preceding review without repeated modal dialogs. Automatic intake has a 250 MB archive-size cap; existing extraction limits still apply.
- Validation: 210 regression tests ran, 209 passed and the existing Windows symlink-privilege test was skipped. Twelve new tests cover newest Refresh and failure preservation, arrival baselines/stability/replacements, partial sidecars, changing archives, invalid ZIP rejection, session-only arming and GUI deferral/cancellation.
- A real NUP2105LT1G SamacSys ZIP was copied into a temporary browser-download folder after arming the GUI watcher. It loaded symbol/footprint/STEP automatically for review without writing a library. The original ZIP hash, production libraries and app preferences were unchanged; all test cache/settings/output paths were temporary.

## Loader-managed easyeda2kicad dependency — 2026-10-22

- Added easyeda2kicad 1.0.1 to requirements and installed it into this application's own virtual environment. pip check reports no broken requirements. The separate test venv remains unchanged and is no longer needed for normal use.
- Download LCSC resolves only the running Python environment's scripts directory by default; it does not pick a different PATH tool. The dialog now starts with the C-number field and hides executable selection behind an explicit advanced external-converter option. Old saved paths alone do not enable that override.
- Retained subprocess cancellation/cache/review behaviour. Mode and override path are saved locally; missing dependencies explain how to update the loader environment.
- Added converter attribution and the unmodified AGPL licence text shipped by the installed release. This is not completion of the full release/installer licence inventory or source-delivery requirements.
- Validation: 214 regression tests, 213 passed and one existing Windows symlink-privilege skip. Four added tests cover own-environment resolution, ignoring legacy saved external paths by default, setup errors without launch and explicit override persistence. A live GUI C2040 download passed with no executable selection and no external venv, auto-selecting symbol/footprint/STEP into a temporary cache without importing. Production libraries and user preferences were unchanged; no Git operations were performed.

## Reviewed category moves — 2026-10-23

- Import history now offers **Move to category…** for the latest active component record. Destination selection leads to explicit review, diffs/warnings and confirmation. Settings changes or changed dependencies invalidate the reviewed plan.
- Moves preserve names and the selected native format, copy/reuse destination footprint/STEP assets, change symbol/3D references and retain geometry/transforms. Other packed symbols are preserved; an empty packed source library and empty folders are retained. Differing destination files, duplicate symbols, manual edits, ambiguous history and inherited dependants are blocked.
- Source footprint/model sharing is checked against active history and generated-library references. Shared files remain; unshared files are removed only after exact backups. External projects/libraries and already placed instances are not scanned or rewritten; users must review/reassign old nicknames in KiCad and register destination libraries as needed.
- The move event preserves ZIP/acquisition provenance and records source changes as well as destination hashes. Current-component tracking retires the source identity; later sibling updates/restoration and moving back remain supported when checks pass. No automatic move undo, removal wizard or format conversion is included; Restore still applies only to updates.
- Backup, destination, history and source-removal actions participate in I/O rollback under the output lock. Power loss remains non-atomic. No production libraries, preferences or Git state were modified.
- Validation: **230 regression tests, 229 passed, one existing Windows symlink-privilege skip**. Sixteen new move tests cover preservation/sharing, collisions/manual changes, dependency races, backup/write/deletion failure recovery, update/restore after moves, source-independent move-back and GUI confirmation/settings guards.
- Real NUP2105LT1G validation used only temporary extraction and separate temporary output roots. Both native layouts imported and moved successfully; exact backups and linked history matched. KiCad 9.0.7 packed and KiCad 10.0.7 native-directory symbol/footprint SVG exports passed; moved STEP tessellation produced 612 triangles. The downloaded ZIP and extracted inputs were unchanged. Interactive schematic-to-PCB reassignment remains a manual check.

## Reviewed removal and recovery — 2026-10-23

- Import history offers **Remove component…** for the latest active component and **Recover removed…** for its latest removal. Both use explicit review/confirmation, rebuild checks and settings-change guards. Opening/cancelling review does not write assets, history or backups.
- Shared lifecycle verification is reused by moves and removals: recorded hashes/symbol fingerprints, native layouts, protected inputs, history and generated-library reference snapshots. Active history/reference sharing retains source footprint/model assets. Inherited dependants and unreadable/missing/manually edited assets block removal; external projects/libraries are not scanned or rewritten.
- Removal backs up changed/deleted files before removing a selected packed definition or unpacked symbol and unshared footprint/STEP files. Other packed symbols, empty libraries and folders remain. A linked tombstone event retires the component; stale update/move/removal records cannot act on it.
- Recovery verifies the latest removal, predecessor, manifest/hashes and current destinations. It preserves later recorded packed appends, restores exact component content and can reuse identical footprint/STEP files. Existing symbols, differing assets, edited/missing retained assets or damaged backups block recovery. Original ZIPs/exports are not required; provenance is retained. Recovered components can subsequently update/move/remove normally.
- Writes, metadata, backups and deletions use the existing lock and I/O rollback. Recovery backs up an existing packed library first. Multi-file operations remain non-crash-atomic; no general multi-step undo, move undo, automatic backup cleanup or adoption of untracked components is added.
- Seventeen new synthetic tests cover both layouts, sharing, manual edits/collisions, inherited dependants, races, backup/write/deletion failures, move/remove/recover/update integration, packed appends and GUI confirmation/settings guards.
- Real NUP2105LT1G validation used temporary extraction and separate output roots only. Import → remove → recover returned every asset byte exactly; backups/history/provenance matched. KiCad 9.0.7 packed and KiCad 10.0.7 native-directory symbol/footprint SVG exports passed; STEP preview produced 612 triangles. The original ZIP and extracted inputs were unchanged; production libraries, user preferences and Git were untouched.
- Next development priority: interface cleanup and visual polish. Broader interactive schematic/PCB/3D validation, release preparation and online-acquisition improvements remain on the roadmap.

- Final regression suite: **247 tests, 246 passed, one existing Windows directory-symlink privilege skip**. The user also reported the preceding category-move feature validated; this does not substitute for the broader interactive CAD checklist.

## Main-window interface refresh — 2026-10-23

- Source, independent asset selection and destination/naming now live in numbered left-column cards with scrolling and focus visibility. The right workspace gives full-height Symbol, Footprint and Review plan tabs. Validate/import explicitly select the report tab; acknowledgement/import controls remain outside the scrollable form.
- Added an English ttk palette/type hierarchy, status summaries, empty preview states, asset/CLI-aware preview controls and a read-only locations window. Library tools groups existing folder/category/preparation/diagnostic actions; import history stays directly accessible. Existing download selection, watching/acquisition, updates and lifecycle controls remain available.
- Expanded simplified drawings open in a separate resizable window without invalidating selection/confirmation. Canvas geometry fits smaller visible panes. Approximation limits and exact SVG alternatives remain explicit; STEP rendering and native import formats are unchanged.
- Visual iteration caught an unreadably short report in a split layout at minimum size; final tabs give both report and drawing the full available height. Seven GUI regressions cover review gating/invalidation, empty previews/tabs, menu routing, non-mutating locations/expanded views, minimum-window reachability and Downloads visibility. Existing tests continue to cover actual temporary imports and safety workflows.
- Desktop inspection used AD7190BRUZ from a read-only provider folder and temporary settings/output roots only. No production library writes, saved user preference changes, vendor assets added to source, dependencies or Git operations were involved. This is a presentation change, not a new claim of full schematic/PCB validation.

- Final verification: **254 tests ran, 253 passed, one existing Windows directory-symlink privilege test skipped**. Desktop checks of the final tabbed layout included a 1000 × 680 client window, Downloads controls and explicit validation opening the readable full-height report. Native CAD loading evidence from preceding changes remains separate from these presentation checks.

## Interface feedback revision — 2026-10-23

- Replaced the tabbed experiment with simultaneous symbol and footprint previews above an adjustable report pane, as requested. Expanded drawings and exact SVG controls remain available.
- Fixed the leftover Source gap after leaving Downloads by hiding the entire wrapper, not just its packed children; repeated source-switch tests verify its height returns to baseline.
- Destination shows the actual symbol ID and separate footprint/STEP filenames for Original, Suggestion and Custom, matching the planned asset names/extensions. Omitted files are clearly marked. Naming algorithms and native import formats are unchanged.
- Added visible button borders. Settings, Categories, Check KiCad setup and Import history are direct header buttons. Categories now has Save & prepare folders: successful save is required before opening the existing folder preview; no implicit folder creation is added.
- Main report text uses black generic information, green success, orange warnings and red errors. Blank lines separate paths, model configuration, symbols, registration, writes, warnings and results. Filename substrings do not determine severity; source messages and transaction/history data remain unchanged.
- Existing GUI tests were adapted and four new regressions cover wrapper shrinking, names matching actual plans, report preservation/colors/spacing and save-before-preparation. Windows inspection used the read-only AD7190BRUZ input and temporary settings/output only. Production libraries, user preferences and Git remain untouched.

Final feedback-revision verification: **258 tests ran, 257 passed, one existing Windows directory-symlink privilege skip**. Desktop inspection confirmed bordered source buttons, simultaneous drawings, the report below, three explicit output values and grouped report text. Validation was exercised only in a temporary output workspace; no production import or Git operation was performed.

## Compact naming and combobox focus correction — 2026-10-23

- Suggestions retain MPN + specific vendor geometry without appending redundant package aliases, case numbers or revision prose. Normalised duplicate MPN/geometry names collapse to one identity. Generic/component-only footprint names can use a recognised compact package label from their description. No dimensions or package identity are guessed from pad count.
- Names exceeding 100 characters use a deterministic hash suffix instead of blind truncation; Original/Custom and tracked update naming behaviour remain unchanged. Existing library files are not renamed.
- Combobox popup focus also reaches ancestor frames. Focus scrolling now requires keyboard Tab/Shift-Tab navigation and the event target to be the actual focused control. Mouse opening/closing of combos no longer scrolls; keyboard access still reveals off-screen fields. Key bindings respect the Windows/X11 difference.
- Four naming tests and two GUI regressions were added. Final suite: **264 tests, 263 passed, one existing Windows directory-symlink privilege skip**. The real NUP2105LT1G ZIP produced NUP2105LT1G_SOT96P237X111-3N in temporary packed and unpacked imports with consistent internal references and an unchanged archive hash. No production libraries, user preferences or Git were changed.
