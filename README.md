# ICCPrint

[繁體中文](README_zh-TW.md)

ICCPrint is a local Windows utility for **ICC-managed printing without Photoshop**. It converts documents to an RGB printer profile with an explicit rendering intent, provides a source/soft-proof comparison, and submits output through the Windows printer driver. The interface is primarily Traditional Chinese.

**0.3.0 is a development build.** Automated tests exercise color validation, rendering, layout, job preparation and packaging. They do not certify a printer or color accuracy. Epson L15160 with a Datacolor/SpyderPRINT RGB profile is the project's original reference workflow; this version still requires recorded Windows, driver and physical-print acceptance before a public release.

## Start here

### Portable Windows package

Extract the entire versioned ZIP and double-click `ICCPrint/ICCPrint.exe`. **No Python installation is needed.** Keep `_internal` with the executable. Read [Windows installation](docs/INSTALL_WINDOWS.md) and [the first-print guide](docs/USER_GUIDE.md).

The repository does not contain a prebuilt EXE. The Windows artifact workflow builds a downloadable test artifact on demand or for qualifying pull requests; it does not publish releases.

### Source checkout

Use x64 Windows 10/11 and Python 3.12 or 3.13:

```bat
install_and_run.bat
```

After setup, launch with `run.bat`. Or install manually:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iccprint
```

The tested dependency set is pinned in `requirements-lock.txt`. A manufacturer printer driver and suitable RGB output ICC/ICM are required for printing. LibreOffice is optional for Office conversion and is not bundled.

## Workflow

1. Add images, PDFs or supported Office documents. Import/conversion runs in the background.
2. Choose the profile for the exact **printer, ink and paper**. ICCPrint validates RGB output-device profiles and their supported intent.
3. Choose paper, orientation and Fit / Fill / Actual. Compare the color-managed source preview with ICC soft proof; review resolution/cropping warnings.
4. Select intent and BPC. New installations default to Relative Colorimetric with Black Point Compensation. Named local presets save repeatable application settings.
5. In the printer driver's own properties, **disable additional color correction** and match the profiled media/quality settings. Confirm the checkbox each session; it is never restored from a preset.
6. Review preflight and the native print dialog. Selected pages are fully rendered and color-converted to a temporary disk spool before the printer job begins. Start with a single physical test page.

For Epson, the driver path is often similar to `Printer Properties → More Options → Color Correction → Custom → Advanced → No Color Adjustment`; names vary by driver. ICCPrint cannot enforce this vendor-specific setting.

## Features

- PDF, JPEG, PNG, multipage TIFF, BMP and WebP; optional Word/Excel/PowerPoint via LibreOffice
- Strict source ICC validation, white transparency compositing, and explicit sRGB assumptions for untagged RGB content
- RGB **printer output** ICC/ICM validation; monitor/sRGB and CMYK output profiles are rejected
- Perceptual, Relative Colorimetric, Saturation and Absolute Colorimetric intents; optional BPC
- Background preview/import/job preparation, stale-result suppression, queue reordering, direct page navigation and source/proof toggle
- Fit, Fill and Actual 100%; embedded image DPI with configurable fallback; standard/custom paper and orientation
- Named local application presets; preflight readiness and layout/resolution warnings
- Complete pre-render before submission, bounded raster allocation, temporary-job cleanup and cooperative cancellation
- Native Windows dialog, selected page ranges, and printer copy/collation handling
- Versioned portable ZIP, executable metadata, dependency notices, file manifest and SHA-256 checksum
- Local document processing; no document-upload service

## Color and size boundaries

- **Fit** shows the whole source; **Fill** intentionally crops; **Actual** preserves physical dimensions and can extend beyond the sheet. Images use embedded or fallback DPI. PDFs use their physical page dimensions independently of rasterization DPI.
- PDFium rasterizes PDFs before output, so vector/text content becomes pixels. The rendered bitmap is treated as sRGB; this is not a vector-preserving prepress/RIP workflow.
- Proofing simulates the selected printer profile back to sRGB. The app does not automatically use your monitor ICC profile or provide calibrated-display guarantees.
- Preview and output share a full-paper coordinate system. Hardware margins can still clip output; this is not a promise of borderless printing.
- Driver settings and the actual profiling condition remain the user's responsibility. Cancellation cannot retract pages already submitted; “submitted” does not mean physically printed.
- Current raster safeguards are 100 million pixels and 32,768 pixels on either axis. Oversized pages are rejected with guidance rather than allocated without limits.

## Build and verify

On native x64 Windows with Python 3.12 or 3.13:

```bat
build_exe.bat
```

This recreates an isolated build environment, installs pinned dependencies, runs tests, builds and smoke-tests the EXE, collects documentation/notices, and writes:

```text
dist/ICCPrint/ICCPrint.exe
dist/ICCPrint/BUILD_MANIFEST.json
dist/ICCPrint-0.3.0-Windows-x64.zip
dist/ICCPrint-0.3.0-Windows-x64.zip.sha256
```

CI runs headless tests on Ubuntu and Windows with Python 3.12/3.13. The Windows build workflow also verifies the extracted archive. These checks do not exercise a physical printer. See [reproducibility boundaries](docs/INSTALL_WINDOWS.md#reproducibility-boundary) and the [release checklist](docs/RELEASE_CHECKLIST.md).

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Windows installation and building](docs/INSTALL_WINDOWS.md)
- [Color-management pipeline](docs/COLOR_MANAGEMENT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Contributing and tests](CONTRIBUTING.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md) and [dependency sources](docs/DEPENDENCY_SOURCES.md)
- [Changelog](CHANGELOG.md)

## License and trademarks

ICCPrint source is [MIT-licensed](LICENSE). Dependencies retain their own licenses; binary redistribution requires the review described in the notices. Epson, Datacolor, SpyderPRINT, Adobe, Windows and other product names are trademarks of their respective owners. This independent project is not affiliated with or endorsed by those companies.
