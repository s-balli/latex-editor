"""Derleme çıktı paneli — hatalar, uyarılar, ham log."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTabWidget,
    QListWidget, QListWidgetItem, QPlainTextEdit, QMenu,
)

from core.log_parser import CompileResult
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("OutputPanel", s)


class OutputPanel(QWidget):
    error_clicked = pyqtSignal(str, int)  # file_path, line_number

    def __init__(self, parent=None, *, theme: dict = None):
        super().__init__(parent)
        self._theme = theme or {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        t = self._theme

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {t['border_normal']}; background: {t['bg_primary']}; border-top: 2px solid {t['tab_active_border']}; }}"
            f"QTabBar::tab {{ background: {t['bg_toolbar']}; color: {t['fg_muted']}; padding: 5px 14px;"
            f"border: 1px solid transparent; border-bottom: none;"
            f"border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 1px; }}"
            f"QTabBar::tab:hover {{ color: {t['fg_label']}; background: {t['bg_hover_alt']}; }}"
            f"QTabBar::tab:selected {{ background: {t['bg_primary']}; color: {t['fg_bright']}; border: 1px solid {t['border_normal']}; }}"
        )

        list_base = (
            f"QListWidget {{ background: {t['bg_primary']}; font-family: Consolas, 'DejaVu Sans Mono', Menlo, monospace; font-size: 12px; border: none; }}"
            f"QListWidget::item {{ padding: 4px 6px; border-bottom: 1px solid {t['bg_item_hover']}; }}"
            f"QListWidget::item:hover {{ background: {t['bg_item_hover']}; }}"
            f"QListWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )

        # Hatalar sekmesi
        self._error_list = QListWidget()
        self._error_list.setStyleSheet(f"{list_base} color: {t['sem_error']};")
        self._error_list.itemClicked.connect(self._on_error_click)
        self._error_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._error_list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._error_tab_index = self._tabs.addTab(self._error_list, _("Hatalar"))

        # Uyarılar sekmesi
        self._warn_list = QListWidget()
        self._warn_list.setStyleSheet(f"{list_base} color: {t['sem_warning']};")
        self._warn_list.itemClicked.connect(self._on_warn_click)
        self._warn_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._warn_list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._warn_tab_index = self._tabs.addTab(self._warn_list, _("Uyarılar"))

        # Öneriler sekmesi
        self._suggest_list = QListWidget()
        self._suggest_list.setStyleSheet(f"{list_base} color: {t['sem_suggestion']};")
        self._suggest_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._suggest_list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._suggest_tab_index = self._tabs.addTab(self._suggest_list, _("Öneriler"))

        # Ham log sekmesi
        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setStyleSheet(
            f"QPlainTextEdit {{ background: {t['bg_primary']}; color: {t['fg_primary']}; font-family: Consolas, 'DejaVu Sans Mono', Menlo, monospace; font-size: 11px; border: none; }}"
        )
        self._tabs.addTab(self._log_text, "Log")

        layout.addWidget(self._tabs)
        self.setMaximumHeight(200)

    def clear(self):
        self._error_list.clear()
        self._warn_list.clear()
        self._suggest_list.clear()
        self._log_text.clear()
        self._tabs.setTabText(self._error_tab_index, _("Hatalar"))
        self._tabs.setTabText(self._warn_tab_index, _("Uyarılar"))
        self._tabs.setTabText(self._suggest_tab_index, _("Öneriler"))

    def show_result(self, result: CompileResult):
        self.clear()

        # Hatalar
        for err in result.errors:
            text = _("Satır {n}: {msg}").format(n=err.line_number, msg=err.message) if err.line_number else err.message
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (err.file_path, err.line_number))
            self._error_list.addItem(item)
        self._tabs.setTabText(self._error_tab_index, _("Hatalar ({n})").format(n=len(result.errors)))

        # Uyarılar
        for w in result.warnings:
            line_info = _("Satır {n}: ").format(n=w.line_number) if w.line_number else ""
            text = f"{line_info}[{w.warning_type}] {w.message}" if w.warning_type else f"{line_info}{w.message}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (w.file_path, w.line_number))
            self._warn_list.addItem(item)
        self._tabs.setTabText(self._warn_tab_index, _("Uyarılar ({n})").format(n=len(result.warnings)))

        # Öneriler
        for s in result.suggestions:
            text = s.message
            if s.install_command:
                text += f"\n    {s.install_command}"
            item = QListWidgetItem(text)
            self._suggest_list.addItem(item)
        suggest_count = self._suggest_list.count()
        self._tabs.setTabText(self._suggest_tab_index, _("Öneriler ({n})").format(n=suggest_count))

        # Ham çıktı — etiketleri çevir
        raw = result.raw_output
        for src, dst in self._get_tag_map().items():
            if src != dst:
                raw = raw.replace(src, dst)
        self._log_text.setPlainText(raw)

        # Öncelik: öneriler > hatalar > uyarılar
        if result.suggestions:
            self._tabs.setCurrentIndex(self._suggest_tab_index)
        elif result.errors:
            self._tabs.setCurrentIndex(self._error_tab_index)
        elif result.warnings:
            self._tabs.setCurrentIndex(self._warn_tab_index)

    def show_engine_hint(self, current: str, other: str):
        """Başarısız derlemede motor değiştirme önerisini ekle ve tab'ı aç."""
        hint = QListWidgetItem(
            _("Derleme başarısız oldu. Şu an {current} kullanılıyor.\n    → Araç çubuğundan motoru {other} olarak değiştirip tekrar deneyin.").format(current=current, other=other)
        )
        hint.setForeground(QColor(self._theme["sem_hint"]))
        self._suggest_list.insertItem(0, hint)
        suggest_count = self._suggest_list.count()
        self._tabs.setTabText(self._suggest_tab_index, f"Öneriler ({suggest_count})")
        self._tabs.setCurrentIndex(self._suggest_tab_index)

    def show_cannot_compile(self, msg: str):
        """Derlenemeyecek dosya uyarısını öneriler tab'ında göster."""
        item = QListWidgetItem(msg)
        item.setForeground(QColor(self._theme["sem_hint"]))
        self._suggest_list.addItem(item)
        self._tabs.setTabText(self._suggest_tab_index, _("Öneriler ({n})").format(n=self._suggest_list.count()))
        self._tabs.setCurrentIndex(self._suggest_tab_index)

    # derle.sh ve compiler.py çıktılarındaki Türkçe etiketlerin çeviri tablosu
    _TAG_MAP = None

    @classmethod
    def _get_tag_map(cls):
        if cls._TAG_MAP is None:
            cls._TAG_MAP = {
                "[derleniyor]": "[" + _("derleniyor") + "]",
                "[basarili]": "[" + _("basarili") + "]",
                "[basarisiz]": "[" + _("basarisiz") + "]",
                "[uyari]": "[" + _("uyari") + "]",
                "[hata]": "[" + _("hata") + "]",
                "[bilgi]": "[" + _("bilgi") + "]",
            }
        return cls._TAG_MAP

    def append_output(self, text: str):
        for src, dst in self._get_tag_map().items():
            if src != dst:
                text = text.replace(src, dst)
        cursor = self._log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self._log_text.setTextCursor(cursor)

    def _on_error_click(self, item: QListWidget):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            file_path, line = data
            if line and line > 0:
                self.error_clicked.emit(file_path or "", line)

    def _on_warn_click(self, item: QListWidget):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            file_path, line = data
            if line and line > 0:
                self.error_clicked.emit(file_path or "", line)

    def _on_list_context_menu(self, pos):
        list_widget = self.sender()
        if not isinstance(list_widget, QListWidget):
            return
        item = list_widget.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        copy_action = menu.addAction(_("Kopyala"))
        action = menu.exec(list_widget.mapToGlobal(pos))
        if action == copy_action:
            QApplication.clipboard().setText(item.text())

    def apply_theme(self, t: dict):
        self._theme = t
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {t['border_normal']}; background: {t['bg_primary']}; border-top: 2px solid {t['tab_active_border']}; }}"
            f"QTabBar::tab {{ background: {t['bg_toolbar']}; color: {t['fg_muted']}; padding: 5px 14px;"
            f"border: 1px solid transparent; border-bottom: none;"
            f"border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 1px; }}"
            f"QTabBar::tab:hover {{ color: {t['fg_label']}; background: {t['bg_hover_alt']}; }}"
            f"QTabBar::tab:selected {{ background: {t['bg_primary']}; color: {t['fg_bright']}; border: 1px solid {t['border_normal']}; }}"
        )
        list_base = (
            f"QListWidget {{ background: {t['bg_primary']}; font-family: Consolas, 'DejaVu Sans Mono', Menlo, monospace; font-size: 12px; border: none; }}"
            f"QListWidget::item {{ padding: 4px 6px; border-bottom: 1px solid {t['bg_item_hover']}; }}"
            f"QListWidget::item:hover {{ background: {t['bg_item_hover']}; }}"
            f"QListWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )
        self._error_list.setStyleSheet(f"{list_base} color: {t['sem_error']};")
        self._warn_list.setStyleSheet(f"{list_base} color: {t['sem_warning']};")
        self._suggest_list.setStyleSheet(f"{list_base} color: {t['sem_suggestion']};")
        self._log_text.setStyleSheet(
            f"QPlainTextEdit {{ background: {t['bg_primary']}; color: {t['fg_primary']}; font-family: Consolas, 'DejaVu Sans Mono', Menlo, monospace; font-size: 11px; border: none; }}"
        )
        for i in range(self._error_list.count()):
            self._error_list.item(i).setForeground(QColor(t["sem_error"]))
        for i in range(self._warn_list.count()):
            self._warn_list.item(i).setForeground(QColor(t["sem_warning"]))
        for i in range(self._suggest_list.count()):
            self._suggest_list.item(i).setForeground(QColor(t["sem_hint"]))
