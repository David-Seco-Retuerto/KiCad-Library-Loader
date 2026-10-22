# Third-party software notices

## easyeda2kicad 1.0.1

- Project: [easyeda2kicad.py](https://github.com/uPesy/easyeda2kicad.py)
- Author: uPesy; see upstream source for contributor and copyright notices.
- Package release: [easyeda2kicad 1.0.1](https://pypi.org/project/easyeda2kicad/1.0.1/)
- Licence: GNU Affero General Public License, version 3 (AGPL-3.0), as declared by the installed release.
- Unmodified licence text from that release: [licenses/easyeda2kicad-AGPL-3.0.txt](licenses/easyeda2kicad-AGPL-3.0.txt).

The loader installs this dependency through `requirements.txt` and invokes its CLI as a child process for an explicit single-part LCSC acquisition. Its implementation has not been copied into the loader's own scripts or modified by this integration. The generated provider CAD assets are kept in the ignored local cache, not distributed as application source.

This notice preserves the converter's attribution and licence information. A packaged release must also retain applicable upstream notices and provide its corresponding source as required by the licences of the components it ships. A link to a changing upstream default branch is not a substitute for matching source for a shipped version.

## Release inventory

This document currently records the converter added by the LCSC integration. The remaining runtime/dependency licences, source delivery and installer notices must be inventoried as part of release packaging. It is not a declaration that a complete binary distribution has been audited or prepared.
