"""Düzenleme işlemleri mixin — geri al, yinele, bul, değiştir, yorum, satıra git."""

from PyQt6.QtWidgets import QInputDialog, QApplication
from PyQt6.QtCore import QCoreApplication

_ = lambda s: QCoreApplication.translate("EditOpsMixin", s)


class EditOpsMixin:

    def _undo(self):
        editor = self._current_editor()
        if editor:
            editor.undo()

    def _redo(self):
        editor = self._current_editor()
        if editor:
            editor.redo()

    def _show_find(self):
        # PDF viewer odaktaysa PDF aramasını aç
        focus = QApplication.focusWidget()
        if focus and self._pdf_viewer.isAncestorOf(focus):
            self._pdf_viewer._toggle_search_bar()
            return
        editor = self._current_editor()
        if not editor:
            return
        self._ensure_find_bar(editor)
        self._find_bar.show_find()

    def _show_replace(self):
        editor = self._current_editor()
        if not editor:
            return
        self._ensure_find_bar(editor)
        self._find_bar.show_replace()

    def _ensure_find_bar(self, editor):
        if self._find_bar is None:
            from gui.find_replace import FindReplaceBar
            self._find_bar = FindReplaceBar(self)
            self._find_bar.apply_theme(self._theme_mgr.theme)
            self._editor_layout.insertWidget(0, self._find_bar)
        self._find_bar.set_editor(editor)

    def _toggle_comment(self):
        editor = self._current_editor()
        if not editor:
            return

        line, _ = editor.getCursorPosition()

        if editor.hasSelectedText():
            pos_start = editor.SendScintilla(editor.SCI_GETSELECTIONSTART)
            pos_end = editor.SendScintilla(editor.SCI_GETSELECTIONEND)
            line_from, _ = editor.lineIndexFromPosition(pos_start)
            line_to, _ = editor.lineIndexFromPosition(pos_end)
        else:
            line_from = line
            line_to = line

        first_line_text = editor.text(line_from).lstrip()
        is_commented = first_line_text.startswith('%')

        editor.beginUndoAction()
        for ln in range(line_from, line_to + 1):
            text = editor.text(ln)
            if is_commented:
                idx = text.find('%')
                if idx >= 0:
                    editor.setSelection(ln, idx, ln, idx + 1)
                    editor.removeSelectedText()
            else:
                indent = len(text) - len(text.lstrip())
                if text.strip():
                    editor.setSelection(ln, indent, ln, indent)
                    editor.replaceSelectedText('%')
        editor.endUndoAction()

    def _goto_line_dialog(self):
        editor = self._current_editor()
        if not editor:
            return
        line, _ = editor.getCursorPosition()
        max_line = editor.lines()
        num, ok = QInputDialog.getInt(
            self, _("Satıra Git"), _("Satır numarası") + f" (1-{max_line}):", line + 1, 1, max_line
        )
        if ok:
            editor.setCursorPosition(num - 1, 0)
            editor.ensureLineVisible(num - 1)
            editor.setFocus()

    # --- Referans denetimi (tanımsız \ref/\cite, kullanılmayan .bib girdileri) ---

    @staticmethod
    def _audit_lines(r) -> list[str]:
        """RefAudit raporunu OutputPanel'e yazılacak satırlara çevir."""
        lines = []
        if r.undefined_refs:
            lines.append(_("Tanımsız \\ref (etiketi yok): {n}").format(n=len(r.undefined_refs)))
            lines.extend(f"    {k}" for k in r.undefined_refs)
        if r.undefined_cites:
            lines.append(_("Tanımsız \\cite (.bib/\\bibitem'te yok): {n}").format(n=len(r.undefined_cites)))
            lines.extend(f"    {k}" for k in r.undefined_cites)
        if r.unused_bib_keys:
            lines.append(_("Kullanılmayan .bib girdisi: {n}").format(n=len(r.unused_bib_keys)))
            lines.extend(f"    {k}" for k in r.unused_bib_keys)
        if not lines:
            lines.append(_("Sorun bulunamadı — tüm \\ref/\\cite anahtarları tanımlı."))
        return lines

    def _audit_references(self):
        """Düzenle > Referansları Denetle — derlemeden bağımsız lokal analiz."""
        from core.latex_refs import audit_references
        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Önce bir .tex dosyası açın"))
            return
        report = audit_references(editor.text(), editor.file_path)
        self._output_panel.show_report(_("== Referans Denetimi =="), self._audit_lines(report))
        total = len(report.undefined_refs) + len(report.undefined_cites) + len(report.unused_bib_keys)
        if total == 0:
            self._status.showMessage(_("Referans denetimi: sorun yok"))
        else:
            self._status.showMessage(
                _("Referans denetimi: {r} tanımsız ref, {c} tanımsız cite, {b} kullanılmayan .bib girdisi").format(
                    r=len(report.undefined_refs),
                    c=len(report.undefined_cites),
                    b=len(report.unused_bib_keys),
                )
            )
