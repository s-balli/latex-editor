"""Proje dosya ağacı — .tex/.cls/.sty/.bib dosyaları, alt klasör desteği."""

# Taranmayacak klasörler (büyük / ilgisiz)
_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".svn",
    "build", "dist", ".venv", "venv", ".env",
    ".mypy_cache", ".pytest_cache",
}
_MAX_DEPTH = 5

import os
import send2trash

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QColor, QDrag
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QMenu, QMessageBox,
)
from PyQt6.QtCore import QFileSystemWatcher, QMimeData

from core.input_parser import parse_inputs, group_by_directory
from core.engine_detector import can_compile as _can_compile
from core.log import get_logger
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("FileTree", s)
_logger = get_logger("file_tree")

# Derlenebilir/doğrudan ilgili dosyalar
_EXTENSIONS = {".tex", ".cls", ".sty", ".bib"}
# Editörde açılabilir dosyalar
_EDITABLE = {".tex", ".cls", ".sty", ".bib"}
# Gizlenecek dosya uzantıları (build artifact, geçici)
_HIDDEN_EXT = {".pdf", ".log", ".aux", ".toc", ".bbl", ".bcf", ".blg", ".fdb_latexmk", ".fls", ".synctex.gz", ".gz", ".out", ".run.xml", ".idx", ".ilg", ".ind", ".lof", ".lot", ".nav", ".snm", ".vrb"}


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

    def __init__(self, parent=None, *, theme: dict = None):
        super().__init__(parent)
        self._root = ""
        self._theme = theme or {}
        self._setup_ui()
        self._setup_autorefresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        t = self._theme

        # Üst bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(8, 8, 8, 4)
        lbl = QLabel(_("DOSYALAR"))
        lbl.setStyleSheet(f"color: {t['fg_muted']}; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        top_bar.addWidget(lbl)

        self._btn_refresh = QPushButton(_("Yenile"))
        self._btn_refresh.setFixedHeight(26)
        self._btn_refresh.clicked.connect(self.refresh)
        self._btn_refresh.setStyleSheet(
            f"QPushButton {{ background: {t['bg_button']}; color: {t['fg_primary']}; border: 1px solid {t['border_input']}; "
            f"border-radius: 4px; font-size: 11px; padding: 2px 12px; }}"
            f"QPushButton:hover {{ background: {t['bg_hover']}; border: 1px solid {t['accent']}; }}"
            f"QPushButton:pressed {{ background: {t['bg_pressed']}; }}"
        )
        top_bar.addStretch()
        top_bar.addWidget(self._btn_refresh)

        bar_widget = QWidget()
        bar_widget.setStyleSheet(f"background: {t['bg_secondary']};")
        bar_widget.setLayout(top_bar)
        layout.addWidget(bar_widget)
        self._bar_widget = bar_widget

        # Klasör yolu
        self._root_label = QLabel("")
        self._root_label.setStyleSheet(
            f"color: {t['fg_dim']}; font-size: 10px; padding: 2px 10px; "
            f"background: {t['bg_secondary']}; border-bottom: 1px solid {t['border_normal']};"
        )
        self._root_label.setWordWrap(True)
        layout.addWidget(self._root_label)

        tree_ss = (
            f"QTreeWidget {{ background: {t['bg_secondary']}; color: {t['fg_primary']}; border: none; font-size: 12px; }}"
            f"QTreeWidget::item {{ padding: 3px 4px; }}"
            f"QTreeWidget::item:hover {{ background: {t['bg_hover']}; }}"
            f"QTreeWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )

        # Ağaç
        self._tree = _DragTree()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.setStyleSheet(tree_ss)
        self._title_label = lbl

        layout.addWidget(self._tree)

        # Bağlantılı dosyalar bölümü
        self._input_header = QLabel(_(" BAĞLANTILI DOSYALAR"))
        self._input_header.setStyleSheet(
            f"color: {t['fg_muted']}; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
            f"background: {t['bg_secondary']}; padding: 6px 8px 4px 8px; border-top: 1px solid {t['border_normal']};"
        )
        self._input_header.hide()
        layout.addWidget(self._input_header)

        self._input_tree = _DragTree()
        self._input_tree.setHeaderHidden(True)
        self._input_tree.setAnimated(True)
        self._input_tree.setDragEnabled(True)
        self._input_tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        self._input_tree.itemDoubleClicked.connect(self._on_double_click)
        self._input_tree.setStyleSheet(tree_ss)
        self._input_tree.hide()
        layout.addWidget(self._input_tree)

        self.setMinimumWidth(150)
        self.setMaximumWidth(300)

    def _setup_autorefresh(self):
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_fs_changed)
        self._last_snapshot = set()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_deferred_refresh)
        self._pending_refresh = False

    def set_root(self, path: str):
        self._root = os.path.normpath(path)
        self._root_label.setText(self._root)
        self.refresh()

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

    def _populate_input_tree(self, refs, parent):
        for ref in refs:
            if ref.get('is_dir'):
                item = QTreeWidgetItem(parent, [f"📁 {ref['name']}"])
                item.setData(0, Qt.ItemDataRole.UserRole, None)
                item.setForeground(0, QColor(self._theme["sem_folder"]))
            else:
                ok, _ = _can_compile(ref['path'])
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
        self._update_watcher()
        self._tree.clear()
        self._input_tree.clear()
        self._input_header.hide()
        self._input_tree.hide()
        self._scan_dir()
        self._save_snapshot()

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

        for name in entries:
            if name.startswith('.'):
                continue
            full = os.path.join(dir_path, name)
            if os.path.isdir(full):
                if name in _SKIP_DIRS:
                    continue
                # Önce alt klasörü tara; içinde dosya yoksa ağaçta gösterme
                folder_item = QTreeWidgetItem([f"📁 {name}"])
                folder_item.setData(0, Qt.ItemDataRole.UserRole, None)
                folder_item.setForeground(0, QColor(self._theme["sem_folder"]))
                self._scan_recursive(full, folder_item, depth + 1)
                if folder_item.childCount() > 0:
                    parent_item.addChild(folder_item)
            elif os.path.isfile(full):
                ext = os.path.splitext(name)[1].lower()
                if ext in _HIDDEN_EXT:
                    continue
                ok, _ = _can_compile(full)
                editable = ext in _EDITABLE
                icon = "📄" if ext == ".tex" else "⚙" if ext in _EDITABLE else "🖼"
                item = QTreeWidgetItem(parent_item, [f"{icon} {name}"])
                item.setData(0, Qt.ItemDataRole.UserRole, full)
                item.setData(0, Qt.ItemDataRole.UserRole + 1, editable)
                if ok:
                    item.setForeground(0, QColor(self._theme["sem_compilable"]))
                elif editable:
                    item.setForeground(0, QColor(self._theme["fg_muted"]))
                else:
                    item.setForeground(0, QColor(self._theme["fg_dim"]))

    def _save_snapshot(self):
        self._last_snapshot = self._collect_files(self._root)

    def _collect_files(self, dir_path):
        files = set()
        try:
            for entry in os.listdir(dir_path):
                if entry.startswith('.'):
                    continue
                full = os.path.join(dir_path, entry)
                if os.path.isdir(full):
                    files |= self._collect_files(full)
                elif os.path.isfile(full):
                    ext = os.path.splitext(entry)[1].lower()
                    if ext not in _HIDDEN_EXT:
                        files.add(full)
        except (PermissionError, OSError) as e:
            _logger.warning("Dosya toplama başarısız: %s — %s", dir_path, e)
        return files

    def _check_refresh(self):
        if not self._root:
            return
        current = self._collect_files(self._root)
        if current != self._last_snapshot:
            self.refresh()

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        editable = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if path and os.path.isfile(path) and editable:
            self.file_open_requested.emit(path)

    def _on_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path or not os.path.isfile(path):
            return

        menu = QMenu(self)
        t = self._theme
        menu.setStyleSheet(
            f"QMenu {{ background: {t['bg_toolbar']}; color: {t['fg_primary']}; border: 1px solid {t['border_separator']}; padding: 4px; }}"
            f"QMenu::item {{ padding: 5px 24px; border-radius: 3px; }}"
            f"QMenu::item:selected {{ background: {t['bg_pressed']}; }}"
            f"QMenu::separator {{ height: 1px; background: {t['border_separator']}; margin: 4px 8px; }}"
        )

        ext = os.path.splitext(path)[1].lower()
        editable = ext in _EDITABLE

        # Derle — sadece derlenebilir .tex için
        act_compile = None
        if ext == ".tex" and editable:
            ok, _ = _can_compile(path)
            if ok:
                act_compile = menu.addAction(_("▶ Derle"))

        act_open = None
        if editable:
            act_open = menu.addAction(_("📂 Düzenle"))

        # Klasörde aç
        act_folder = menu.addAction(_("📁 Klasörde Aç"))

        menu.addSeparator()

        # Sil
        act_delete = menu.addAction(_("🗑 Sil"))

        action = menu.exec(self._tree.mapToGlobal(pos))

        if action == act_compile:
            self.compile_requested.emit(path)
        elif action == act_open:
            self.file_open_requested.emit(path)
        elif action == act_folder:
            self._open_in_explorer(path)
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

    def _delete_file(self, path: str):
        """Dosyayı geri dönüşüm kutusuna gönder."""
        name = os.path.basename(path)
        msg = QMessageBox(self)
        msg.setWindowTitle(_("Sil"))
        msg.setText(_("'{name}' dosyasını silmek istediğinize emin misiniz?\n(Geri dönüşüm kutusuna taşınır)").format(name=name))
        msg.setIcon(QMessageBox.Icon.Question)
        btn_yes = msg.addButton(_("Evet"), QMessageBox.ButtonRole.YesRole)
        msg.addButton(_("Hayır"), QMessageBox.ButtonRole.NoRole)
        msg.exec()
        if msg.clickedButton() == btn_yes:
            try:
                send2trash.send2trash(path)
                self.refresh()
            except Exception as e:
                _logger.error("Dosya silinemedi (send2trash): %s", path, exc_info=True)
                QMessageBox.warning(self, _("Hata"), _("Dosya silinemedi: {e}").format(e=e))

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
