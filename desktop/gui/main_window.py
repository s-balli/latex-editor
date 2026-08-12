"""Ana pencere — editor, PDF viewer, file tree, output panel layout."""

import os
import shutil
import tempfile

from core.version import VERSION
from core.log import get_logger, log_path as _log_path
from PyQt6.QtCore import QCoreApplication

_logger = get_logger("main_window")
_ = lambda s: QCoreApplication.translate("MainWindow", s)

import sys

from PyQt6.QtCore import Qt, QEvent, QSettings, QSize, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QTabWidget, QComboBox, QToolBar, QLabel, QMessageBox, QStatusBar,
    QWidget, QApplication, QProgressBar, QVBoxLayout,
)

from gui.editor import EditorWidget
from gui.pdf_viewer import PdfViewer
from gui.file_tree import FileTree
from gui.output_panel import OutputPanel
from gui.theme import ThemeManager
from gui.stylesheet import build_stylesheet
from core.compiler import LatexCompiler

from gui.mixins.file_watch import FileWatchMixin
from gui.mixins.file_ops import FileOpsMixin
from gui.mixins.tab_ops import TabOpsMixin
from gui.mixins.edit_ops import EditOpsMixin
from gui.mixins.compile_ops import CompileOpsMixin
from gui.mixins.image_ops import ImageOpsMixin
from gui.mixins.synctex_ops import SyncTexMixin


class UpdateCheckThread(QThread):
    """Arka planda GitHub Releases API kontrolü. GUI'yi bloklamaz."""
    update_found = pyqtSignal(dict)
    finished_no_update = pyqtSignal()
    finished_network_error = pyqtSignal()
    _force = False

    def run(self):
        try:
            from core.updater import check_for_update
            result = check_for_update(force=self._force)
            if result is None:
                self.finished_no_update.emit()
            elif result.get("error") == "network":
                self.finished_network_error.emit()
            else:
                self.update_found.emit(result)
        except Exception:
            self.finished_network_error.emit()


