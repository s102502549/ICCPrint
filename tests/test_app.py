"""Headless UI/lifecycle tests with a PDF-only end-to-end printer target."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from PIL import Image, ImageCms
from PySide6.QtCore import QRectF, QSettings
from PySide6.QtGui import QCloseEvent, QImage, QPainter
from PySide6.QtPrintSupport import QPrinter, QAbstractPrintDialog
from PySide6.QtWidgets import QApplication, QProgressDialog, QDialog

from iccprint.app import MainWindow
from iccprint.documents import LoadedDocument, load_document
from iccprint.jobs import (ColorOptions, ImportResult, PreparedJob, PreparedPage, PreviewResult,
                           prepare_job)
from iccprint.printing import PageRef


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        self.settings_patch = patch("iccprint.app.QSettings", return_value=self.settings)
        self.settings_patch.start()
        self.dialog_patches = []
        for method in ("critical", "warning", "information"):
            p = patch(f"iccprint.app.QMessageBox.{method}")
            self.dialog_patches.append(p)
            setattr(self, method, p.start())
        self.window = MainWindow()
        self.window.preview_timer.stop()

    def tearDown(self):
        window = self.window
        window._closing = True
        for task in tuple(window._tasks.values()):
            task.cancel.set()
        window.pool.waitForDone(5000)
        self.app.processEvents()
        if window._printer is not None or window._prepared_job is not None:
            window._finish_print("cancelled")
        window._busy = False
        window.preview_timer.stop()
        window.close()
        window.deleteLater()
        self.app.processEvents()
        for p in self.dialog_patches:
            p.stop()
        self.settings_patch.stop()
        self.temp.cleanup()

    def wait_until(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(condition(), "Qt operation did not finish before test timeout")
        self.app.processEvents()

    def add_document(self, name="test.png", pages=1):
        path = self.root / name
        with Image.new("RGB", (120, 60), "red") as image:
            image.save(path)
        doc = LoadedDocument(path, path, "image", pages)
        self.window.documents.append(doc)
        self.window.file_list.addItem(name)
        self.window.preview_timer.stop()
        return doc

    def profile(self, name="printer.icc"):
        path = self.root / name
        data = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        data[12:16] = b"prtr"
        path.write_bytes(data)
        return path

    def prepared_job(self, pages=1):
        directory = Path(tempfile.mkdtemp(prefix="prepared_", dir=self.window.temp_dir_obj.name))
        prepared = []
        for index in range(pages):
            path = directory / f"page-{index}.png"
            with Image.new("RGB", (120, 60), "red" if index == 0 else "blue") as image:
                image.save(path)
            prepared.append(PreparedPage(path, 0.4, 0.2))
        return PreparedJob(directory, prepared)

    def begin_fake_spool(self, pages=1):
        window = self.window
        window._set_busy(True)
        window._operation_token = 11
        window._prepared_job = self.prepared_job(pages)
        window._spool_index = 0
        window._print_mode = "fit"
        window._progress = Mock()
        window._progress.wasCanceled.return_value = False
        window._painter = Mock(spec=QPainter)
        window._painter.isActive.return_value = True
        window._painter.end.return_value = True
        window._printer = Mock(spec=QPrinter)
        window._printer.newPage.return_value = True
        window._printer.paperRect.return_value = QRectF(0, 0, 595, 842)
        window._printer.logicalDpiX.return_value = 72
        window._printer.logicalDpiY.return_value = 72
        window._printer.printerState.return_value = QPrinter.PrinterState.Active
        return window._printer, window._painter, window._progress, window._prepared_job

    def assert_failed_not_success(self):
        self.assertIn("失敗", self.window.statusBar().currentMessage())
        self.assertNotIn("工作已送往", self.window.statusBar().currentMessage())
        self.critical.assert_called_once()
        self.assertFalse(self.window._busy)
        self.assertIsNone(self.window._printer)
        self.assertIsNone(self.window._prepared_job)

    def test_default_session_requires_fresh_driver_confirmation(self):
        self.settings.setValue("no_color_adjust", True)
        self.window._restore_settings()
        self.assertFalse(self.window.no_color_adjust_check.isChecked())
        self.assertFalse(self.window.print_btn.isEnabled())

    def test_preflight_requires_output_profile_and_confirmation(self):
        self.add_document()
        path = self.profile()
        self.window.profile_combo.addItem("Fixture", str(path))
        self.window.profile_combo.setCurrentIndex(self.window.profile_combo.count() - 1)
        self.window.no_color_adjust_check.setChecked(True)
        self.window._update_preflight()
        self.assertTrue(self.window.print_btn.isEnabled())
        self.window._set_busy(True)
        self.assertFalse(self.window.print_btn.isEnabled())
        self.window._set_busy(False)
        self.assertTrue(self.window.print_btn.isEnabled())

    def test_monitor_profile_cannot_pass_preflight(self):
        self.add_document()
        path = self.root / "monitor.icc"
        path.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        self.window.profile_combo.addItem("Monitor", str(path))
        self.window.profile_combo.setCurrentIndex(self.window.profile_combo.count() - 1)
        self.window.no_color_adjust_check.setChecked(True)
        self.window._update_preflight()
        self.assertFalse(self.window.print_btn.isEnabled())
        self.assertIn("prtr", self.window.preflight_label.text())

    def test_stale_preview_result_and_error_do_not_replace_current_preview(self):
        self.add_document()
        window = self.window
        window._preview_token = 22
        window.preview_info_label.setText("current preview")
        result = PreviewResult(QImage(20, 10, QImage.Format.Format_RGB888), 20, 10, 2, 1, "dpi", "source")
        with patch.object(window.preview_widget, "set_preview") as set_preview, patch.object(window.preview_widget, "clear_preview") as clear_preview:
            window._preview_ready(21, result)
            window._preview_error(21, "old error")
        set_preview.assert_not_called()
        clear_preview.assert_not_called()
        self.assertEqual(window.preview_info_label.text(), "current preview")

    def test_clear_files_cancels_pending_preview_and_rejects_late_result(self):
        self.add_document()
        window = self.window
        fake_task = Mock()
        window._tasks[5] = fake_task
        window._preview_token = 5
        window.clear_files()
        fake_task.cancel.set.assert_called_once()
        self.assertEqual(window.documents, [])
        self.assertEqual(window.file_list.count(), 0)
        self.assertIsNone(window._preview_token)
        with patch.object(window.preview_widget, "set_preview") as set_preview:
            window._preview_ready(5, object())
        set_preview.assert_not_called()
        window._tasks.clear()

    def test_remove_multiple_selected_files_keeps_refs_and_selection_valid(self):
        for index in range(3):
            self.add_document(f"file-{index}.png", index + 1)
        window = self.window
        window.preview_page_index = 5
        window.file_list.item(0).setSelected(True)
        window.file_list.item(2).setSelected(True)
        window.remove_selected()
        self.assertEqual([doc.original_path.name for doc in window.documents], ["file-1.png"])
        self.assertEqual(window.total_pages(), 2)
        self.assertEqual(window.preview_page_index, 1)
        self.assertEqual(window.page_refs(), [PageRef(0, 0), PageRef(0, 1)])
        self.assertEqual(window.page_jump.value(), 2)
        self.assertEqual(window.preview_page_label.text(), "/ 共 2 頁")

    def test_busy_guards_document_changes(self):
        doc = self.add_document()
        window = self.window
        window._set_busy(True)
        window.file_list.item(0).setSelected(True)
        window.clear_files()
        window.remove_selected()
        window.add_files([str(self.root / "missing.png")])
        self.assertEqual(window.documents, [doc])

    def test_cancelled_prepared_result_is_cleaned_before_painter_starts(self):
        window = self.window
        window._operation_token = 10
        window._set_busy(True)
        window._progress = Mock()
        window._progress.wasCanceled.return_value = True
        window._printer = Mock(spec=QPrinter)
        printer = window._printer
        job = self.prepared_job()
        with patch("iccprint.app.QPainter") as painter:
            window._print_prepared(10, job)
        painter.assert_not_called()
        self.assertFalse(job.directory.exists())
        printer.abort.assert_called_once()
        self.assertIn("取消", window.statusBar().currentMessage())
        self.critical.assert_not_called()
        self.assertFalse(window._busy)

    def test_stale_prepared_result_only_cleans_its_own_job(self):
        window = self.window
        printer, painter, progress, current_job = self.begin_fake_spool()
        stale_job = self.prepared_job()
        window._print_prepared(10, stale_job)
        self.assertFalse(stale_job.directory.exists())
        self.assertTrue(current_job.directory.exists())
        self.assertIs(window._printer, printer)
        self.assertIs(window._prepared_job, current_job)
        self.assertEqual(window._operation_token, 11)
        printer.abort.assert_not_called()

    def test_painter_begin_failure_cleans_and_reports_failure(self):
        window = self.window
        window._operation_token = 11
        window._set_busy(True)
        window._progress = Mock()
        window._progress.wasCanceled.return_value = False
        window._printer = Mock(spec=QPrinter)
        painter = Mock(spec=QPainter)
        painter.begin.return_value = False
        painter.isActive.return_value = False
        job = self.prepared_job()
        with patch("iccprint.app.QPainter", return_value=painter):
            window._print_prepared(11, job)
        self.assertFalse(job.directory.exists())
        self.assert_failed_not_success()

    def test_next_page_failure_never_reports_success(self):
        printer, painter, progress, job = self.begin_fake_spool(2)
        self.window._spool_index = 1
        printer.newPage.return_value = False
        self.window._spool_next_page()
        self.assertFalse(job.directory.exists())
        printer.abort.assert_called_once()
        self.assert_failed_not_success()

    def test_missing_prepared_page_never_reports_success(self):
        printer, painter, progress, job = self.begin_fake_spool()
        job.pages[0].path.unlink()
        self.window._spool_next_page()
        painter.drawImage.assert_not_called()
        self.assert_failed_not_success()

    def test_draw_failure_never_reports_success(self):
        printer, painter, progress, job = self.begin_fake_spool()
        painter.drawImage.side_effect = RuntimeError("draw failed")
        self.window._spool_next_page()
        self.assert_failed_not_success()

    def test_printer_error_after_draw_never_reports_success(self):
        printer, painter, progress, job = self.begin_fake_spool()
        printer.printerState.return_value = QPrinter.PrinterState.Error
        self.window._spool_next_page()
        self.assert_failed_not_success()

    def test_painter_end_failure_never_reports_success(self):
        printer, painter, progress, job = self.begin_fake_spool()
        self.window._spool_index = len(job.pages)
        painter.end.return_value = False
        self.window._spool_next_page()
        self.assert_failed_not_success()

    def test_printer_error_at_finalization_never_reports_success(self):
        printer, painter, progress, job = self.begin_fake_spool()
        self.window._spool_index = len(job.pages)
        printer.printerState.return_value = QPrinter.PrinterState.Error
        self.window._spool_next_page()
        self.assert_failed_not_success()

    def test_cancellation_during_modal_progress_update_stays_cancelled(self):
        printer, painter, progress, job = self.begin_fake_spool()
        progress.setValue.side_effect = lambda value: self.window._cancel_operation()
        with patch("iccprint.app.QTimer.singleShot"):
            self.window._spool_next_page()
        self.assertIn("取消", self.window.statusBar().currentMessage())
        self.assertNotIn("失敗", self.window.statusBar().currentMessage())
        self.critical.assert_not_called()
        self.assertFalse(job.directory.exists())
        self.assertFalse(self.window._busy)

    def test_cancel_spooling_aborts_printer_and_cleans_output(self):
        printer, painter, progress, job = self.begin_fake_spool()
        self.window._cancel_operation()
        printer.abort.assert_called_once()
        self.assertFalse(job.directory.exists())
        self.assertIsNone(self.window._painter)
        self.assertIsNone(self.window._printer)
        self.assertIn("取消", self.window.statusBar().currentMessage())
        self.critical.assert_not_called()

    def test_close_waits_for_worker_before_cleaning_temp(self):
        started, release = Event(), Event()
        self.addCleanup(release.set)
        window = self.window
        def worker(cancel, progress):
            started.set()
            release.wait(5)
            return None
        window._submit_task(worker, (), lambda *args: None)
        self.assertTrue(started.wait(2))
        root = Path(window.temp_dir_obj.name)
        event = QCloseEvent()
        with patch("iccprint.app.QTimer.singleShot") as retry_close:
            window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(root.exists())
        self.assertTrue(all(task.cancel.is_set() for task in window._tasks.values()))
        retry_close.assert_called_once()
        release.set()
        self.wait_until(lambda: not window._tasks)
        event = QCloseEvent()
        window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertFalse(root.exists())

    def test_preset_roundtrip_restores_layout_and_clears_confirmation(self):
        window = self.window
        window.dpi_spin.setValue(450)
        window.fallback_dpi_spin.setValue(180)
        window.orientation_combo.setCurrentIndex(1)
        window.scale_combo.setCurrentIndex(2)
        window.no_color_adjust_check.setChecked(True)
        with patch("iccprint.app.QInputDialog.getText", return_value=("Photo", True)):
            window.save_preset()
        window.dpi_spin.setValue(150)
        window.fallback_dpi_spin.setValue(300)
        window.orientation_combo.setCurrentIndex(0)
        window.scale_combo.setCurrentIndex(0)
        with patch("iccprint.app.QInputDialog.getItem", return_value=("Photo", True)):
            window.load_preset()
        self.assertEqual(window.dpi_spin.value(), 450)
        self.assertEqual(window.fallback_dpi_spin.value(), 180)
        self.assertEqual(window.orientation_combo.currentData(), "landscape")
        self.assertEqual(window.scale_combo.currentData(), "actual")
        self.assertFalse(window.no_color_adjust_check.isChecked())

    def test_preset_uses_saved_profile_instead_of_current_selection(self):
        window = self.window
        first, second = self.profile("first.icc"), self.profile("second.icc")
        for path in (first, second):
            window.profile_combo.addItem(path.name, str(path))
        window.profile_combo.setCurrentIndex(1)
        with patch("iccprint.app.QInputDialog.getText", return_value=("First", True)):
            window.save_preset()
        window.profile_combo.setCurrentIndex(2)
        with patch("iccprint.app.QInputDialog.getItem", return_value=("First", True)):
            window.load_preset()
        self.assertEqual(window.current_profile_path(), str(first))

    def test_malformed_presets_do_not_crash(self):
        for invalid in ("not JSON", "[]", "null"):
            with self.subTest(invalid=invalid):
                self.settings.setValue("presets", invalid)
                self.window.load_preset()
        self.assertEqual(self.information.call_count, 3)

    def test_reorder_documents_updates_print_refs_and_preview_page(self):
        first = self.add_document("first.png", 2)
        second = self.add_document("second.png", 3)
        third = self.add_document("third.png", 1)
        window = self.window
        window.file_list.setCurrentRow(1)
        window.move_document(1)
        self.assertEqual(window.documents, [first, third, second])
        self.assertEqual([window.file_list.item(i).text() for i in range(3)], ["first.png", "third.png", "second.png"])
        self.assertEqual(window.preview_page_index, 3)
        self.assertEqual(window.file_list.currentRow(), 2)
        self.assertEqual(window.page_refs(), [PageRef(0, 0), PageRef(0, 1), PageRef(1, 0), PageRef(2, 0), PageRef(2, 1), PageRef(2, 2)])
        window.move_document(1)  # Out-of-range movement leaves order unchanged.
        self.assertEqual(window.documents, [first, third, second])
        window._set_busy(True)
        window.move_document(-1)
        self.assertEqual(window.documents, [first, third, second])

    def test_rejected_paper_size_has_actionable_error(self):
        printer = Mock(spec=QPrinter)
        printer.setPageSize.return_value = False
        with self.assertRaisesRegex(ValueError, "紙張尺寸"):
            self.window.configure_printer_page(printer)
        printer.setPageOrientation.assert_not_called()

    def test_import_is_asynchronous_and_runs_on_serial_pool(self):
        window = self.window
        path = self.root / "async.png"
        with Image.new("RGB", (30, 20)) as image:
            image.save(path)
        window.add_files([str(path), str(path), str(self.root / "missing.png")])
        self.assertTrue(window._busy)
        self.assertEqual(window.pool.maxThreadCount(), 1)
        self.wait_until(lambda: not window._busy)
        self.assertEqual(len(window.documents), 1)
        self.assertEqual(window.file_list.count(), 1)
        self.assertEqual(window.documents[0].original_path, path)
        self.assertIsNone(window._operation_token)
        self.assertIsNone(window._progress)
        self.warning.assert_called_once()

    def test_cancelled_import_result_cleans_office_output_without_adding_it(self):
        window = self.window
        window._operation_token = 11
        window._set_busy(True)
        window._progress = Mock()
        window._progress.wasCanceled.return_value = True
        directory = Path(tempfile.mkdtemp(prefix="office_", dir=window.temp_dir_obj.name))
        output = directory / "converted.pdf"
        output.write_bytes(b"fixture")
        doc = LoadedDocument(self.root / "source.docx", output, "office_pdf", 1, True)
        window._files_imported(11, ImportResult([doc], []))
        self.assertEqual(window.documents, [])
        self.assertFalse(directory.exists())
        window._task_finished(11)
        self.assertFalse(window._busy)
        self.assertIsNone(window._operation_token)
        self.assertIsNone(window._progress)

    def test_prepare_cancellation_finished_clears_printer_and_busy_state(self):
        window = self.window
        window._operation_token = 11
        window._set_busy(True)
        window._progress = Mock()
        window._printer = Mock(spec=QPrinter)
        printer = window._printer
        window._task_finished(11)
        self.assertIsNone(window._printer)
        self.assertIsNone(window._operation_token)
        self.assertIsNone(window._progress)
        self.assertFalse(window._busy)
        printer.abort.assert_called_once()
        self.assertIn("取消", window.statusBar().currentMessage())

    def test_manual_copy_order_reuses_prepared_pages_without_rerendering(self):
        window = self.window
        for collate, expected in ((True, [0, 1, 0, 1, 0, 1]), (False, [0, 0, 0, 1, 1, 1])):
            with self.subTest(collate=collate):
                window._operation_token = 11
                window._set_busy(True)
                window._progress = Mock()
                window._progress.wasCanceled.return_value = False
                window._printer = Mock(spec=QPrinter)
                window._manual_copies = 3
                window._collate_copies = collate
                job = self.prepared_job(2)
                original = list(job.pages)
                painter = Mock(spec=QPainter)
                painter.begin.return_value = True
                with patch("iccprint.app.QPainter", return_value=painter), patch("iccprint.app.QTimer.singleShot"):
                    window._print_prepared(11, job)
                self.assertEqual(job.pages, [original[index] for index in expected])
                self.assertEqual(len(list(job.directory.glob("*.png"))), 2)
                window._progress.setRange.assert_called_once_with(0, 6)
                window._finish_print("cancelled")

    def test_native_dialog_range_reverse_order_and_unsupported_copy_fallback(self):
        window = self.window
        self.add_document(pages=4)
        profile = self.profile()
        window.profile_combo.addItem("Fixture", str(profile))
        window.profile_combo.setCurrentIndex(1)
        window.no_color_adjust_check.setChecked(True)
        printer = Mock(spec=QPrinter)
        printer.pageOrder.return_value = QPrinter.PageOrder.LastPageFirst
        printer.supportsMultipleCopies.return_value = False
        printer.copyCount.return_value = 3
        printer.collateCopies.return_value = True
        printer_factory = Mock(return_value=printer)
        printer_factory.PrinterMode = QPrinter.PrinterMode
        printer_factory.PageOrder = QPrinter.PageOrder
        dialog = Mock()
        dialog.exec.return_value = QDialog.DialogCode.Accepted
        dialog.printRange.return_value = QAbstractPrintDialog.PrintRange.PageRange
        dialog.fromPage.return_value = 2
        dialog.toPage.return_value = 3
        with patch("iccprint.app.QPrinter", printer_factory), patch("iccprint.app.QPrintDialog", return_value=dialog), patch.object(window, "configure_printer_page"), patch.object(window, "_submit_task", return_value=17) as submit:
            window.print_documents()
        args = submit.call_args.args[1]
        self.assertEqual(args[1], (PageRef(0, 2), PageRef(0, 1)))
        self.assertEqual(window._manual_copies, 3)
        self.assertTrue(window._collate_copies)
        printer.setCopyCount.assert_called_once_with(1)
        self.assertEqual(window._operation_token, 17)
        self.assertTrue(window._busy)
        window._finish_print("cancelled")

    def test_printer_aborted_at_finalization_is_cancellation_not_success(self):
        printer, painter, progress, job = self.begin_fake_spool()
        self.window._spool_index = len(job.pages)
        printer.printerState.return_value = QPrinter.PrinterState.Aborted
        self.window._spool_next_page()
        self.assertIn("取消", self.window.statusBar().currentMessage())
        self.assertNotIn("工作已送往", self.window.statusBar().currentMessage())
        self.critical.assert_not_called()

    def test_profile_test_rejects_monitor_profile(self):
        path = self.root / "monitor.icc"
        path.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        self.window.profile_combo.addItem("Monitor", str(path))
        self.window.profile_combo.setCurrentIndex(1)
        self.window.test_profile()
        self.critical.assert_called_once()
        self.information.assert_not_called()

    def test_malformed_preset_entry_does_not_crash_or_apply(self):
        window = self.window
        for entry in (None, "bad", [], {"dpi": "broken"}):
            with self.subTest(entry=entry):
                self.settings.setValue("presets", json.dumps({"Broken": entry}))
                with patch("iccprint.app.QInputDialog.getItem", return_value=("Broken", True)):
                    window.load_preset()
                self.assertEqual(window.dpi_spin.value(), 300)

    def test_page_jump_tracks_document_and_bounds(self):
        self.add_document("first.png", 2)
        self.add_document("second.png", 3)
        window = self.window
        window._update_preview_nav()
        window.page_jump.setValue(4)
        self.assertEqual(window.preview_page_index, 3)
        self.assertEqual(window.file_list.currentRow(), 1)
        window.page_jump.setValue(100)
        self.assertEqual(window.preview_page_index, 4)
        self.assertFalse(window.next_btn.isEnabled())
        window.clear_files()
        self.assertEqual(window.page_jump.value(), 0)
        self.assertFalse(window.page_jump.isEnabled())

    def run_pdf_workflow(self, filename):
        """Only the native printer picker is replaced; the worker and spooler run."""
        window = self.window
        profile = self.profile()
        window.profile_combo.addItem("Fixture", str(profile))
        window.profile_combo.setCurrentIndex(1)
        window.no_color_adjust_check.setChecked(True)
        output = self.root / filename
        class PdfOnlyPrinter(QPrinter):
            def __init__(self, mode):
                super().__init__(mode)
                self.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                self.setOutputFileName(str(output))
                self.setResolution(150)
        dialog = Mock()
        dialog.exec.return_value = QDialog.DialogCode.Accepted
        dialog.printRange.return_value = QAbstractPrintDialog.PrintRange.AllPages
        with patch("iccprint.app.QPrinter", PdfOnlyPrinter), patch("iccprint.app.QPrintDialog", return_value=dialog):
            window.print_documents()
            self.assertTrue(window._busy)
            self.wait_until(lambda: not window._busy and not window._tasks)
        return output

    def test_complete_async_print_workflow_targets_pdf_only(self):
        import pypdfium2 as pdfium
        self.add_document()
        output = self.run_pdf_workflow("complete.pdf")
        self.assertTrue(output.is_file())
        self.assertIn("工作已送往", self.window.statusBar().currentMessage())
        self.assertIsNone(self.window._printer)
        self.assertEqual(list(Path(self.window.temp_dir_obj.name).glob("print_*")), [])
        self.critical.assert_not_called()
        pdf = pdfium.PdfDocument(str(output))
        try:
            self.assertEqual(len(pdf), 1)
        finally:
            pdf.close()

    def test_late_corrupt_page_never_starts_a_pdf_print_job(self):
        self.add_document("good.png")
        bad = self.add_document("bad.png")
        bad.prepared_path.write_bytes(b"corrupt image data")
        output = self.run_pdf_workflow("must-not-start.pdf")
        self.assertFalse(output.exists())
        self.assert_failed_not_success()
        self.assertEqual(list(Path(self.window.temp_dir_obj.name).glob("print_*")), [])

    def test_real_preparation_and_qprinter_pdf_two_pages(self):
        """Exercises ICC conversion, disk staging, Qt painting, and PDF page output."""
        import pypdfium2 as pdfium
        window = self.window
        docs = []
        for index, color in enumerate(("red", "blue")):
            path = self.root / f"source-{index}.png"
            with Image.new("RGB", (120, 60), color) as image:
                image.save(path, dpi=(300, 300))
            docs.append(load_document(path, window.temp_dir_obj.name))
        options = ColorOptions(str(self.profile()), ImageCms.Intent.RELATIVE_COLORIMETRIC,
                               True, 300, 150)
        job = prepare_job(Event(), Mock(), tuple(docs), (PageRef(0, 0), PageRef(1, 0)),
                          options, window.temp_dir_obj.name)
        pdf_path = self.root / "result.pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(pdf_path))
        printer.setResolution(150)
        printer.setFullPage(True)
        window.configure_printer_page(printer)
        window._printer = printer
        window._print_mode = "fit"
        window._operation_token = 42
        window._set_busy(True)
        window._progress = QProgressDialog("Test", "Cancel", 0, 2, window)
        window._progress.setAutoClose(False)
        window._progress.setAutoReset(False)
        window._print_prepared(42, job)
        self.wait_until(lambda: not window._busy)
        self.assertIn("工作已送往", window.statusBar().currentMessage())
        self.assertFalse(job.directory.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)
        self.critical.assert_not_called()
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            self.assertEqual(len(pdf), 2)
            for index, dominant_channel in ((0, 0), (1, 2)):
                page = pdf[index]
                try:
                    width, height = page.get_size()
                    self.assertAlmostEqual(width / 72 * 25.4, 210, delta=0.5)
                    self.assertAlmostEqual(height / 72 * 25.4, 297, delta=0.5)
                    bitmap = page.render(scale=0.3)
                    try:
                        image = bitmap.to_pil()
                        try:
                            center = image.getpixel((image.width // 2, image.height // 2))
                            self.assertGreater(center[dominant_channel], 240)
                            self.assertLess(center[(dominant_channel + 1) % 3], 20)
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        finally:
            pdf.close()


if __name__ == "__main__":
    unittest.main()
