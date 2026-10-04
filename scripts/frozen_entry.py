"""Frozen launcher with a non-printing, settings-free bundle smoke test."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import traceback


def smoke_test(report_path: Path) -> int:
    """Exercise native libraries from the frozen bundle, without a print job."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    report: dict[str, object] = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    try:
        from PIL import Image, ImageCms, features
        import pypdfium2 as pdfium
        from PySide6.QtCore import qVersion
        from PySide6.QtPrintSupport import QPrinter  # noqa: F401
        from PySide6.QtWidgets import QApplication
        from iccprint import __version__
        from iccprint.app import MainWindow  # noqa: F401 - test the full import graph
        from iccprint.preview import PrintPreviewWidget
        from iccprint.printing import pil_to_qimage

        app = QApplication.instance() or QApplication(["ICCPrint smoke test"])
        profile = ImageCms.createProfile("sRGB")
        source = Image.new("RGB", (16, 16), (30, 120, 210))
        converted = ImageCms.profileToProfile(source, profile, profile, outputMode="RGB")
        if converted.size != (16, 16) or not features.check("littlecms2"):
            raise RuntimeError("LittleCMS conversion failed")
        document = pdfium.PdfDocument.new()
        page = document.new_page(72, 72)
        try:
            bitmap = page.render(scale=1)
            try:
                if bitmap.to_pil().size != (72, 72):
                    raise RuntimeError("PDFium rendering failed")
            finally:
                bitmap.close()
        finally:
            page.close()
            document.close()
        widget = PrintPreviewWidget()
        widget.set_preview(pil_to_qimage(converted), 210, 297, "fit")
        widget.resize(480, 640)
        if widget.grab().isNull():
            raise RuntimeError("Qt preview rendering failed")
        widget.close()
        app.processEvents()
        report.update(ok=True, version=__version__, qt=qVersion(),
                      checks=["application imports", "LittleCMS", "PDFium", "Qt preview", "QtPrintSupport import"])
    except Exception:
        report["error"] = traceback.format_exc()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        return smoke_test(Path(sys.argv[2]))
    from iccprint.__main__ import main as application_main
    return application_main()


if __name__ == "__main__":
    raise SystemExit(main())
