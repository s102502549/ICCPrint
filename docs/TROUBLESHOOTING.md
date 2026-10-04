# Troubleshooting

## The EXE does not open

- Extract the complete ZIP before running it. Keep `_internal` beside `ICCPrint.exe`.
- Confirm x64 Windows and a current manufacturer printer driver. A source ZIP requires the source setup instructions instead.
- Check the download's checksum and provenance. Do not disable antivirus or automatically bypass Windows security warnings. Report a false-positive detection through your organization's approved process.
- Maintainers can run the non-printing bundle test from PowerShell:

  ```powershell
  $p = Start-Process .\ICCPrint.exe -ArgumentList @('--smoke-test', 'smoke-test.json') -PassThru -Wait
  Get-Content .\smoke-test.json
  $p.ExitCode
  ```

  It tests imports, Qt preview, LittleCMS and PDFium, and writes the named report. It does not test a driver, print dialog or physical output. Use a writable report destination. Do not include private document paths or profiles in public bug reports.

## Profile rejected or colors look wrong

- Select an RGB **printer output** ICC/ICM, not a monitor, scanner, sRGB display, or CMYK profile. A filename ending in `.icc` does not prove that its contents are valid.
- Replace a corrupt or incompatible profile with the correct original. Do not rename a different profile to bypass validation.
- Check the embedded source profile and chosen intent. Untagged RGB content uses an sRGB assumption; malformed embedded profiles or unsupported source encodings must be corrected rather than silently treated as accurate color.
- Disable extra driver color correction, and match paper, ink, media type, quality, and all relevant driver settings to the profiling condition.
- A soft proof is an sRGB simulation. Calibrated display/viewing conditions and a physical test print remain necessary.

## Large, encrypted or damaged files

ICCPrint bounds preview and print rendering to avoid uncontrolled image allocations. If a page is rejected, reduce its dimensions or PDF rasterization DPI, export a smaller copy, or split the document. Do not disable the guard to force an unknown file through. Damaged PDFs/images can fail during load or render; preserve the original and re-export from its authoring application. Password-protected PDFs must be exported as an authorized readable copy first.

## Office document conversion fails

LibreOffice is optional and is not bundled. Install it from its official source, close problematic LibreOffice instances, or export to PDF yourself. Conversion is temporary and may change fonts, pagination or layout; inspect every converted page. Unsupported files and conversion failures should not be mistaken for printable blank pages.

## Cropped or incorrectly sized output

Fit keeps the full source visible; Fill intentionally crops; Actual preserves physical dimensions and may extend past the page. For raster images, check embedded DPI and the fallback DPI setting. PDF physical dimensions come from the PDF, independently of rasterization DPI. Match the actual driver paper size and orientation, and remember that the printable region can be smaller than the sheet.

## Cancellation or a failed job

Cancel stops further application submission at the next safe point; it cannot retract a sheet already sent to the printer. Check the Windows print queue to remove any remaining queued job. A success message indicates submission completed, not that all sheets physically printed. Do not immediately retry a whole document without checking the queue: duplicate pages may print.

## Useful bug report details

Record application version, Windows version, Python version (source installs only), printer/driver model and version, file type, page count/dimensions, selected intent and layout, and exact error text. State whether the problem occurs in source, a portable build, or both. Use a small redistributable sample; never attach private documents, licensed ICC profiles, serial numbers, credentials or personal information.