class MainWindow(
    FileWatchMixin,
    FileOpsMixin,
    TabOpsMixin,
    EditOpsMixin,
    CompileOpsMixin,
    ImageOpsMixin,
    SyncTexMixin,
    QMainWindow,
):
    def __init__(self, open_file: str = ""):
        super().__init__()
        self.setWindowTitle(f"LaTeX Editor v{VERSION}")
        self.resize(1400, 900)
        self.setMinimumSize(800, 500)
        self._set_window_icon()

        self._compiler = LatexCompiler(self)
        self._auto_compile = True
        self._current_pdf = ""
        self._last_errors = []          # son derlemenin hataları (line>0, çözümlü yol)
        self._err_index = -1            # F4/Shift+F4 imleci (_last_errors içinde)
        self._compile_target = ""       # derlenen ana dosya yolu (path resolve base)
        self._synctex_dir = tempfile.mkdtemp(prefix="latex_editor_")
        self._settings = QSettings("LatexEditor", "LatexEditor")
        self._theme_mgr = ThemeManager(self._settings, self)

        self._init_synctex_worker()
        self._file_watch_init()
        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()
        self._restore_state()
        self._apply_theme()

        # Komut satırından gelen dosyayı aç (Windows "Birlikte Aç" / Linux)
        if open_file and os.path.isfile(open_file):
            ext = os.path.splitext(open_file)[1].lower()
            if ext in ('.tex', '.cls', '.sty', '.bib'):
                self._open_file_in_editor(open_file)
                self._file_tree.set_root(os.path.dirname(open_file))

        # Ctrl+/ için application event filter (klavye düzeninden bağımsız)
        QApplication.instance().installEventFilter(self)

        # Sürükle-bırak ile dosya açma
        self.setAcceptDrops(True)

        # Açılışta arka planda güncelleme kontrolü
        self._update_thread = None
        self._update_check_silent = True
        self._start_update_check(silent=True)

    def _set_window_icon(self):
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.abspath(__file__))
            base = os.path.dirname(base)  # desktop/
        for path in [
            os.path.join(base, 'linux', 'latex-editor.png'),
            os.path.join(base, 'linux', 'latex-editor.svg'),
        ]:
            if os.path.isfile(path):
                self.setWindowIcon(QIcon(path))
                return

    def _setup_ui(self):
        # Ana dikey splitter: üst (editor alanı) / alt (çıktı paneli)
        self._main_splitter = QSplitter(Qt.Orientation.Vertical)

        # Üst: yatay splitter — [dosya ağacı | outline] | editor | PDF
        self._top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sol panel: dosya ağacı + outline dikey splitter
        self._left_splitter = QSplitter(Qt.Orientation.Vertical)

        self._file_tree = FileTree(theme=self._theme_mgr.theme)
        self._left_splitter.addWidget(self._file_tree)

        from gui.outline import OutlinePanel
        self._outline = OutlinePanel(theme=self._theme_mgr.theme)
        self._outline.goto_line_requested.connect(self._goto_outline_line)
        self._left_splitter.addWidget(self._outline)

        self._left_splitter.setSizes([500, 300])
        self._top_splitter.addWidget(self._left_splitter)

        # Editor alanı — find bar + sekmeler
        self._editor_container = QWidget()
        self._editor_layout = QVBoxLayout(self._editor_container)
        self._editor_layout.setContentsMargins(0, 0, 0, 0)
        self._editor_layout.setSpacing(0)

        self._find_bar = None  # Lazy init

        self._editor_tabs = QTabWidget()
        self._editor_tabs.setMovable(True)
        self._editor_tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._editor_tabs.tabBar().customContextMenuRequested.connect(self._tab_context_menu)
        self._editor_tabs.tabBar().installEventFilter(self)

        self._editor_layout.addWidget(self._editor_tabs)
        self._top_splitter.addWidget(self._editor_container)

        # PDF görüntüleyici
        self._pdf_viewer = PdfViewer(theme=self._theme_mgr.theme)
        self._top_splitter.addWidget(self._pdf_viewer)

        # Oranlar: sol panel %15, editor %35, PDF %50
        self._top_splitter.setSizes([150, 350, 500])

        self._main_splitter.addWidget(self._top_splitter)

        # Çıktı paneli
        self._output_panel = OutputPanel(theme=self._theme_mgr.theme)
        self._main_splitter.addWidget(self._output_panel)

        # Oran: üst %85, çıktı %15
        self._main_splitter.setSizes([765, 135])

        self.setCentralWidget(self._main_splitter)

    def _setup_menus(self):
        menubar = self.menuBar()

        # Dosya menüsü
        file_menu = menubar.addMenu(_("&Dosya"))
        self._add_action(file_menu, _("Yeni &Dosya"), self._new_file, "Ctrl+N")
        file_menu.addSeparator()
        self._add_action(file_menu, _("&Klasör Aç..."), self._open_folder, "Ctrl+O")
        self._add_action(file_menu, _("&Dosya Aç..."), self._open_file, "Ctrl+Shift+O")
        file_menu.addSeparator()
        self._add_action(file_menu, _("&Kaydet"), self._save_file)
        self._add_action(file_menu, _("Farklı &Kaydet..."), self._save_file_as, "Ctrl+Shift+S")
        file_menu.addSeparator()

        self._recent_menu = file_menu.addMenu(_("Son Açılanlar"))
        self._refresh_recent_menu()

        file_menu.addSeparator()

        export_menu = file_menu.addMenu(_("Dışa Akta&r"))
        from core.exporter import FORMATS, pandoc_available
        self._pandoc_available = pandoc_available()
        for fmt_name, ext in FORMATS.items():
            act = export_menu.addAction(f"{fmt_name} ({ext})")
            act.triggered.connect(lambda checked, f=fmt_name, e=ext: self._export_file(f, e))
            if not self._pandoc_available:
                act.setToolTip(_("pandoc gerekli: apt install pandoc"))
        self._add_action(file_menu, _("Çı&kış"), self.close, "Ctrl+Q")

        # Düzenle menüsü
        edit_menu = menubar.addMenu(_("Dü&zenle"))
        self._add_action(edit_menu, _("&Geri Al"), self._undo, "Ctrl+Z")
        self._add_action(edit_menu, _("&Yinele"), self._redo, "Ctrl+Y")
        edit_menu.addSeparator()
        self._add_action(edit_menu, _("&Bul..."), self._show_find, "Ctrl+F")
        self._add_action(edit_menu, _("Bul &Değiştir..."), self._show_replace, "Ctrl+H")
        edit_menu.addSeparator()
        self._add_action(edit_menu, _("Yorum &Toggle"), self._toggle_comment)
        self._add_action(edit_menu, _("Satıra &Git..."), self._goto_line_dialog, "Ctrl+G")
        edit_menu.addSeparator()
        self._add_action(edit_menu, _("&Sonraki Hata"), self._goto_next_error, "F4", app_shortcut=True)
        self._add_action(edit_menu, _("Ö&nceki Hata"), self._goto_prev_error, "Shift+F4", app_shortcut=True)

        # Derle menüsü
        build_menu = menubar.addMenu(_("&Derle"))
        self._add_action(build_menu, _("&Derle"), self._compile, "Ctrl+B", app_shortcut=True)
        self._add_action(build_menu, _("&Durdur"), self._stop_compile)

        # Görünüm menüsü
        view_menu = menubar.addMenu(_("&Görünüm"))
        self._add_action(view_menu, _("&Sunum Modu"), self._pdf_viewer.enter_presentation, "F5")
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu(_("&Tema"))
        self._theme_actions = {}
        for name in self._theme_mgr.available_themes():
            act = QAction(self._theme_mgr.theme_label(name), self, checkable=True)
            act.setData(name)
            act.triggered.connect(lambda checked, n=name: self._select_theme(n))
            theme_menu.addAction(act)
            self._theme_actions[name] = act

        # Yardım menüsü
        help_menu = menubar.addMenu(_("&Yardım"))
        self._add_action(help_menu, _("&Klavye Kısayolları"), self._show_shortcuts)
        self._add_action(help_menu, _("Ö&zellikler"), self._show_features)
        help_menu.addSeparator()
        self._add_action(help_menu, _("&Güncellemeleri Kontrol Et"), self._check_for_update_manual)
        help_menu.addSeparator()
        self._add_action(help_menu, _("&Log Klasörünü Aç"), self._open_log_dir)
        help_menu.addSeparator()
        self._add_action(help_menu, _("&Hakkında"), self._show_about)

    def _add_action(self, menu, text, callback, shortcut=None, app_shortcut=False):
        action = QAction(text, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            if app_shortcut:
                action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        menu.addAction(action)
        return action

    def _setup_toolbar(self):
        t = self._theme_mgr.theme

        toolbar = QToolBar(_("Araç Çubuğu"))
        toolbar.setObjectName("mainToolBar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        toolbar.addAction(_("📂 Klasör Aç"), self._open_folder)
        toolbar.addAction(_("📄 Dosya Aç"), self._open_file)
        toolbar.addSeparator()
        toolbar.addAction(_("💾 Kaydet"), self._save_file)
        toolbar.addAction(_("▶ Derle"), self._compile)
        toolbar.addSeparator()

        # Motor seçici
        self._engine_label = QLabel(_(" Derleyici: "))
        self._engine_label.setStyleSheet(f"color: {t['fg_label']}; font-weight: bold;")
        toolbar.addWidget(self._engine_label)
        self._engine_combo = QComboBox()
        self._engine_combo.addItems(["lualatex", "pdflatex"])
        self._engine_combo.setToolTip(_("Derleme motoru"))
        toolbar.addWidget(self._engine_combo)

        # Otomatik derleme durumu
        self._auto_label = QLabel(_("  ● Otomatik Derle  "))
        self._auto_label.setStyleSheet(
            f"color: {t['accent_progress']}; font-weight: bold; padding: 3px 8px; "
            "border: 1px solid transparent; border-radius: 4px;"
        )
        self._auto_label.mousePressEvent = lambda e: self._toggle_auto()
        toolbar.addWidget(self._auto_label)

        toolbar.addSeparator()

        self._theme_label = QLabel(_(" Tema: "))
        self._theme_label.setStyleSheet(f"color: {t['fg_label']}; font-weight: bold;")
        toolbar.addWidget(self._theme_label)
        self._theme_combo = QComboBox()
        for name in self._theme_mgr.available_themes():
            self._theme_combo.addItem(self._theme_mgr.theme_label(name), name)
        idx = self._theme_combo.findData(self._theme_mgr.current_name)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
        toolbar.addWidget(self._theme_combo)

        toolbar.addSeparator()

        # Dil seçici
        self._lang_label = QLabel(" " + _("Dil") + ": ")
        self._lang_label.setStyleSheet(f"color: {t['fg_label']}; font-weight: bold;")
        toolbar.addWidget(self._lang_label)
        self._lang_combo = QComboBox()
        from core.i18n import available_languages
        from PyQt6.QtCore import QSettings
        self._lang_combo.addItem("Türkçe", "tr")
        for code, name in available_languages():
            if code != "tr":
                self._lang_combo.addItem(name, code)
        saved_lang = QSettings("LatexEditor", "LatexEditor").value("language", "tr")
        idx = self._lang_combo.findData(saved_lang)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        toolbar.addWidget(self._lang_combo)

    def _setup_statusbar(self):
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage(_("Hazır"))

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(14)
        self._progress.setFixedWidth(140)
        self._progress.setTextVisible(False)
        self._progress.hide()
        self._status.addPermanentWidget(self._progress)

        self._status_engine = QLabel("lualatex")
        self._status.addWidget(self._status_engine)

        self._status_pos = QLabel(_("Satır 1, Sütun 1"))
        self._status.addPermanentWidget(self._status_pos)

        self._status_wordcount = QLabel("")
        self._status.addPermanentWidget(self._status_wordcount)

        self._wordcount_timer = QTimer(self)
        self._wordcount_timer.setSingleShot(True)
        self._wordcount_timer.setInterval(500)
        self._wordcount_timer.timeout.connect(self._do_wordcount)
        self._wordcount_editor = None

        self._outline_timer = QTimer(self)
        self._outline_timer.setSingleShot(True)
        self._outline_timer.setInterval(500)
        self._outline_timer.timeout.connect(self._do_update_outline)
        self._outline_editor = None

    def _connect_signals(self):
        self._compiler.compilation_started.connect(self._on_compile_started)
        self._compiler.compilation_finished.connect(self._on_compile_finished)
        self._compiler.output_line.connect(self._output_panel.append_output)

        self._file_tree.file_open_requested.connect(self._open_file_in_editor)
        self._file_tree.compile_requested.connect(self._compile_file)
        self._output_panel.error_clicked.connect(self._goto_line)

        self._pdf_viewer.reverse_search_requested.connect(self._on_reverse_search)

        self._theme_mgr.theme_changed.connect(self._apply_theme)

        self._editor_tabs.currentChanged.connect(self._on_tab_changed)

        self._engine_combo.currentTextChanged.connect(
            lambda t: self._status_engine.setText(t)
        )

        # QShortcut — ApplicationShortcut ile QScintilla focus problemi çözülür
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        save_shortcut.activated.connect(self._on_save_and_compile)

        stop_shortcut = QShortcut(QKeySequence("Esc"), self)
        stop_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        stop_shortcut.activated.connect(self._on_esc)

    # --- Tema ---

    def _apply_theme(self, t: dict = None):
        if t is None:
            t = self._theme_mgr.theme
        self.setStyleSheet(build_stylesheet(t))
        self._engine_label.setStyleSheet(
            f"color: {t['fg_label']}; font-weight: bold;"
        )
        self._theme_label.setStyleSheet(
            f"color: {t['fg_label']}; font-weight: bold;"
        )
        self._update_auto_label_theme(t)
        # Combobox'ı senkronize et
        idx = self._theme_combo.findData(self._theme_mgr.current_name)
        if idx >= 0:
            self._theme_combo.blockSignals(True)
            self._theme_combo.setCurrentIndex(idx)
            self._theme_combo.blockSignals(False)
        # Menü checkbox'larını güncelle
        for name, act in self._theme_actions.items():
            act.setChecked(name == self._theme_mgr.current_name)

        # Alt widget'lara ilet
        self._file_tree.apply_theme(t)
        self._output_panel.apply_theme(t)
        self._pdf_viewer.apply_theme(t)
        self._outline.apply_theme(t)
        if self._find_bar:
            self._find_bar.apply_theme(t)
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget):
                editor.apply_theme(t)
        for i in range(self._editor_tabs.count()):
            self._update_tab_close_theme(i, t)

    def _select_theme(self, name: str):
        self._theme_mgr.apply(name)

    def _on_theme_combo_changed(self, index: int):
        name = self._theme_combo.itemData(index)
        if name:
            self._theme_mgr.apply(name)

    def _on_lang_changed(self, index: int):
        from core.i18n import set_language
        from PyQt6.QtWidgets import QMessageBox
        code = self._lang_combo.itemData(index)
        if code:
            set_language(code)
            QMessageBox.information(self, "LaTeX Editor", _("Dil değişikliği yeniden başlatma gerektirir."))

    # --- Yardımcılar ---

    def _current_editor(self) -> EditorWidget | None:
        return self._editor_tabs.currentWidget()

    def _save_dialog(self, name: str) -> str:
        """Türkçe kaydetme dialogu — 'save', 'discard', veya 'cancel' döner."""
        msg = QMessageBox(self)
        msg.setWindowTitle(_("Kaydet"))
        msg.setText("'" + name + "' " + _("değiştirildi."))
        msg.setInformativeText(_("Kaydetmek ister misiniz?"))
        btn_save = msg.addButton(_("&Kaydet"), QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg.addButton(_("&Kaydetme"), QMessageBox.ButtonRole.DestructiveRole)
        msg.addButton(_("İ&ptal"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_save:
            return "save"
        if clicked == btn_discard:
            return "discard"
        return "cancel"

    def _show_shortcuts(self):
        t = self._theme_mgr.theme
        c = t["fg_primary"]
        html = "<span style='color:" + c + "'>"
        html += "<b>Dosya</b><br>"
        html += "Ctrl+S — " + _("Kaydet + Derle (Otomatik modda)") + "<br>"
        html += "Ctrl+B — " + _("Derle (Manuel modda veya yeniden derle)") + "<br>"
        html += "Ctrl+O — " + _("Klasör Aç") + "<br>"
        html += "Ctrl+Shift+O — " + _("Dosya Aç") + "<br>"
        html += "Ctrl+Shift+S — " + _("Farklı Kaydet") + "<br>"
        html += "Ctrl+Q — " + _("Çıkış") + "<br><br>"
        html += "<b>Düzenle</b><br>"
        html += "Ctrl+Z — " + _("Geri Al") + "<br>"
        html += "Ctrl+Y — " + _("Yinele") + "<br>"
        html += "Ctrl+F — " + _("Bul") + "<br>"
        html += "Ctrl+H — " + _("Bul ve Değiştir") + "<br>"
        html += "Ctrl+/ — " + _("Yorum Toggle") + "<br>"
        html += "Ctrl+G — " + _("Satıra Git") + "<br>"
        html += "F4 — " + _("Sonraki Hata") + "<br>"
        html += "Shift+F4 — " + _("Önceki Hata") + "<br><br>"
        html += "<b>" + _("Diğer") + "</b><br>"
        html += "Esc — " + _("Derlemeyi Durdur") + "<br>"
        html += "F5 — " + _("Sunum Modu") + "<br>"
        html += "Ctrl+" + _("Fare Tekerleği") + " — " + _("PDF Yakınlaştır") + "<br><br>"
        html += "<b>SyncTeX (PDF ↔ " + _("Kaynak") + ")</b><br>"
        html += "Ctrl+" + _("Tıklama") + " (" + _("Editör") + ") — " + _("PDF'te konumu göster") + "<br>"
        html += "Ctrl+" + _("Tıklama") + " (PDF) — " + _("Kaynak koda git")
        html += "</span>"
        QMessageBox.information(self, _("Klavye Kısayolları"), html)

    def _show_features(self):
        t = self._theme_mgr.theme
        c = t["fg_primary"]
        dim = t.get("fg_muted", c)
        # Sol sütun — Editör özellikleri
        left = ""
        left += "<b>" + _("Sözdizimi Renklendirme") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Komutlar, matematik, ortamlar — Notepad++ tarzı renklendirme.") + "</span>"
        left += "<br><br>"
        left += "<b>SyncTeX (PDF ↔ " + _("Kaynak") + ")</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Ctrl+tıkla → PDF/kaynak arasında geçiş. Önce derleyin.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Otomatik Parantezleme") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("(, [, {, $ yazınca kapanışı eklenir. \\begin{ad}'a \\end{ad} otomatik kapanır.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Otomatik Tamamlama") + " (Ctrl+Space)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("\\ komutları, ortam adları; \\ref{/\\eqref{/\\cite{/\\citep{ vb. için \\label'lar ve .bib anahtarları önerilir.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Belge Anahattı") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("\\section, \\chapter gibi bölümleri ağaç yapısında gösterir.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Bul / Değiştir") + " (Ctrl+F / Ctrl+H)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("VS Code tarzı inline panel, büyük/küçük harf duyarlı.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Yorum Toggle") + " (Ctrl+/)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Seçili satırları % ile yorum yapar/kaldırır.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Görsel Sürükle-Bırak") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("PNG, JPG, PDF, EPS → otomatik \\begin{figure} bloğu.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Panodan Resim Yapıştır") + " (Ctrl+V)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Panodaki resmi media/'a kaydeder, \\begin{figure} bloğu ekler.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Dosya Sürükle-Bırak") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _(".tex, .cls, .sty, .bib dosyalarını sürükleyerek açın.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Yeni Dosya") + " (Ctrl+N)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Otomatik \\documentclass şablonu ile yeni .tex dosyası.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Hata İşareti + F4") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Derleyince hata satırları gutter'da kırmızı işaretlenir. F4/Shift+F4 ile hatalar arasında dolaşın.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Otomatik Derleme") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Ctrl+S ile kaydederken otomatik derler. Toolbar'dan kapatıp Manuel mod'a geçebilirsiniz — büyük belgelerde her kayıtta derleme yapmak yavaşlatır, o durumda Ctrl+B ile derleyin.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Sekme Yönetimi") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Sağ tık → kapat, diğerlerini kapat, yol kopyala. Orta tık ile kapat.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Kelime Sayacı") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Durum çubuğunda anlık kelime/karakter sayısı. Matematik içeriği sayılmaz.") + "</span>"

        # Orta sütun — PDF özellikleri
        middle = ""
        middle += "<b>" + _("PDF Yer İmleri") + "</b><br>"
        middle += "<span style='color:" + dim + "'>" + _("PDF bölüm/başlık yapısına erişin, tıklayarak sayfaya gidin.") + "</span>"
        middle += "<br><br>"
        middle += "<b>" + _("PDF Arama") + " (Ctrl+F)</b><br>"
        middle += "<span style='color:" + dim + "'>" + _("Metin arayın, Enter ile sonraki eşleşmeye geçin.") + "</span>"
        middle += "<br><br>"
        middle += "<b>" + _("PDF Metin Seçme") + "</b><br>"
        middle += "<span style='color:" + dim + "'>" + _("Sürükleyerek metin seçin, Ctrl+C ile kopyalayın. Çift tık → kelime seç.") + "</span>"
        middle += "<br><br>"
        middle += "<b>" + _("Sayfaya Sığdır") + "</b><br>"
        middle += "<span style='color:" + dim + "'>" + _("Genişliğe veya tam sayfaya sığdırma düğmeleri.") + "</span>"
        middle += "<br><br>"
        middle += "<b>" + _("Çift Sayfa Görünümü") + "</b><br>"
        middle += "<span style='color:" + dim + "'>" + _("Sayfaları yan yana ikişerli gösterin.") + "</span>"
        middle += "<br><br>"
        middle += "<b>" + _("Sunum Modu") + " (F5)</b><br>"
        middle += "<span style='color:" + dim + "'>" + _("Tam ekran sunum. Sol/sağ tık veya ok tuşları ile gezin.") + "</span>"
        middle += "<br><br>"
        middle += "<b>" + _("PDF Renk Tersi") + "</b><br>"
        middle += "<span style='color:" + dim + "'>" + _("PDF renklerini ters çevirerek koyu modda görüntüleyin.") + "</span>"
        middle += "<br><br>"
        middle += "<b>" + _("Farklı Kaydet") + "</b><br>"
        middle += "<span style='color:" + dim + "'>" + _("PDF'i başka bir konuma kopyalayın.") + "</span>"

        # Sağ sütun — Genel özellikler
        right = ""
        right += "<b>" + _("Tema") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("7 tema: Koyu, Açık, Solarized, Dracula, Monokai, Nord, Gruvbox.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Çoklu Dil") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Türkçe ve İngilizce arayüz. Toolbar'dan dil değiştirin.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Akıllı Motor Algılama") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("fontspec → lualatex, inputenc → pdflatex otomatik seçilir.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Eksik Paket Tespiti") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Derleme hatasında eksik .sty/.cls dosyasını yakalar, kurulum komutunu önerir.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Dışa Aktarma") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Pandoc ile HTML, DOCX, Markdown, TXT formatlarına dışa aktarın.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Dosya İzleme") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Açık dosyaların diskte değişmesini algılar, yeniden yükleme sunar.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Otomatik Güncelleme Kontrolü") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Açılışta veya Yardım menüsünden yeni sürüm kontrolü.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Tek Instance Koruması") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Aynı anda yalnızca bir örnek çalıştırılabilir.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Geri Al / Yinele") + " (Ctrl+Z / Ctrl+Y)</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Sınırsız geri al ve yinele.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Satıra Git") + " (Ctrl+G)</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Belirli bir satır numarasına hızlıca gidin.") + "</span>"

        html = (
            f"<table width='100%'><tr>"
            f"<td width='33%' style='vertical-align:top; padding-right:10px; color:{c}'>"
            "<h3 style='color:" + c + "; margin:0'>" + _("Editör") + "</h3><br>"
            f"{left}</td>"
            f"<td width='33%' style='vertical-align:top; padding-left:5px; padding-right:5px; color:{c}'>"
            "<h3 style='color:" + c + "; margin:0'>" + _("PDF Görüntüleyici") + "</h3><br>"
            f"{middle}</td>"
            f"<td width='33%' style='vertical-align:top; padding-left:10px; color:{c}'>"
            "<h3 style='color:" + c + "; margin:0'>" + _("Genel") + "</h3><br>"
            f"{right}</td>"
            f"</tr></table>"
        )
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser
        dlg = QDialog(self)
        dlg.setWindowTitle(_("Özellikler"))
        dlg.resize(950, 600)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setOpenExternalLinks(True)
        layout.addWidget(browser)
        dlg.exec()

    def _show_about(self):
        from core.version import VERSION
        t = self._theme_mgr.theme
        c = t["fg_primary"]
        html = "<span style='color:" + c + "'>"
        html += "<h2>LaTeX Editor v" + VERSION + "</h2>"
        html += "<p>" + _("LaTeX editörü ve derleyici") + "</p>"
        html += "<p><b>" + _("Geliştirici:") + "</b> Serkan Ballı</p>"
        html += "<p><b>" + _("E-posta:") + "</b> serkanballi@gmail.com</p>"
        html += "<p><b>GitHub:</b> <a href='https://github.com/s-balli/latex-editor'>github.com/s-balli/latex-editor</a></p>"
        html += "</span>"
        QMessageBox.about(self, _("LaTeX Editor"), html)

    def _goto_line(self, file_path: str, line: int):
        if file_path:
            found = False
            for i in range(self._editor_tabs.count()):
                editor = self._editor_tabs.widget(i)
                if isinstance(editor, EditorWidget) and editor.file_path == os.path.normpath(file_path):
                    self._editor_tabs.setCurrentIndex(i)
                    found = True
                    break
            if not found and os.path.isfile(file_path):
                self._open_file_in_editor(file_path)

        editor = self._current_editor()
        if editor and line > 0:
            editor.setCursorPosition(line - 1, 0)
            editor.ensureLineVisible(line - 1)
            editor.setFocus()

    def _goto_outline_line(self, line: int):
        editor = self._current_editor()
        if editor:
            editor.setCursorPosition(line, 0)
            editor.ensureLineVisible(line)
            editor.setFocus()

    def _open_log_dir(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        log = _log_path()
        log_dir = os.path.dirname(log)
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        # AppImage sandbox'ta dosya yöneticisi açılamaz — panoya kopyala
        is_appimage = getattr(sys, 'frozen', False) and os.environ.get('APPIMAGE')
        if is_appimage:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(log_dir)
            self._status.showMessage(_("Panoya kopyalandı — terminalde cd ile geçin:") + f" {log_dir}")
            return
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))
        if ok:
            self._status.showMessage(f"Log: {log_dir}")
        else:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(log_dir)
            self._status.showMessage(_("Panoya kopyalandı — terminalde cd ile geçin:") + f" {log_dir}")

    # --- Event filter + sürükle-bırak ---

    def _start_update_check(self, silent: bool = False):
        """Arka planda güncelleme kontrolü başlat. silent=True ise açılış kontrolü."""
        # Mevcut thread çalışıyorsa, silent flag'i güncelle ve sonucunu bekle
        if self._update_thread and self._update_thread.isRunning():
            self._update_check_silent = silent
            if not silent:
                self._status.showMessage(_("Güncellemeler kontrol ediliyor..."))
            return
        self._update_check_silent = silent
        if not silent:
            self._status.showMessage(_("Güncellemeler kontrol ediliyor..."))
        self._update_thread = UpdateCheckThread(self)
        self._update_thread._force = not silent
        self._update_thread.update_found.connect(self._on_update_found)
        self._update_thread.finished_no_update.connect(self._on_no_update)
        self._update_thread.finished_network_error.connect(self._on_network_error)
        self._update_thread.finished.connect(self._on_thread_finished)
        self._update_thread.start()

    def _check_for_update_manual(self):
        """Yardım menüsünden manuel güncelleme kontrolü."""
        self._start_update_check(silent=False)

    def _on_thread_finished(self):
        """Thread bitti — referansı temizle."""
        if self._update_thread:
            self._update_thread.deleteLater()
            self._update_thread = None

    def _on_update_found(self, info: dict):
        """Yeni sürüm bulundu — kullanıcıya bildir."""
        self._status.showMessage("")
        tag = info.get("tag", "")
        url = info.get("url", "")
        notes = info.get("notes", "")
        msg = QMessageBox(self)
        msg.setWindowTitle(_("Güncelleme Mevcut"))
        t = self._theme_mgr.theme
        c = t["fg_primary"]
        html = f"<span style='color:{c}'>"
        html += f"<h3>{_('Yeni sürüm')} {tag} {_('mevcut')}</h3>"
        html += f"<p>{_('Kullandığınız sürüm')}: v{VERSION}</p>"
        if notes:
            html += f"<p><b>{_('Sürüm notları')}:</b><br>{notes}</p>"
        html += f"<p><a href='{url}'>{_('İndirmek için Releases sayfasını aç')}</a></p>"
        html += "</span>"
        msg.setText(html)
        msg.setInformativeText(_("Şimdi indirip kurmak ister misiniz?"))
        btn_open = msg.addButton(_("Tarayıcıda Aç"), QMessageBox.ButtonRole.AcceptRole)
        msg.addButton(_("Daha Sonra"), QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        if msg.clickedButton() == btn_open:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url))

    def _on_no_update(self):
        """Güncelleme yok — sadece manuel kontrolde bilgi ver."""
        self._status.showMessage("")
        if getattr(self, '_update_check_silent', True):
            return
        QMessageBox.information(self, _("Güncellemeleri Kontrol Et"),
                                f"{_('En güncel sürümü kullanıyorsunuz')} (v{VERSION}).")

    def _on_network_error(self):
        """Ağ hatası / rate limit — sadece manuel kontrolde bilgi ver."""
        self._status.showMessage("")
        if getattr(self, '_update_check_silent', True):
            return
        QMessageBox.information(self, _("Güncellemeleri Kontrol Et"),
                                _("Güncelleme kontrol edilemedi — bağlantı kurulamadı."))

    # --- Event filter + sürükle-bırak ---

    def eventFilter(self, obj, event):
        # QScintilla viewport drag/drop yakala
        parent = obj.parent() if isinstance(obj, QWidget) else None
        if isinstance(obj, EditorWidget) or isinstance(parent, EditorWidget):
            if event.type() == QEvent.Type.DragEnter:
                mime = event.mimeData()
                if mime and mime.hasUrls():
                    for url in mime.urls():
                        if url.isLocalFile():
                            event.acceptProposedAction()
                            return True
            elif event.type() == QEvent.Type.DragMove:
                mime = event.mimeData()
                if mime and mime.hasUrls():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Type.Drop:
                mime = event.mimeData()
                if mime and mime.hasUrls():
                    self._handle_dropped_urls(mime.urls())
                    return True

        if event.type() == QEvent.Type.KeyPress:
            # Esc — sunum modu çıkışı
            if event.key() == Qt.Key.Key_Escape and not event.modifiers():
                if self._pdf_viewer.in_presentation:
                    self._pdf_viewer.exit_presentation()
                    return True
                self._on_esc()
                return True

            # Ctrl+/ — klavye düzeninden bağımsız (text "/" olan her tuşu yakala)
            mods = event.modifiers()
            if (mods & Qt.KeyboardModifier.ControlModifier and
                    not (mods & Qt.KeyboardModifier.ShiftModifier) and
                    event.text() == "/"):
                editor = self._current_editor()
                if editor:
                    self._toggle_comment()
                    return True

        # Orta tık ile sekme kapatma
        if obj == self._editor_tabs.tabBar() and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.MiddleButton:
                index = self._editor_tabs.tabBar().tabAt(event.position().toPoint())
                if index >= 0:
                    self._close_tab(index)
                return True
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self._handle_dropped_urls(event.mimeData().urls())

    def _handle_dropped_urls(self, urls):
        for url in urls:
            path = url.toLocalFile()
            if os.path.isfile(path):
                ext = os.path.splitext(path)[1].lower()
                if ext in ('.tex', '.cls', '.sty', '.bib'):
                    self._open_file_in_editor(path)
                elif ext in ('.png', '.jpg', '.jpeg', '.pdf', '.eps'):
                    self._insert_image(path)

    # --- Durum kaydetme ---

    def closeEvent(self, event):
        # Güncelleme kontrolü thread'i çalışıyorsa bekle
        if self._update_thread and self._update_thread.isRunning():
            self._update_thread.quit()
            self._update_thread.wait(3000)
        # Kaydedilmemiş sekmeleri kontrol et
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget) and editor.isModified():
                self._editor_tabs.setCurrentIndex(i)
                reply = self._save_dialog(editor.display_name)
                if reply == "save":
                    editor.save_file()
                elif reply == "cancel":
                    event.ignore()
                    return
                # Discard → devam et
        self._cleanup_synctex_worker()
        shutil.rmtree(self._synctex_dir, ignore_errors=True)
        self._save_state()
        super().closeEvent(event)

    def _save_state(self):
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())
        self._settings.setValue("main_splitter", self._main_splitter.saveState())
        self._settings.setValue("top_splitter", self._top_splitter.saveState())
        self._settings.setValue("left_splitter", self._left_splitter.saveState())
        self._settings.setValue("engine", self._engine_combo.currentText())

        # Açık sekmeleri kaydet
        open_tabs = []
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget) and editor.file_path:
                open_tabs.append(editor.file_path)
        self._settings.setValue("open_tabs", open_tabs)
        # Aktif sekmenin dosya yolunu kaydet (index yerine) — silinen tablar sonrası kayma önler
        active_editor = self._current_editor()
        active_path = active_editor.file_path if isinstance(active_editor, EditorWidget) else ""
        self._settings.setValue("active_tab_path", active_path)

        # Dosya ağacı kökünü kaydet
        if self._file_tree._root:
            self._settings.setValue("file_tree_root", self._file_tree._root)

    def _restore_state(self):
        geo = self._settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        ws = self._settings.value("windowState")
        if ws:
            self.restoreState(ws)
        ms = self._settings.value("main_splitter")
        if ms:
            self._main_splitter.restoreState(ms)
        ts = self._settings.value("top_splitter")
        if ts:
            self._top_splitter.restoreState(ts)
        ls = self._settings.value("left_splitter")
        if ls:
            self._left_splitter.restoreState(ls)
        engine = self._settings.value("engine")
        if engine:
            idx = self._engine_combo.findText(engine)
            if idx >= 0:
                self._engine_combo.setCurrentIndex(idx)

        # Açık sekmeleri geri yükle
        open_tabs = self._settings.value("open_tabs", []) or []
        if isinstance(open_tabs, str):
            open_tabs = [open_tabs]
        for path in open_tabs:
            if os.path.isfile(path):
                self._open_file_in_editor(path)
        # Aktif sekmeyi dosya yolundan bul (index kayma riski yok)
        active_path = self._settings.value("active_tab_path", "")
        if active_path:
            active_path = os.path.normpath(active_path)
            for i in range(self._editor_tabs.count()):
                editor = self._editor_tabs.widget(i)
                if isinstance(editor, EditorWidget) and editor.file_path == active_path:
                    self._editor_tabs.setCurrentIndex(i)
                    break

        # Dosya ağacı kökünü geri yükle
        tree_root = self._settings.value("file_tree_root", "")
        if tree_root and os.path.isdir(tree_root):
            self._file_tree.set_root(tree_root)
