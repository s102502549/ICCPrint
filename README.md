# ICCPrint

[繁體中文 README](README_zh-TW.md)

ICCPrint is a free, open-source Windows utility for **ICC-managed printing without Photoshop**. It applies a printer ICC/ICM profile with an explicit rendering intent, provides a soft-proof preview, and then hands the converted output to the normal Windows printer driver.

> **Project status:** alpha. The workflow has been developed and tested around an Epson L15160 + Datacolor/SpyderPRINT RGB printer profile. Other Windows printers with RGB output profiles may work, but driver-specific behavior is not guaranteed.

## Why ICCPrint?

Many consumer and office printer drivers expose an ICM mode but do not let the user choose the ICC rendering intent. ICCPrint performs the color conversion itself with Pillow/LittleCMS, so you can explicitly choose:

- Perceptual
- Relative Colorimetric
- Saturation
- Absolute Colorimetric
- Optional Black Point Compensation (BPC)

The printer driver should then be configured to **disable additional color correction** (for Epson drivers, typically `No Color Adjustment`) to avoid double color management.

## Features

- PDF, JPEG, PNG, TIFF (including multipage), BMP, and WebP
- Optional Word/Excel/PowerPoint support through an installed LibreOffice conversion step
- RGB printer ICC/ICM profiles
- Four ICC rendering intents
- Black Point Compensation
- ICC soft-proof preview
- Fit / Fill / Actual 100% layout modes
- Embedded image DPI handling with a configurable fallback DPI
- Common paper sizes plus custom millimeter sizes
- Portrait / landscape orientation
- Multipage preview navigation
- Native Windows print dialog and printer-driver properties
- Local processing only; documents are not uploaded

## Important color-management rule

ICCPrint already converts the source image/document into the selected printer profile. **Do not enable a second color-management pass in the printer driver.**

For an Epson workflow, the usual driver path is similar to:

`Printer Properties -> More Options -> Color Correction -> Custom -> Advanced -> No Color Adjustment`

Also use the same media type, quality, ink, paper, and other driver settings that were used when the printer ICC profile was created.

## Quick start on Windows

Requirements:

- Windows 10 or 11
- 64-bit Python 3.12 or 3.13
- A printer ICC/ICM profile
- Optional: LibreOffice for Office-document conversion

Clone or download the repository, then run:

```bat
install_and_run.bat
```

After the first setup, `run.bat` starts ICCPrint using the local virtual environment.

You can also use standard Python commands:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m iccprint
```

## Build a Windows executable

Run:

```bat
build_exe.bat
```

The PyInstaller folder build is written to:

```text
dist\ICCPrint\ICCPrint.exe
```

The repository also contains a GitHub Actions workflow that can build a Windows artifact on demand.

## Fit, Fill, and Actual

- **Fit** keeps the whole source visible and scales it to fit inside the paper.
- **Fill** fills the paper and crops the source symmetrically when needed.
- **Actual 100%** preserves physical size. PDF pages use their PDF page dimensions; raster images use embedded DPI, or the user-defined fallback DPI if no DPI is present.

## Soft proofing

ICCPrint uses LittleCMS proofing transforms to simulate the selected printer profile on an sRGB display preview. This is useful for comparing profiles, rendering intents, BPC, crop/layout, and paper orientation.

A soft proof is still an approximation. Monitor calibration, screen brightness, ambient light, paper white, ink, drying time, and the actual printer-driver configuration all affect the physical result.

## Limitations

- Windows only at the moment.
- Printer profiles must currently use an RGB device color space.
- PDF pages are rasterized before ICC conversion. Text/vector content therefore becomes pixels for output.
- ICCPrint cannot reliably force vendor-specific driver settings such as Epson's `No Color Adjustment`; you must confirm those settings in the driver's own properties dialog.
- The preview represents the full paper rectangle; non-printable margins are still controlled by the printer driver.

## Documentation

- [Windows installation](docs/INSTALL_WINDOWS.md)
- [Color-management workflow](docs/COLOR_MANAGEMENT.md)
- [Project architecture](docs/ARCHITECTURE.md)
- [Contributing](CONTRIBUTING.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## Development

Run the test suite with:

```powershell
python -m unittest discover -s tests -v
```

A basic CI workflow runs compilation and unit tests on Windows with supported Python versions.

## License

ICCPrint source code is released under the [MIT License](LICENSE). Dependencies retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Trademark notice

Epson, Datacolor, SpyderPRINT, Adobe, Windows, and other product names are trademarks of their respective owners. ICCPrint is an independent open-source project and is not affiliated with or endorsed by those companies.
