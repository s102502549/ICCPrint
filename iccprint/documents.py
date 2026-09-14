from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
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
    # Physical page/image size. For images this is None when no usable DPI is embedded.
    physical_width_in: Optional[float] = None
    physical_height_in: Optional[float] = None
    native_dpi_x: Optional[float] = None
    native_dpi_y: Optional[float] = None


def find_libreoffice() -> Optional[str]:
    candidates = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "LibreOffice", "program", "soffice.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "LibreOffice", "program", "soffice.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def _pdf_page_count(path: Path) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        return len(pdf)
    finally:
        pdf.close()


def _image_page_count(path: Path) -> int:
    with Image.open(path) as img:
        return int(getattr(img, "n_frames", 1))


def convert_office_to_pdf(path: Path, temp_dir: Path) -> Path:
    soffice = find_libreoffice()
    if not soffice:
        raise RuntimeError(
            "要直接開 Word / Excel / PowerPoint，需要先安裝免費 LibreOffice。\n"
            "你也可以先在原程式另存成 PDF，再加入 ICCPrint。"
        )

    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(temp_dir),
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    expected = temp_dir / f"{path.stem}.pdf"
    if result.returncode != 0 or not expected.exists():
        details = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"LibreOffice 轉 PDF 失敗。{('\n' + details) if details else ''}")
    return expected


def load_document(path: str | Path, temp_dir: str | Path) -> LoadedDocument:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支援的檔案格式：{ext or '(無副檔名)'}")

    if ext in IMAGE_EXTENSIONS:
        return LoadedDocument(path, path, "image", _image_page_count(path), False)

    if ext in PDF_EXTENSIONS:
        return LoadedDocument(path, path, "pdf", _pdf_page_count(path), False)

    office_dir = Path(temp_dir) / f"office_{uuid.uuid4().hex}"
    office_dir.mkdir(parents=True, exist_ok=True)
    prepared = convert_office_to_pdf(path, office_dir)
    return LoadedDocument(path, prepared, "office_pdf", _pdf_page_count(prepared), True)


def _valid_dpi(value) -> Optional[tuple[float, float]]:
    try:
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            x, y = float(value[0]), float(value[1])
        else:
            x = y = float(value)
        if x > 1.0 and y > 1.0 and x < 100000 and y < 100000:
            return x, y
    except Exception:
        pass
    return None


def render_page(document: LoadedDocument, page_index: int, dpi: int) -> RenderedPage:
    if document.kind == "image":
        with Image.open(document.prepared_path) as src:
            if page_index:
                src.seek(page_index)
            embedded_icc = src.info.get("icc_profile")
            native_dpi = _valid_dpi(src.info.get("dpi"))
            image = ImageOps.exif_transpose(src).copy()
            image.load()

        physical_w = physical_h = None
        dpi_x = dpi_y = None
        if native_dpi:
            dpi_x, dpi_y = native_dpi
            physical_w = image.width / dpi_x
            physical_h = image.height / dpi_y

        return RenderedPage(
            image=image,
            embedded_icc=embedded_icc,
            source_label="圖片內嵌 ICC" if embedded_icc else "sRGB（無內嵌 ICC）",
            physical_width_in=physical_w,
            physical_height_in=physical_h,
            native_dpi_x=dpi_x,
            native_dpi_y=dpi_y,
        )

    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(document.prepared_path))
    try:
        page = pdf[page_index]
        try:
            width_pt, height_pt = page.get_size()
            # PDF canvas units are normally 1/72 inch, so scale=dpi/72.
            bitmap = page.render(scale=float(dpi) / 72.0)
            try:
                image = bitmap.to_pil().convert("RGB")
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        pdf.close()

    # PDFium has already rendered all PDF color spaces into a display RGB bitmap.
    # ICCPrint treats that bitmap as sRGB before converting to the printer profile.
    return RenderedPage(
        image=image,
        embedded_icc=None,
        source_label="PDF → sRGB",
        physical_width_in=float(width_pt) / 72.0,
        physical_height_in=float(height_pt) / 72.0,
        native_dpi_x=None,
        native_dpi_y=None,
    )
