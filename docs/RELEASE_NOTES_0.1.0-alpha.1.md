# KiCad Library Loader 0.1.0-alpha.1

Draft release notes. The owner decides when to publish and creates the release manually.

Import native KiCad symbols, footprints and STEP models with independent asset selection, readable naming, previews and a reviewed import plan. Supports packed KiCad 9 libraries and genuine unpacked KiCad 10+ symbol directories.

## Included

- Native SamacSys/LCSC folders, ZIP intake and Downloads refresh.
- Browser search and explicit LCSC acquisition through easyeda2kicad.
- Configurable output locations, categories and model path variables.
- Symbol/footprint previews and an integrated STEP viewer.
- Collision protection, history and reviewed update/restore/move/remove/recover workflows.
- English UI and documentation. AGPL-3.0-only, copyright (C) 2026 David-Seco-Retuerto.

## Source installation

Follow README.md to create a Python environment, install requirements and run the application. Python with Tcl/Tk and internet access for dependency installation are required. KiCad is installed separately. Source and dependency licences are included/referenced in the project notices.

## Known limits

- This is an alpha. Use a disposable output/project for evaluation and review every plan.
- Available native test systems are Windows x86_64 and Ubuntu 24.04 x86_64 under WSLg. No independent clean machine has been tested. Other Linux distributions, older glibc, ARM and macOS are not validated targets.
- SamacSys browser search/download remains manual. LCSC acquisition uses an unofficial converter and provider endpoints may change; verify the selected package and CAD data against the datasheet.
- Approximate 2D previews are not full CAD validation. Installed KiCad enables exact SVG previews.
- Managed library changes do not automatically update placed schematic/PCB instances. Multi-file writes roll back handled I/O errors but are not power-loss atomic.
- Minimal portables include a locally built STEP helper with complete pinned OCCT source and runtime notices. Independent-runner and owner acceptance checks remain before public binary release; follow docs/RELEASING.md. The legacy OCP-wheel bundles are development-only.
