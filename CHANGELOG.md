# Changelog

## 0.3.0 (unreleased development build)

### Workflow and safety

- Added background document import, source/proof preview and print preparation with stale-result suppression and cooperative cancellation.
- Added document queue reordering and direct page navigation; source signature checks stop preparation if an input changes mid-job.
- Added preflight readiness, layout/resolution warnings, named validated local presets, and Relative Colorimetric + BPC defaults for new installations.
- Driver color-correction acknowledgment is never saved/restored; vendor-specific settings remain manual.
- Require RGB printer-class output profiles and supported intents; validate embedded source profiles and source color spaces rather than silently ignoring invalid color metadata.
- Preserve source-profile context during transparency handling and reject untagged unsupported CMYK/Lab conversions.
- Bound raster dimensions/pixel counts and validate render DPI; isolate Office conversion and improve deterministic resource cleanup.
- Prepare every selected page into temporary disk-backed output before beginning a printer job; clean up after completion/failure/cancel.
- Align preview/print full-paper geometry, validate layouts, and support page range/copy/collation handling without claiming physical-print completion.

### Distribution and verification

- Added an isolated clean Windows x64 build with pinned runtime/build dependencies, executable version metadata and a frozen native-library smoke test.
- Bundle first-run instructions, bilingual overview, user/troubleshooting guides, notices and preserved nested upstream license material.
- Generate a versioned portable ZIP, build/package manifest, file hashes and archive SHA-256; verify extracted artifacts in CI.
- Expand headless tests to Ubuntu and Windows with Python 3.12 and 3.13; no release/tag publication is automated.
- Use a single version source and a GUI entry point; document the manual Windows, physical-printer and dependency-review gates still required before release.

## Earlier unreleased repository preparation

- Reorganized the source tree for public GitHub development.
- Added bilingual README files, contributor/security docs, issue/PR templates, CI, Windows artifact workflow, unit tests, and Python project metadata.
- Generalized the UI from an L15160-only label to RGB printer ICC workflows while retaining Epson L15160 as the original reference workflow; this does not validate the new version on hardware.
- Changed the application settings organization name to `ICCPrint`, with automatic migration from pre-GitHub builds.

## 0.2.0

- Added live print-layout preview.
- Added ICC soft proofing using the selected printer profile and rendering intent.
- Added Actual 100% size mode.
- Added embedded image DPI handling and configurable fallback DPI.
- Added paper size and portrait/landscape controls, including custom mm size.
- Added preview navigation for multi-page documents.
- PDF Actual size now uses the PDF page's physical dimensions independently of rasterization DPI.

## 0.1.1

- Replaced Windows batch-file text with ASCII/CRLF to avoid Traditional Chinese code-page corruption.
- Added fallback from `py.exe` to `python.exe` during setup.
