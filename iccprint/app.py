from __future__ import annotations

import os
import tempfile
import json
from pathlib import Path

from PySide6.QtCore import QSettings, QSizeF, QTimer, Qt, QThreadPool
from PySide6.QtGui import QAction, QPageLayout, QPageSize, QPainter, QImage, QKeySequence
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
    QInputDialog,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .color import INTENTS, read_profile_info, validate_printer_profile
from .documents import SUPPORTED_EXTENSIONS, LoadedDocument
from .preview import PrintPreviewWidget
from .presets import DEFAULTS, normalize_preset, validate_value
from .printing import PAPER_SIZES_MM, PageRef, layout_rects, target_rect_for_image
from .jobs import ColorOptions, Task, make_preview, prepare_job, import_documents


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ICCPrint {__version__} | ICC 色彩管理列印")
        self.resize(1280, 850)
        self.setAcceptDrops(True)
        self.settings = QSettings("ICCPrint", "ICCPrint")
        self._migrate_legacy_settings()
        self.temp_dir_obj = tempfile.TemporaryDirectory(prefix="iccprint_")
        self.documents: list[LoadedDocument] = []
        self.preview_page_index = 0
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._tasks = {}
        self._next_token = 0
        self._preview_token = None
        self._operation_token = None
        self._busy = False
        self._closing = False
        self._printer = None
        self._painter = None
        self._prepared_job = None
        self._spool_index = 0
        self._progress = None
        self._preview_ok = False
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
        self.preview_timer.stop()
        if self._busy or self.pool.activeThreadCount():
            self._closing = True
            for task in self._tasks.values():
                task.cancel.set()
            if self._printer is not None:
                self._finish_print("cancelled")
            self.statusBar().showMessage("正在取消作業並清理暫存檔…")
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        self._save_settings()
        self.temp_dir_obj.cleanup()
        super().closeEvent(event)

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setSpacing(10)

        self._content = central
        title = QLabel("ICCPrint  /  色彩管理工作室")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        outer.addWidget(title)
        subtitle = QLabel("選擇文件 → 設定色彩與版面 → 檢查並列印  ·  文件全程留在這台電腦")
        subtitle.setObjectName("subtitle")
        outer.addWidget(subtitle)

        warning = QLabel(
            "重要：如果印表機驅動有自己的色彩校正，請設為「無色彩校正 / No Color Adjustment」，"
            "並使用建立 ICC 描述檔時完全相同的紙張種類、品質與其他驅動設定。"
            "螢幕軟打樣不代表實體色彩保證。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("padding: 10px; color: #654c13; background: #fff8e5; border: 1px solid #edd395; border-radius: 6px;")
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
        self.add_btn = add_btn
        file_buttons.addWidget(add_btn)
        file_buttons.addWidget(remove_btn)
        file_buttons.addWidget(clear_btn)
        for label, offset, description in (("↑", -1, "將目前文件上移"), ("↓", 1, "將目前文件下移")):
            move = QPushButton(label)
            move.setFixedWidth(36)
            move.setToolTip(description)
            move.setAccessibleName(description)
            move.clicked.connect(lambda checked=False, delta=offset: self.move_document(delta))
            file_buttons.addWidget(move)
        file_buttons.addStretch(1)
        files_layout.addLayout(file_buttons)
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.currentRowChanged.connect(self._file_row_changed)
        self.file_list.setMinimumHeight(105)
        self.file_list.setMaximumHeight(160)
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
        self.profile_info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        icc_layout.addWidget(self.profile_info_label, 1, 0, 1, 4)
        left.addWidget(icc_box)

        color_box = QGroupBox("3. 色彩、尺寸與版面")
        color_layout = QGridLayout(color_box)
        self.intent_combo = QComboBox()
        for label in INTENTS:
            self.intent_combo.addItem(label)
        self.intent_combo.setCurrentText("相對比色 (Relative Colorimetric)")
        self.intent_combo.currentIndexChanged.connect(self._schedule_preview)

        self.bpc_check = QCheckBox("黑點補償 (BPC)")
        self.bpc_check.setToolTip("通常較常搭配相對比色；也可以和其他 Intent 比較實際輸出。")
        self.bpc_check.setChecked(True)
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
        print_layout = QHBoxLayout(print_box)
        print_status = QVBoxLayout()
        print_layout.addLayout(print_status, 1)
        self.no_color_adjust_check = QCheckBox(
            "已確認驅動使用「無色彩校正」，且媒材與品質符合 ICC"
        )
        self.no_color_adjust_check.toggled.connect(self._update_preflight)
        print_status.addWidget(self.no_color_adjust_check)
        self.preflight_label = QLabel()
        self.preflight_label.setWordWrap(True)
        self.preflight_label.setObjectName("preflight")
        print_status.addWidget(self.preflight_label)
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
        outer.addWidget(print_box)
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
        proof_row = QHBoxLayout()
        self.proof_check = QCheckBox("ICC 軟打樣")
        self.proof_check.setChecked(True)
        self.proof_check.setToolTip("取消勾選可查看正確轉換到 sRGB 的原稿，方便與軟打樣比較。")
        self.proof_check.toggled.connect(self._schedule_preview)
        proof_row.addWidget(self.proof_check)
        proof_row.addStretch(1)
        proof_row.addWidget(QLabel("原稿 / 紙上效果"))
        preview_layout.addLayout(proof_row)
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
        self.page_jump = QSpinBox()
        self.page_jump.setRange(0, 0)
        self.page_jump.setPrefix("第 ")
        self.page_jump.setSuffix(" 頁")
        self.page_jump.setAccessibleName("跳至預覽頁面")
        self.page_jump.valueChanged.connect(self._jump_to_page)
        nav.addWidget(self.page_jump)
        nav.addWidget(self.preview_page_label)
        nav.addStretch(1)
        nav.addWidget(self.next_btn)
        preview_layout.addLayout(nav)

        self.preview_info_label = QLabel(
            "預覽會依 ICC、Rendering Intent、Fit/Fill/Actual、紙張與方向即時更新。"
        )
        self.preview_info_label.setWordWrap(True)
        self.preview_info_label.setMinimumHeight(90)
        self.preview_info_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
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
        self.setStyleSheet("""
            QMainWindow { background: #f3f5f8; }
            QWidget { color: #172b42; }
            QMenuBar, QMenu, QStatusBar { background: #f3f5f8; }
            QGroupBox { background: white; border: 1px solid #d9e0e9; border-radius: 8px;
                        margin-top: 14px; padding: 14px 10px 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; }
            QPushButton { padding: 7px 12px; border: 1px solid #c8d2df;
                          border-radius: 5px; background: #f8fafc; }
            QPushButton:hover { background: #eaf1fb; border-color: #7b9dc7; }
            QPushButton:disabled { color: #9299a5; background: #eef1f5; }
            QComboBox, QSpinBox, QDoubleSpinBox { padding: 5px; }
            QLabel#subtitle { color: #53667c; padding-bottom: 4px; }
            QLabel#preflight { padding: 8px; background: #f0f5fb; border-radius: 5px; }
        """)
        self.print_btn.setStyleSheet("QPushButton {font-weight: 700; padding: 9px 24px; background: #245c9f; color: white;} QPushButton:disabled {background: #c2cedd; color: #4a6079;}")
        file_menu = self.menuBar().addMenu("檔案")
        open_action = QAction("加入檔案…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.add_files_dialog)
        file_menu.addAction(open_action)
        print_action = QAction("列印…", self)
        print_action.setShortcut(QKeySequence.StandardKey.Print)
        print_action.triggered.connect(self.print_documents)
        file_menu.addAction(print_action)
        preset_menu = self.menuBar().addMenu("列印預設")
        save_preset = QAction("儲存目前設定…", self)
        save_preset.triggered.connect(self.save_preset)
        load_preset = QAction("套用已儲存設定…", self)
        load_preset.triggered.connect(self.load_preset)
        preset_menu.addActions([save_preset, load_preset])


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
    def _setting(self, key):
        try:
            return validate_value(key, self.settings.value(key, DEFAULTS[key]))
        except (TypeError, ValueError, OverflowError):
            return DEFAULTS[key]

    def _restore_settings(self):
        self.intent_combo.setCurrentText(self._setting("intent"))
        self.bpc_check.setChecked(self._setting("bpc"))
        self.dpi_spin.setValue(self._setting("dpi"))
        self.fallback_dpi_spin.setValue(self._setting("fallback_dpi"))

        scale = self._setting("scale")
        idx = self.scale_combo.findData(scale)
        if idx >= 0:
            self.scale_combo.setCurrentIndex(idx)

        paper = self._setting("paper")
        idx = self.paper_combo.findData(paper)
        if idx >= 0:
            self.paper_combo.setCurrentIndex(idx)
        orientation = self._setting("orientation")
        idx = self.orientation_combo.findData(orientation)
        if idx >= 0:
            self.orientation_combo.setCurrentIndex(idx)
        self.custom_w_spin.setValue(self._setting("custom_w_mm"))
        self.custom_h_spin.setValue(self._setting("custom_h_mm"))
        # Confirmation is deliberately per-session, never restored from a preset.
        self.no_color_adjust_check.setChecked(False)
        geometry = self.settings.value("window_geometry")
        if geometry:
            try:
                self.restoreGeometry(geometry)
            except (TypeError, ValueError):
                pass
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
        self.settings.setValue("window_geometry", self.saveGeometry())
        profile = self.current_profile_path()
        self.settings.setValue("profile", profile or "")

    def save_preset(self):
        if self._busy:
            return
        name, ok = QInputDialog.getText(self, "儲存列印預設", "名稱（例如：霧面 A4 相片）：")
        name = name.strip()
        if not ok or not name:
            return
        self._save_settings()
        keys = ("intent", "bpc", "dpi", "fallback_dpi", "scale", "paper", "orientation",
                "custom_w_mm", "custom_h_mm", "profile")
        try:
            presets = json.loads(str(self.settings.value("presets", "{}")))
            if not isinstance(presets, dict):
                presets = {}
        except (TypeError, ValueError):
            presets = {}
        if name in presets and QMessageBox.question(self, "取代預設", f"要取代「{name}」嗎？") != QMessageBox.StandardButton.Yes:
            return
        presets[name] = {key: self.settings.value(key) for key in keys}
        self.settings.setValue("presets", json.dumps(presets, ensure_ascii=False))
        self.statusBar().showMessage(f"已儲存預設：{name}", 5000)

    def load_preset(self):
        if self._busy:
            return
        try:
            presets = json.loads(str(self.settings.value("presets", "{}")))
            if not isinstance(presets, dict) or not presets:
                raise ValueError()
        except (TypeError, ValueError):
            QMessageBox.information(self, "列印預設", "尚無預設。先設定紙張、ICC 與色彩，再選擇儲存目前設定。")
            return
        name, ok = QInputDialog.getItem(self, "套用列印預設", "選擇預設：", sorted(presets), 0, False)
        if ok:
            allowed = {"intent", "bpc", "dpi", "fallback_dpi", "scale", "paper", "orientation",
                       "custom_w_mm", "custom_h_mm", "profile"}
            try:
                selected = normalize_preset(presets[name])
            except (TypeError, ValueError, OverflowError) as exc:
                QMessageBox.warning(self, "預設內容無效", str(exc) + "\n目前設定未變更，請重新儲存此預設。")
                return
            for key, value in selected.items():
                if key in allowed:
                    self.settings.setValue(key, value)
            self._restore_settings()
            self._refresh_installed_profiles(preferred=self.settings.value("profile", ""))
            self.statusBar().showMessage(f"已套用：{name}。請重新確認驅動紙張與色彩設定。", 8000)

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
            QPageSize.SizeMatchPolicy.ExactMatch,
        )
        if not printer.setPageSize(page_size):
            raise ValueError("印表機未接受選擇的紙張尺寸，請確認驅動支援此尺寸。")
        orientation = (
            QPageLayout.Orientation.Landscape
            if self.orientation_combo.currentData() == "landscape"
            else QPageLayout.Orientation.Portrait
        )
        printer.setPageOrientation(orientation)

    # ---------- profiles ----------
    @staticmethod
    def windows_color_dir() -> Path:
        windir = os.environ.get("WINDIR", r"C:\Windows")
        return Path(windir) / "System32" / "spool" / "drivers" / "color"

    def _refresh_installed_profiles(self, *args, preferred=None):
        saved = preferred if preferred is not None else (self.current_profile_path() or self._setting("profile"))
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
                f"{info.description} · {info.color_space or '未知'} / {info.device_class or '未知'}\n"
                f"支援 {len(info.supported_intents)} 種輸出 Intent · 詳細資料請將游標移至此處"
            )
            self.profile_info_label.setToolTip(f"支援的輸出 Intent：{supported}\n{info.path}")
        except Exception as exc:
            self.profile_info_label.setText(f"描述檔讀取失敗：{exc}")
        self._schedule_preview()

    def test_profile(self):
        path = self.current_profile_path()
        if not path:
            QMessageBox.warning(self, "尚未選 ICC", "請先選擇 RGB 印表機 ICC / ICM 描述檔。")
            return
        try:
            intent = INTENTS[self.intent_combo.currentText()]
            info = validate_printer_profile(path, intent)
            # validate_printer_profile already checks the selected intent.
            supported = self.intent_combo.currentText() in info.supported_intents
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
        if not paths or self._busy:
            return
        existing = frozenset(os.path.normcase(str(d.original_path.resolve())) for d in self.documents)
        self._set_busy(True)
        self._progress = QProgressDialog("正在開啟文件…", "取消", 0, len(paths), self)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.setWindowModality(Qt.WindowModality.NonModal)
        self._progress.setMinimumDuration(0)
        self._progress.canceled.connect(self._cancel_operation)
        self._progress.show()
        self._operation_token = self._submit_task(import_documents,
            (tuple(str(p) for p in paths), self.temp_dir_obj.name, existing),
            self._files_imported, self._import_error, self._print_progress)

    def _files_imported(self, token, result):
        if token != self._operation_token or self._closing or (self._progress and self._progress.wasCanceled()):
            import shutil
            for doc in result.documents:
                if doc.temporary:
                    shutil.rmtree(doc.prepared_path.parent, ignore_errors=True)
            return
        was_empty = not self.documents
        for doc in result.documents:
            self.documents.append(doc)
            item = QListWidgetItem(f"{doc.original_path.name}    |    {doc.display_type}    |    {doc.page_count} 頁")
            item.setToolTip(str(doc.original_path))
            self.file_list.addItem(item)
        if was_empty and self.documents:
            self.preview_page_index = 0
            self.file_list.setCurrentRow(0)
        self.statusBar().showMessage(f"已加入 {len(self.documents)} 個檔案，共 {self.total_pages()} 頁")
        self._update_preview_nav()
        if result.errors:
            QMessageBox.warning(self, "部分檔案未加入", "\n\n".join(result.errors))

    def _import_error(self, token, message):
        if token == self._operation_token and not self._closing:
            QMessageBox.warning(self, "開啟文件失敗", message)

    def move_document(self, offset):
        if self._busy:
            return
        row = self.file_list.currentRow()
        target = row + offset
        if not 0 <= row < len(self.documents) or not 0 <= target < len(self.documents):
            return
        self._invalidate_preview()
        self.file_list.blockSignals(True)
        document = self.documents.pop(row)
        self.documents.insert(target, document)
        item = self.file_list.takeItem(row)
        self.file_list.insertItem(target, item)
        self.file_list.setCurrentRow(target)
        self.file_list.blockSignals(False)
        self._file_row_changed(target)
        self.statusBar().showMessage("已更新文件列印順序", 4000)

    def remove_selected(self):
        if self._busy:
            return
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
        if self._busy:
            return
        self._invalidate_preview()
        self.documents.clear()
        self.file_list.clear()
        self.preview_page_index = 0
        self.statusBar().showMessage("已清除")
        self._update_preview_nav()
        self.preview_widget.clear_preview()
        self.preview_info_label.setText("加入文件後會顯示列印預覽。")
        self._update_preflight()

    def total_pages(self) -> int:
        return sum(d.page_count for d in self.documents)

    def page_refs(self) -> list[PageRef]:
        refs = []
        for di, doc in enumerate(self.documents):
            for pi in range(doc.page_count):
                refs.append(PageRef(di, pi))
        return refs

    # ---------- preview ----------
    def _invalidate_preview(self):
        self._preview_ok = False
        if self._preview_token in self._tasks:
            self._tasks[self._preview_token].cancel.set()
        self._preview_token = None

    def _schedule_preview(self, *args):
        self._invalidate_preview()
        if not self._busy and not self._closing:
            self.preview_timer.start()
        self._update_preflight()

    def _color_options(self):
        return ColorOptions(self.current_profile_path(), INTENTS[self.intent_combo.currentText()],
                            self.bpc_check.isChecked(), self.fallback_dpi_spin.value(),
                            self.dpi_spin.value(), self.proof_check.isChecked())

    def _submit_task(self, function, args, result, error=None, progress=None):
        self._next_token += 1
        token = self._next_token
        task = Task(token, function, *args)
        self._tasks[token] = task
        task.signals.result.connect(result)
        if error:
            task.signals.error.connect(error)
        if progress:
            task.signals.progress.connect(progress)
        task.signals.finished.connect(self._task_finished)
        self.pool.start(task)
        return token

    def _task_finished(self, token):
        self._tasks.pop(token, None)
        if token == self._operation_token and self._prepared_job is None:
            if self._printer is not None:
                self._finish_print("cancelled")
            else:
                self._operation_token = None
                cancelled = bool(self._progress and self._progress.wasCanceled())
                if self._progress:
                    self._progress.blockSignals(True)
                    self._progress.close()
                    self._progress = None
                self._set_busy(False)
                if cancelled:
                    self.statusBar().showMessage("已取消開啟文件。", 8000)
                self._schedule_preview()

    def _set_busy(self, busy):
        self._busy = busy
        self._content.setEnabled(not busy)
        self.menuBar().setEnabled(not busy)
        self.setAcceptDrops(not busy)
        if busy:
            self.preview_timer.stop()
            self._invalidate_preview()
        self._update_preflight()

    def _update_preflight(self):
        if not hasattr(self, "preflight_label"):
            return
        reasons = []
        if not self.documents:
            reasons.append("加入文件")
        try:
            path = self.current_profile_path()
            if not path:
                reasons.append("選擇 RGB 印表機 ICC")
            else:
                validate_printer_profile(path, INTENTS[self.intent_combo.currentText()])
        except Exception as exc:
            reasons.append(str(exc))
        if not self.no_color_adjust_check.isChecked():
            reasons.append("確認驅動已關閉額外色彩校正")
        if reasons:
            self.preflight_label.setText("待確認：" + " / ".join(reasons))
        else:
            self.preflight_label.setText(f"設定就緒 · {self.total_pages()} 頁 · 全部頁面通過檢查與轉換後才送出")
        self.print_btn.setEnabled(not reasons and not self._busy)


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
        self.preview_page_label.setText(f"/ 共 {total} 頁")
        self.page_jump.blockSignals(True)
        self.page_jump.setRange(1 if total else 0, total)
        self.page_jump.setValue(current)
        self.page_jump.setEnabled(bool(total))
        self.page_jump.blockSignals(False)
        self.prev_btn.setEnabled(total > 0 and self.preview_page_index > 0)
        self.next_btn.setEnabled(total > 0 and self.preview_page_index < total - 1)

    def _jump_to_page(self, page):
        if 1 <= page <= self.total_pages():
            self.preview_page_index = page - 1
            self._sync_file_selection_to_preview()
            self._update_preview_nav()
            self._schedule_preview()

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
        if self._busy or self._closing:
            return
        refs = self.page_refs()
        if not refs:
            self.preview_widget.clear_preview()
            self.preview_info_label.setText("加入文件後會顯示列印預覽。")
            self._update_preview_nav()
            return
        self.preview_page_index = max(0, min(self.preview_page_index, len(refs) - 1))
        ref = refs[self.preview_page_index]
        self._invalidate_preview()
        self.preview_info_label.setText("正在背景建立預覽…")
        self._preview_token = self._submit_task(make_preview,
            (self.documents[ref.document_index], ref.page_index, self._color_options()),
            self._preview_ready, self._preview_error)

    def _preview_ready(self, token, result):
        if token != self._preview_token or self._closing:
            return
        refs = self.page_refs()
        if not refs:
            return
        doc = self.documents[refs[self.preview_page_index].document_index]
        paper_w, paper_h = self.effective_paper_mm()
        mode = str(self.scale_combo.currentData())
        w_mm, h_mm = result.width_in * 25.4, result.height_in * 25.4
        self.preview_widget.set_preview(result.image, paper_w, paper_h, mode, w_mm, h_mm,
                                       f"第 {self.preview_page_index + 1} / {len(refs)} 頁")
        r = layout_rects(paper_w, paper_h, result.width_px, result.height_px, mode, w_mm, h_mm)
        effective_dpi = min(r.source_w / (r.target_w / 25.4), r.source_h / (r.target_h / 25.4))
        warnings = []
        if doc.kind == "image" and effective_dpi < 150:
            warnings.append(f"注意：有效解析度約 {effective_dpi:.0f} dpi，可能不夠清晰")
        if mode == "fill" and (r.source_w < result.width_px - 1 or r.source_h < result.height_px - 1):
            warnings.append("Fill 模式會裁切部分原稿")
        if mode == "actual" and (w_mm > paper_w or h_mm > paper_h):
            warnings.append("原始尺寸超出紙張，邊緣會被裁切")
        color = "ICC 軟打樣" if self.proof_check.isChecked() and self.current_profile_path() else "原稿（色彩管理 sRGB）"
        self.preview_info_label.setText(
            f"{doc.original_path.name} · {paper_w:.1f} × {paper_h:.1f} mm · {mode.title()}\n"
            f"來源 {w_mm:.1f} × {h_mm:.1f} mm（{result.size_note}）\n"
            f"{result.source_label} · {color}" + ("\n" + "；".join(warnings) if warnings else ""))
        self._preview_ok = True
        self._update_preview_nav()

    def _preview_error(self, token, message):
        if token != self._preview_token or self._closing:
            return
        self.preview_widget.clear_preview("無法建立預覽")
        self.preview_info_label.setText(f"預覽失敗：{message}")
        self._preview_ok = False

    # ---------- printing ----------
    def print_documents(self):
        if self._busy or self._closing or not self.documents:
            return
        if not self.no_color_adjust_check.isChecked():
            QMessageBox.warning(self, "確認色彩管理", "請先確認印表機驅動已關閉額外色彩校正。")
            return
        try:
            options = self._color_options()
            if not options.profile_path:
                raise ValueError("請選擇 RGB 印表機 ICC。")
            validate_printer_profile(options.profile_path, options.intent)
        except Exception as exc:
            QMessageBox.critical(self, "ICC 設定錯誤", str(exc))
            return
        refs = self.page_refs()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName("ICCPrint color-managed job")
        # Full-page coordinates keep the same physical origin/scale as preview.
        # Hardware nonprintable margins still clip output; no borderless claim.
        printer.setFullPage(True)
        try:
            self.configure_printer_page(printer)
        except ValueError:
            # The default device may differ from the one chosen in the dialog.
            pass
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("選擇印表機 · 確認媒材、品質與無色彩校正")
        dialog.setMinMax(1, len(refs))
        dialog.setFromTo(1, len(refs))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        # Freeze the app layout after the native dialog to match its preview.
        try:
            self.configure_printer_page(printer)
        except ValueError as exc:
            QMessageBox.warning(self, "紙張設定不相符", str(exc))
            return
        printer.setFullPage(True)
        if dialog.printRange() == QAbstractPrintDialog.PrintRange.PageRange:
            refs = refs[max(1, dialog.fromPage()) - 1:min(len(refs), dialog.toPage())]
        if printer.pageOrder() == QPrinter.PageOrder.LastPageFirst:
            refs.reverse()
        if not refs:
            return
        self._manual_copies = 1
        self._collate_copies = printer.collateCopies()
        if not printer.supportsMultipleCopies():
            self._manual_copies = max(1, printer.copyCount())
            printer.setCopyCount(1)
        self._printer = printer
        self._print_mode = str(self.scale_combo.currentData())
        self._set_busy(True)
        self._progress = QProgressDialog("正在檢查與準備所有頁面…", "取消", 0, len(refs), self)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.setWindowModality(Qt.WindowModality.NonModal)
        self._progress.setMinimumDuration(0)
        self._progress.canceled.connect(self._cancel_operation)
        self._progress.show()
        self._operation_token = self._submit_task(prepare_job,
            (tuple(self.documents), tuple(refs), options, self.temp_dir_obj.name),
            self._print_prepared, self._print_prepare_error, self._print_progress)

    def _cancel_operation(self):
        if self._operation_token in self._tasks:
            self._tasks[self._operation_token].cancel.set()
        if self._painter is not None:
            self._finish_print("cancelled")
        else:
            self.statusBar().showMessage("正在取消準備作業…")

    def _print_progress(self, token, current, message):
        if token == self._operation_token and self._progress:
            self._progress.setValue(current)
            self._progress.setLabelText(message)

    def _print_prepare_error(self, token, message):
        if token == self._operation_token:
            self._finish_print("failed", message)

    def _print_prepared(self, token, job):
        if token != self._operation_token:
            job.cleanup()
            return
        if self._closing or not self._progress or self._progress.wasCanceled():
            job.cleanup()
            self._finish_print("cancelled")
            return
        self._prepared_job = job
        copies = getattr(self, "_manual_copies", 1)
        if copies > 1:
            job.pages = (job.pages * copies if self._collate_copies else
                         [page for page in job.pages for _ in range(copies)])
        self._painter = QPainter()
        if not self._painter.begin(self._printer):
            self._finish_print("failed", "無法啟動印表機工作。")
            return
        self._spool_index = 0
        self._progress.setRange(0, len(job.pages))
        self._progress.setValue(0)
        self._progress.setLabelText("全部頁面已通過檢查，正在送往印表機…")
        QTimer.singleShot(0, self._spool_next_page)

    def _spool_next_page(self):
        if self._prepared_job is None or self._painter is None:
            return
        if self._closing or self._progress.wasCanceled():
            self._finish_print("cancelled")
            return
        try:
            if self._spool_index >= len(self._prepared_job.pages):
                if not self._painter.end():
                    raise RuntimeError("印表機未確認工作結束。請檢查列印佇列。")
                if self._printer.printerState() == QPrinter.PrinterState.Error:
                    raise RuntimeError("列印工作結束時印表機回報錯誤。")
                if self._printer.printerState() == QPrinter.PrinterState.Aborted:
                    self._finish_print("cancelled")
                    return
                self._finish_print("success")
                return
            if self._spool_index and not self._printer.newPage():
                raise RuntimeError("印表機無法建立下一頁。")
            page = self._prepared_job.pages[self._spool_index]
            image = QImage(str(page.path))
            if image.isNull():
                raise RuntimeError("已準備的頁面無法讀取，工作已中止。")
            rect = self._printer.paperRect(QPrinter.Unit.DevicePixel)
            target, source = target_rect_for_image(float(rect.width()), float(rect.height()),
                image.width(), image.height(), self._print_mode,
                page.width_in * self._printer.logicalDpiX(), page.height_in * self._printer.logicalDpiY())
            self._painter.save()
            self._painter.setClipRect(rect)
            self._painter.fillRect(rect, Qt.GlobalColor.white)
            self._painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            self._painter.drawImage(target, image, source)
            self._painter.restore()
            if self._printer.printerState() == QPrinter.PrinterState.Error:
                raise RuntimeError("印表機回報錯誤。請檢查 Windows 列印佇列。")
            self._spool_index += 1
            progress = self._progress
            total = len(self._prepared_job.pages)
            progress.setValue(self._spool_index)
            if self._progress is not progress or self._prepared_job is None:
                return
            progress.setLabelText(f"正在送出 {self._spool_index}/{total} 頁…")
            QTimer.singleShot(0, self._spool_next_page)
        except Exception as exc:
            self._finish_print("failed", str(exc))

    def _finish_print(self, outcome, message=""):
        printer, painter = self._printer, self._painter
        output_started = painter is not None
        self._printer = self._painter = None
        if outcome != "success" and printer is not None:
            printer.abort()
        if painter is not None and painter.isActive():
            painter.end()
        if self._prepared_job is not None:
            self._prepared_job.cleanup()
            self._prepared_job = None
        if self._progress is not None:
            self._progress.blockSignals(True)
            self._progress.close()
            self._progress = None
        self._operation_token = None
        self._set_busy(False)
        if outcome == "success":
            self.statusBar().showMessage("工作已送往列印系統；實體完成狀態請查看 Windows 列印佇列。", 15000)
        elif outcome == "cancelled":
            text = ("作業已取消。已送至印表機的頁面可能仍會列印，請檢查列印佇列。"
                    if output_started else "已取消準備作業，未送出任何頁面。")
            self.statusBar().showMessage(text, 15000)
        else:
            self.statusBar().showMessage("列印失敗，工作已中止。", 15000)
            if not self._closing:
                QMessageBox.critical(self, "列印失敗", message + "\n\n尚未送出的頁面已停止；請確認列印佇列後再重試。")

    # ---------- drag/drop/help ----------
    def dragEnterEvent(self, event):
        if self._busy:
            event.ignore()
            return
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
