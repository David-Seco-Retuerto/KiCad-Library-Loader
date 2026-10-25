# Changelog

## 0.1.0-alpha.1 — Unreleased

First public alpha candidate: reviewed native KiCad 9/10 imports, ZIP intake, provider search, LCSC acquisition, 2D/STEP previews, managed history/update/restore/move/removal/recovery and portable Windows/Linux build support.

Portable candidates require the build checks and release checklist in docs/RELEASING.md. No release is published by the build scripts.

Portable candidates bundle a shared runtime and separate CAD/converter worker, with source/notices/checksums and platform smoke reports. First native baseline: Windows x86_64 and Ubuntu 24.04 x86_64/WSLg. Public release remains gated by docs/RELEASING.md.

Minimal STEP portables now use a C++ helper and locally built OCCT 7.9.3, with full pinned source delivery, Windows runtime notice pins, Ubuntu package notices, archive boundary checks and a manually dispatched build/separate-runner launch workflow. Source installations retain OCP. Independent-runner and owner acceptance remain pending.
