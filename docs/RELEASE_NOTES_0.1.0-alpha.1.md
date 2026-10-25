# KiCad Library Loader v0.1.0-alpha.1

First public alpha: import symbols, footprints and STEP models into KiCad libraries with independent selection, previews and a reviewed import plan.

## Download and run

Download only the portable for your operating system:

- **Windows x86_64:** extract the complete ZIP and run `KiCad-Library-Loader.exe`.
- **Linux x86_64:** extract the complete tar.gz and run `./KiCad-Library-Loader`. Tested on Ubuntu 24.04; other distributions are not yet validated. Compatible glibc and C++ system runtimes are required.

Keep the worker and `_internal` folder together with the application. No separate Python installation is needed. KiCad is installed separately.

`KiCad-Library-Loader-0.1.0-alpha.1-source-complete.tar.gz` is an optional separate download for users. It contains the exact matching application/dependency sources, build recipes, developer documentation and original provenance. `SHA256SUMS` covers all three archives. GitHub's automatic Source code downloads are not portable executables and do not replace this complete source asset.

## Features

- SamacSys/LCSC export folders, ZIP intake and Downloads refresh.
- Browser search and explicit LCSC acquisition through easyeda2kicad.
- Independent asset selection, naming, configurable categories and destinations.
- Packed KiCad 9 and genuine unpacked KiCad 10+ symbol libraries.
- Symbol/footprint previews, integrated STEP preview and managed import history.
- Reviewed update, restore, move, removal and recovery workflows.

## Validation and limits

The original Windows and Ubuntu candidates passed build and application launch checks on separate GitHub-hosted runners. Public packaging preserves every runtime file byte and Linux executable mode/symlink. The reorganized packages passed local worker, GUI, packed/unpacked import and STEP checks on Windows and Ubuntu WSLg with a reduced PATH.

This is an alpha: evaluate it with a temporary library/project and check pin mapping, footprint dimensions and 3D alignment in KiCad. Automated tests and approximate previews do not establish electrical correctness. SamacSys downloading remains manual; LCSC acquisition uses an unofficial converter and provider interfaces may change. Other Linux distributions, ARM and macOS are not validated. Managed library changes do not automatically update placed schematic/PCB instances.

## Licence

Copyright (C) 2026 David-Seco-Retuerto. Application code: AGPL-3.0-only. Third-party components retain their own licences. Runtime notices remain in each portable; complete matching application/dependency sources are available in the separate complete source asset at this same release.
