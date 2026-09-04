"""Ana pencere — editor, PDF viewer, file tree, output panel layout."""

import os
import shutil
import tempfile
from html import escape as _kacir

from core.version import VERSION
from core.log import get_logger, log_path as _log_path
from PyQt6.QtCore import QCoreApplication

_logger = get_logger("main_window")
_ = lambda s: QCoreApplication.translate("MainWindow", s)

import sys

from PyQt6.QtCore import Qt, QEvent, QObject, QSettings, QSize, QTimer, QThread, pyqtSignal
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
from gui.mixins.table_ops import TableOpsMixin
from gui.mixins.version_ops import VersionOpsMixin
from gui.mixins.synctex_ops import SyncTexMixin
from gui.mixins.recovery_ops import RecoveryOpsMixin
from gui.mixins.project_search_ops import ProjectSearchMixin
from gui.mixins.yazim_ops import YazimOpsMixin


class _PandocCheckSignal(QObject):
    """Arka plan pandoc kontrolünden UI'ya sonuç taşıyan sinyal köprüsü."""
    ready = pyqtSignal(bool)


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


def ekrana_sigan_boyut(genislik: int, yukseklik: int, alan=None):
    """İstenen ilk pencere boyutunu kullanılabilir ekran alanına sığdırır.

    Boyut sabit 1400x900 idi ve ekrana HİÇ bakılmıyordu. 1366x768 gibi hâlâ
    yaygın dizüstü ekranlarında pencere ilk açılışta taşıyor, bir kısmı
    ekranın dışında kalıyordu. Sonraki açılışlarda `restoreGeometry` devreye
    girdiği için yalnızca İLK açılış etkileniyordu; kaydedilmiş boyutu olan
    hiç kimse görmüyordu. AppImageHub'ın 800x600'lük Xvfb ekranında aldığı
    ekran görüntüsünde ortaya çıktı.

    `availableGeometry` görev çubuğunu zaten dışlıyor. Pencere çerçevesi
    (başlık çubuğu) `resize`a dahil değil, o yüzden çok dar ekranlarda
    yükseklikte çerçeve kadar taşma kalabilir; asıl kusur olan genişlik
    taşması tamamen kapanıyor.

    `alan` yalnızca test için: ekransız ortamda gerçek bir QScreen yok.
    """
    if alan is None:
        ekran = QApplication.primaryScreen()
        if ekran is None:
            return genislik, yukseklik
        alan = ekran.availableGeometry()
    return min(genislik, alan.width()), min(yukseklik, alan.height())


