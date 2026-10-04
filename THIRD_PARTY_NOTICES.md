# Third-party notices

ICCPrint's source is MIT-licensed. A portable distribution also includes Python, PySide6/Qt/shiboken6, Pillow/LittleCMS, pypdfium2/PDFium, the PyInstaller bootloader, and native components collected from these dependencies. Each retains its own copyright and license.

## Included materials

- `LICENSE`: ICCPrint's MIT license
- `third_party_licenses/Python/LICENSE.txt`: the build interpreter's Python license
- `third_party_licenses/<package>-<version>/`: upstream package metadata and discovered license/notice files, preserving nested paths and third-party PDFium attributions
- `third_party_licenses/Qt-license-texts/`: standard LGPLv3/GPLv3 texts (also in source at `docs/licenses/`)
- `third_party_licenses/COLLECTED_LICENSES.json` and `.txt`: inventory, exact package versions, and warnings when a wheel omits license files
- `BUILD_MANIFEST.json`: build environment and hashes of the bundled files

These generated directories are included in portable builds, not stored as a second copy of installed dependencies in the source repository.

## Component overview

- PySide6/Qt/shiboken6 have LGPL, GPL and commercial licensing options depending on the component. Review exactly which Qt libraries and plugins the build collects.
- Pillow and LittleCMS, and Pillow's bundled codecs, have their own permissive licenses and notices; preserve the installed distribution's full license text.
- pypdfium2 and PDFium include BSD/Apache and other third-party license material. All nested license-directory contents are collected, not just filenames containing the word `LICENSE`.
- Python includes the PSF license and historical/third-party notices.
- PyInstaller's bootloader license includes a distribution exception; preserve the upstream license and exception.
- LibreOffice is optional and external. ICCPrint does not bundle LibreOffice, printer drivers or printer profiles.

## Redistribution review remains required

A successful build or automated collector is not a legal-compliance certification. In particular, some Qt wheels contain license metadata without separate texts. Check every native component actually bundled; provide any required corresponding-source materials/offers, notices, and library replacement/relinking information. Standard license texts and upstream links alone do not satisfy every obligation. See [dependency sources](docs/DEPENDENCY_SOURCES.md) and [release checklist](docs/RELEASE_CHECKLIST.md).
