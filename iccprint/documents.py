from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
PDF_EXTENSIONS = {".pdf"}
OFFICE_EXTENSIONS = {
    ".doc", ".docx", ".odt", ".rtf",
    ".xls", ".xlsx", ".ods",
    ".ppt", ".pptx", ".odp",
}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS | OFFICE_EXTENSIONS
# Bound individual allocations before decoding/rasterizing. Several source,
# transform and Qt buffers can coexist; do not disable Pillow's own bomb checks.
MAX_RASTER_PIXELS = 100_000_000
MAX_RASTER_DIMENSION = 32_768
MIN_RENDER_DPI = 1
MAX_RENDER_DPI = 2_400


@dataclass
class LoadedDocument:
    original_path: Path
    prepared_path: Path
    kind: str  # image | pdf | office_pdf
    page_count: int
    temporary: bool = False

    @property
    def display_type(self) -> str:
        if self.kind == "image":
            return "圖片"
        if self.kind == "office_pdf":
            return "Office → PDF"
        return "PDF"


@dataclass
class RenderedPage:
    image: Image.Image
    embedded_icc: Optional[bytes]
    source_label: str
    # Physical size is unknown for a raster image with no usable embedded DPI.
    physical_width_in: Optional[float] = None
    physical_height_in: Optional[float] = None
    native_dpi_x: Optional[float] = None
    native_dpi_y: Optional[float] = None