class MainWindow(
    FileWatchMixin,
    FileOpsMixin,
    TabOpsMixin,
    EditOpsMixin,
    CompileOpsMixin,
    ImageOpsMixin,
    TableOpsMixin,
    VersionOpsMixin,
    SyncTexMixin,
    RecoveryOpsMixin,
    ProjectSearchMixin,
    YazimOpsMixin,
    QMainWindow,
):
    def __init__(self, open_file: str = ""):
        super().__init__()
        self.setWindowTitle(f"LaTeX Editor v{VERSION}")
        self.resize(*ekrana_sigan_boyut(1400, 900))
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
        # Otomatik derleme tercihi kalıcı (varsayılan: açık). QSettings bool'u
        # bazı arka uçlarda dizge olarak döndürüyor — _auto_audit_enabled ile
        # aynı gevşek karşılaştırma.
        self._auto_compile = self._settings.value("compile/auto_compile", True) not in (
            False, "false", "False")
        self._theme_mgr = ThemeManager(self._settings, self)

        self._init_synctex_worker()
        self._init_project_search()
        self._file_watch_init()
        self._recovery_init()
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

        # Klasör sürümleniyorsa geçmiş sekmesini doldur
        self._refresh_history()

        # Ctrl+/ için application event filter (klavye düzeninden bağımsız)
        QApplication.instance().installEventFilter(self)

        # Sürükle-bırak ile dosya açma
        self.setAcceptDrops(True)

        # Açılışta arka planda güncelleme kontrolü
        self._update_thread = None
        self._update_check_silent = True
        self._start_update_check(silent=True)

        # Çökme kurtarma sorusu. singleShot(0) ŞART: doğrudan çağrılırsa modal
        # dialog __init__ içinde, yani main.py'nin window.show()'undan ÖNCE
        # açılır — kullanıcı boş masaüstünde tek başına duran bir soru görür ve
        # pencere ancak yanıtladıktan sonra belirir. Kuyruğa alınca olay döngüsü
        # başladıktan sonra, pencere görünürken çalışır.
        QTimer.singleShot(0, self._recovery_prompt)

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
        # Pencere büyüyünce fazla alanı ÜST bölme alsın, çıktı paneli
        # sürüklendiği yükseklikte kalsın. Panelin tavanı 200'ken bu fark
        # edilmiyordu; 400'e çıkınca uzun bir pencerede panel kendiliğinden
        # 400'e kadar şişiyor ve editörü eziyordu (ölçüldü: 1600x2000'de
        # 181 -> 400). Esneme çarpanı yalnız YENİDEN BOYUTLAMADA gelen fazla
        # alanı paylaştırıyor; kullanıcının ayırıcıyı sürüklemesini
        # engellemiyor.
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 0)

        self.setCentralWidget(self._main_splitter)

    def _setup_menus(self):
        menubar = self.menuBar()

        # Dosya menüsü
        file_menu = menubar.addMenu(_("&Dosya"))
        self._add_action(file_menu, _("Yeni &Dosya"), self._new_file, "Ctrl+N")
        file_menu.addSeparator()
        self._add_action(file_menu, _("&Klasör Aç..."), self._open_folder, "Ctrl+O")
        self._add_action(file_menu, _("D&osya Aç..."), self._open_file, "Ctrl+Shift+O")
        file_menu.addSeparator()
        # Ctrl+S menüde görünür ve menü/araç çubuğu/kısayol AYNI işi yapar.
        # Eskiden menü ve toolbar _save_file (yalnız kaydet), Ctrl+S ise
        # _on_save_and_compile (kaydet + derle) çağırıyordu; üstelik menüde
        # kısayol yazmıyordu. Yardım diyaloğu Ctrl+S'i "Kaydet + Derle" diye
        # belgelediği için menü belgelenen davranışla çelişiyordu.
        # app_shortcut: QScintilla odaktayken de çalışsın (eski QShortcut'ın
        # ApplicationShortcut context'i buraya taşındı).
        self._add_action(file_menu, _("Ka&ydet"), self._on_save_and_compile,
                         "Ctrl+S", app_shortcut=True)
        self._add_action(file_menu, _("Farklı Kayde&t..."), self._save_file_as, "Ctrl+Shift+S")
        file_menu.addSeparator()
        self._add_action(file_menu, _("Sürümle"), self._snapshot, "Ctrl+K", app_shortcut=True)
        self._add_action(file_menu, _("Sürüm &Geçmişi"), self._show_history)
        file_menu.addSeparator()

        self._recent_menu = file_menu.addMenu(_("Son Açılanlar"))
        # TEK bağlantı, öğe başına DEĞİL. `addAction(metin, lambda)` her
        # yenilemede bir kapanış sızdırıyor: QMenu.clear() QAction'ı siliyor
        # ama PyQt Python çağrılabilirini bırakmıyor. Ölçüldü: lambda'lı hâl
        # +5,00 nesne/çağrı, lambda'sız hâl +0,00. Menü her dosya açılışında
        # yenilendiği için sızıntı oturum boyunca birikiyordu.
        self._recent_menu.triggered.connect(self._on_recent_triggered)
        self._refresh_recent_menu()

        file_menu.addSeparator()

        export_menu = file_menu.addMenu(_("Dışa Akta&r"))
        from core.exporter import FORMATS, pandoc_available
        # pandoc_available() Windows'ta WSL'e 'which pandoc' sorar — soğuk
        # başlangıçta 1-3 sn sürebilir ve pencere çizilmeden önce bloklar.
        # Kontrol arka planda yapılır, bayrak gelince tooltip'ler güncellenir.
        # Linux/macOS'ta shutil.which anlıktır, orada doğrudan çağrılır.
        self._export_actions = []
        self._pandoc_available = True
        if sys.platform == "win32":
            self._pandoc_sig = _PandocCheckSignal()
            self._pandoc_sig.ready.connect(self._on_pandoc_checked)

            def _bg_check(sig=self._pandoc_sig):
                sig.ready.emit(pandoc_available())

            import threading
            threading.Thread(target=_bg_check, name="pandoc-check", daemon=True).start()
        else:
            self._pandoc_available = pandoc_available()
        for fmt_name, ext in FORMATS.items():
            act = export_menu.addAction(f"{fmt_name} ({ext})")
            act.triggered.connect(lambda checked, f=fmt_name, e=ext: self._export_file(f, e))
            self._export_actions.append(act)
            if not self._pandoc_available:
                act.setToolTip(_("pandoc gerekli: apt install pandoc"))
        self._add_action(file_menu, _("Çıkı&ş"), self.close, "Ctrl+Q")

        # Düzenle menüsü
        edit_menu = menubar.addMenu(_("Dü&zenle"))
        self._add_action(edit_menu, _("&Geri Al"), self._undo, "Ctrl+Z")
        self._add_action(edit_menu, _("&Yinele"), self._redo, "Ctrl+Y")
        edit_menu.addSeparator()
        self._add_action(edit_menu, _("&Bul..."), self._show_find, "Ctrl+F")
        self._add_action(edit_menu, _("Bul &Değiştir..."), self._show_replace, "Ctrl+H")
        self._add_action(edit_menu, _("Klasörde &Ara..."), self._project_search,
                         "Ctrl+Shift+F", app_shortcut=True)
        edit_menu.addSeparator()
        self._add_action(edit_menu, _("Yorum &Toggle"), self._toggle_comment)
        self._add_action(edit_menu, _("Satıra G&it..."), self._goto_line_dialog, "Ctrl+G")
        edit_menu.addSeparator()
        self._add_action(edit_menu, _("Tablo &Sihirbazı..."), self._table_wizard, "Ctrl+T", app_shortcut=True)
        self._add_action(edit_menu, _("Tabloyu &Hizala"), self._align_table)
        edit_menu.addSeparator()
        self._add_action(edit_menu, _("&Referansları Denetle"), self._audit_references)
        # Yazım denetimi KOMUTLA çalışır, canlı değil: istenmeden sözlük
        # yüklenmez (3.5 sn, 9.3 MB) ve ekranda hiçbir şey değişmez.
        # spylls kurulu değilse öğe HİÇ EKLENMEZ: görünüp tıklanınca hata
        # vermesindense hiç olmaması dürüst.
        from gui.mixins.yazim_ops import yazim_kullanilabilir
        if yazim_kullanilabilir():
            self._add_action(edit_menu, _("Yazı&mı Denetle"),
                             self._yazim_denetle, "Ctrl+Shift+Y",
                             app_shortcut=True)
        self._add_action(edit_menu, _("&Kaynakçayı Listele"), self._show_bibliography)
        self._add_action(edit_menu, _("DOI ile Kaynak &Ekle..."), self._add_by_doi)
        edit_menu.addSeparator()
        self._add_action(edit_menu, _("S&onraki Hata"), self._goto_next_error, "F4", app_shortcut=True)
        self._add_action(edit_menu, _("Ö&nceki Hata"), self._goto_prev_error, "Shift+F4", app_shortcut=True)

        # Derle menüsü
        build_menu = menubar.addMenu(_("De&rle"))
        self._add_action(build_menu, _("&Derle"), self._compile, "Ctrl+B", app_shortcut=True)
        self._add_action(build_menu, _("D&urdur"), self._stop_compile)
        build_menu.addSeparator()
        # Otomatik Derle anahtarı eskiden YALNIZ araç çubuğundaki QLabel'daydı:
        # klavye odağı almıyor, Space/Enter tetiklemiyor, menüde ve kısayol
        # listesinde hiç görünmüyordu. Menüdeki QAction ile etiket senkron.
        auto_act = self._add_action(build_menu, _("&Otomatik Derle"), self._toggle_auto)
        auto_act.setCheckable(True)
        auto_act.setChecked(self._auto_compile)
        self._auto_compile_action = auto_act
        act = self._add_action(build_menu, _("Derleme Sonrası &Referans Denetimi"), self._toggle_auto_audit)
        act.setCheckable(True)
        act.setChecked(self._auto_audit_enabled(self._settings))
        self._auto_audit_action = act
        build_menu.addSeparator()
        # Kabuk erişimi kararı proje başına kalıcı; yanlışlıkla verilen cevabın
        # geri alınacak bir yeri olmalı.
        self._add_action(build_menu, _("&Kabuk Erişimi İznini Sıfırla"),
                         self._reset_shell_escape)

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
        view_menu.addSeparator()
        self._add_action(view_menu, _("Editör A&yarları..."), self._open_settings_dialog)

        # Yardım menüsü
        help_menu = menubar.addMenu(_("&Yardım"))
        self._add_action(help_menu, _("&Klavye Kısayolları"), self._show_shortcuts)
        self._add_action(help_menu, _("Ö&zellikler"), self._show_features)
        help_menu.addSeparator()
        self._add_action(help_menu, _("&Güncellemeleri Kontrol Et"), self._check_for_update_manual)
        help_menu.addSeparator()
        self._add_action(help_menu, _("Ortam &Denetimi..."), self._open_env_doctor)
        self._add_action(help_menu, _("&Log Klasörünü Aç"), self._open_log_dir)
        help_menu.addSeparator()
        self._add_action(help_menu, _("&Hakkında"), self._show_about)

    def _on_pandoc_checked(self, available: bool):
        """Arka plan pandoc kontrolü bitti — bayrak ve dışa aktarma tooltip'leri."""
        self._pandoc_available = available
        tip = "" if available else _("pandoc gerekli: apt install pandoc")
        for act in getattr(self, "_export_actions", []):
            act.setToolTip(tip)

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
        toolbar.addAction(_("💾 Kaydet"), self._on_save_and_compile)
        toolbar.addAction(_("✔ Sürümle"), self._snapshot)
        toolbar.addAction(_("▶ Derle"), self._compile)
        toolbar.addSeparator()

        # Motor seçici
        self._engine_label = QLabel(_(" Derleyici: "))
        self._engine_label.setStyleSheet(f"color: {t['fg_label']}; font-weight: bold;")
        toolbar.addWidget(self._engine_label)
        self._engine_combo = QComboBox()
        self._engine_combo.addItems(["lualatex", "pdflatex", "xelatex"])
        self._engine_combo.setToolTip(_("Derleme motoru"))
        toolbar.addWidget(self._engine_combo)

        # Otomatik derleme durumu
        self._auto_label = QLabel(_("  ● Otomatik Derle  "))
        self._auto_label.setStyleSheet(
            f"color: {t['accent_progress']}; font-weight: bold; padding: 3px 8px; "
            "border: 1px solid transparent; border-radius: 4px;"
        )
        self._auto_label.setToolTip(_("Kaydederken otomatik derle. Açmak/kapatmak için tıklayın (Derle menüsü)"))
        self._auto_label.setCursor(Qt.CursorShape.PointingHandCursor)
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
        from core.i18n import VARSAYILAN_DIL, available_languages
        from PyQt6.QtCore import QSettings
        self._lang_combo.addItem("Türkçe", "tr")
        for code, name in available_languages():
            if code != "tr":
                self._lang_combo.addItem(name, code)
        # Varsayılan i18n ile AYNI kaynaktan geliyor: burada "tr" yazılıydı,
        # ayrışsaydı arayüz İngilizce açılır ama seçicide Türkçe görünürdü.
        saved_lang = QSettings("LatexEditor", "LatexEditor").value(
            "language", VARSAYILAN_DIL)
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
        self._output_panel.version_action.connect(self._on_version_action)
        self._output_panel.env_check_requested.connect(self._open_env_doctor)
        self._output_panel.project_search_requested.connect(
            self._on_project_search_requested)
        self._output_panel.bibliography_requested.connect(self._show_bibliography)
        # Yazım: panel kurulduktan SONRA bağlanmalı (sinyaller ondan geliyor)
        self._init_yazim()
        self._file_tree.root_changed.connect(self._on_project_root_changed)
        self._file_tree.file_renamed.connect(self._on_file_renamed)

        self._pdf_viewer.reverse_search_requested.connect(self._on_reverse_search)

        self._theme_mgr.theme_changed.connect(self._apply_theme)

        self._editor_tabs.currentChanged.connect(self._on_tab_changed)

        self._engine_combo.currentTextChanged.connect(
            lambda t: self._status_engine.setText(t)
        )

        # QShortcut — ApplicationShortcut ile QScintilla focus problemi çözülür
        # (Ctrl+S artık Dosya menüsündeki QAction'da, app_shortcut=True ile.)
        quick_open = QShortcut(QKeySequence("Ctrl+P"), self)
        quick_open.setContext(Qt.ShortcutContext.ApplicationShortcut)
        quick_open.activated.connect(self._quick_open)

        # Ctrl+Shift+F BURAYA EKLENMEZ. Düzenle menüsündeki QAction zaten
        # app_shortcut=True ile ApplicationShortcut olarak kayıtlı; ikinci bir
        # QShortcut aynı diziyi aynı bağlamda kaydedince Qt "Ambiguous
        # shortcut overload" deyip HİÇBİRİNİ tetiklemiyor — tuşa basmak
        # sessizce hiçbir şey yapmıyordu (kullanıcı bildirdi, ölçümle
        # doğrulandı). Aynı ders Ctrl+S için de yazılıydı; kapı artık
        # test_menu_actions.py'de tüm diziler için genel.

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

    # --- Editör ayarları (tab genişliği, font boyutu, satır kaydırma) ---

    _EDITOR_SETTING_DEFAULTS = {"editor/tab_width": 4, "editor/font_size": 11, "editor/wrap": True}

    @staticmethod
    def _ayar_sayi(deger, varsayilan, en_az: int, en_cok: int) -> int:
        """QSettings degerini tam sayiya cevir; bozuksa varsayilana don.

        Ayar dosyasina yarim yazma (elektrik kesintisi, dolu disk) bos ya da
        bozuk bir deger birakabiliyor. `int("")` ValueError atiyor ve bu,
        oturumda ACIK SEKME varsa __init__ -> _restore_state ->
        _apply_editor_settings zincirinde patliyordu: uygulama BIR DAHA
        ACILMIYORDU. Olculdu (2026-09-02): bos, metin ve ondalik degerlerin
        ucu de acilisi kesiyordu; sekme yokken sorun cikmiyordu.

        Aralik da sinirli: sifir ya da absurt buyuk bir deger uygulamayi
        acar ama kullanilamaz halde birakirdi, yani ayni kilitlenme.
        """
        try:
            n = int(deger)
        except (TypeError, ValueError):
            return int(varsayilan)
        return max(en_az, min(n, en_cok))

    def _read_editor_settings(self) -> dict:
        d = self._EDITOR_SETTING_DEFAULTS
        return {
            "tab_width": self._ayar_sayi(
                self._settings.value("editor/tab_width", d["editor/tab_width"]),
                d["editor/tab_width"], 1, 16),
            "font_size": self._ayar_sayi(
                self._settings.value("editor/font_size", d["editor/font_size"]),
                d["editor/font_size"], 6, 72),
            "wrap": self._settings.value("editor/wrap", d["editor/wrap"]) in (True, "true", "True"),
        }

    def _apply_editor_settings(self, editor):
        """Kayıtlı editör ayarlarını bir editöre uygula (yeni sekmelerde çağrılır)."""
        s = self._read_editor_settings()
        editor.apply_editor_settings(s["tab_width"], s["font_size"], s["wrap"])

    def _open_settings_dialog(self):
        from PyQt6.QtWidgets import QDialog
        from gui.settings_dialog import EditorSettingsDialog
        dlg = EditorSettingsDialog(self._read_editor_settings(), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        self._settings.setValue("editor/tab_width", vals["tab_width"])
        self._settings.setValue("editor/font_size", vals["font_size"])
        self._settings.setValue("editor/wrap", vals["wrap"])
        for i in range(self._editor_tabs.count()):
            ed = self._editor_tabs.widget(i)
            if isinstance(ed, EditorWidget):
                self._apply_editor_settings(ed)
        self._status.showMessage(_("Editör ayarları kaydedildi"))

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
        html += "<b>" + _("Dosya") + "</b><br>"
        html += "Ctrl+N · " + _("Yeni Dosya") + "<br>"
        html += "Ctrl+S · " + _("Kaydet + Derle (Otomatik modda)") + "<br>"
        html += "Ctrl+B · " + _("Derle (Manuel modda veya yeniden derle)") + "<br>"
        html += "Ctrl+O · " + _("Klasör Aç") + "<br>"
        html += "Ctrl+Shift+O · " + _("Dosya Aç") + "<br>"
        html += "Ctrl+Shift+S · " + _("Farklı Kaydet") + "<br>"
        html += "Ctrl+K · " + _("Sürümle (tüm değişiklikleri tek kayda al)") + "<br>"
        html += "Ctrl+P · " + _("Hızlı Dosya Aç") + "<br>"
        html += "Ctrl+Q · " + _("Çıkış") + "<br><br>"
        html += "<b>" + _("Düzenle") + "</b><br>"
        html += "Ctrl+Z · " + _("Geri Al") + "<br>"
        html += "Ctrl+Y · " + _("Yinele") + "<br>"
        html += "Ctrl+F · " + _("Bul") + "<br>"
        html += "Ctrl+Shift+F · " + _("Klasörde Ara") + "<br>"
        html += "Ctrl+H · " + _("Bul ve Değiştir") + "<br>"
        html += "Ctrl+/ · " + _("Yorum Toggle") + "<br>"
        html += "Ctrl+G · " + _("Satıra Git") + "<br>"
        html += "Ctrl+T · " + _("Tablo Sihirbazı") + "<br>"
        html += "F2 · " + _("Etiketi/Kaynakça Anahtarını Yeniden Adlandır (imleç \\label/\\ref/\\cite/\\bibitem veya .bib girdisi üzerinde)") + "<br>"
        html += "F4 · " + _("Sonraki Hata") + "<br>"
        html += "Shift+F4 · " + _("Önceki Hata") + "<br><br>"
        html += "<b>" + _("Diğer") + "</b><br>"
        html += "Esc · " + _("Derlemeyi Durdur") + "<br>"
        html += "F5 · " + _("Sunum Modu") + "<br>"
        html += "Ctrl+" + _("Fare Tekerleği") + " · " + _("PDF Yakınlaştır") + "<br><br>"
        html += "<b>SyncTeX (PDF ↔ " + _("Kaynak") + ")</b><br>"
        html += "Ctrl+" + _("Tıklama") + " (" + _("Editör") + ") · " + _("PDF'te konumu göster") + "<br>"
        html += "Ctrl+" + _("Tıklama") + " (PDF) · " + _("Kaynak koda git") + "<br><br>"
        html += "<b>" + _("Tanıma Git") + "</b><br>"
        html += "Alt+" + _("Tıklama") + " · " + _("\\ref/\\cite tanıma git (\\label veya .bib girişi)")
        html += "</span>"
        QMessageBox.information(self, _("Klavye Kısayolları"), html)

    def _show_features(self):
        t = self._theme_mgr.theme
        c = t["fg_primary"]
        dim = t.get("fg_muted", c)
        # Sol sütun — Editör özellikleri
        left = ""
        left += "<b>" + _("Sözdizimi Renklendirme") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Komutlar, matematik, ortamlar: Notepad++ tarzı renklendirme.") + "</span>"
        left += "<br><br>"
        left += "<b>SyncTeX (PDF ↔ " + _("Kaynak") + ")</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Ctrl+tıkla → PDF/kaynak arasında geçiş. Önce derleyin.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Otomatik Parantezleme") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("(, [, {, $ yazınca kapanışı eklenir. \\begin{ad}'a \\end{ad} otomatik kapanır.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Otomatik Tamamlama") + " (Ctrl+Space)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("\\ komutları, ortam adları; \\ref{/\\eqref{/\\cite{ vb. için \\label'lar ve .bib anahtarları; \\input{/\\include{ için .tex dosyaları, \\includegraphics{ için resimler önerilir.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Belge Anahattı") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("\\section, \\chapter gibi bölümleri ağaç yapısında gösterir.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Bul / Değiştir") + " (Ctrl+F / Ctrl+H)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("VS Code tarzı inline panel. Üç seçenek: büyük/küçük harf eşleştir, tam kelime, düzenli ifade. Desen kipinde değiştirmede \\1 yakalanan gruba karşılık gelir.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Klasörde Ara") + " (Ctrl+Shift+F)</b><br>"
        left += "<b>" + _("Yazım Denetimi") + " (Ctrl+Shift+N)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Yazım sekmesinden Denetle: belge taranır, bulgular satır numarasıyla listelenir, tıklayınca o satıra gidilir. Denetim canlı değildir, siz istemeden çalışmaz. Dil belgeden anlaşılır (% !TEX spellcheck ya da babel); Türkçe tezin İngilizce özeti gibi iki dilli belgelerde 'İkinci dil de var' kutusunu işaretleyin. Bulguya sağ tıklayarak öneri alabilir ya da kelimeyi kendi sözlüğünüze ekleyebilirsiniz.") + "</span><br><br>"
        left += "<span style='color:" + dim + "'>" + _("Klasör ağacındaki TÜM .tex/.bib/.cls/.sty dosyalarının İÇİNDE arar, sekmede açık olmayanlar dahil. Ctrl+F yalnız açık sekmede arar. Sonuca tıklayınca o dosyanın o satırına gidilir.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Hızlı Dosya Aç") + " (Ctrl+P)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Dosya adını yaz, bulanık filtreyle bul, Enter ile aç. Klasör ağacındaki .tex/.bib/.cls/.sty dosyaları.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Yorum Toggle") + " (Ctrl+/)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Seçili satırları % ile yorum yapar/kaldırır.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Tablo Sihirbazı") + " (Ctrl+T)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Hücrelere yazarak veya CSV yükleyerek tabular tablosu üret; booktabs, hizalama, caption/label dahil. İmleç tablonun içindeyse mevcut tabloyu düzenler; Tabloyu Hizala ile kolonları hizalar.") + "</span>"
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
        left += "<b>" + _("Çıktı Paneli") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Alt paneldeki sekmeler: Hatalar, Uyarılar, Öneriler, Log, Sürüm Geçmişi, Klasörde Ara, Kaynakça ve Yazım. Hata ve uyarı satırlarına tıklayınca ilgili dosyanın o satırına gidilir; Öneriler sekmesi hatanın ne anlama geldiğini Türkçe anlatır. Panel ayırıcıdan sürüklenerek büyütülebilir. Esc derlemeyi durdurur.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Hata İşareti + F4") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Derleyince hata satırları gutter'da kırmızı işaretlenir. F4/Shift+F4 ile hatalar arasında dolaşın.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Tanıma Git") + " (Alt+" + _("Tıklama") + ")</b><br>"
        left += "<span style='color:" + dim + "'>" + _("\\ref/\\cite üzerine Alt basılı tıkla → \\label, .bib veya \\bibitem girişine atlar. .bib girdisine tıklayınca makaledeki \\cite yerine gider. Çok dosyalı (\\input) ve çok anahtarlı \\cite destekli.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Yeniden Adlandır") + " (F2)</b><br>"
        left += "<span style='color:" + dim + "'>" + _("\\label/\\ref/\\cite/\\bibitem veya .bib girdisi üzerinde F2 → anahtar doküman, \\input zinciri ve .bib'te toplu değişir. Açık sekmeler tek undo adımı alır; çift isim engellenir.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Referans Denetimi (Düzenle menüsü)") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Tanımsız \\ref/\\cite, kullanılmayan .bib girdisi ve label'ları derlemeden bulur; ayrıca mükerrer .bib anahtarını ve eksik zorunlu alanı bildirir. Bulguya tıkla, yerine atla. Derle menüsünden her derleme sonrası otomatik çalışacak şekilde açılabilir.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Kaynakça Sekmesi (Düzenle menüsü)") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _(".bib girdilerini anahtar, tür, yazar, yıl ve başlık sütunlarında listeler; sütuna göre sırala, süz, satıra tıklayıp dosyadaki yerine git. Kaynakça elle yazılmışsa (\\bibitem) o girdiler de listelenir.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("DOI ile Kaynak Ekle (Düzenle menüsü)") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("DOI'yi yapıştır (tam URL de olur), girdi Crossref'ten gelsin ve .bib dosyasının sonuna eklensin. Ay makrosu, sayfa aralığı ve anahtar çakışması düzeltilir; eklenecek metni önce görüp düzenleyebilirsiniz.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Dosya Ağacı İşlemleri") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Ağaçta sağ tık: yeni dosya, yeni klasör, yeniden adlandır, sil. Yeniden adlandırılan dosya açıksa sekme de yeni ada taşınır. Şekil olarak kullanılan PDF'ler ağaçta görünür, derleme çıktısı gizli kalır.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Editör Ayarları (Görünüm menüsü)") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Tab genişliği, font boyutu ve satır kaydırma; kalıcıdır, tüm sekmelere uygulanır. Ctrl+tekerlek ile anlık zoom da vardır.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Otomatik Derleme") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Ctrl+S ile kaydederken otomatik derler. Toolbar'dan kapatıp Manuel mod'a geçebilirsiniz; büyük belgelerde her kayıtta derleme yapmak yavaşlatır, o durumda Ctrl+B ile derleyin.") + "</span>"
        left += "<br><br>"
        left += "<b>% !TEX root</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Çok dosyalı projelerde alt dosyanın başına '% !TEX root = ana.tex' yazın; derleme otomatik olarak kök belgeye yönlendirilir, motor kökün içeriğinden algılanır.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Sekme Yönetimi") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Sağ tık → kapat, diğerlerini kapat, yol kopyala. Orta tık ile kapat.") + "</span>"
        left += "<br><br>"
        left += "<b>" + _("Kelime Sayacı") + "</b><br>"
        left += "<span style='color:" + dim + "'>" + _("Durum çubuğunda anlık kelime/karakter sayısı. Matematik içeriği sayılmaz.") + "</span>"

        # Orta sütun — PDF özellikleri
        middle = ""
        middle += "<b>" + _("Derleme Sonrası Otomatik Atlama") + "</b><br>"
        middle += "<span style='color:" + dim + "'>" + _("Başarılı derleme bitince PDF, imlecin olduğu yere SyncTeX ile otomatik kaydırılır.") + "</span>"
        middle += "<br><br>"
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
        right += "<b>" + _("Ortam Denetimi") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("WSL, TeX motorları, biber, pandoc ve synctex hazır mı tek ekranda gösterir; eksik olana kurulum komutu önerir (Yardım menüsü).") + "</span>"
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
        right += "<span style='color:" + dim + "'>" + _("Aynı anda tek pencere. İkinci kez açılan dosya (ör. 'Birlikte Aç') yeni pencere yerine çalışan uygulamada sekme olarak açılır.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Geri Al / Yinele") + " (Ctrl+Z / Ctrl+Y)</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Sınırsız geri al ve yinele.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Sürümleme") + " (Ctrl+K)</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Ctrl+K ile tüm değişiklikleri adlandırılmış bir sürüme kaydedin. Sürüm Geçmişi sekmesinde sağ tık: farkları gör, dosyayı geri yükle, o sürümdeki hâlini panoya kopyala ya da sürümü sil. Git bilgisine gerek yok; klasörde standart .git oluşur.") + "</span>"
        right += "<br><br>"
        right += "<b>" + _("Çökme Kurtarma") + "</b><br>"
        right += "<span style='color:" + dim + "'>" + _("Kaydedilmemiş değişiklikler 30 saniyede bir uygulama veri dizinine yedeklenir. Uygulama öldürülür ya da elektrik giderse bir sonraki açılışta geri yüklenmesi önerilir; kendi dosyalarınıza dokunulmaz.") + "</span>"
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
        # Zemin ACIKCA veriliyor: QTextBrowser uygulamanin stylesheet'ine
        # takilmiyor, kendi palet Base rengini (beyaz) koruyor. Koyu temada
        # bu pencere beyaz zemin uzerine krem yazi oluyordu, karsitlik 1.37
        # (olculdu 2026-09-03, esik 4.50).
        browser.setStyleSheet(
            "QTextBrowser {{ background: {bg}; color: {fg};"
            " border: 1px solid {kenar}; }}".format(
                bg=t["bg_primary"], fg=c, kenar=t["border_normal"]))
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
        # `<a>` govdenin span rengini ALMIYOR, Qt kendi sabit palet Link
        # rengini kullaniyor: koyu temada karsitlik 1.43 olcüldü (esik 4.50).
        # Ayni kusur guncelleme diyalogunda da vardi (bkz. _on_update_found).
        vurgu = t["fg_bright"]
        html += ("<p><b>GitHub:</b> "
                 f"<a href='https://github.com/s-balli/latex-editor' "
                 f"style='color:{vurgu}'>github.com/s-balli/latex-editor</a></p>")
        html += ("<p><b>" + _("Tanıtım sayfası:") + "</b> "
                 f"<a href='https://s-balli.github.io/latex-editor/' "
                 f"style='color:{vurgu}'>"
                 "s-balli.github.io/latex-editor</a></p>")
        html += "</span>"
        QMessageBox.about(self, _("LaTeX Editor"), html)

    def _goto_line(self, file_path: str, line: int):
        if file_path:
            editor = self._editor_by_path(file_path)
            if editor is not None:
                self._editor_tabs.setCurrentWidget(editor)
            elif os.path.isfile(file_path):
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

    def _on_goto_definition(self, key: str, kind: str):
        """Alt+tık ile \\ref/\\cite tanıma git: \\label, .bib girişi veya .bib'ten
        makaledeki \\cite yerine."""
        from core.latex_refs import (
            find_label_location, find_cite_location, find_cite_usage,
            find_bibitem_location,
        )
        ed = self.sender()
        if not isinstance(ed, EditorWidget):
            ed = self._current_editor()
        if not ed or not ed.file_path or not key:
            return
        content = ed.text()
        if kind == "label":
            loc = find_label_location(content, ed.file_path, key)
        elif kind == "cite":
            loc = find_cite_location(content, ed.file_path, key)
            # .bib yoksa / anahtar .bib'te yoksa: el ile kaynakça (\bibitem) fallback
            if loc is None:
                loc = find_bibitem_location(content, ed.file_path, key)
        else:  # cite-usage: .bib girdisinden makalede \cite edildiği yere
            loc = find_cite_usage(ed.file_path, key)
        if loc:
            path, line = loc
            self._goto_line(path, line)
            self._status.showMessage(_("Tanım") + f": {os.path.basename(path)}:{line}")
        else:
            self._status.showMessage(_("Tanım bulunamadı") + f": {key}")

    def _open_env_doctor(self):
        """Ortam denetimi: WSL/TeX Live/pandoc/synctex kontrolü (Yardım menüsü).

        Kontroller dialog içinde arka planda koşar (WSL soğuk başlangıçta
        saniyeler sürebilir); pencere hemen açılır.
        """
        from gui.env_doctor import EnvDoctorDialog
        dlg = EnvDoctorDialog(self, theme=self._theme_mgr.theme)
        dlg.exec()

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
            self._status.showMessage(_("Panoya kopyalandı, terminalde cd ile geçin:") + f" {log_dir}")
            return
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))
        if ok:
            self._status.showMessage(f"Log: {log_dir}")
        else:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(log_dir)
            self._status.showMessage(_("Panoya kopyalandı, terminalde cd ile geçin:") + f" {log_dir}")

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
            # Notlar HTML'e gomuluyor: KACIS sart, yoksa surum notundaki bir
            # `<` etiket sanilip gosterimi bozar. Satir sonlari da <br>
            # olmadan bosluga cokuyor ve 13 madde tek paragrafa yapisiyordu
            # (olculdu 2026-09-02, gercek v1.0.19 yaniti Qt'ye cizdirilerek).
            govde = _kacir(notes).replace("\n", "<br>")
            html += f"<p><b>{_('Sürüm notları')}:</b><br>{govde}</p>"
            if info.get("kirpildi"):
                html += (f"<p><i>{_('Notların tamamı Releases sayfasında.')}"
                         "</i></p>")
        # `<a>` govdenin span rengini ALMIYOR: Qt kendi sabit palet Link
        # rengini (0, 66, 117) kullaniyor ve koyu zeminde okunmuyor. Olculdu
        # (2026-09-02, gercek diyalog goruntusu uzerinden): yedi temanin
        # besinde karsitlik 1.21 ile 1.62 arasinda, WCAG AA esigi 4.50; ayni
        # diyalogda govde metni 9.25 ile 13.94 arasinda, yani sorun temada
        # degil yalnizca baglantida.
        #
        # `accent` yetmiyor (dark'ta 3.14, light'ta 3.94), `fg_primary` de
        # solarized_light'ta esigin altinda (4.13). `fg_bright` yedi temada
        # da geciyor, en dusugu 10.84. Alti cizili oldugu icin tiklanabilirlik
        # renkten bagimsiz belli oluyor.
        vurgu = t["fg_bright"]
        html += (f"<p><a href='{url}' style='color:{vurgu}'>"
                 f"{_('İndirmek için Releases sayfasını aç')}</a></p>")
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
                                _("Güncelleme kontrol edilemedi, bağlantı kurulamadı."))

    # --- Event filter + sürükle-bırak ---

    def _handle_app_key_shortcut(self, event) -> bool:
        """Uygulama düzeyi tuş kısayolları — tüketilirse True döner.

        Bu kısayollar editör (QScintilla) odaktayken çalışmalı; Scintilla bazı
        tuşları (Ctrl+T: satır transpoze) gömülü komut olarak yuttuğundan Qt
        kısayol sistemine ulaşmazlar. Uygulama filtresi (eventFilter) hedef
        widget'tan önce görür; mantık burada saf tutulur ki Qt kurulmadan
        test edilebilsin.

        Modal dialog açıkken HİÇBİR tuş tüketilmez: filtre QApplication'a
        kuruludur ve dialog'a giden tuşları da görür. Tüketseydik Esc dialog'u
        kapatamaz, Ctrl+K/Ctrl+T sürüm-adı dialogu açıkken ikinci bir
        Sürümle/Sihirbaz penceresi açardı.

        BU FİLTRE GLOBAL KISAYOL KAPMASINA KARŞI İŞE YARAMAZ. 2026-09-01'de
        ölçüldü: kullanıcının makinesinde başka bir uygulama Ctrl+H ve Ctrl+T'yi
        sistem genelinde kapıyordu; Ctrl+T ZATEN bu filtredeydi ve yine
        çalışmıyordu (o uygulamanın kendi işlevi açılıyordu). Tuş işletim
        sistemi seviyesinde tutulunca buraya hiç gelmiyor. "Kısayol hiç
        tetiklenmiyor" raporu geldiğinde ÖNCE dışarısı elenmeli: uygulamayı
        kapatıp açmak, çakışan programı kapatmak. Kısayolu buraya taşımak o
        sınıftaki sorunu çözmez.
        """
        if QApplication.activeModalWidget() is not None:
            return False
        if event.key() == Qt.Key.Key_Escape and not event.modifiers():
            if self._pdf_viewer.in_presentation:
                self._pdf_viewer.exit_presentation()
                return True
            self._on_esc()
            return True

        mods = event.modifiers()
        # Ctrl+/ — klavye düzeninden bağımsız (text "/" olan her tuşu yakala)
        if (mods & Qt.KeyboardModifier.ControlModifier and
                not (mods & Qt.KeyboardModifier.ShiftModifier) and
                event.text() == "/"):
            if self._current_editor():
                self._toggle_comment()
                return True
            return False

        # Ctrl+T — tablo sihirbazı (Scintilla'nın gömülü komodu yutuyor)
        if (event.key() == Qt.Key.Key_T and
                mods == Qt.KeyboardModifier.ControlModifier):
            if self._current_editor():
                self._table_wizard()
                return True
        # Ctrl+K — sürümle (aynı gerekçe: filtreye alınmış tuş)
        if (event.key() == Qt.Key.Key_K and
                mods == Qt.KeyboardModifier.ControlModifier):
            self._snapshot()
            return True
        return False

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
            if self._handle_app_key_shortcut(event):
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

    # --- İkinci örnekten gelen istek ---

    # 'Birlikte Aç' ile gelen dosyalar; sürükle-bırakla aynı küme.
    _OPENABLE_EXT = ('.tex', '.cls', '.sty', '.bib')

    def open_from_other_instance(self, path: str):
        """Çalışan örneğe iletilen dosyayı aç ve pencereyi öne getir.

        İkinci örnek (ör. Explorer'da .tex'e çift tıklama) kendi penceresini
        açmaz; yolu buraya iletip çıkar. Yol boş olabilir: kullanıcı yalnız
        uygulamayı yeniden başlatmayı denemiştir, o zaman sadece öne gel.
        """
        path = (path or "").strip()
        if path and os.path.isfile(path):
            if os.path.splitext(path)[1].lower() in self._OPENABLE_EXT:
                self._open_file_in_editor(path)
            else:
                # Sessiz kalmıyoruz: pencere öne geliyor ama hiçbir şey
                # açılmıyordu, kullanıcı yalnız log'a bakarak anlayabilirdi.
                _logger.info("İkinci örnekten desteklenmeyen tür: %s", path)
                self._status.showMessage(
                    _("Bu dosya türü açılamıyor: {name}").format(
                        name=os.path.basename(path)))
        elif path:
            _logger.warning("İkinci örnekten gelen dosya bulunamadı: %s", path)
            self._status.showMessage(
                _("Dosya bulunamadı: {name}").format(name=os.path.basename(path)))

        # Simge durumundaysa geri al, sonra öne getir. Windows arka plandaki
        # sürecin pencere aktifleştirmesini kısıtlayabilir; o durumda görev
        # çubuğunda yanıp söner — kullanıcı yine de olup biteni görür.
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    # --- Durum kaydetme ---

    # Kapanışta beklenecek arka plan yazıcıları: (öznitelik, süre ms).
    # Sürümleme daha uzun tutulur — büyük klasörde add+commit saniyeler sürer
    # ve yarıda kesilmesi depoyu bozabilir; dışa aktarmada en kötü hâl yarım
    # bir çıktı dosyasıdır.
    # _doi_runner diske YAZMIYOR (yalnız ağdan okuyup sinyal yayıyor) ama yine
    # de bekleniyor: 8 sn'lik zaman aşımıyla çalışan bir thread pencere yok
    # edilirken canlı kalırsa sinyali ölü bir nesneye ulaşır.
    _BG_WRITERS = (("_snapshot_runner", 15000), ("_export_runner", 10000),
                   ("_doi_runner", 9000))

    def _wait_background_writers(self):
        """Diske yazan daemon thread'lerin bitmesini bekle.

        _SnapshotRunner / _ExportRunner düz daemon thread kullanır; bunlar
        yorumlayıcı çıkışında haber vermeden KESİLİR. git commit'in ya da
        pandoc çıktısının ortasında kesilmek yarım iş bırakır.
        """
        for attr, timeout_ms in self._BG_WRITERS:
            runner = getattr(self, attr, None)
            if runner is None:
                continue
            if not runner.wait(timeout_ms):
                _logger.warning("Arka plan işi kapanışta bitmedi: %s", attr)

    def closeEvent(self, event):
        # Güncelleme kontrolü thread'i çalışıyorsa bekle. quit() işe yaramaz
        # (run() override event loop çalıştırmaz); tek güvence wait. check_for_update
        # 5 sn ağ timeout'u kullandığından 6 sn bekle: thread pencere yok edilirken
        # çalışır durumda kalmasın ("QThread destroyed while running" çökmesi).
        if self._update_thread and self._update_thread.isRunning():
            self._update_thread.quit()
            self._update_thread.wait(6000)
        self._wait_background_writers()
        # Kaydedilmemiş sekmeleri kontrol et
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget) and editor.isModified():
                self._editor_tabs.setCurrentIndex(i)
                reply = self._save_dialog(editor.display_name)
                if reply == "save":
                    # Kayıt başarısızsa çıkışı iptal et: dirty içerik kaybolmasın.
                    # (Hata dialogunu save_file kendi gösterir.)
                    if not editor.save_file():
                        event.ignore()
                        return
                elif reply == "cancel":
                    event.ignore()
                    return
                # Discard → devam et
        self._cleanup_synctex_worker()
        self._cleanup_project_search()
        self._cleanup_yazim()
        self._pdf_viewer.shutdown()
        shutil.rmtree(self._synctex_dir, ignore_errors=True)
        # Buraya ancak TEMİZ kapanışta gelinir: yukarıdaki döngü her kirli
        # sekmeyi sordu ve kullanıcı iptal etmedi. Kurtarılacak bir şey
        # kalmadı; artıkları bırakmak bir sonraki açılışta boşuna "kaydedilmemiş
        # değişiklik bulundu" sorusu üretirdi.
        self._recovery_clear()
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
                # add_recent=False: oturum sekmeleri 'Son Açılanlar'ı ezmesin;
                # liste kullanıcının gerçekte en son açtığı dosyaları taşısın
                self._open_file_in_editor(path, add_recent=False)
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
