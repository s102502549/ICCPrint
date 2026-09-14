# Architecture

ICCPrint is intentionally small and keeps color conversion separate from UI and layout code.

## Modules

- `iccprint/app.py` — PySide6 main window, settings, print workflow, preview coordination
- `iccprint/color.py` — ICC profile inspection, printer conversion, soft-proof transforms
- `iccprint/documents.py` — image/PDF loading, PDF rasterization, optional LibreOffice conversion
- `iccprint/printing.py` — paper sizes, Fit/Fill/Actual geometry, PIL-to-Qt conversion helpers
- `iccprint/preview.py` — paper/print preview widget
- `iccprint/__main__.py` — application entry point

## Design constraints

### Windows printer-driver settings

Qt and Windows expose standard print-dialog behavior, but vendor-specific driver properties such as Epson's color-correction mode are not reliably portable across driver versions. ICCPrint therefore asks the user to confirm those settings in the vendor's own driver UI instead of modifying private DEVMODE fields.

### PDF rendering

PDF pages are rasterized by PDFium before ICC conversion. This gives a predictable whole-page RGB color pipeline at the cost of converting text/vector content to pixels.

### RGB printer profiles

The current output pipeline is intentionally limited to RGB printer profiles. CMYK/RIP workflows are outside the current project scope.
