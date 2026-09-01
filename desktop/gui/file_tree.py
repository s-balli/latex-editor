"""Proje dosya ağacı — .tex/.cls/.sty/.bib dosyaları, alt klasör desteği."""

import os

import send2trash

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QMenu, QMessageBox, QInputDialog,
)
from PyQt6.QtCore import QFileSystemWatcher, QMimeData

from core.input_parser import parse_inputs, group_by_directory
from core.engine_detector import (
    can_compile as _can_compile,
    detect_root as _detect_root,
    can_compile_from_content as _can_compile_content,
    detect_root_from_head as _detect_root_head,
)
from core.log import get_logger
# Taranmayacak klasörler TEK KAYNAKTAN. Aynı küme üç yerde kullanılıyor
# (ağaç çizimi, Ctrl+P hızlı açma, Ctrl+Shift+F projede ara); kopyalanınca
# sürükleniyor — bu depoda paketleme tanımlarında bilfiil yaşandı.
from core.project_search import SKIP_DIRS as _SKIP_DIRS
from core import fs_ops
from PyQt6.QtCore import QCoreApplication

# Ağaç çiziminde inilen en derin seviye (bu dosyaya özgü)
_MAX_DEPTH = 5

_ = lambda s: QCoreApplication.translate("FileTree", s)
_logger = get_logger("file_tree")

# Derlenebilir/doğrudan ilgili dosyalar
_EXTENSIONS = {".tex", ".cls", ".sty", ".bib"}
# Editörde açılabilir dosyalar
_EDITABLE = {".tex", ".cls", ".sty", ".bib"}
# Gizlenecek dosya uzantıları (build artifact, geçici)
_HIDDEN_EXT = {".pdf", ".log", ".aux", ".toc", ".bbl", ".bcf", ".blg", ".fdb_latexmk", ".fls", ".synctex.gz", ".gz", ".out", ".run.xml", ".idx", ".ilg", ".ind", ".lof", ".lot", ".nav", ".snm", ".vrb"}


def _dosya_gizli_mi(ad: str, dizin: str, kok: str, tex_adlari: set) -> bool:
    """Bu dosya ağaçta gizlensin mi.

    `.pdf` DIŞINDAKİ uzantılar her zaman gizli: .aux/.log/.toc gibi dosyaların
    tek kaynağı derleme.

    `.pdf` ÇİFT ANLAMLI ve tek kural ikisini ayırt etmiyordu:
      - `ana.tex` yanındaki `ana.pdf`  -> derleme çıktısı, gizlenmeli
      - `Figures/Sample.pdf`           -> vektörel ŞEKİL, kaynak dosya

    İkincisi de gizlendiği için tez yazarı kendi şekillerini ağaçta hiç
    göremiyordu. Üstelik uygulama ağaçtan editöre sürükle-bırakta `.pdf`
    için `\\includegraphics` bloğu üretiyor (main_window._handle_dropped_urls),
    yani özellik yazılmış ama kullanılamıyordu.

    AYRIM (39 şablonun tamamında ölçüldü, 84 dosyanın 84'ü doğru tarafta):
      1. Aynı klasörde aynı adlı bir `.tex` varsa -> çıktı. Kesin bilgi.
      2. Dosya proje KÖKÜNDEyse -> çıktı. Kökteki 61 PDF'in hepsi
         `main_pdflatex.pdf`, `Sample.fallback.pdf` gibi çıktılardı.
      3. Alt klasördeyse -> kaynak. 23 dosyanın hepsi Figures/logo/figs/
         Definitions içindeydi, biri bile çıktı değildi.

    2. madde sezgi, kesin bilgi değil: bölümlerini ayrı derleyip PDF'i alt
    klasöra koyan biri o çıktıyı ağaçta görür. Şablonların hiçbirinde olmuyor.

    Kök PDF'lerin gizli kalması ayrıca ŞART: `_collect_files` yenileme anlık
    görüntüsünü buradan üretiyor ve derleme her koştuğunda kökteki PDF
    değişiyor. Görünür olsalardı her derleme ağacı baştan taratırdı.
    """
    ext = os.path.splitext(ad)[1].lower()
    if ext != ".pdf":
        return ext in _HIDDEN_EXT
    if os.path.splitext(ad)[0] in tex_adlari:
        return True
    return os.path.normpath(dizin) == os.path.normpath(kok)


