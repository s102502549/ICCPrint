"""Cancellable worker and prepared-output regressions; no physical printers."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from PIL import Image, ImageCms

from iccprint.documents import LoadedDocument, RenderedPage, load_document
from iccprint.jobs import (Cancelled, ColorOptions, PreparedJob, Task, make_preview,
                           physical_size, prepare_job, import_documents)
from iccprint.printing import PageRef


def printer_profile(path):
    """Synthetic RGB output-device fixture, never a real printer characterization."""
    data = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    data[12:16] = b"prtr"
    path.write_bytes(data)
    return str(path)


class TaskTests(unittest.TestCase):
    def test_cancel_before_run_never_calls_function(self):
        function = Mock()
        task = Task(4, function)
        results, errors, finished = [], [], []
        task.signals.result.connect(lambda *args: results.append(args))
        task.signals.error.connect(lambda *args: errors.append(args))
        task.signals.finished.connect(finished.append)
        task.cancel.set()
        task.run()
        function.assert_not_called()
        self.assertEqual((results, errors, finished), ([], [], [4]))

    def test_late_cancellation_still_delivers_owned_result(self):
        owned = object()
        def function(cancel, progress):
            progress(1, "ready")
            cancel.set()
            return owned
        task = Task(7, function)
        results, progresses, finished = [], [], []
        task.signals.result.connect(lambda *args: results.append(args))
        task.signals.progress.connect(lambda *args: progresses.append(args))
        task.signals.finished.connect(finished.append)
        task.run()
        self.assertEqual(results, [(7, owned)])
        self.assertEqual(progresses, [(7, 1, "ready")])
        self.assertEqual(finished, [7])

    def test_exception_reports_error_then_finished_without_result(self):
        task = Task(9, Mock(side_effect=RuntimeError("bad page")))
        events = []
        task.signals.error.connect(lambda *args: events.append(("error", args)))
        task.signals.result.connect(lambda *args: events.append(("result", args)))
        task.signals.finished.connect(lambda token: events.append(("finished", token)))
        task.run()
        self.assertEqual(events, [("error", (9, "bad page")), ("finished", 9)])

    def test_cancelled_is_not_reported_as_error(self):
        task = Task(3, Mock(side_effect=Cancelled()))
        errors, finished = [], []
        task.signals.error.connect(lambda *args: errors.append(args))
        task.signals.finished.connect(finished.append)
        task.run()
        self.assertEqual(errors, [])
        self.assertEqual(finished, [3])


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "jobs"
        self.output.mkdir()
        self.profile = printer_profile(self.root / "printer.icc")
        self.options = ColorOptions(self.profile, ImageCms.Intent.RELATIVE_COLORIMETRIC,
                                    True, 300, 150)
        self.image_path = self.root / "source.png"
        with Image.new("RGB", (120, 60), "red") as image:
            image.save(self.image_path, dpi=(300, 300))
        self.document = load_document(self.image_path, self.temp.name)
        self.refs = (PageRef(0, 0),)

    def prepare(self, cancel=None, progress=None, refs=None):
        return prepare_job(cancel or Event(), progress or Mock(), (self.document,),
                           refs or self.refs, self.options, str(self.output))

    def test_prepare_real_image_and_profile_untagged_output(self):
        job = self.prepare()
        self.addCleanup(job.cleanup)
        self.assertEqual(len(job.pages), 1)
        self.assertTrue((job.directory / "output.icc").exists())
        page = job.pages[0]
        self.assertAlmostEqual(page.width_in, 0.4, places=3)
        self.assertAlmostEqual(page.height_in, 0.2, places=3)
        with Image.open(page.path) as image:
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (120, 60))
            self.assertFalse(image.info.get("icc_profile"))
        job.cleanup()
        job.cleanup()  # Ownership cleanup is safe twice.
        self.assertFalse(job.directory.exists())

    def test_cancel_before_prepare_cleans_created_directory(self):
        cancel = Event()
        cancel.set()
        with patch("iccprint.jobs.render_page") as render:
            with self.assertRaises(Cancelled):
                self.prepare(cancel)
        render.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_cancel_after_render_closes_source_and_cleans_directory(self):
        cancel = Event()
        source = Image.new("RGB", (10, 10))
        def render(*args):
            cancel.set()
            return RenderedPage(source, None, "source")
        with patch("iccprint.jobs.render_page", side_effect=render), patch("iccprint.jobs.convert_to_printer_rgb") as convert:
            with self.assertRaises(Cancelled):
                self.prepare(cancel)
        convert.assert_not_called()
        with self.assertRaises(ValueError):
            source.getpixel((0, 0))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_cancel_after_conversion_closes_images_and_cleans_directory(self):
        cancel = Event()
        source, converted = Image.new("RGB", (10, 10)), Image.new("RGB", (10, 10))
        def convert(*args):
            cancel.set()
            return converted
        with patch("iccprint.jobs.render_page", return_value=RenderedPage(source, None, "source")), patch("iccprint.jobs.convert_to_printer_rgb", side_effect=convert):
            with self.assertRaises(Cancelled):
                self.prepare(cancel)
        for image in (source, converted):
            with self.assertRaises(ValueError):
                image.getpixel((0, 0))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_conversion_failure_closes_image_and_cleans_directory(self):
        source = Image.new("RGB", (10, 10))
        with patch("iccprint.jobs.render_page", return_value=RenderedPage(source, None, "source")), patch("iccprint.jobs.convert_to_printer_rgb", side_effect=ValueError("bad transform")):
            with self.assertRaisesRegex(ValueError, "bad transform"):
                self.prepare()
        with self.assertRaises(ValueError):
            source.getpixel((0, 0))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_failure_on_late_page_removes_prior_prepared_pages(self):
        calls = 0
        from iccprint.jobs import render_page
        def render(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("corrupt later page")
            return render_page(*args)
        with patch("iccprint.jobs.render_page", side_effect=render):
            with self.assertRaisesRegex(ValueError, "corrupt later page"):
                self.prepare(refs=self.refs * 2)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_save_failure_removes_partial_output_and_closes_images(self):
        source, converted = Image.new("RGB", (10, 10)), Image.new("RGB", (10, 10))
        with patch("iccprint.jobs.render_page", return_value=RenderedPage(source, None, "source")), patch("iccprint.jobs.convert_to_printer_rgb", return_value=converted), patch.object(converted, "save", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.prepare()
        for image in (source, converted):
            with self.assertRaises(ValueError):
                image.getpixel((0, 0))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_source_changed_during_render_rejected_and_image_closed(self):
        source = Image.new("RGB", (10, 10))
        def render(*args):
            self.image_path.write_bytes(self.image_path.read_bytes() + b"changed")
            return RenderedPage(source, None, "source")
        with patch("iccprint.jobs.render_page", side_effect=render), patch("iccprint.jobs.convert_to_printer_rgb") as convert:
            with self.assertRaisesRegex(ValueError, "變更"):
                self.prepare()
        convert.assert_not_called()
        with self.assertRaises(ValueError):
            source.getpixel((0, 0))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_source_changed_between_pages_discards_whole_preparation(self):
        from iccprint.jobs import convert_to_printer_rgb
        def convert(*args):
            converted = convert_to_printer_rgb(*args)
            self.image_path.write_bytes(self.image_path.read_bytes() + b"changed")
            return converted
        with patch("iccprint.jobs.convert_to_printer_rgb", side_effect=convert) as transform:
            with self.assertRaisesRegex(ValueError, "變更"):
                self.prepare(refs=self.refs * 2)
        self.assertEqual(transform.call_count, 1)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_disappeared_source_cleans_temporary_job(self):
        self.image_path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_profile_snapshot_used_for_every_page(self):
        used_profiles = []
        from iccprint.jobs import convert_to_printer_rgb
        def convert(image, profile, *args):
            used_profiles.append(Path(profile).read_bytes())
            return convert_to_printer_rgb(image, profile, *args)
        original = Path(self.profile).read_bytes()
        def progress(current, message):
            if current == 0:
                Path(self.profile).write_bytes(b"replaced externally")
        with patch("iccprint.jobs.convert_to_printer_rgb", side_effect=convert):
            job = self.prepare(progress=progress, refs=self.refs * 2)
        self.addCleanup(job.cleanup)
        self.assertEqual(used_profiles, [original, original])

    def test_missing_profile_creates_no_temporary_output(self):
        options = ColorOptions(None, 1, True, 300, 150)
        with self.assertRaises(ValueError):
            prepare_job(Event(), Mock(), (self.document,), self.refs, options, str(self.output))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_physical_size_uses_metadata_or_fallback(self):
        with Image.new("RGB", (600, 300)) as image:
            self.assertEqual(physical_size(RenderedPage(image, None, "x", 2, 1, 300, 300), 150)[:2], (2, 1))
            self.assertEqual(physical_size(RenderedPage(image, None, "x"), 150)[:2], (4, 2))

    def test_real_preview_owns_qimage_after_pillow_sources_close(self):
        result = make_preview(Event(), Mock(), self.document, 0, self.options)
        self.assertFalse(result.image.isNull())
        self.assertEqual((result.width_px, result.height_px), (120, 60))
        self.assertGreater(result.image.pixelColor(0, 0).red(), 240)

    def test_preview_cancellation_closes_rendered_source(self):
        cancel = Event()
        source = Image.new("RGB", (10, 10))
        def render(*args):
            cancel.set()
            return RenderedPage(source, None, "source")
        with patch("iccprint.jobs.render_page", side_effect=render):
            with self.assertRaises(Cancelled):
                make_preview(cancel, Mock(), self.document, 0, self.options)
        with self.assertRaises(ValueError):
            source.getpixel((0, 0))

    def test_nonproof_preview_still_converts_source_color(self):
        source = Image.new("RGB", (2000, 1000))
        display = Image.new("RGB", (2000, 1000), "blue")
        options = ColorOptions(None, 1, True, 300, 600, False)
        with patch("iccprint.jobs.render_page", return_value=RenderedPage(source, b"source-profile", "source")) as render, patch("iccprint.jobs.source_to_srgb", return_value=display) as convert:
            result = make_preview(Event(), Mock(), self.document, 0, options)
        render.assert_called_once_with(self.document, 0, 120)
        convert.assert_called_once_with(source, b"source-profile")
        self.assertEqual((result.width_px, result.height_px), (2000, 1000))
        self.assertEqual((result.image.width(), result.image.height()), (1600, 800))
        for image in (source, display):
            with self.assertRaises(ValueError):
                image.getpixel((0, 0))


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        with Image.new("RGB", (10, 10)) as image:
            image.save(self.source)

    def test_import_deduplicates_existing_and_repeated_paths(self):
        existing = frozenset({os.path.normcase(str(self.source.resolve()))})
        result = import_documents(Event(), Mock(), (str(self.source),), str(self.root), existing)
        self.assertEqual(result.documents, [])
        result = import_documents(Event(), Mock(), (str(self.source), str(self.source)), str(self.root), frozenset())
        self.assertEqual(len(result.documents), 1)
        self.assertEqual(result.errors, [])

    def test_import_keeps_good_files_and_reports_each_bad_file(self):
        result = import_documents(Event(), Mock(), (str(self.source), str(self.root / "missing.png"), str(self.root / "unknown.xyz")), str(self.root), frozenset())
        self.assertEqual(len(result.documents), 1)
        self.assertEqual(len(result.errors), 2)
        self.assertIn("missing.png", result.errors[0])
        self.assertIn("unknown.xyz", result.errors[1])

    def test_cancelled_import_cleans_owned_office_outputs_only(self):
        cancel = Event()
        office_dir = self.root / "office_fixture"
        office_dir.mkdir()
        output = office_dir / "converted.pdf"
        output.write_bytes(b"fixture")
        doc = LoadedDocument(self.root / "source.docx", output, "office_pdf", 1, True)
        def load(*args):
            cancel.set()
            return doc
        with patch("iccprint.documents.load_document", side_effect=load):
            with self.assertRaises(Cancelled):
                import_documents(cancel, Mock(), (str(doc.original_path),), str(self.root), frozenset())
        self.assertFalse(office_dir.exists())
        self.assertTrue(self.source.exists())

    def test_cancelled_import_never_deletes_original_images(self):
        cancel = Event()
        doc = LoadedDocument(self.source, self.source, "image", 1, False)
        def load(*args):
            cancel.set()
            return doc
        with patch("iccprint.documents.load_document", side_effect=load):
            with self.assertRaises(Cancelled):
                import_documents(cancel, Mock(), (str(self.source),), str(self.root), frozenset())
        self.assertTrue(self.source.exists())


if __name__ == "__main__":
    unittest.main()