def find_libreoffice() -> Optional[str]:
    candidates = [shutil.which("soffice"), shutil.which("libreoffice")]
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        if os.environ.get(variable):
            candidates.append(str(Path(os.environ[variable]) / "LibreOffice" / "program" / "soffice.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _require_pages(count: int) -> int:
    if count < 1:
        raise ValueError("文件沒有可列印的頁面。請重新匯出後再加入。")
    return count


def _check_raster_size(width: int, height: int) -> None:
    if width < 1 or height < 1:
        raise ValueError("圖片或 PDF 頁面尺寸必須大於零。")
    if width > MAX_RASTER_DIMENSION or height > MAX_RASTER_DIMENSION or width * height > MAX_RASTER_PIXELS:
        raise ValueError(
            f"此頁面預計產生 {width:,} × {height:,} 像素，超過安全記憶體上限"
            f"（{MAX_RASTER_PIXELS:,} 像素、單邊 {MAX_RASTER_DIMENSION:,}）。"
            "請降低輸出 DPI，或先在原程式縮小圖片 / 頁面。"
        )


def _pdf_page_count(path: Path) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        return _require_pages(len(pdf))
    finally:
        pdf.close()


def _image_page_count(path: Path) -> int:
    with Image.open(path) as img:
        _check_raster_size(*img.size)
        return _require_pages(int(getattr(img, "n_frames", 1)))


def convert_office_to_pdf(path: Path, temp_dir: Path) -> Path:
    """Convert in an isolated LibreOffice profile; never reuse a desktop instance."""
    path, temp_dir = Path(path).resolve(), Path(temp_dir).resolve()
    soffice = find_libreoffice()
    if not soffice:
        raise RuntimeError(
            "要直接開 Word / Excel / PowerPoint，需要先安裝免費 LibreOffice。\n"
            "你也可以先在原程式另存成 PDF，再加入 ICCPrint。"
        )
    temp_dir.mkdir(parents=True, exist_ok=True)
    expected = temp_dir / f"{path.stem}.pdf"
    if expected.exists():
        raise FileExistsError("轉換目的地已有同名 PDF；請使用新的暫存目錄，避免誤讀舊檔。")
    try:
        with tempfile.TemporaryDirectory(prefix="lo_profile_", dir=temp_dir) as profile_dir:
            result = subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={Path(profile_dir).as_uri()}",
                    "--headless", "--nologo", "--nodefault", "--nofirststartwizard",
                    "--convert-to", "pdf", "--outdir", str(temp_dir), str(path),
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=120,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        if result.returncode != 0 or not expected.is_file() or expected.stat().st_size == 0:
            details = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"LibreOffice 轉 PDF 失敗。{('\n' + details) if details else ''}")
        return expected
    except subprocess.TimeoutExpired as exc:
        expected.unlink(missing_ok=True)
        raise RuntimeError("LibreOffice 轉 PDF 超過 120 秒。請先在原程式另存成 PDF，再加入 ICCPrint。") from exc
    except Exception:
        expected.unlink(missing_ok=True)
        raise


def load_document(path: str | Path, temp_dir: str | Path) -> LoadedDocument:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支援的檔案格式：{ext or '(無副檔名)'}")
    if not path.is_file():
        raise FileNotFoundError(f"找不到可讀取的檔案：{path}")
    if ext in IMAGE_EXTENSIONS:
        return LoadedDocument(path, path, "image", _image_page_count(path), False)
    if ext in PDF_EXTENSIONS:
        return LoadedDocument(path, path, "pdf", _pdf_page_count(path), False)
    office_dir = Path(temp_dir) / f"office_{uuid.uuid4().hex}"
    office_dir.mkdir(parents=True, exist_ok=False)
    try:
        prepared = convert_office_to_pdf(path, office_dir)
        return LoadedDocument(path, prepared, "office_pdf", _pdf_page_count(prepared), True)
    except Exception:
        shutil.rmtree(office_dir, ignore_errors=True)
        raise


def _valid_dpi(value) -> Optional[tuple[float, float]]:
    try:
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            x, y = float(value[0]), float(value[1])
        else:
            x = y = float(value)
        if math.isfinite(x) and math.isfinite(y) and 1.0 < x < 100000 and 1.0 < y < 100000:
            return x, y
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _validate_render_request(document: LoadedDocument, page_index: int, dpi: int) -> None:
    if document.kind not in {"image", "pdf", "office_pdf"}:
        raise ValueError(f"不支援的文件類型：{document.kind}")
    _require_pages(document.page_count)
    if isinstance(page_index, bool) or not isinstance(page_index, Integral) or not 0 <= page_index < document.page_count:
        raise ValueError(f"頁碼超出範圍；有效頁面是 1–{document.page_count}。")
    if isinstance(dpi, bool) or not isinstance(dpi, Real) or not MIN_RENDER_DPI <= dpi <= MAX_RENDER_DPI or not math.isfinite(dpi):
        raise ValueError(f"輸出 DPI 必須介於 {MIN_RENDER_DPI} 與 {MAX_RENDER_DPI}。")


def _image_source_label(mode: str, embedded_icc: Optional[bytes]) -> str:
    if embedded_icc is not None:
        return "圖片內嵌 ICC（轉換前驗證）"
    if mode in {"CMYK", "LAB"}:
        return f"{mode}（缺少來源 ICC，無法安全轉換）"
    if mode not in {"RGB", "RGBA", "RGBa", "RGBX", "P", "L", "LA", "La", "1"}:
        return f"{mode}（需先轉存為 8-bit RGB）"
    return "sRGB（無內嵌 ICC，假設 sRGB）"


def render_page(document: LoadedDocument, page_index: int, dpi: int) -> RenderedPage:
    """Render an owned image. Caller must close it; all file/native handles close here."""
    _validate_render_request(document, page_index, dpi)
    if document.kind == "image":
        with Image.open(document.prepared_path) as src:
            if page_index >= int(getattr(src, "n_frames", 1)):
                raise ValueError("圖片頁數已變更，請移除文件後重新加入。")
            src.seek(page_index)
            _check_raster_size(*src.size)
            embedded_icc = src.info.get("icc_profile")
            native_dpi = _valid_dpi(src.info.get("dpi"))
            orientation = src.getexif().get(274, 1)
            # EXIF transpose rotates the pixel grid for orientations 5–8. The
            # x/y density values must rotate too for correct Actual-size output.
            if native_dpi and orientation in {5, 6, 7, 8}:
                native_dpi = native_dpi[1], native_dpi[0]
            image = ImageOps.exif_transpose(src)
            try:
                image.load()
            except Exception:
                image.close()
                raise
        physical_w = physical_h = dpi_x = dpi_y = None
        if native_dpi:
            dpi_x, dpi_y = native_dpi
            physical_w, physical_h = image.width / dpi_x, image.height / dpi_y
        return RenderedPage(
            image=image,
            embedded_icc=embedded_icc,
            source_label=_image_source_label(image.mode, embedded_icc),
            physical_width_in=physical_w,
            physical_height_in=physical_h,
            native_dpi_x=dpi_x,
            native_dpi_y=dpi_y,
        )

    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(document.prepared_path))
    try:
        if page_index >= len(pdf):
            raise ValueError("PDF 頁數已變更，請移除文件後重新加入。")
        page = pdf[page_index]
        try:
            width_pt, height_pt = page.get_size()
            if not all(math.isfinite(n) and n > 0 for n in (width_pt, height_pt)):
                raise ValueError("PDF 頁面尺寸無效。")
            scale = float(dpi) / 72.0
            width_px, height_px = width_pt * scale, height_pt * scale
            if not all(math.isfinite(n) for n in (width_px, height_px)):
                raise ValueError("PDF 頁面尺寸超過安全記憶體上限，請先縮小頁面。")
            _check_raster_size(math.ceil(width_px), math.ceil(height_px))
            bitmap = page.render(scale=scale)
            try:
                raw_image = bitmap.to_pil()
                try:
                    image = raw_image.convert("RGB")
                finally:
                    raw_image.close()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        pdf.close()
    # PDFium has already rasterized PDF color spaces to display RGB. Treat the
    # bitmap as sRGB; this is not preservation of PDF vectors or original ICCs.
    return RenderedPage(
        image=image,
        embedded_icc=None,
        source_label="PDF → sRGB（PDFium 點陣化）",
        physical_width_in=float(width_pt) / 72.0,
        physical_height_in=float(height_pt) / 72.0,
    )