def _tex_adlari(girdiler) -> set:
    """Bir klasördeki .tex dosyalarının uzantısız adları."""
    return {os.path.splitext(a)[0] for a in girdiler if a.lower().endswith(".tex")}


class _DragTree(QTreeWidget):
    """Dosya yollarını URL olarak taşıyan sürüklenebilir ağaç."""

    def mimeData(self, items):
        mime = QMimeData()
        urls = []
        for item in items:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path and os.path.isfile(path):
                urls.append(QUrl.fromLocalFile(path))
        mime.setUrls(urls)
        return mime


class FileTree(QWidget):
    file_open_requested = pyqtSignal(str)
    compile_requested = pyqtSignal(str)
    # Kök GERÇEKTEN değiştiğinde (aynı klasör yeniden seçilince DEĞİL).
    # Köke bağlı her şey bayatlar: proje araması sonuçları eski klasörün
    # dosyalarını gösteriyordu ve tıklanınca proje dışına götürüyordu.
    root_changed = pyqtSignal(str)
    # (eski_yol, yeni_yol): dosya ağacından yeniden adlandırma. Dosya açıksa
    # sekmenin de takip etmesi gerekiyor: eski yola bağlı kalan bir sekme
    # Ctrl+S'te silinmiş adı yeniden yaratır ve kullanıcı iki dosyayla kalır.
    file_renamed = pyqtSignal(str, str)

    def __init__(self, parent=None, *, theme: dict = None):
        super().__init__(parent)
        self._root = ""
        self._theme = theme or {}
        self._setup_ui()
        self._setup_autorefresh()
        # Derlenebilirlik denetimi (her .tex için tam dosya okuma +
        # strip_comments) tarama sırasında senkron yapılırsa büyük klasörlerde
        # arayüz saniyelerce kilitlenir (WSL /mnt_c'de dosya açma başına
        # ~5-15 ms). Denetimler event loop'a küçük gruplar halinde iade
        # edilir; yeşil renkler kademeli dolar.
        self._pending_checks: list[tuple[QTreeWidgetItem, str]] = []
        self._check_timer = QTimer(self)
        self._check_timer.setInterval(30)
        self._check_timer.timeout.connect(self._process_pending_checks)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        t = self._theme

        # Üst bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(8, 8, 8, 4)
        lbl = QLabel(_("DOSYALAR"))
        top_bar.addWidget(lbl)

        self._btn_refresh = QPushButton(_("Yenile"))
        self._btn_refresh.setFixedHeight(26)
        self._btn_refresh.clicked.connect(self.refresh)
        top_bar.addStretch()
        top_bar.addWidget(self._btn_refresh)

        bar_widget = QWidget()
        bar_widget.setLayout(top_bar)
        layout.addWidget(bar_widget)
        self._bar_widget = bar_widget

        # Klasör yolu
        self._root_label = QLabel("")
        self._root_label.setWordWrap(True)
        layout.addWidget(self._root_label)

        # Ağaç
        self._tree = _DragTree()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._title_label = lbl

        layout.addWidget(self._tree)

        # Bağlantılı dosyalar bölümü
        self._input_header = QLabel(_(" BAĞLANTILI DOSYALAR"))
        self._input_header.hide()
        layout.addWidget(self._input_header)

        self._input_tree = _DragTree()
        self._input_tree.setHeaderHidden(True)
        self._input_tree.setAnimated(True)
        self._input_tree.setDragEnabled(True)
        self._input_tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self._input_tree.itemDoubleClicked.connect(self._on_double_click)
        self._input_tree.hide()
        layout.addWidget(self._input_tree)

        self.setMinimumWidth(150)
        self.setMaximumWidth(300)

        # Stiller TEK kaynaktan: kurulum kendi kopyasını kurmuyor,
        # apply_theme'i çağırıyor. Eskiden yedi blok burada ve
        # apply_theme'de birebir tekrarlanıyordu; tema değiştirilince
        # ikisini birden güncellemek gerekiyordu.
        self.apply_theme(t)

    def _setup_autorefresh(self):
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_fs_changed)
        self._last_snapshot = set()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_deferred_refresh)
        self._pending_refresh = False

    def set_root(self, path: str):
        """Ağacın kökünü değiştir. Kök zaten aynıysa yeniden TARAMAZ.

        Açılışta iki kez çağrılabiliyor: `_restore_state()` kayıtlı kökü
        kuruyor, hemen ardından komut satırından/"Birlikte Aç"tan bir dosya
        geldiyse `main_window` onun dizinini kök yapıyor. İkisi genellikle
        AYNI dizin — o hâlde ikinci çağrı ağacı boşaltıp baştan tarıyor ve
        her .tex için `_can_compile` denetim kuyruğunu ikinci kez dolduruyordu.
        Kökü gerçekten değiştiren çağrılar etkilenmez; yenileme isteyenler
        zaten `refresh()` çağırıyor (dosya izleyici, elle yenileme).

        "Klasör Aç" ile AYNI klasör seçilirse artık ağaç yeniden taranmaz.
        Bu bilinçli: ağaç zaten o klasörü gösteriyor ve dosya izleyici +
        `_do_deferred_refresh` onu güncel tutuyor. (Sekmelerin kapanması,
        PDF'in temizlenmesi gibi diğer "Klasör Aç" etkileri değişmedi.)
        """
        yeni = os.path.normpath(path)
        if yeni == self._root:
            return
        self._root = yeni
        self._root_label.setText(self._root)
        self.refresh()
        self.root_changed.emit(self._root)

    def update_input_tree(self, file_path: str, content: str):
        """Aktif dosyanın \\input/\\include bağımlılıklarını göster."""
        self._input_tree.clear()

        if not file_path or not file_path.endswith('.tex'):
            self._input_header.hide()
            self._input_tree.hide()
            return

        refs = parse_inputs(content, os.path.dirname(file_path))
        refs = group_by_directory(refs, os.path.dirname(file_path))
        if not refs:
            self._input_header.hide()
            self._input_tree.hide()
            return

        self._populate_input_tree(refs, self._input_tree.invisibleRootItem())
        self._input_tree.expandAll()
        self._input_header.show()
        self._input_tree.show()

    def _input_ref_ok(self, path: str) -> bool:
        """Bağlantılı dosya derlenebilir mi (ya da % !TEX root'a mı yönlendirilmiş)?

        Sekme degistiginde her baglanti icin cagriliyor; eskiden can_compile
        (tam okuma) + detect_root (30 satir okuma) iki ayri acilis yapiyordu.
        Simdi dosya TEK okusla okunup iki denetim de icerikten yapiliyor.
        """
        if not path.endswith(".tex"):
            return False
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return False
        if _can_compile_content(content, os.path.basename(path))[0]:
            return True
        return _detect_root_head(content, path) != ""

    def _populate_input_tree(self, refs, parent):
        for ref in refs:
            if ref.get('is_dir'):
                item = QTreeWidgetItem(parent, [f"📁 {ref['name']}"])
                item.setData(0, Qt.ItemDataRole.UserRole, None)
                item.setForeground(0, QColor(self._theme["sem_folder"]))
            else:
                ok = self._input_ref_ok(ref['path'])
                item = QTreeWidgetItem(parent, [f"📎 {ref['name']}"])
                item.setData(0, Qt.ItemDataRole.UserRole, ref['path'])
                if ok:
                    item.setForeground(0, QColor(self._theme["sem_compilable"]))
                else:
                    item.setForeground(0, QColor(self._theme["fg_muted"]))
            if ref.get('children'):
                self._populate_input_tree(ref['children'], item)

    def refresh(self):
        if not self._root:
            return
        # Bekleyen kademeli denetimler eski (silinecek) öğelere bağlı — temizle
        self._pending_checks.clear()
        self._check_timer.stop()
        self._update_watcher()
        self._tree.clear()
        self._input_tree.clear()
        self._input_header.hide()
        self._input_tree.hide()
        self._scan_dir()
        if self._pending_checks:
            self._check_timer.start()
        self._save_snapshot()

    def _process_pending_checks(self):
        """Bir grup .tex dosyasının derlenebilirliğini denetle (UI thread).

        '% !TEX root' magic comment'ı olan alt dosyalar da derlenebilir sayılır
        (derleme köke yönlendirilir); renkleri yeşil olur.
        """
        batch = self._pending_checks[:5]
        del self._pending_checks[:5]
        for item, path in batch:
            try:
                ok = _can_compile(path)[0] or _detect_root(path) != ""
            except Exception as e:
                # Denetim düşerse dosya "derlenemez" renginde kalır; sebebi
                # görünmezdi. exc_info YOK: bu kod her dosya için koşuyor,
                # sistematik bir hatada yüzlerce traceback log'u doldururdu —
                # yol + hata mesajı teşhis için yeterli.
                _logger.warning("Derlenebilirlik denetimi başarısız: %s — %s", path, e)
                ok = False
            if ok:
                item.setForeground(0, QColor(self._theme["sem_compilable"]))
        if self._pending_checks:
            self._check_timer.start()
        else:
            self._check_timer.stop()

    def _update_watcher(self):
        """Watcher'ı root ve alt klasörleri izleyecek şekilde güncelle."""
        old_dirs = set(self._watcher.directories())
        new_dirs = self._collect_watched_dirs(self._root)
        for d in old_dirs - new_dirs:
            self._watcher.removePath(d)
        for d in new_dirs - old_dirs:
            self._watcher.addPath(d)

    def _collect_watched_dirs(self, dir_path, depth=0):
        """İzlenecek klasörleri recursive topla."""
        dirs = set()
        if depth > _MAX_DEPTH:
            return dirs
        try:
            entries = os.listdir(dir_path)
        except (PermissionError, OSError) as e:
            _logger.warning("Klasör listelenemedi (watch): %s — %s", dir_path, e)
            return dirs
        dirs.add(dir_path)
        for name in entries:
            if name.startswith('.'):
                continue
            full = os.path.join(dir_path, name)
            if os.path.isdir(full) and name not in _SKIP_DIRS:
                dirs |= self._collect_watched_dirs(full, depth + 1)
        return dirs

    def _on_fs_changed(self, path: str):
        """Dosya sistemi değişikliği algılandı — debounce ile yenile."""
        if not self._pending_refresh:
            self._pending_refresh = True
            self._refresh_timer.start(300)

    def _do_deferred_refresh(self):
        self._pending_refresh = False
        if not self._root:
            return
        current = self._collect_files(self._root)
        if current != self._last_snapshot:
            self.refresh()

    def _scan_dir(self):
        """Kök ve alt klasörlerdeki dosyaları recursive listele."""
        self._scan_recursive(self._root, self._tree.invisibleRootItem(), depth=0)

    def _scan_recursive(self, dir_path, parent_item, depth: int):
        if depth > _MAX_DEPTH:
            return
        try:
            entries = sorted(os.listdir(dir_path))
        except (PermissionError, OSError) as e:
            _logger.warning("Klasör taranamadı (tree): %s — %s", dir_path, e)
            return

        # Aynı klasördeki .tex adları: `ana.pdf`i `ana.tex`in çıktısı diye
        # ayırt etmek için gerekiyor (bkz. _dosya_gizli_mi).
        tex_adlari = _tex_adlari(entries)

        for name in entries:
            if name.startswith('.'):
                continue
            full = os.path.join(dir_path, name)
            if os.path.isdir(full):
                if name in _SKIP_DIRS:
                    continue
                folder_item = QTreeWidgetItem([f"📁 {name}"])
                # Klasörün de yolu taşınıyor: bağlam menüsündeki "Yeni Dosya /
                # Yeni Klasör / Yeniden Adlandır" hangi klasörde çalışacağını
                # buradan öğreniyor. Eskiden None'dı ve klasöre sağ tıklamak
                # hiçbir menü açmıyordu. Yolu okuyan diğer iki yer (çift tık,
                # sürükleme) zaten `os.path.isfile` ile eliyor.
                folder_item.setData(0, Qt.ItemDataRole.UserRole, full)
                folder_item.setForeground(0, QColor(self._theme["sem_folder"]))
                self._scan_recursive(full, folder_item, depth + 1)
                # HER klasör gösteriliyor. Eskiden koşul `childCount() > 0`
                # idi, yani "görünür dosyası olmayan klasörü gizle". İki şeyi
                # birden bozuyordu:
                #   - Menüden yaratılan klasör HİÇ görünmüyordu. Boş olduğu
                #     için ağaca girmiyor, girmediği için içine dosya
                #     eklenemiyor; kullanıcı Explorer'a gitmek zorundaydı.
                #   - Şablonlarda ölçüldü (39 şablon, 56 klasör): gizlenen 7
                #     klasörün beşi `Figures` ve `logo` gibi KAYNAK klasörleri.
                #     İçlerindeki .pdf'ler _HIDDEN_EXT'te olduğu için klasör
                #     "dosyasız" sayılıyordu; tez yazarı kendi şekil klasörünü
                #     göremiyordu.
                parent_item.addChild(folder_item)
            elif os.path.isfile(full):
                ext = os.path.splitext(name)[1].lower()
                if _dosya_gizli_mi(name, dir_path, self._root, tex_adlari):
                    continue
                editable = ext in _EDITABLE
                icon = "📄" if ext == ".tex" else "⚙" if ext in _EDITABLE else "🖼"
                item = QTreeWidgetItem(parent_item, [f"{icon} {name}"])
                item.setData(0, Qt.ItemDataRole.UserRole, full)
                item.setData(0, Qt.ItemDataRole.UserRole + 1, editable)
                if editable:
                    item.setForeground(0, QColor(self._theme["fg_muted"]))
                    if ext == ".tex":
                        # Derlenebilirlik rengi kademeli denetimle sonradan gelir
                        self._pending_checks.append((item, full))
                else:
                    item.setForeground(0, QColor(self._theme["fg_dim"]))

    def _save_snapshot(self):
        self._last_snapshot = self._collect_files(self._root)

    def _collect_files(self, dir_path, depth=0):
        # Ağaç çizimiyle aynı kurallar: _SKIP_DIRS'e inilmez, _MAX_DEPTH'i
        # aşan derinlik taranmaz. (Snapshot/refresh yürüyüşü her FS olayında
        # çalıştığından node_modules/venv'e inmek WSL'de arayüzü kilitlerdi.)
        files = set()
        if depth > _MAX_DEPTH:
            return files
        try:
            girdiler = os.listdir(dir_path)
            # Görünürlük kuralı ağaç çizimiyle AYNI olmak zorunda: burası
            # "ağaçta bir değişiklik var mı" anlık görüntüsü. Ayrışırsa yeni
            # eklenen bir şekil ağaca kendiliğinden düşmez (ya da tersi:
            # kökteki PDF her derlemede değişip ağacı boşuna taratır).
            tex_adlari = _tex_adlari(girdiler)
            for entry in girdiler:
                if entry.startswith('.') or entry in _SKIP_DIRS:
                    continue
                full = os.path.join(dir_path, entry)
                if os.path.isdir(full):
                    files |= self._collect_files(full, depth + 1)
                elif os.path.isfile(full):
                    if not _dosya_gizli_mi(entry, dir_path, self._root, tex_adlari):
                        files.add(full)
        except (PermissionError, OSError) as e:
            _logger.warning("Dosya toplama başarısız: %s — %s", dir_path, e)
        return files

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        editable = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if path and os.path.isfile(path) and editable:
            self.file_open_requested.emit(path)

    def _on_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        path = item.data(0, Qt.ItemDataRole.UserRole) if item else ""
        # Boş alana sağ tık = kök klasör. "Projede ilk dosyayı nasıl
        # yaratacağım" sorusunun cevabı: ağaç boşken tıklanacak öğe yok.
        if not path:
            path = self._root
        if not path:
            return

        # Ağaç bayat olabilir (dosya dışarıdan silinmiş). Diske sor.
        klasor_mu = os.path.isdir(path)
        if not klasor_mu and not os.path.isfile(path):
            return

        menu = QMenu(self)
        t = self._theme
        menu.setStyleSheet(
            f"QMenu {{ background: {t['bg_toolbar']}; color: {t['fg_primary']}; border: 1px solid {t['border_separator']}; padding: 4px; }}"
            f"QMenu::item {{ padding: 5px 24px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background: {t['bg_pressed']}; }}"
            f"QMenu::separator {{ height: 1px; background: {t['border_separator']}; margin: 4px 8px; }}"
        )

        ext = "" if klasor_mu else os.path.splitext(path)[1].lower()
        editable = ext in _EDITABLE

        # Derle — derlenebilir .tex için (alt dosyaysa % !TEX root kökü derlenir)
        act_compile = None
        if ext == ".tex" and editable:
            if _can_compile(path)[0] or _detect_root(path) != "":
                act_compile = menu.addAction(_("▶ Derle"))

        act_open = None
        if editable:
            act_open = menu.addAction(_("📂 Düzenle"))

        if act_compile or act_open:
            menu.addSeparator()

        # Yeni öğeler: klasöre tıklandıysa İÇİNE, dosyaya tıklandıysa YANINA.
        # (VS Code'un davranışı; kullanıcı kardeş dosya yaratmak için üstteki
        # klasörü aramak zorunda kalmıyor.)
        hedef_dizin = path if klasor_mu else os.path.dirname(path)
        # Üç nokta bilinçli: Dosya menüsündeki "Yeni Dosya" (Ctrl+N) KAYDEDİLMEMİŞ
        # bir sekme açıyor, buradaki ise diske gerçek bir dosya yaratıyor. Üç
        # nokta "önce soracak" demek ve ikisini birbirinden ayırıyor.
        act_new_file = menu.addAction(_("📄 Yeni Dosya..."))
        act_new_dir = menu.addAction(_("📁 Yeni Klasör..."))

        menu.addSeparator()

        # Klasörde aç
        act_folder = menu.addAction(_("📂 Klasörde Aç"))

        # Kökün kendisi ağacın dayanağı: buradan adı değiştirilemez ve
        # silinemez (klasörü değiştirmek "Klasör Aç" ile yapılıyor).
        kok_mu = os.path.normpath(path) == os.path.normpath(self._root or "")
        act_rename = None
        act_delete = None
        if not kok_mu:
            act_rename = menu.addAction(_("✏ Yeniden Adlandır"))
            menu.addSeparator()
            act_delete = menu.addAction(_("🗑 Sil"))

        action = menu.exec(self._tree.mapToGlobal(pos))

        if action is None:
            return
        if action == act_compile:
            self.compile_requested.emit(path)
        elif action == act_open:
            self.file_open_requested.emit(path)
        elif action == act_new_file:
            self._yeni_oge(hedef_dizin, klasor=False)
        elif action == act_new_dir:
            self._yeni_oge(hedef_dizin, klasor=True)
        elif action == act_folder:
            self._open_in_explorer(path)
        elif action == act_rename:
            self._yeniden_adlandir(path)
        elif action == act_delete:
            self._delete_file(path)

    def _open_in_explorer(self, path: str):
        """Dosyanın bulunduğu klasörü platforma göre aç."""
        import subprocess
        import sys
        if sys.platform == "win32":
            subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    # ------------------------------------------------------------------
    # Yeni dosya / yeni klasör / yeniden adlandır
    # ------------------------------------------------------------------

    @staticmethod
    def _ad_hata_metni(kod: str) -> str:
        """Gerekçe kodunu kullanıcı diline çevir.

        Sözlük fonksiyonun İÇİNDE kuruluyor: modül düzeyinde kurulsaydı
        `_()` çağrıları import anında, yani çevirmen yüklenmeden önce
        koşardı ve İngilizce arayüzde Türkçe kalırdı (aynı hata bu depoda
        `error_hints` şablonlarında bilfiil yaşandı).
        """
        return {
            fs_ops.BOS: _("Ad boş olamaz."),
            fs_ops.NOKTA_ADI: _("'.' ve '..' ad olarak kullanılamaz."),
            fs_ops.YASAK_KARAKTER: _(
                "Ad şu karakterleri içeremez:  < > : \" / \\ | ? *"),
            fs_ops.SONU_NOKTA_BOSLUK: _(
                "Ad nokta veya boşlukla bitemez: Windows bunları sessizce "
                "siler ve dosyayı adıyla bulamazsınız."),
            fs_ops.AYGIT_ADI: _(
                "Bu ad Windows'ta aygıt adı olarak ayrılmış (CON, PRN, AUX, "
                "NUL, COM1-9, LPT1-9); uzantı eklense de kullanılamaz."),
            fs_ops.COK_UZUN: _("Ad çok uzun (en fazla 255 karakter)."),
        }.get(kod, _("Ad geçersiz."))

    def _ad_iste(self, baslik: str, etiket: str, mevcut: str = "") -> str:
        """Geçerli bir ad alınana kadar sor. İptal edilirse "" döner.

        Hata çıkınca kutu yazılanı KORUYARAK yeniden açılıyor: uzun bir adın
        tek karakteri yüzünden baştan yazdırmak gereksiz.
        """
        ad = mevcut
        while True:
            ad, ok = QInputDialog.getText(self, baslik, etiket, text=ad)
            if not ok:
                return ""
            # Görünmez karakter yüzünden hata vermek anlamsız; baştaki/sondaki
            # boşluk kırpılıyor. Sondaki NOKTA kırpılmıyor: o görünür bir
            # karakter ve kullanıcının kastı olabilir, uyarmak doğrusu.
            ad = ad.strip()
            hata = fs_ops.ad_hatasi(ad)
            if not hata:
                return ad
            QMessageBox.warning(self, baslik, self._ad_hata_metni(hata))

    def _yeni_oge(self, dizin: str, *, klasor: bool):
        baslik = _("Yeni Klasör") if klasor else _("Yeni Dosya")
        etiket = _("Klasör adı:") if klasor else _("Dosya adı (örn. bolum2.tex):")
        ad = self._ad_iste(baslik, etiket)
        if not ad:
            return
        try:
            yol = (fs_ops.yeni_klasor(dizin, ad) if klasor
                   else fs_ops.yeni_dosya(dizin, ad))
        except FileExistsError:
            QMessageBox.warning(self, baslik, _("'{name}' zaten var.").format(name=ad))
            return
        except OSError as e:
            _logger.error("Oluşturulamadı: %s/%s", dizin, ad, exc_info=True)
            QMessageBox.warning(self, baslik, _("Oluşturulamadı: {e}").format(e=e))
            return

        self.refresh()
        # Yeni .tex/.bib dosyası hemen düzenlenebilsin: kullanıcı yaratıp
        # sonra ağaçta arayıp çift tıklamak zorunda kalmıyor.
        if not klasor and os.path.splitext(ad)[1].lower() in _EDITABLE:
            self.file_open_requested.emit(yol)

    def _yeniden_adlandir(self, path: str):
        baslik = _("Yeniden Adlandır")
        eski_ad = os.path.basename(path)
        yeni_ad = self._ad_iste(baslik, _("Yeni ad:"), eski_ad)
        if not yeni_ad or yeni_ad == eski_ad:
            return
        try:
            yeni_yol = fs_ops.yeniden_adlandir(path, yeni_ad)
        except FileExistsError:
            QMessageBox.warning(self, baslik,
                                _("'{name}' zaten var.").format(name=yeni_ad))
            return
        except OSError as e:
            _logger.error("Yeniden adlandırılamadı: %s → %s", path, yeni_ad, exc_info=True)
            QMessageBox.warning(self, baslik,
                                _("Yeniden adlandırılamadı: {e}").format(e=e))
            return

        # Sinyal ÖNCE: açık sekme yeni yola bağlansın, sonra ağaç tazelensin.
        self.file_renamed.emit(path, yeni_yol)
        self.refresh()

    def _delete_file(self, path: str):
        """Dosyayı veya klasörü geri dönüşüm kutusuna gönder."""
        name = os.path.basename(path)
        klasor_mu = os.path.isdir(path)
        msg = QMessageBox(self)
        msg.setWindowTitle(_("Sil"))
        soru = (_("'{name}' klasörünü ve İÇİNDEKİLERİ silmek istediğinize emin "
                  "misiniz?\n(Geri dönüşüm kutusuna taşınır)") if klasor_mu else
                _("'{name}' dosyasını silmek istediğinize emin misiniz?\n"
                  "(Geri dönüşüm kutusuna taşınır)"))
        msg.setText(soru.format(name=name))
        msg.setIcon(QMessageBox.Icon.Question)
        btn_yes = msg.addButton(_("Evet"), QMessageBox.ButtonRole.YesRole)
        msg.addButton(_("Hayır"), QMessageBox.ButtonRole.NoRole)
        msg.exec()
        if msg.clickedButton() == btn_yes:
            try:
                send2trash.send2trash(path)
                self.refresh()
            except Exception as e:
                _logger.error("Silinemedi (send2trash): %s", path, exc_info=True)
                QMessageBox.warning(self, _("Hata"), _("Silinemedi: {e}").format(e=e))

    def apply_theme(self, t: dict):
        self._theme = t
        self._bar_widget.setStyleSheet(f"background: {t['bg_secondary']};")
        self._title_label.setStyleSheet(
            f"color: {t['fg_muted']}; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        )
        self._btn_refresh.setStyleSheet(
            f"QPushButton {{ background: {t['bg_button']}; color: {t['fg_primary']}; border: 1px solid {t['border_input']}; "
            f"border-radius: 4px; font-size: 11px; padding: 2px 12px; }}"
            f"QPushButton:hover {{ background: {t['bg_hover']}; border: 1px solid {t['accent']}; }}"
            f"QPushButton:pressed {{ background: {t['bg_pressed']}; }}"
        )
        self._root_label.setStyleSheet(
            f"color: {t['fg_dim']}; font-size: 10px; padding: 2px 10px; "
            f"background: {t['bg_secondary']}; border-bottom: 1px solid {t['border_normal']};"
        )
        tree_ss = (
            f"QTreeWidget {{ background: {t['bg_secondary']}; color: {t['fg_primary']}; border: none; font-size: 12px; }}"
            f"QTreeWidget::item {{ padding: 3px 4px; }}"
            f"QTreeWidget::item:hover {{ background: {t['bg_hover']}; }}"
            f"QTreeWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )
        self._tree.setStyleSheet(tree_ss)
        self._input_tree.setStyleSheet(tree_ss)
        self._input_header.setStyleSheet(
            f"color: {t['fg_muted']}; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
            f"background: {t['bg_secondary']}; padding: 6px 8px 4px 8px; border-top: 1px solid {t['border_normal']};"
        )
        if self._root:
            self.refresh()
