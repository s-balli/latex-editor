"""Sekme yönetimi mixin — kapatma, context menu, değişim, wordcount, outline."""

import re

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QTabBar as _QTabBar, QToolButton, QMenu, QApplication, QStyle,
)

from gui.editor import EditorWidget
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("TabOpsMixin", s)

# LaTeX-aware kelime sayımı için regex'ler
_RE_COMMENT = re.compile(r'%.*$', re.MULTILINE)
_RE_COMMANDS = re.compile(r'\\[a-zA-Z]+')           # \command
# Matematik bölgeleri: $$...$$ ÖNCE denenmeli (yoksa $$ boş satır içi math gibi yanlış eşlenir)
_RE_MATH_DELIM = re.compile(
    r'\$\$.+?\$\$|\$[^$\n]*\$|\\\(.+?\\\)|\\\[.+?\\\]',
    re.DOTALL,
)
# Matematik ortamları (içerik dahil): \begin{equation}...\end{equation} vb. (* opsiyonel)
_RE_MATH_ENV_BLOCK = re.compile(
    r'\\begin\{((?:equation|align|gather|multline|eqnarray|math|displaymath|split|cases)\*?)\}.*?\\end\{\1\}',
    re.DOTALL,
)
_RE_BRACES = re.compile(r'[{}\[\]]')
_RE_LABELS = re.compile(r'\\(?:label|ref|cite|eqref|pageref|bibliography|addbibresource)\{[^}]*\}')
_RE_BEGIN_END = re.compile(r'\\(?:begin|end)\{[^}]*\}')


def _latex_wordcount(text: str) -> tuple[int, int]:
    """LaTeX kaynağından gerçek kelime ve karakter sayısı.

    Yorumları, matematik bölgelerini/ortamlarını, komutları, label/ref'leri ve
    begin/end etiketlerini temizler; sadece görünür metni sayar."""
    t = _RE_COMMENT.sub('', text)
    t = _RE_MATH_ENV_BLOCK.sub('', t)   # \begin{equation}...\end{equation} (tag'ler ayrılmadan önce)
    t = _RE_MATH_DELIM.sub('', t)       # $...$, $$...$$, \(...\), \[...\]
    t = _RE_LABELS.sub('', t)
    t = _RE_BEGIN_END.sub('', t)
    t = _RE_COMMANDS.sub('', t)
    t = _RE_BRACES.sub('', t)
    words = len(t.split())
    chars = len(t.strip())
    return words, chars


