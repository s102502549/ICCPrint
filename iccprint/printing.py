from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PIL import Image


# Width x height in millimetres, stored in portrait orientation.
PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A5 (148 × 210 mm)": (148.0, 210.0),
    "A4 (210 × 297 mm)": (210.0, 297.0),
    "A3 (297 × 420 mm)": (297.0, 420.0),
    "A3+ / Super B (329 × 483 mm)": (329.0, 483.0),
    "B5 JIS (182 × 257 mm)": (182.0, 257.0),
    "Letter (216 × 279 mm)": (215.9, 279.4),
    "Legal (216 × 356 mm)": (215.9, 355.6),
    "4 × 6 in (102 × 152 mm)": (101.6, 152.4),
    "5 × 7 in (127 × 178 mm)": (127.0, 177.8),
    "自訂尺寸": (210.0, 297.0),
}


@dataclass(frozen=True)
class PageRef:
    document_index: int
    page_index: int


@dataclass(frozen=True)
class LayoutRects:
    """Geometry independent from Qt.

    target_x/y/w/h use the same units as page_width/page_height.
    source_x/y/w/h use source image pixel coordinates.
    """

    target_x: float
    target_y: float
    target_w: float
    target_h: float
    source_x: float
    source_y: float
    source_w: float
    source_h: float


def layout_rects(
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
    mode: str,
    actual_width: Optional[float] = None,
    actual_height: Optional[float] = None,
) -> LayoutRects:
    """Calculate Fit/Fill/Actual placement.

    For ``actual``, actual_width/actual_height must use the same physical units
    represented by page_width/page_height (e.g. mm for preview, device pixels
    for printing after converting the physical size to printer pixels).
    """
    if page_width <= 0 or page_height <= 0 or image_width <= 0 or image_height <= 0:
        return LayoutRects(0, 0, max(page_width, 0), max(page_height, 0), 0, 0, max(image_width, 0), max(image_height, 0))

    if mode == "actual":
        if not actual_width or not actual_height or actual_width <= 0 or actual_height <= 0:
            # A safe fallback; the caller should normally always provide it.
            mode = "fit"
        else:
            x = (page_width - actual_width) / 2.0
            y = (page_height - actual_height) / 2.0
            return LayoutRects(
                x,
                y,
                actual_width,
                actual_height,
                0.0,
                0.0,
                float(image_width),
                float(image_height),
            )

    page_ratio = page_width / page_height
    image_ratio = image_width / image_height

    if mode == "fill":
        # Scale to cover page, cropping the source symmetrically.
        if image_ratio > page_ratio:
            visible_w = image_height * page_ratio
            left = (image_width - visible_w) / 2.0
            source_x, source_y, source_w, source_h = left, 0.0, visible_w, float(image_height)
        else:
            visible_h = image_width / page_ratio
            top = (image_height - visible_h) / 2.0
            source_x, source_y, source_w, source_h = 0.0, top, float(image_width), visible_h
        return LayoutRects(
            0.0,
            0.0,
            page_width,
            page_height,
            source_x,
            source_y,
            source_w,
            source_h,
        )

    # Default: fit, preserving the whole page/image.
    if image_ratio > page_ratio:
        width = page_width
        height = width / image_ratio
    else:
        height = page_height
        width = height * image_ratio
    x = (page_width - width) / 2.0
    y = (page_height - height) / 2.0
    return LayoutRects(
        x,
        y,
        width,
        height,
        0.0,
        0.0,
        float(image_width),
        float(image_height),
    )


def pil_to_qimage(image: Image.Image):
    from PySide6.QtGui import QImage

    image = image.convert("RGB")
    raw = image.tobytes("raw", "RGB")
    qimage = QImage(
        raw,
        image.width,
        image.height,
        image.width * 3,
        QImage.Format.Format_RGB888,
    )
    # Detach from the Python bytes buffer before returning.
    return qimage.copy()


def target_rect_for_image(
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
    mode: str,
    actual_width: Optional[float] = None,
    actual_height: Optional[float] = None,
):
    from PySide6.QtCore import QRectF

    r = layout_rects(
        page_width,
        page_height,
        image_width,
        image_height,
        mode,
        actual_width,
        actual_height,
    )
    return (
        QRectF(r.target_x, r.target_y, r.target_w, r.target_h),
        QRectF(r.source_x, r.source_y, r.source_w, r.source_h),
    )
