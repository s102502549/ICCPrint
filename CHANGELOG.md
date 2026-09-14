# Changelog

## Unreleased

- Reorganized the source tree for public GitHub development.
- Added bilingual README files, contributor/security docs, issue/PR templates, CI, Windows artifact workflow, unit tests, and Python project metadata.
- Generalized the UI from an L15160-only label to RGB printer ICC workflows while keeping Epson L15160 as the tested reference workflow.
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
