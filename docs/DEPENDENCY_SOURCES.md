# Dependency source and license review

The generated `BUILD_MANIFEST.json` is the authoritative list of installed package versions for a particular build. `third_party_licenses/COLLECTED_LICENSES.json` records copied upstream notices and flags packages with no discoverable license files. The collector preserves the original relative paths, including all files under license directories, and includes the build interpreter's Python license.

The following are upstream project sources, not an assertion that the entire redistribution review is complete:

- PySide6 / shiboken6: [Qt for Python source](https://code.qt.io/cgit/pyside/pyside-setup.git/), [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html)
- Qt libraries/plugins: [Qt source repositories](https://code.qt.io/qt/), [Qt licensing](https://doc.qt.io/qt-6/licensing.html), [third-party attribution](https://doc.qt.io/qt-6/licenses-used-in-qt.html)
- Pillow and bundled imaging libraries: [Pillow source](https://github.com/python-pillow/Pillow), [license](https://pillow.readthedocs.io/en/stable/about.html#license)
- pypdfium2 and PDFium: [pypdfium2 source and licensing](https://github.com/pypdfium2-team/pypdfium2), [PDFium source](https://pdfium.googlesource.com/pdfium/), plus the exact wheel's `BUILD_LICENSES` directory
- Python interpreter and standard library: [CPython source](https://github.com/python/cpython), [Python license](https://docs.python.org/3/license.html)
- PyInstaller bootloader: [PyInstaller source/license](https://github.com/pyinstaller/pyinstaller), [licensing and exception](https://pyinstaller.org/en/stable/license.html)

The pinned PySide6 wheels may supply license metadata without separate texts. Standard LGPLv3 and GPLv3 texts are included in `docs/licenses` and copied to `third_party_licenses/Qt-license-texts`. Match exact Qt/PySide versions and bundled plugins to their upstream source, preserve all required attributions, and meet applicable corresponding-source/relinking obligations before redistribution. A link to an upstream homepage alone is not a completed source offer.

ICCPrint uses an onedir build so libraries remain separate. Do not remove or prohibit replacement of LGPL-covered libraries. Validate any replacement libraries for compatible ABI and behavior. See the upstream licensing documents and exact component licenses for their conditions. Seek qualified review if obligations are unclear.

LibreOffice is an optional external program and is not redistributed by this build. Printer ICC profiles and manufacturer drivers are also not bundled; users supply them under their own licenses.
