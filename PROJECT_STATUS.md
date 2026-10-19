# Project status

The loader has been extracted from the library repository into an independent application folder. No Git repository is created by the extraction. The original embedded scripts remain a legacy snapshot until the owner removes them.

## Implemented

- Independent source and output folders; local SamacSys and LCSC provider adapters.
- Independent asset selection, naming preferences, validation and collision protection.
- Packed KiCad 9 and unpacked KiCad 10+ symbol output with rewritten references.
- Configurable categories and explicit folder preparation.
- Symbol/footprint previews and an integrated STEP viewer.
- Persistent local preferences and a non-overwriting settings migration utility.
- Browser search for SamacSys / Component Search Engine and LCSC, explicit export-folder selection and new-asset notices on refresh.
- Open ZIP for native KiCad downloads, selective extraction into an ignored persistent cache, and review/import through either output format.
- Downloads source with an in-app ZIP list, configurable remembered folder and refresh.
- Concise asset labels, with disambiguation for duplicate names and unchanged internal file identities.

## Code map

- `scripts/import_gui.py`: Tk application and CLI entry point.
- `scripts/library_core.py`: scanning, syntax, associations, plans and writes.
- `scripts/library_layout.py`, `loader_settings.py`: categories, paths and validation.
- `scripts/providers.py`: local provider contract and encoded browser search URLs.
- `scripts/search_dialog.py`: browser search and download-folder handoff.
- `scripts/input_choices.py`: asset display labels and shallow date-ordered download listing.
- `scripts/archive_import.py`: bounded native ZIP extraction and managed cache cleanup on failure.
- `scripts/step_preview.py`: OpenCascade tessellation and preview support.
- `scripts/verify_local.py`: optional real-export verification with temporary outputs.
- `tests/`: synthetic core and GUI regression tests.

## Next milestones

1. Manual launch and import check from the independent installation; validate native symdir directory loading with KiCad 10+.
2. Use SamacSys for current real-world validations. Real LCSC export validation and EasyEDA download/conversion integration are deferred; the source folder was empty during development.
3. Manually check the implemented browser-search/download-folder workflow. ZIP extraction is implemented. Automatic downloads and background folder watching remain future work.
4. Prepare a public release: choose an application licence, versioning and packaging, then evaluate KiCad plugin integration.
5. Investigate provider-specific APIs subject to available access and terms.

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
