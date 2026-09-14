# Contributing to ICCPrint

Thanks for helping improve ICCPrint.

## Before opening a pull request

1. Keep changes focused and explain the user-visible reason for them.
2. Do not commit personal ICC/ICM profiles, printer serial numbers, private documents, or sample files that you do not have permission to redistribute.
3. Keep printer-specific behavior isolated where possible. Vendor driver settings are often private APIs and can differ between driver versions.
4. Add or update tests for geometry, file handling, or other logic that can be tested without a physical printer.
5. Update `CHANGELOG.md` for user-visible changes.

## Development setup

On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iccprint
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Compile-check the source:

```powershell
.\.venv\Scripts\python.exe -m compileall iccprint main.py tests
```

## Pull request checklist

- The application starts on Windows.
- Unit tests pass.
- New UI text is understandable without color-management jargon where possible.
- Color-management changes document whether they affect source profile handling, rendering intent, BPC, proofing, or printer output.
- No new dependency is added without a clear reason and a license check.

## Color-management changes

ICCPrint intentionally separates these stages:

1. Decode/rasterize source content.
2. Determine the source color profile (embedded profile or sRGB fallback).
3. Convert to the selected RGB printer ICC with the chosen rendering intent and optional BPC.
4. Send device RGB values to the Windows printer driver.
5. The user disables additional color correction in the printer driver.

Changes that alter this pipeline should be called out explicitly in the PR description.
