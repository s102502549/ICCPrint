from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image, ImageCms
from PySide6.QtCore import QSettings, QSizeF, QTimer, Qt
from PySide6.QtGui import QAction, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .color import INTENTS, convert_to_printer_rgb, read_profile_info, softproof_to_srgb
from .documents import SUPPORTED_EXTENSIONS, LoadedDocument, RenderedPage, load_document, render_page
from .preview import PrintPreviewWidget
from .printing import PAPER_SIZES_MM, PageRef, pil_to_qimage, target_rect_for_image


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ICCPrint {__version__} — ICC 色彩管理列印")
        self.resize(1280, 850)
        self.setAcceptDrops(True)
        self.settings = QSettings("ICCPrint", "ICCPrint")
        self._migrate_legacy_settings()
        self.temp_dir_obj = tempfile.TemporaryDirectory(prefix="iccprint_")
        self.documents: list[LoadedDocument] = []
        self.preview_page_index = 0
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(220)
        self.preview_timer.timeout.connect(self.update_preview)
        self._build_ui()
        self._restore_settings()
        self._refresh_installed_profiles()
        self._schedule_preview()

    def _migrate_legacy_settings(self):
        """Copy settings from pre-GitHub builds without keeping the old vendor id."""
        if self.settings.allKeys():
            return
        legacy = QSettings("OpenAI-UserTool", "ICCPrint")
        for key in legacy.allKeys():
            self.settings.setValue(key, legacy.value(key))

    def closeEvent(self, event):
        self._save_settings()
        try:
            self.temp_dir_obj.cleanup()
        finally:
            super().closeEvent(event)

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setSpacing(10)

        title = QLabel("不用 Photoshop：由 ICCPrint 套用印表機 ICC，再交給 Windows 印表機驅動輸出")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        outer.addWidget(title)

        warning = QLabel(
            "重要：如果印表機驅動有自己的色彩校正，請設為「無色彩校正 / No Color Adjustment」，"
            "並使用建立 ICC 描述檔時完全相同的紙張種類、品質與其他驅動設定。"
            "Epson L15160 已依此工作流程測試。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("padding: 9px; background: #fff3cd; border: 1px solid #e5c66a;")
        outer.addWidget(warning)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        # ----- left: controls -----
        left_container = QWidget()
        left = QVBoxLayout(left_container)
        left.setContentsMargins(0, 0, 8, 0)
        left.setSpacing(9)

        files_box = QGroupBox("1. 文件 / 圖片")
        files_layout = QVBoxLayout(files_box)
        file_buttons = QHBoxLayout()
        add_btn = QPushButton("加入檔案…")
        add_btn.clicked.connect(self.add_files_dialog)
        remove_btn = QPushButton("移除選取")
        remove_btn.clicked.connect(self.remove_selected)
        clear_btn = QPushButton("全部清除")
        clear_btn.clicked.connect(self.clear_files)
        file_buttons.addWidget(add_btn)
        file_buttons.addWidget(remove_btn)
        file_buttons.addWidget(clear_btn)
        file_buttons.addStretch(1)
        files_layout.addLayout(file_buttons)
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.currentRowChanged.connect(self._file_row_changed)
        self.file_list.setMinimumHeight(140)
        files_layout.addWidget(self.file_list)
        info = QLabel(
            "支援：PDF、JPG/JPEG、PNG、TIFF（含多頁）、BMP、WebP；Word/Excel/PowerPoint 可透過 LibreOffice 自動轉 PDF。也可直接拖曳檔案進來。"
        )
        info.setWordWrap(True)
        files_layout.addWidget(info)
        left.addWidget(files_box)

        icc_box = QGroupBox("2. 印表機 ICC / ICM 描述檔")
        icc_layout = QGridLayout(icc_box)
        self.profile_combo = QComboBox()
        self.profile_combo.currentIndexChanged.connect(self.profile_changed)
        self.browse_profile_btn = QPushButton("瀏覽 ICC…")
        self.browse_profile_btn.clicked.connect(self.browse_profile)
        self.refresh_profiles_btn = QPushButton("重新掃描")
        self.refresh_profiles_btn.clicked.connect(self._refresh_installed_profiles)
        icc_layout.addWidget(QLabel("印表機描述檔："), 0, 0)
        icc_layout.addWidget(self.profile_combo, 0, 1)
        icc_layout.addWidget(self.browse_profile_btn, 0, 2)
        icc_layout.addWidget(self.refresh_profiles_btn, 0, 3)
        self.profile_info_label = QLabel("尚未選擇 ICC")
        self.profile_info_label.setWordWrap(True)
        icc_layout.addWidget(self.profile_info_label, 1, 0, 1, 4)
        left.addWidget(icc_box)

        color_box = QGroupBox("3. 色彩、尺寸與版面")
        color_layout = QGridLayout(color_box)
        self.intent_combo = QComboBox()
        for label in INTENTS:
            self.intent_combo.addItem(label)
        self.intent_combo.setCurrentText("飽和度 (Saturation)")
        self.intent_combo.currentIndexChanged.connect(self._schedule_preview)

        self.bpc_check = QCheckBox("黑點補償 (Black Point Compensation)")
        self.bpc_check.setToolTip("通常較常搭配相對比色；也可以和其他 Intent 比較實際輸出。")
        self.bpc_check.toggled.connect(self._schedule_preview)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(150, 600)
        self.dpi_spin.setSingleStep(150)
        self.dpi_spin.setValue(300)
        self.dpi_spin.setSuffix(" dpi")
        self.dpi_spin.valueChanged.connect(self._schedule_preview)

        self.scale_combo = QComboBox()
        self.scale_combo.addItem("完整縮放至紙面 (Fit)", "fit")
        self.scale_combo.addItem("填滿紙面、必要時裁切 (Fill)", "fill")
        self.scale_combo.addItem("原始實體尺寸 100% (Actual)", "actual")
        self.scale_combo.currentIndexChanged.connect(self._schedule_preview)

        self.fallback_dpi_spin = QSpinBox()
        self.fallback_dpi_spin.setRange(36, 2400)
        self.fallback_dpi_spin.setValue(300)
        self.fallback_dpi_spin.setSuffix(" dpi")
        self.fallback_dpi_spin.setToolTip("只有圖片沒有內嵌 DPI、而且選 Actual 時才會使用。")
        self.fallback_dpi_spin.valueChanged.connect(self._schedule_preview)

        self.paper_combo = QComboBox()
        for label in PAPER_SIZES_MM:
            self.paper_combo.addItem(label, label)
        self.paper_combo.setCurrentText("A4 (210 × 297 mm)")
        self.paper_combo.currentIndexChanged.connect(self._paper_changed)

        self.orientation_combo = QComboBox()
        self.orientation_combo.addItem("直向 (Portrait)", "portrait")
        self.orientation_combo.addItem("橫向 (Landscape)", "landscape")
        self.orientation_combo.currentIndexChanged.connect(self._schedule_preview)

        self.custom_w_spin = QDoubleSpinBox()
        self.custom_w_spin.setRange(50.0, 500.0)
        self.custom_w_spin.setDecimals(1)
        self.custom_w_spin.setValue(210.0)
        self.custom_w_spin.setSuffix(" mm")
        self.custom_w_spin.valueChanged.connect(self._schedule_preview)
        self.custom_h_spin = QDoubleSpinBox()
        self.custom_h_spin.setRange(50.0, 700.0)
        self.custom_h_spin.setDecimals(1)
        self.custom_h_spin.setValue(297.0)
        self.custom_h_spin.setSuffix(" mm")
        self.custom_h_spin.valueChanged.connect(self._schedule_preview)

        color_layout.addWidget(QLabel("Rendering Intent："), 0, 0)
        color_layout.addWidget(self.intent_combo, 0, 1, 1, 2)
        color_layout.addWidget(self.bpc_check, 0, 3, 1, 2)
        color_layout.addWidget(QLabel("PDF / Office 點陣化："), 1, 0)
        color_layout.addWidget(self.dpi_spin, 1, 1)
        color_layout.addWidget(QLabel("版面："), 1, 2)
        color_layout.addWidget(self.scale_combo, 1, 3, 1, 2)
        color_layout.addWidget(QLabel("紙張："), 2, 0)
        color_layout.addWidget(self.paper_combo, 2, 1, 1, 2)
        color_layout.addWidget(QLabel("方向："), 2, 3)
        color_layout.addWidget(self.orientation_combo, 2, 4)
        self.custom_w_label = QLabel("自訂寬：")
        self.custom_h_label = QLabel("高：")
        color_layout.addWidget(self.custom_w_label, 3, 0)
        color_layout.addWidget(self.custom_w_spin, 3, 1)
        color_layout.addWidget(self.custom_h_label, 3, 2)
        color_layout.addWidget(self.custom_h_spin, 3, 3)
        color_layout.addWidget(QLabel("圖片無 DPI、Actual 時："), 4, 0, 1, 2)
        color_layout.addWidget(self.fallback_dpi_spin, 4, 2)
        left.addWidget(color_box)

        print_box = QGroupBox("4. 列印")
        print_layout = QVBoxLayout(print_box)
        self.no_color_adjust_check = QCheckBox(
            "我會在印表機驅動中關閉額外色彩校正（Epson：色彩校正 → 自訂 → 進階 → 無色彩校正）"
        )
        print_layout.addWidget(self.no_color_adjust_check)
        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("檢查 ICC")
        self.test_btn.clicked.connect(self.test_profile)
        self.print_btn = QPushButton("列印…")
        self.print_btn.setDefault(True)
        self.print_btn.clicked.connect(self.print_documents)
        self.print_btn.setStyleSheet("font-weight: 700; padding: 7px 20px;")
        btn_row.addWidget(self.test_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.print_btn)
        print_layout.addLayout(btn_row)
        left.addWidget(print_box)
        left.addStretch(1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setWidget(left_container)
        splitter.addWidget(left_scroll)

        # ----- right: live preview -----
        preview_box = QGroupBox("列印預覽 / ICC 軟打樣")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_widget = PrintPreviewWidget()
        preview_layout.addWidget(self.preview_widget, 1)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("◀ 上一頁")
        self.prev_btn.clicked.connect(self.preview_previous_page)
        self.preview_page_label = QLabel("0 / 0")
        self.preview_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_btn = QPushButton("下一頁 ▶")
        self.next_btn.clicked.connect(self.preview_next_page)
        nav.addWidget(self.prev_btn)
        nav.addStretch(1)
        nav.addWidget(self.preview_page_label)
        nav.addStretch(1)
        nav.addWidget(self.next_btn)
        preview_layout.addLayout(nav)

        self.preview_info_label = QLabel(
            "預覽會依 ICC、Rendering Intent、Fit/Fill/Actual、紙張與方向即時更新。"
        )
        self.preview_info_label.setWordWrap(True)
        self.preview_info_label.setStyleSheet("padding: 6px; background: #f2f2f2;")
        preview_layout.addWidget(self.preview_info_label)
        preview_note = QLabel(
            "色彩預覽為 sRGB 軟打樣近似值；實際成品仍受螢幕校正、紙張白點、環境光、墨水與印表機驅動設定影響。預覽以整張紙為基準，實際不可列印邊界由印表機驅動決定。"
        )
        preview_note.setWordWrap(True)
        preview_note.setStyleSheet("color: #666;")
        preview_layout.addWidget(preview_note)
        splitter.addWidget(preview_box)
        splitter.setSizes([650, 600])

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("就緒")

        help_action = QAction("使用說明", self)
        help_action.triggered.connect(self.show_help)
        about_action = QAction("關於", self)
        about_action.triggered.connect(self.show_about)
        menu = self.menuBar().addMenu("說明")
        menu.addAction(help_action)
        menu.addAction(about_action)
        self._paper_changed()
        self._update_preview_nav()

    # ---------- settings ----------
    def _restore_settings(self):
        self.intent_combo.setCurrentText(self.settings.value("intent", "飽和度 (Saturation)"))
        self.bpc_check.setChecked(self.settings.value("bpc", False, type=bool))
        self.dpi_spin.setValue(self.settings.value("dpi", 300, type=int))
        self.fallback_dpi_spin.setValue(self.settings.value("fallback_dpi", 300, type=int))

        scale = self.settings.value("scale", "fit")
        idx = self.scale_combo.findData(scale)
        if idx >= 0:
            self.scale_combo.setCurrentIndex(idx)

        paper = self.settings.value("paper", "A4 (210 × 297 mm)")
        idx = self.paper_combo.findData(paper)
        if idx >= 0:
            self.paper_combo.setCurrentIndex(idx)
        orientation = self.settings.value("orientation", "portrait")
        idx = self.orientation_combo.findData(orientation)
        if idx >= 0:
            self.orientation_combo.setCurrentIndex(idx)
        self.custom_w_spin.setValue(self.settings.value("custom_w_mm", 210.0, type=float))
        self.custom_h_spin.setValue(self.settings.value("custom_h_mm", 297.0, type=float))
        self.no_color_adjust_check.setChecked(self.settings.value("no_color_adjust_ack", False, type=bool))
        self._paper_changed()

    def _save_settings(self):
        self.settings.setValue("intent", self.intent_combo.currentText())
        self.settings.setValue("bpc", self.bpc_check.isChecked())
        self.settings.setValue("dpi", self.dpi_spin.value())
        self.settings.setValue("fallback_dpi", self.fallback_dpi_spin.value())
        self.settings.setValue("scale", self.scale_combo.currentData())
        self.settings.setValue("paper", self.paper_combo.currentData())
        self.settings.setValue("orientation", self.orientation_combo.currentData())
        self.settings.setValue("custom_w_mm", self.custom_w_spin.value())
        self.settings.setValue("custom_h_mm", self.custom_h_spin.value())
        self.settings.setValue("no_color_adjust_ack", self.no_color_adjust_check.isChecked())
        profile = self.current_profile_path()
        if profile:
            self.settings.setValue("profile", profile)

    # ---------- paper/layout ----------
    def _paper_changed(self):
        custom = self.paper_combo.currentData() == "自訂尺寸"
        for w in (self.custom_w_label, self.custom_h_label, self.custom_w_spin, self.custom_h_spin):
            w.setEnabled(custom)
        self._schedule_preview()

    def base_paper_mm(self) -> tuple[float, float]:
        key = self.paper_combo.currentData() or "A4 (210 × 297 mm)"
        if key == "自訂尺寸":
            return float(self.custom_w_spin.value()), float(self.custom_h_spin.value())
        return PAPER_SIZES_MM.get(str(key), (210.0, 297.0))

    def effective_paper_mm(self) -> tuple[float, float]:
        w, h = self.base_paper_mm()
        if self.orientation_combo.currentData() == "landscape":
            return h, w
        return w, h

    def configure_printer_page(self, printer: QPrinter):
        w, h = self.base_paper_mm()
        page_size = QPageSize(
            QSizeF(w, h),
            QPageSize.Unit.Millimeter,
            self.paper_combo.currentText(),
        )
        printer.setPageSize(page_size)
        orientation = (
            QPageLayout.Orientation.Landscape
            if self.orientation_combo.currentData() == "landscape"
            else QPageLayout.Orientation.Portrait
        )
        printer.setPageOrientation(orientation)

    def _actual_inches(self, rendered: RenderedPage, pixel_w: int, pixel_h: int) -> tuple[float, float, str]:
        if rendered.physical_width_in and rendered.physical_height_in:
            if rendered.native_dpi_x and rendered.native_dpi_y:
                note = f"內嵌/文件 DPI 約 {rendered.native_dpi_x:.1f} × {rendered.native_dpi_y:.1f}"
            else:
                note = "文件實體尺寸"
            return rendered.physical_width_in, rendered.physical_height_in, note
        dpi = float(self.fallback_dpi_spin.value())
        return pixel_w / dpi, pixel_h / dpi, f"無內嵌 DPI，使用 {dpi:.0f} dpi"

    # ---------- profiles ----------
    @staticmethod
    def windows_color_dir() -> Path:
        windir = os.environ.get("WINDIR", r"C:\Windows")
        return Path(windir) / "System32" / "spool" / "drivers" / "color"

    def _refresh_installed_profiles(self):
        saved = self.settings.value("profile", "")
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("— 選擇已安裝 ICC / ICM —", None)
        paths = []
        color_dir = self.windows_color_dir()
        if color_dir.exists():
            paths = sorted(
                [*color_dir.glob("*.icc"), *color_dir.glob("*.icm")],
                key=lambda p: p.name.lower(),
            )
        for path in paths:
            try:
                info = read_profile_info(path)
                label = f"{info.description}  [{path.name}]"
            except Exception:
                label = path.name
            self.profile_combo.addItem(label, str(path))

        target_idx = self.profile_combo.findData(str(saved)) if saved else -1
        if target_idx < 0 and saved and Path(str(saved)).exists():
            try:
                info = read_profile_info(str(saved))
                self.profile_combo.addItem(f"{info.description}  [{Path(str(saved)).name}]", str(saved))
                target_idx = self.profile_combo.count() - 1
            except Exception:
                pass
        if target_idx >= 0:
            self.profile_combo.setCurrentIndex(target_idx)
        self.profile_combo.blockSignals(False)
        self.profile_changed()

    def current_profile_path(self) -> str | None:
        data = self.profile_combo.currentData()
        return str(data) if data else None

    def browse_profile(self):
        start = str(self.windows_color_dir()) if self.windows_color_dir().exists() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "選擇印表機 ICC 描述檔", start, "ICC 描述檔 (*.icc *.icm)")
        if not path:
            return
        try:
            info = read_profile_info(path)
        except Exception as exc:
            QMessageBox.critical(self, "ICC 錯誤", f"無法開啟此 ICC 描述檔：\n{exc}")
            return
        idx = self.profile_combo.findData(path)
        if idx < 0:
            self.profile_combo.addItem(f"{info.description}  [{Path(path).name}]", path)
            idx = self.profile_combo.count() - 1
        self.profile_combo.setCurrentIndex(idx)
        self.settings.setValue("profile", path)

    def profile_changed(self):
        path = self.current_profile_path()
        if not path:
            self.profile_info_label.setText("尚未選擇 ICC。請選擇為目前印表機、墨水、紙張與驅動設定建立的 RGB 印表機描述檔。")
            self._schedule_preview()
            return
        try:
            info = read_profile_info(path)
            supported = "、".join(info.supported_intents) or "未偵測到可用的輸出 intent"
            self.profile_info_label.setText(
                f"{info.description}｜色彩空間：{info.color_space or '未知'}｜裝置類別：{info.device_class or '未知'}\n"
                f"支援的輸出 Intent：{supported}\n{info.path}"
            )
        except Exception as exc:
            self.profile_info_label.setText(f"描述檔讀取失敗：{exc}")
        self._schedule_preview()

    def test_profile(self):
        path = self.current_profile_path()
        if not path:
            QMessageBox.warning(self, "尚未選 ICC", "請先選擇 RGB 印表機 ICC / ICM 描述檔。")
            return
        try:
            info = read_profile_info(path)
            intent = INTENTS[self.intent_combo.currentText()]
            profile = ImageCms.getOpenProfile(path)
            supported = ImageCms.isIntentSupported(profile, intent, ImageCms.Direction.OUTPUT) == 1
            if info.color_space.strip().upper() != "RGB":
                raise ValueError(f"ICCPrint 目前只輸出 RGB 印表機描述檔；此檔是 {info.color_space}。")
            QMessageBox.information(
                self,
                "ICC 檢查",
                f"描述檔：{info.description}\n色彩空間：{info.color_space}\n"
                f"目前 Intent：{self.intent_combo.currentText()}\n支援：{'是' if supported else '否'}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "ICC 檢查失敗", str(exc))

    # ---------- documents ----------
    def add_files_dialog(self):
        filters = (
            "支援檔案 (*.pdf *.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp *.doc *.docx *.odt *.rtf *.xls *.xlsx *.ods *.ppt *.pptx *.odp);;"
            "所有檔案 (*.*)"
        )
        paths, _ = QFileDialog.getOpenFileNames(self, "加入文件或圖片", str(Path.home()), filters)
        self.add_files(paths)

    def add_files(self, paths):
        if not paths:
            return
        existing = {str(d.original_path.resolve()).lower() for d in self.documents}
        errors = []
        was_empty = not self.documents
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for raw in paths:
                path = Path(raw)
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    errors.append(f"{path.name}: 不支援的格式")
                    continue
                key = str(path.resolve()).lower()
                if key in existing:
                    continue
                try:
                    doc = load_document(path, self.temp_dir_obj.name)
                    self.documents.append(doc)
                    item = QListWidgetItem(f"{doc.original_path.name}    |    {doc.display_type}    |    {doc.page_count} 頁")
                    item.setToolTip(str(doc.original_path))
                    self.file_list.addItem(item)
                    existing.add(key)
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
        finally:
            QApplication.restoreOverrideCursor()
        if errors:
            QMessageBox.warning(self, "部分檔案未加入", "\n\n".join(errors))
        if was_empty and self.documents:
            self.preview_page_index = 0
            self.file_list.setCurrentRow(0)
        self.statusBar().showMessage(f"已加入 {len(self.documents)} 個檔案，共 {self.total_pages()} 頁")
        self._update_preview_nav()
        self._schedule_preview()

    def remove_selected(self):
        rows = sorted({self.file_list.row(item) for item in self.file_list.selectedItems()}, reverse=True)
        for row in rows:
            self.file_list.takeItem(row)
            del self.documents[row]
        self.preview_page_index = min(self.preview_page_index, max(0, self.total_pages() - 1))
        if self.documents:
            self._sync_file_selection_to_preview()
        self.statusBar().showMessage(f"剩下 {len(self.documents)} 個檔案，共 {self.total_pages()} 頁")
        self._update_preview_nav()
        self._schedule_preview()

    def clear_files(self):
        self.documents.clear()
        self.file_list.clear()
        self.preview_page_index = 0
        self.statusBar().showMessage("已清除")
        self._update_preview_nav()
        self.preview_widget.clear_preview()
        self.preview_info_label.setText("加入文件後會顯示列印預覽。")

    def total_pages(self) -> int:
        return sum(d.page_count for d in self.documents)

    def page_refs(self) -> list[PageRef]:
        refs = []
        for di, doc in enumerate(self.documents):
            for pi in range(doc.page_count):
                refs.append(PageRef(di, pi))
        return refs

    # ---------- preview ----------
    def _schedule_preview(self, *args):
        self.preview_timer.start()

    def _file_row_changed(self, row: int):
        if row < 0 or row >= len(self.documents):
            return
        self.preview_page_index = sum(d.page_count for d in self.documents[:row])
        self._update_preview_nav()
        self._schedule_preview()

    def _sync_file_selection_to_preview(self):
        refs = self.page_refs()
        if not refs:
            return
        self.preview_page_index = max(0, min(self.preview_page_index, len(refs) - 1))
        row = refs[self.preview_page_index].document_index
        self.file_list.blockSignals(True)
        self.file_list.setCurrentRow(row)
        self.file_list.blockSignals(False)

    def _update_preview_nav(self):
        total = self.total_pages()
        current = self.preview_page_index + 1 if total else 0
        self.preview_page_label.setText(f"{current} / {total}")
        self.prev_btn.setEnabled(total > 0 and self.preview_page_index > 0)
        self.next_btn.setEnabled(total > 0 and self.preview_page_index < total - 1)

    def preview_previous_page(self):
        if self.preview_page_index > 0:
            self.preview_page_index -= 1
            self._sync_file_selection_to_preview()
            self._update_preview_nav()
            self._schedule_preview()

    def preview_next_page(self):
        if self.preview_page_index < self.total_pages() - 1:
            self.preview_page_index += 1
            self._sync_file_selection_to_preview()
            self._update_preview_nav()
            self._schedule_preview()

    def update_preview(self):
        refs = self.page_refs()
        if not refs:
            self.preview_widget.clear_preview()
            self.preview_info_label.setText("加入文件後會顯示列印預覽。")
            self._update_preview_nav()
            return
        self.preview_page_index = max(0, min(self.preview_page_index, len(refs) - 1))
        ref = refs[self.preview_page_index]
        doc = self.documents[ref.document_index]
        paper_w_mm, paper_h_mm = self.effective_paper_mm()
        mode = str(self.scale_combo.currentData())
        rendered = None
        preview_source = None
        proofed = None
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            # A lower raster DPI is sufficient for live preview. Physical page size is
            # tracked separately, so this does not change Actual-size placement.
            preview_dpi = min(150, self.dpi_spin.value())
            rendered = render_page(doc, ref.page_index, preview_dpi)
            orig_w, orig_h = rendered.image.width, rendered.image.height
            actual_w_in, actual_h_in, actual_note = self._actual_inches(rendered, orig_w, orig_h)
            actual_w_mm, actual_h_mm = actual_w_in * 25.4, actual_h_in * 25.4

            preview_source = rendered.image.copy()
            preview_source.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            profile_path = self.current_profile_path()
            color_note = "未套 ICC（請選擇印表機描述檔）"
            if profile_path:
                intent = INTENTS[self.intent_combo.currentText()]
                proofed = softproof_to_srgb(
                    preview_source,
                    profile_path,
                    intent,
                    self.bpc_check.isChecked(),
                    rendered.embedded_icc,
                )
                display_image = proofed
                color_note = f"軟打樣：{self.intent_combo.currentText()}" + (" + BPC" if self.bpc_check.isChecked() else "")
            else:
                display_image = preview_source.convert("RGB")

            qimage = pil_to_qimage(display_image)
            self.preview_widget.set_preview(
                qimage,
                paper_w_mm,
                paper_h_mm,
                mode,
                actual_w_mm,
                actual_h_mm,
                f"第 {self.preview_page_index + 1} / {len(refs)} 頁",
            )

            layout_names = {"fit": "Fit", "fill": "Fill", "actual": "Actual 100%"}
            source_size = f"{actual_w_mm / 10.0:.2f} × {actual_h_mm / 10.0:.2f} cm"
            self.preview_info_label.setText(
                f"{doc.original_path.name}｜紙張 {paper_w_mm:.1f} × {paper_h_mm:.1f} mm｜{layout_names.get(mode, mode)}\n"
                f"來源實體尺寸：{source_size}（{actual_note}）｜{rendered.source_label}\n{color_note}"
            )
        except Exception as exc:
            self.preview_widget.set_preview(
                None,
                paper_w_mm,
                paper_h_mm,
                mode,
                message="預覽產生失敗",
            )
            self.preview_info_label.setText(f"預覽產生失敗：{exc}")
        finally:
            QApplication.restoreOverrideCursor()
            if proofed is not None:
                proofed.close()
            if preview_source is not None:
                preview_source.close()
            if rendered is not None:
                rendered.image.close()
            self._update_preview_nav()

    # ---------- printing ----------
    def print_documents(self):
        if not self.documents:
            QMessageBox.warning(self, "沒有文件", "請先加入要列印的 PDF、圖片或 Office 文件。")
            return
        profile_path = self.current_profile_path()
        if not profile_path:
            QMessageBox.warning(self, "尚未選 ICC", "請先選擇 RGB 印表機 ICC / ICM 描述檔。")
            return
        if not self.no_color_adjust_check.isChecked():
            QMessageBox.warning(
                self,
                "避免雙重色彩管理",
                "請先勾選確認：你會在印表機驅動中關閉額外色彩校正（Epson 通常稱為『無色彩校正 / No Color Adjustment』）。\n\n"
                "否則 ICCPrint 已經轉換一次，驅動又再調一次，通常會造成雙重色彩管理。",
            )
            return

        try:
            info = read_profile_info(profile_path)
            if info.color_space.strip().upper() != "RGB":
                raise ValueError(f"此版本只支援 RGB 印表機 ICC；選到的是 {info.color_space}。")
            intent = INTENTS[self.intent_combo.currentText()]
            profile = ImageCms.getOpenProfile(profile_path)
            if ImageCms.isIntentSupported(profile, intent, ImageCms.Direction.OUTPUT) != 1:
                raise ValueError("這個 ICC 不支援目前選擇的 Rendering Intent。")
        except Exception as exc:
            QMessageBox.critical(self, "ICC 設定錯誤", str(exc))
            return

        refs = self.page_refs()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName("ICCPrint color-managed job")
        try:
            self.configure_printer_page(printer)
        except Exception as exc:
            QMessageBox.warning(self, "紙張設定", f"無法預先設定紙張尺寸，仍會開啟列印視窗：\n{exc}")

        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("選擇印表機 — 請確認驅動已關閉額外色彩校正")
        dialog.setMinMax(1, len(refs))
        dialog.setFromTo(1, len(refs))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # Paper size and orientation in ICCPrint are authoritative, so preview and
        # output use the same layout. Epson Properties should be used for media type,
        # quality and No Color Adjustment.
        try:
            self.configure_printer_page(printer)
        except Exception:
            pass

        if dialog.printRange() == QAbstractPrintDialog.PrintRange.PageRange:
            start = max(1, dialog.fromPage())
            end = min(len(refs), dialog.toPage())
            refs = refs[start - 1:end]
        if not refs:
            return

        progress = QProgressDialog("正在套用 ICC 並送往印表機…", "取消", 0, len(refs), self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.critical(self, "列印失敗", "無法啟動印表機工作。")
            return

        try:
            page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            page_w = float(page_rect.width())
            page_h = float(page_rect.height())
            dpi = self.dpi_spin.value()
            bpc = self.bpc_check.isChecked()
            scale_mode = str(self.scale_combo.currentData())
            printer_dpi_x = float(printer.logicalDpiX())
            printer_dpi_y = float(printer.logicalDpiY())

            for i, ref in enumerate(refs):
                progress.setValue(i)
                QApplication.processEvents()
                if progress.wasCanceled():
                    printer.abort()
                    break

                if i > 0 and not printer.newPage():
                    raise RuntimeError("印表機無法建立下一頁。")

                doc = self.documents[ref.document_index]
                rendered = render_page(doc, ref.page_index, dpi)
                orig_w, orig_h = rendered.image.width, rendered.image.height
                actual_w_in, actual_h_in, _ = self._actual_inches(rendered, orig_w, orig_h)
                converted = convert_to_printer_rgb(
                    rendered.image,
                    profile_path,
                    intent,
                    bpc,
                    rendered.embedded_icc,
                )
                qimage = pil_to_qimage(converted)
                actual_w_px = actual_w_in * printer_dpi_x
                actual_h_px = actual_h_in * printer_dpi_y
                target, source = target_rect_for_image(
                    page_w,
                    page_h,
                    qimage.width(),
                    qimage.height(),
                    scale_mode,
                    actual_w_px,
                    actual_h_px,
                )
                painter.fillRect(0, 0, int(page_w), int(page_h), Qt.GlobalColor.white)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawImage(target, qimage, source)

                rendered.image.close()
                converted.close()
                del qimage

            progress.setValue(len(refs))
        except Exception as exc:
            printer.abort()
            QMessageBox.critical(self, "列印失敗", f"處理或列印時發生錯誤：\n{exc}")
        finally:
            if painter.isActive():
                painter.end()
            progress.close()

        if not progress.wasCanceled():
            self.statusBar().showMessage("列印工作已送出。請以實際紙張輸出判斷最終色彩。", 8000)

    # ---------- drag/drop/help ----------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
            if any(p.suffix.lower() in SUPPORTED_EXTENSIONS for p in paths):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.add_files(paths)
        event.acceptProposedAction()

    def show_help(self):
        QMessageBox.information(
            self,
            "ICCPrint 使用重點",
            "1. 加入 PDF / 圖片；Office 文件需 LibreOffice，或先另存 PDF。\n"
            "2. 選擇為目前印表機 + 墨水 + 紙張 + 驅動設定製作的 RGB ICC。\n"
            "3. 選 Rendering Intent，例如『飽和度 (Saturation)』，右側會做 ICC 軟打樣。\n"
            "4. 版面可選 Fit / Fill / Actual 100%。Actual：PDF 使用文件實體尺寸；圖片使用內嵌 DPI，沒有 DPI 時使用你設定的預設 DPI。\n"
            "5. 在 ICCPrint 選紙張尺寸與直/橫向。\n"
            "6. 按列印，在 Windows 原生列印視窗選擇你的印表機。\n"
            "7. 進『印表機內容』：更多選項 → 色彩校正 → 自訂 → 進階 → 無色彩校正。\n"
            "8. 驅動的紙張種類、品質等必須與當初建立 ICC 時一致。\n\n"
            "注意：右側預覽是 sRGB 軟打樣近似值，不等於實體紙張的絕對顏色。",
        )

    def show_about(self):
        QMessageBox.information(
            self,
            "關於 ICCPrint",
            f"ICCPrint {__version__}\n\n"
            "用途：讓沒有 Photoshop 的 Windows 使用者，以 LittleCMS/Pillow 套用 RGB 印表機 ICC，"
            "選擇 Perceptual / Relative / Saturation / Absolute Rendering Intent，並提供 ICC 軟打樣與 Fit / Fill / Actual 列印版面預覽。\n\n"
            "本程式不會自動修改印表機廠商的私有驅動設定，也不會上傳文件。",
        )