class TabOpsMixin:

    def _editor_by_path(self, path: str) -> "EditorWidget | None":
        """``path`` açık sekmedeyse editörünü döndür (yoksa None).

        Tek kaynak: bu aramayı beş mixin ayrı kopya tutuyordu
        (compile/edit_ops/file_watch/file_ops/main_window); yeni sinyal veya
        karşılaştırma kuralı eklendiğinde beşini birden güncellemek
        gerekiyordu. Yollar her iki tarafta normpath'tir (open_file
        normpath'le saklar).
        """
        path = os.path.normpath(path)
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget) and editor.file_path == path:
                return editor
        return None

    def _add_tab_close_button(self, index: int):
        btn = QToolButton()
        btn.setFixedSize(18, 18)
        btn.setToolTip(_("Kapat"))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)
        btn.setIcon(icon)
        t = self._theme_mgr.theme
        btn.setStyleSheet(
            "QToolButton { background: transparent; border: none; border-radius: 3px; padding: 1px; }"
            f"QToolButton:hover {{ background: {t['tab_close_hover']}; }}"
        )
        editor = self._editor_tabs.widget(index)
        btn.clicked.connect(lambda _, e=editor: self._close_tab(self._editor_tabs.indexOf(e)))
        self._editor_tabs.tabBar().setTabButton(
            index, _QTabBar.ButtonPosition.RightSide, btn
        )

    def _close_tab(self, index: int):
        self._close_tab_safe(index)

    def _close_tab_safe(self, index: int) -> bool:
        if index < 0 or index >= self._editor_tabs.count():
            return True
        editor = self._editor_tabs.widget(index)
        if isinstance(editor, EditorWidget) and editor.isModified():
            reply = self._save_dialog(editor.display_name)
            if reply == "save":
                # Kayıt başarısızsa sekmeyi KAPATMA: dirty içerik kaybolur.
                # (Hata dialogunu save_file kendi gösterir.)
                if not editor.save_file():
                    return False
            elif reply == "cancel":
                return False
        # Dosya izlemeyi kaldır
        if isinstance(editor, EditorWidget) and editor.file_path:
            self._file_watch_remove(editor.file_path)
        # Kapatılan tab'ın ürettiği PDF açıksa temizle
        if (isinstance(editor, EditorWidget) and editor.file_path
                and self._current_pdf):
            tex_base = os.path.splitext(editor.file_path)[0]
            pdf_base = os.path.splitext(self._current_pdf)[0]
            if tex_base == pdf_base:
                self._pdf_viewer.clear()
                self._current_pdf = ""
        self._editor_tabs.removeTab(index)
        if self._wordcount_editor is editor:
            self._wordcount_editor = None
        if self._outline_editor is editor:
            self._outline_editor = None
        if self._find_bar and self._find_bar._editor is editor:
            self._find_bar._editor = None
            self._find_bar.hide()
        if editor:
            editor.deleteLater()
        return True

    def _tab_context_menu(self, pos):
        index = self._editor_tabs.tabBar().tabAt(pos)
        if index < 0:
            return
        menu = QMenu(self)
        t = self._theme_mgr.theme
        menu.setStyleSheet(f"QMenu {{ background: {t['bg_toolbar']}; color: {t['fg_editor']}; }}"
                          f"QMenu::item:selected {{ background: {t['bg_pressed']}; }}")

        close_action = menu.addAction(_("Kapat"))
        close_others = menu.addAction(_("Diğer Sekmeleri Kapat"))
        close_all = menu.addAction(_("Tümünü Kapat"))
        menu.addSeparator()
        copy_path = menu.addAction(_("Dosya Yolunu Kopyala"))

        action = menu.exec(self._editor_tabs.tabBar().mapToGlobal(pos))

        if action == close_action:
            self._close_tab(index)
        elif action == close_others:
            target_path = None
            editor = self._editor_tabs.widget(index)
            if isinstance(editor, EditorWidget):
                target_path = editor.file_path
            for i in range(self._editor_tabs.count() - 1, -1, -1):
                editor = self._editor_tabs.widget(i)
                if isinstance(editor, EditorWidget) and editor.file_path == target_path:
                    continue
                if not self._close_tab_safe(i):
                    break
        elif action == close_all:
            for i in range(self._editor_tabs.count() - 1, -1, -1):
                if not self._close_tab_safe(i):
                    break
            self._pdf_viewer.clear()
            self._current_pdf = ""
        elif action == copy_path:
            editor = self._editor_tabs.widget(index)
            if isinstance(editor, EditorWidget) and editor.file_path:
                QApplication.clipboard().setText(editor.file_path)

    def _on_tab_changed(self, index: int):
        editor = self._current_editor()

        if self._find_bar and editor:
            self._find_bar.set_editor(editor)

        if not editor and self._editor_tabs.count() == 0:
            self._pdf_viewer.clear()
            self._current_pdf = ""

        if isinstance(editor, EditorWidget) and editor._detected_engine:
            self._engine_combo.blockSignals(True)
            idx = self._engine_combo.findText(editor._detected_engine)
            if idx >= 0:
                self._engine_combo.setCurrentIndex(idx)
                self._status_engine.setText(editor._detected_engine)
            self._engine_combo.blockSignals(False)

        self._update_cursor_pos()

        if isinstance(editor, EditorWidget):
            self._update_wordcount(editor)

        if isinstance(editor, EditorWidget):
            self._file_tree.update_input_tree(editor.file_path, editor.text())
            self._outline.update_outline(editor.text())
            self._refresh_error_markers()

    def _update_cursor_pos(self):
        editor = self._current_editor()
        if editor:
            line, col = editor.getCursorPosition()
            self._status_pos.setText(_("Satır") + " " + str(line + 1) + ", " + _("Sütun") + " " + str(col + 1))

    def _update_wordcount(self, editor):
        self._wordcount_editor = editor
        self._wordcount_timer.start()

    def _do_wordcount(self):
        editor = self._wordcount_editor
        if editor and self._editor_tabs.indexOf(editor) >= 0:
            words, chars = _latex_wordcount(editor.text())
            self._status_wordcount.setText("  " + str(words) + " " + _("kelime") + ", " + str(chars) + " " + _("karakter") + "  ")
        else:
            self._status_wordcount.setText("")

    def _update_outline_debounced(self, editor):
        self._outline_editor = editor
        self._outline_timer.start()

    def _do_update_outline(self):
        editor = self._outline_editor
        if editor and editor == self._current_editor():
            self._outline.update_outline(editor.text())

    def _update_tab_close_theme(self, index: int, t: dict):
        btn = self._editor_tabs.tabBar().tabButton(index, _QTabBar.ButtonPosition.RightSide)
        if btn:
            btn.setStyleSheet(
                "QToolButton { background: transparent; border: none; border-radius: 3px; padding: 1px; }"
                f"QToolButton:hover {{ background: {t['tab_close_hover']}; }}"
            )
