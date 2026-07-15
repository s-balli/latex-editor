"""Dosya işlemleri mixin — açma, kaydetme, yeni dosya, son açılanlar, motor algılama, dışa aktarma."""

import os

from PyQt6.QtWidgets import QFileDialog

from gui.editor import EditorWidget
from core.engine_detector import detect_engine as _detect_engine_auto
from core.exporter import export as _export
from core.log import get_logger
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("FileOpsMixin", s)
_logger = get_logger("file_ops")


class FileOpsMixin:

    def _open_folder(self):
        path = QFileDialog.getExistingDirectory(self, _("Klasör Aç"))
        if path:
            _logger.info("Klasör açıldı: %s", path)
            for i in range(self._editor_tabs.count() - 1, -1, -1):
                if not self._close_tab_safe(i):
                    return
            self._pdf_viewer.clear()
            self._current_pdf = ""
            self._file_tree.set_root(path)

    def _new_file(self):
        path, _sel_filter = QFileDialog.getSaveFileName(
            self, _("Yeni Dosya"), "", _("LaTeX Dosyaları (*.tex);;Tüm Dosyalar (*)")
        )
        if not path:
            return
        editor = EditorWidget(theme=self._theme_mgr.theme)
        editor.setText("\\documentclass{article}\n\\begin{document}\n\n\\end{document}\n")
        editor.save_file_as(path)
        editor.setCursorPosition(3, 0)
        editor.modificationChanged.connect(lambda m, e=editor: self._update_tab_title(e))
        editor.cursorPositionChanged.connect(self._update_cursor_pos)
        editor.textChanged.connect(lambda e=editor: self._update_wordcount(e))
        editor.textChanged.connect(lambda e=editor: self._update_outline_debounced(e))
        editor.forward_search_requested.connect(self._on_forward_search)
        idx = self._editor_tabs.addTab(editor, editor.display_name)
        self._editor_tabs.setCurrentIndex(idx)
        self._add_tab_close_button(idx)
        self._add_recent(path)
        self._detect_engine(path)
        self._file_watch_add(path)
        editor.setFocus()

    def _open_file(self):
        paths, _sel_filter = QFileDialog.getOpenFileNames(
            self, _("Dosya Aç"), "",
            _("LaTeX Dosyaları (*.tex *.cls *.sty *.bib);;Tüm Dosyalar (*)")
        )
        for p in paths:
            self._open_file_in_editor(p)

    def _open_file_in_editor(self, path: str):
        for i in range(self._editor_tabs.count()):
            editor = self._editor_tabs.widget(i)
            if isinstance(editor, EditorWidget) and editor.file_path == os.path.normpath(path):
                self._editor_tabs.setCurrentIndex(i)
                return

        editor = EditorWidget(theme=self._theme_mgr.theme)
        if editor.open_file(path):
            _logger.info("Dosya açıldı: %s", path)
            editor.modificationChanged.connect(lambda m, e=editor: self._update_tab_title(e))
            editor.cursorPositionChanged.connect(self._update_cursor_pos)
            editor.textChanged.connect(lambda e=editor: self._update_wordcount(e))
            editor.textChanged.connect(lambda e=editor: self._update_outline_debounced(e))
            editor.forward_search_requested.connect(self._on_forward_search)
            idx = self._editor_tabs.addTab(editor, editor.display_name)
            self._editor_tabs.setCurrentIndex(idx)
            self._add_tab_close_button(idx)
            self._add_recent(path)
            self._detect_engine(path)
            self._file_watch_add(path)

    def _detect_engine(self, path: str):
        """Dosya ve .cls içeriğinden uygun derleme motorunu algıla."""
        if not path.endswith(".tex"):
            return
        engine = _detect_engine_auto(path)
        if engine is None:
            engine = "pdflatex"

        _logger.info("Motor algılandı: %s → %s", os.path.basename(path), engine)

        editor = self._current_editor()
        if isinstance(editor, EditorWidget):
            editor._detected_engine = engine

        idx = self._engine_combo.findText(engine)
        if idx >= 0 and idx != self._engine_combo.currentIndex():
            self._engine_combo.setCurrentIndex(idx)
            self._status.showMessage(_("Motor algılandı") + ": " + engine)

    def _save_file(self):
        editor = self._current_editor()
        if editor:
            if not editor.save_file():
                self._save_file_as()
            else:
                self._file_watch_record_save(editor.file_path)

    def _save_file_as(self):
        editor = self._current_editor()
        if not editor:
            return
        try:
            path, _sel_filter = QFileDialog.getSaveFileName(
                self, _("Farklı Kaydet"), "",
                _("LaTeX Dosyaları (*.tex);;Tüm Dosyalar (*)")
            )
        except Exception as e:
            _logger.error("SaveAs dialog hatası: %s", e, exc_info=True)
            return
        if path:
            try:
                old_path = editor.file_path
                editor.save_file_as(path)
                self._editor_tabs.setTabText(self._editor_tabs.currentIndex(), editor.display_name)
                if old_path:
                    self._file_watch_remove(old_path)
                self._file_watch_add(path)
                self._file_watch_record_save(path)
            except Exception as e:
                _logger.error("Dosya kaydetme hatası: %s", e, exc_info=True)

    def _update_tab_title(self, editor):
        index = self._editor_tabs.indexOf(editor)
        if index < 0:
            return
        title = editor.display_name
        if editor.isModified():
            title = f"* {title}"
        self._editor_tabs.setTabText(index, title)

    def _add_recent(self, path: str):
        path = os.path.normpath(path)
        recent = self._settings.value("recent_files", [])
        if isinstance(recent, str):
            recent = [recent]
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:5]
        self._settings.setValue("recent_files", recent)
        self._refresh_recent_menu()

    def _refresh_recent_menu(self):
        self._recent_menu.clear()
        recent = self._settings.value("recent_files", [])
        if isinstance(recent, str):
            recent = [recent]
        if not recent:
            act = self._recent_menu.addAction(_("(boş)"))
            act.setEnabled(False)
            return
        for path in recent:
            if os.path.isfile(path):
                self._recent_menu.addAction(
                    os.path.basename(path),
                    lambda p=path: self._open_file_in_editor(p),
                )

    def _export_file(self, fmt_name: str, ext: str):
        if not getattr(self, '_pandoc_available', True):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, _("Dışa Aktarma"),
                _("pandoc yüklü değil.\n\nKurmak için:\nLinux: sudo apt install pandoc\nWindows (WSL): sudo apt install pandoc\nWindows: pandoc.org")
            )
            return

        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Dışa aktarılacak dosya yok"))
            return

        default_name = os.path.splitext(os.path.basename(editor.file_path))[0] + ext
        dest, _sel_filter = QFileDialog.getSaveFileName(
            self, _("Dışa Aktar") + " — " + fmt_name, default_name,
            fmt_name + f" (*{ext});;" + _("Tüm Dosyalar (*)")
        )
        if not dest:
            return

        self._status.showMessage(_("Dışa aktarılıyor") + f" ({fmt_name})...")
        ok, err = _export(editor.file_path, dest)
        if ok:
            self._status.showMessage(_("Dışa aktarıldı") + ": " + os.path.basename(dest))
            _logger.info("Export başarılı: %s → %s", editor.file_path, dest)
        else:
            self._status.showMessage(_("Dışa aktarma başarısız") + ": " + str(err))
            _logger.warning("Export başarısız: %s → %s — %s", editor.file_path, dest, err)
