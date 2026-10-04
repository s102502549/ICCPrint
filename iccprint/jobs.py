"""Serial, cancellable work units. No worker touches widgets or a printer.

A single QThreadPool lane is used by MainWindow: PDFium is not thread-safe.
Output is prepared on disk before a printer job starts, bounding resident memory
and ensuring a late corrupt page never starts a partial print job.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from .color import convert_to_printer_rgb, softproof_to_srgb, source_to_srgb
from .documents import LoadedDocument, RenderedPage, render_page
from .printing import PageRef, pil_to_qimage


class Cancelled(Exception):
    """Cooperative cancellation between bounded processing stages."""


def checkpoint(cancel: Event):
    if cancel.is_set():
        raise Cancelled()


class TaskSignals(QObject):
    result = Signal(int, object)
    error = Signal(int, str)
    progress = Signal(int, int, str)
    finished = Signal(int)


class Task(QRunnable):
    def __init__(self, token: int, function: Callable, *args):
        super().__init__()
        self.token = token
        self.function = function
        self.args = args
        self.cancel = Event()
        self.signals = TaskSignals()

    @Slot()
    def run(self):
        try:
            checkpoint(self.cancel)
            result = self.function(self.cancel, self._progress, *self.args)
            # Resource-owning results must reach their owner even after a late cancel.
            self.signals.result.emit(self.token, result)
        except Cancelled:
            pass
        except Exception as exc:
            self.signals.error.emit(self.token, str(exc))
        finally:
            self.signals.finished.emit(self.token)

    def _progress(self, current: int, message: str):
        self.signals.progress.emit(self.token, current, message)


def physical_size(rendered: RenderedPage, fallback_dpi: int) -> tuple[float, float, str]:
    if rendered.physical_width_in and rendered.physical_height_in:
        if rendered.native_dpi_x and rendered.native_dpi_y:
            note = f"內嵌 DPI {rendered.native_dpi_x:.1f} × {rendered.native_dpi_y:.1f}"
        else:
            note = "文件實體尺寸"
        return rendered.physical_width_in, rendered.physical_height_in, note
    return (rendered.image.width / fallback_dpi, rendered.image.height / fallback_dpi,
            f"無內嵌 DPI，假設 {fallback_dpi} dpi")


@dataclass(frozen=True)
class ColorOptions:
    profile_path: str | None
    intent: int
    bpc: bool
    fallback_dpi: int
    raster_dpi: int
    proof: bool = True


@dataclass
class PreviewResult:
    image: object
    width_px: int
    height_px: int
    width_in: float
    height_in: float
    size_note: str
    source_label: str


def make_preview(cancel: Event, progress: Callable, document: LoadedDocument,
                 page: int, options: ColorOptions) -> PreviewResult:
    rendered = render_page(document, page, min(120, options.raster_dpi))
    source = display = None
    try:
        checkpoint(cancel)
        width, height = rendered.image.size
        w_in, h_in, note = physical_size(rendered, options.fallback_dpi)
        # RGB resizing must happen after source conversion, otherwise palette/CMYK
        # modes can lose their profile semantics. Transform before thumbnailing.
        if options.proof and options.profile_path:
            source = rendered.image.copy()
            # Preserve profile mode, especially CMYK, while bounding the proof transform.
            if source.mode not in {"P", "1"}:
                source.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            display = softproof_to_srgb(source, options.profile_path, options.intent,
                                        options.bpc, rendered.embedded_icc)
        else:
            display = source_to_srgb(rendered.image, rendered.embedded_icc)
        checkpoint(cancel)
        display.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        return PreviewResult(pil_to_qimage(display), width, height, w_in, h_in,
                             note, rendered.source_label)
    finally:
        if source is not None:
            source.close()
        if display is not None:
            display.close()
        rendered.image.close()


@dataclass(frozen=True)
class PreparedPage:
    path: Path
    width_in: float
    height_in: float


@dataclass
class PreparedJob:
    directory: Path
    pages: list[PreparedPage]

    def cleanup(self):
        shutil.rmtree(self.directory, ignore_errors=True)


def prepare_job(cancel: Event, progress: Callable, documents: tuple[LoadedDocument, ...],
                refs: tuple[PageRef, ...], options: ColorOptions, temp_root: str) -> PreparedJob:
    if not options.profile_path:
        raise ValueError("請先選擇印表機 ICC 描述檔。")
    directory = Path(tempfile.mkdtemp(prefix="print_", dir=temp_root))
    job = PreparedJob(directory, [])
    try:
        # Freeze the selected output profile for every page in this job.
        profile = directory / "output.icc"
        shutil.copyfile(options.profile_path, profile)
        signatures = {}
        for ref in refs:
            path = documents[ref.document_index].prepared_path
            stat = path.stat()
            signatures[path] = (stat.st_size, stat.st_mtime_ns, stat.st_ino)

        def unchanged(path):
            stat = path.stat()
            if (stat.st_size, stat.st_mtime_ns, stat.st_ino) != signatures[path]:
                raise ValueError(f"文件在準備期間已變更：{path.name}。請重新加入後再列印。")

        for i, ref in enumerate(refs):
            checkpoint(cancel)
            doc = documents[ref.document_index]
            unchanged(doc.prepared_path)
            progress(i, f"檢查與準備 {i + 1}/{len(refs)}：{doc.original_path.name}")
            rendered = render_page(doc, ref.page_index, options.raster_dpi)
            converted = None
            try:
                checkpoint(cancel)
                unchanged(doc.prepared_path)
                w_in, h_in, _ = physical_size(rendered, options.fallback_dpi)
                converted = convert_to_printer_rgb(rendered.image, profile, options.intent,
                                                   options.bpc, rendered.embedded_icc)
                checkpoint(cancel)
                path = directory / f"page-{i + 1:06d}.png"
                # Raw printer RGB is intentionally untagged at the Qt boundary.
                converted.save(path, format="PNG", icc_profile=b"")
                job.pages.append(PreparedPage(path, w_in, h_in))
            finally:
                if converted is not None:
                    converted.close()
                rendered.image.close()
        checkpoint(cancel)
        progress(len(refs), "全部頁面已通過檢查")
        return job
    except BaseException:
        job.cleanup()
        raise


@dataclass
class ImportResult:
    documents: list[LoadedDocument]
    errors: list[str]


def import_documents(cancel: Event, progress: Callable, paths: tuple[str, ...],
                     temp_root: str, existing: frozenset[str]) -> ImportResult:
    import os
    from .documents import load_document

    result = ImportResult([], [])
    known = set(existing)
    try:
        for i, raw in enumerate(paths):
            checkpoint(cancel)
            path = Path(raw)
            key = os.path.normcase(str(path.resolve()))
            if key in known:
                continue
            progress(i, f"開啟 {i + 1}/{len(paths)}：{path.name}")
            try:
                result.documents.append(load_document(path, temp_root))
                known.add(key)
            except Exception as exc:
                result.errors.append(f"{path.name}: {exc}")
        checkpoint(cancel)
        return result
    except BaseException:
        for document in result.documents:
            if document.temporary:
                shutil.rmtree(document.prepared_path.parent, ignore_errors=True)
        raise
