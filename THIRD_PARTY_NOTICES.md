# Third-party notices

ICCPrint's own source code is distributed under the MIT License. Runtime and build dependencies have their own licenses.

## Runtime dependencies

- **PySide6 / Qt for Python / shiboken6** — Qt licensing options include LGPLv3, GPLv3, and commercial licensing depending on the component and distribution. Review the exact license files included with the installed PySide6/Qt packages.
- **Pillow** — Pillow license (HPND-style).
- **LittleCMS** — MIT-style license. Pillow's `ImageCms` support uses LittleCMS.
- **pypdfium2 / PDFium** — pypdfium2 and bundled PDFium components use BSD/Apache-style and additional open-source licenses; review the exact license files shipped with the installed binary packages.
- **LibreOffice** — optional external application used only for Office-to-PDF conversion. It is not bundled by ICCPrint and has its own licenses.

## Binary redistribution

`build_exe.bat` uses `scripts/collect_licenses.py` to copy discoverable license/notice files from installed runtime distributions into `dist\ICCPrint\third_party_licenses`.

This helper is not a substitute for reviewing the exact dependency versions you redistribute. Before publishing a binary release, verify that all required notices, license texts, relinking requirements, and source-offer obligations for the exact bundled versions are satisfied.
