import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image, ImageCms
import pypdfium2 as pdfium

from iccprint.documents import (
    LoadedDocument,
    _pdf_page_count,
    _valid_dpi,
    convert_office_to_pdf,
    load_document,
    render_page,
)


class DpiValidationTests(unittest.TestCase):
    def test_pair(self):
        self.assertEqual(_valid_dpi((300, 600)), (300.0, 600.0))

    def test_scalar(self):
        self.assertEqual(_valid_dpi(254), (254.0, 254.0))

    def test_invalid(self):
        for value in ((0, 300), "not-a-dpi", None, (), (float("nan"), 300), float("inf"), 100000):
            with self.subTest(value=value):
                self.assertIsNone(_valid_dpi(value))


class DocumentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "source.png"
        with Image.new("RGB", (40, 20), "red") as image:
            image.save(self.path)

    def load_image(self):
        return load_document(self.path, self.root)

    def test_render_image_is_owned_and_has_unknown_physical_size_without_dpi(self):
        document = self.load_image()
        result = render_page(document, 0, 300)
        try:
            self.assertEqual(result.image.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(result.image.size, (40, 20))
            self.assertIsNone(result.physical_width_in)
            self.assertIsNone(result.native_dpi_x)
            self.assertIn("假設", result.source_label)
        finally:
            result.image.close()
        # No live Pillow file handle remains after returning the rendered image.
        self.path.unlink()

    def test_embedded_profile_bytes_preserved_including_invalid_bytes(self):
        for profile in (b"broken ICC", ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()):
            with Image.new("RGB", (2, 2)) as image:
                image.save(self.path, icc_profile=profile)
            result = render_page(self.load_image(), 0, 100)
            try:
                self.assertEqual(result.embedded_icc, profile)
                self.assertIn("內嵌 ICC", result.source_label)
            finally:
                result.image.close()

    def test_exif_rotation_swaps_anisotropic_dpi_axes(self):
        path = self.root / "rotated.jpg"
        for orientation in (5, 6, 7, 8):
            with Image.new("RGB", (600, 300)) as image:
                exif = Image.Exif()
                exif[274] = orientation
                image.save(path, dpi=(300, 150), exif=exif)
            result = render_page(load_document(path, self.root), 0, 300)
            try:
                with self.subTest(orientation=orientation):
                    self.assertEqual(result.image.size, (300, 600))
                    self.assertEqual((result.native_dpi_x, result.native_dpi_y), (150, 300))
                    self.assertEqual((result.physical_width_in, result.physical_height_in), (2, 2))
                    self.assertNotIn(274, result.image.getexif())
            finally:
                result.image.close()

    def test_exif_mirror_does_not_swap_dpi(self):
        path = self.root / "mirror.jpg"
        with Image.new("RGB", (600, 300)) as image:
            exif = Image.Exif()
            exif[274] = 2
            image.save(path, dpi=(300, 150), exif=exif)
        result = render_page(load_document(path, self.root), 0, 300)
        try:
            self.assertEqual(result.image.size, (600, 300))
            self.assertEqual((result.native_dpi_x, result.native_dpi_y), (300, 150))
        finally:
            result.image.close()

    def test_untagged_cmyk_never_labeled_srgb(self):
        path = self.root / "cmyk.tif"
        with Image.new("CMYK", (10, 10)) as image:
            image.save(path)
        result = render_page(load_document(path, self.root), 0, 72)
        try:
            self.assertEqual(result.image.mode, "CMYK")
            self.assertIn("缺少來源 ICC", result.source_label)
            self.assertNotIn("sRGB", result.source_label)
        finally:
            result.image.close()

    def test_multipage_tiff_frame_selection(self):
        path = self.root / "multiple.tif"
        with Image.new("RGB", (4, 3), "red") as first, Image.new("RGB", (7, 5), "blue") as second:
            first.save(path, save_all=True, append_images=[second])
        doc = load_document(path, self.root)
        self.assertEqual(doc.page_count, 2)
        result = render_page(doc, 1, 300)
        try:
            self.assertEqual(result.image.size, (7, 5))
            self.assertEqual(result.image.getpixel((0, 0)), (0, 0, 255))
        finally:
            result.image.close()

    def test_render_request_validates_before_opening_files(self):
        doc = self.load_image()
        for index in (-1, 1, True, 0.5, "0"):
            with self.subTest(index=index), patch("iccprint.documents.Image.open") as opened:
                with self.assertRaises(ValueError):
                    render_page(doc, index, 300)
                opened.assert_not_called()
        for dpi in (0, -10, 2401, 10**1000, float("nan"), float("inf"), "300", True):
            with self.subTest(dpi=dpi), patch("iccprint.documents.Image.open") as opened:
                with self.assertRaises(ValueError):
                    render_page(doc, 0, dpi)
                opened.assert_not_called()
        for doc in (LoadedDocument(self.path, self.path, "image", 0), LoadedDocument(self.path, self.path, "unknown", 1)):
            with self.assertRaises(ValueError):
                render_page(doc, 0, 300)

    def test_raster_limit_is_checked_before_decode_and_on_render(self):
        doc = self.load_image()
        with patch("iccprint.documents.MAX_RASTER_PIXELS", 100):
            with self.assertRaisesRegex(ValueError, "記憶體"):
                self.load_image()
            with patch("iccprint.documents.ImageOps.exif_transpose") as transpose:
                with self.assertRaisesRegex(ValueError, "記憶體"):
                    render_page(doc, 0, 300)
                transpose.assert_not_called()

    def test_document_changed_page_count_has_actionable_error(self):
        doc = self.load_image()
        doc.page_count = 2
        with self.assertRaisesRegex(ValueError, "頁數已變更"):
            render_page(doc, 1, 72)

    def create_pdf(self):
        path = self.root / "document.pdf"
        pdf = pdfium.PdfDocument.new()
        try:
            page = pdf.new_page(144, 72)
            page.close()
            page = pdf.new_page(72, 216)
            page.close()
            pdf.save(path)
        finally:
            pdf.close()
        return path

    def test_real_pdf_render_has_correct_physical_and_raster_dimensions(self):
        path = self.create_pdf()
        doc = load_document(path, self.root)
        self.assertEqual(doc.page_count, 2)
        result = render_page(doc, 1, 144)
        try:
            self.assertEqual(result.image.size, (144, 432))
            self.assertEqual(result.image.mode, "RGB")
            self.assertEqual(result.image.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual((result.physical_width_in, result.physical_height_in), (1, 3))
            self.assertIsNone(result.embedded_icc)
        finally:
            result.image.close()
        path.unlink()

    def fake_pdf(self, size=(144, 72)):
        pdf, page, bitmap = MagicMock(), MagicMock(), MagicMock()
        pdf.__len__.return_value = 1
        pdf.__getitem__.return_value = page
        page.get_size.return_value = size
        page.render.return_value = bitmap
        return pdf, page, bitmap

    def test_pdf_allocation_limit_precedes_render_and_closes_handles(self):
        pdf, page, bitmap = self.fake_pdf((100000, 100000))
        doc = LoadedDocument(self.path, self.path, "pdf", 1)
        with patch("pypdfium2.PdfDocument", return_value=pdf):
            with self.assertRaisesRegex(ValueError, "記憶體"):
                render_page(doc, 0, 300)
        page.render.assert_not_called()
        page.close.assert_called_once()
        pdf.close.assert_called_once()

    def test_huge_finite_pdf_dimensions_do_not_overflow(self):
        pdf, page, bitmap = self.fake_pdf((1e308, 100))
        doc = LoadedDocument(self.path, self.path, "pdf", 1)
        with patch("pypdfium2.PdfDocument", return_value=pdf):
            with self.assertRaisesRegex(ValueError, "記憶體"):
                render_page(doc, 0, 2400)
        page.render.assert_not_called()
        page.close.assert_called_once()
        pdf.close.assert_called_once()

    def test_bad_pdf_size_closes_handles(self):
        for size in ((0, 100), (float("nan"), 100), (float("inf"), 100)):
            pdf, page, bitmap = self.fake_pdf(size)
            doc = LoadedDocument(self.path, self.path, "pdf", 1)
            with self.subTest(size=size), patch("pypdfium2.PdfDocument", return_value=pdf):
                with self.assertRaisesRegex(ValueError, "尺寸無效"):
                    render_page(doc, 0, 300)
            page.render.assert_not_called()
            page.close.assert_called_once()
            pdf.close.assert_called_once()

    def test_pdf_pil_failure_closes_bitmap_page_and_document(self):
        pdf, page, bitmap = self.fake_pdf()
        bitmap.to_pil.side_effect = RuntimeError("decode failed")
        doc = LoadedDocument(self.path, self.path, "pdf", 1)
        with patch("pypdfium2.PdfDocument", return_value=pdf):
            with self.assertRaisesRegex(RuntimeError, "decode failed"):
                render_page(doc, 0, 300)
        for native in (bitmap, page, pdf):
            native.close.assert_called_once()

    def test_zero_page_pdf_is_rejected_and_closed(self):
        pdf = MagicMock()
        pdf.__len__.return_value = 0
        with patch("pypdfium2.PdfDocument", return_value=pdf):
            with self.assertRaisesRegex(ValueError, "沒有可列印"):
                _pdf_page_count(self.path)
        pdf.close.assert_called_once()

    def test_missing_file_and_unsupported_extension_rejected(self):
        with self.assertRaises(FileNotFoundError):
            load_document(self.root / "missing.pdf", self.root)
        with self.assertRaises(ValueError):
            load_document(self.root / "unknown.xyz", self.root)


class OfficeConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source file.docx"
        self.source.write_bytes(b"document fixture")
        self.output = self.root / "output"
        self.output.mkdir()
        self.expected = self.output / "source file.pdf"
        patcher = patch("iccprint.documents.find_libreoffice", return_value="/fake/soffice")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_isolated_user_profile_and_cleanup_on_success(self):
        observed = {}
        def convert(command, **kwargs):
            observed["command"] = command
            observed["kwargs"] = kwargs
            profiles = list(self.output.glob("lo_profile_*"))
            self.assertEqual(len(profiles), 1)
            self.assertTrue(profiles[0].is_dir())
            self.assertIn(f"-env:UserInstallation={profiles[0].resolve().as_uri()}", command)
            self.expected.write_bytes(b"%PDF-test")
            return SimpleNamespace(returncode=0, stdout="converted", stderr="")
        with patch("iccprint.documents.subprocess.run", side_effect=convert):
            self.assertEqual(convert_office_to_pdf(self.source, self.output), self.expected.resolve())
        self.assertEqual(list(self.output.glob("lo_profile_*")), [])
        self.assertEqual(observed["kwargs"]["timeout"], 120)
        self.assertIn(str(self.source.resolve()), observed["command"])
        self.assertNotIn("shell", observed["kwargs"])

    def test_timeout_removes_partial_pdf_and_profile(self):
        def timeout(*args, **kwargs):
            self.expected.write_bytes(b"partial")
            raise subprocess.TimeoutExpired("soffice", 120)
        with patch("iccprint.documents.subprocess.run", side_effect=timeout):
            with self.assertRaisesRegex(RuntimeError, "120 秒"):
                convert_office_to_pdf(self.source, self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_nonzero_result_removes_partial_pdf(self):
        def fail(*args, **kwargs):
            self.expected.write_bytes(b"partial")
            return SimpleNamespace(returncode=1, stderr="format error", stdout="")
        with patch("iccprint.documents.subprocess.run", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "format error"):
                convert_office_to_pdf(self.source, self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_success_exit_without_output_is_failure(self):
        with patch("iccprint.documents.subprocess.run", return_value=SimpleNamespace(returncode=0, stderr="", stdout="")):
            with self.assertRaisesRegex(RuntimeError, "轉 PDF 失敗"):
                convert_office_to_pdf(self.source, self.output)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_stale_destination_never_reused_or_deleted(self):
        self.expected.write_bytes(b"existing PDF")
        with patch("iccprint.documents.subprocess.run") as run:
            with self.assertRaises(FileExistsError):
                convert_office_to_pdf(self.source, self.output)
            run.assert_not_called()
        self.assertEqual(self.expected.read_bytes(), b"existing PDF")

    def test_load_document_cleans_conversion_directory_on_failure(self):
        for failing_step in ("convert", "validate"):
            with self.subTest(step=failing_step):
                def convert(source, directory):
                    (directory / "partial.pdf").write_bytes(b"partial")
                    if failing_step == "convert":
                        raise RuntimeError("conversion failed")
                    return directory / "partial.pdf"
                with patch("iccprint.documents.convert_office_to_pdf", side_effect=convert):
                    with patch("iccprint.documents._pdf_page_count", side_effect=RuntimeError("bad PDF")):
                        with self.assertRaises(RuntimeError):
                            load_document(self.source, self.root)
                self.assertEqual(list(self.root.glob("office_*")), [])

    def test_missing_libreoffice_has_pdf_workaround(self):
        with patch("iccprint.documents.find_libreoffice", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "另存成 PDF"):
                convert_office_to_pdf(self.source, self.output)


if __name__ == "__main__":
    unittest.main()
