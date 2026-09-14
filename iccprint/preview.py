from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .printing import layout_rects


class PrintPreviewWidget(QWidget):
    """Lightweight print-layout preview with ICC-soft-proofed image content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 430)
        self._image: Optional[QImage] = None
        self._paper_w_mm = 210.0
        self._paper_h_mm = 297.0
        self._mode = "fit"
        self._actual_w_mm: Optional[float] = None
        self._actual_h_mm: Optional[float] = None
        self._message = "加入文件後會顯示列印預覽"

    def set_preview(
        self,
        image: Optional[QImage],
        paper_w_mm: float,
        paper_h_mm: float,
        mode: str,
        actual_w_mm: Optional[float] = None,
        actual_h_mm: Optional[float] = None,
        message: str = "",
    ):
        self._image = image.copy() if image is not None else None
        self._paper_w_mm = max(1.0, float(paper_w_mm))
        self._paper_h_mm = max(1.0, float(paper_h_mm))
        self._mode = mode
        self._actual_w_mm = actual_w_mm
        self._actual_h_mm = actual_h_mm
        self._message = message
        self.update()

    def clear_preview(self, message: str = "加入文件後會顯示列印預覽"):
        self._image = None
        self._message = message
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(62, 65, 70))

        margin_x = 28.0
        margin_y = 28.0
        footer_h = 42.0
        available_w = max(10.0, self.width() - margin_x * 2.0)
        available_h = max(10.0, self.height() - margin_y * 2.0 - footer_h)
        scale = min(available_w / self._paper_w_mm, available_h / self._paper_h_mm)
        paper_w = self._paper_w_mm * scale
        paper_h = self._paper_h_mm * scale
        paper_x = (self.width() - paper_w) / 2.0
        paper_y = margin_y + (available_h - paper_h) / 2.0
        paper_rect = QRectF(paper_x, paper_y, paper_w, paper_h)

        # Drop shadow and paper.
        shadow = paper_rect.translated(5.0, 6.0)
        painter.fillRect(shadow, QColor(25, 25, 25, 100))
        painter.fillRect(paper_rect, Qt.GlobalColor.white)
        painter.setPen(QPen(QColor(185, 185, 185), 1.0))
        painter.drawRect(paper_rect)

        if self._image is not None and not self._image.isNull():
            r = layout_rects(
                self._paper_w_mm,
                self._paper_h_mm,
                self._image.width(),
                self._image.height(),
                self._mode,
                self._actual_w_mm,
                self._actual_h_mm,
            )
            target = QRectF(
                paper_x + r.target_x * scale,
                paper_y + r.target_y * scale,
                r.target_w * scale,
                r.target_h * scale,
            )
            source = QRectF(r.source_x, r.source_y, r.source_w, r.source_h)
            painter.save()
            painter.setClipRect(paper_rect)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(target, self._image, source)
            painter.restore()

        painter.setPen(QColor(235, 235, 235))
        label = self._message or f"紙張 {self._paper_w_mm:.1f} × {self._paper_h_mm:.1f} mm"
        footer = QRectF(12.0, self.height() - footer_h + 6.0, self.width() - 24.0, footer_h - 10.0)
        painter.drawText(footer, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, label)
        painter.end()
