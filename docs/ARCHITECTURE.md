# Architecture

ICCPrint separates source loading, color conversion, layout and Windows submission from the UI.

## Modules

- `iccprint/app.py`: main window, per-user settings/presets, readiness, asynchronous operations and native print-dialog coordination
- `iccprint/color.py`: source-profile validation, RGB printer-output profile checks, conversion/proof transforms and display conversion
- `iccprint/documents.py`: image/PDF loading, PDFium rendering, bounded raster allocation and isolated LibreOffice conversion
- `iccprint/printing.py`: paper/layout geometry, image conversion and submission helpers
- `iccprint/preview.py`: full-paper preview presentation
- `iccprint/jobs.py`: worker signals, cancellation checkpoints, preview/import requests and temporary prepared jobs
- `iccprint/presets.py`: validation/normalization of saved application preset values
- `iccprint/__main__.py`: source/GUI entry point
- `scripts/frozen_entry.py`: packaged launcher and settings-free native-library smoke test
- `scripts/build_windows.py`: isolated Windows build, testing and frozen executable validation
- `scripts/collect_licenses.py`: upstream package metadata and nested notices
- `scripts/package_distribution.py`: content inventory, manifest verification, versioned ZIP and checksum


## Background work and ownership

A serial worker pool coordinates import, preview and preparation, avoiding simultaneous PDFium operations. Immutable request snapshots and generation tokens separate worker data from live widgets and discard obsolete preview results. Qt widgets and printing remain on the GUI side. Cancellation is cooperative at stage boundaries; native decode/render/conversion is not forcibly interrupted. Closing the window cancels work and coordinates resource cleanup.

## Prepare before submission

The selected pages are rendered and color-converted to a temporary disk spool before a printer job starts. A source/conversion failure therefore prevents submission of a partially validated document. During submission, cleanup ends/aborts painter and printer state as appropriate and releases prepared files. Cancellation cannot recall already submitted pages. Success reports queue submission, never physical completion.

## Color and geometry contracts

Raster source color space must match the embedded ICC. Invalid profiles and untagged unsupported color modes are explicit errors. Output is limited to RGB printer-class profiles. PDFium bitmaps are treated as sRGB; PDF vectors/output intents are not preserved as a RIP would preserve them.

Preview and printer layout share a full-paper coordinate system. Driver hardware margins can clip it. Actual-size PDFs use their page dimensions; raster images use embedded or fallback DPI. Limits bound raster dimensions and allocation before native rendering.

## Platform and build boundaries

The product targets Windows. Linux headless tests are a portability/regression aid, not Linux printing support. Native dialog and vendor-specific driver behavior require Windows testing. ICCPrint never rewrites undocumented vendor DEVMODE fields to force color settings.

The portable distribution is PyInstaller onedir, keeping runtime libraries and notices inspectable. Package versions are pinned; the manifest records exact Python/platform/packages and content hashes. ZIP structure is deterministic for identical input contents, but native binary reproducibility across OS images or Python patch versions is not guaranteed. No release publishing or signing is performed by the workflow.
