"""Düzenleme işlemleri mixin — geri al, yinele, bul, değiştir, yorum, satıra git."""

import os

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
    def _audit_item(label: str, key: str, loc) -> tuple[str, str, int]:
        """Bulguyu OutputPanel öğesine çevir: (metin, dosya, satır).

        Konum varsa metne 'dosya: satır' öneki eklenir; yoksa (ör. kullanım
        zincirde bir önceki denetimden sonra değişti) satır 0 olur ve öğe
        tıklanamaz kalır.
        """
        if loc:
            path, line = loc
            return (f"{os.path.basename(path)}:{line} — {label}: {key}", path, line)
        return (f"{label}: {key}", "", 0)

    def _audit_references(self):
        """Düzenle > Referansları Denetle — derlemeden bağımsız lokal analiz.

        Bulgular tıklanabilir: tanımsız \ref/\cite kullanıldığı satıra,
        kullanılmayan .bib girdisi .bib'teki satırına atlar.
        """
        from core.latex_refs import audit_references, find_cite_location, find_key_usage
        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Önce bir .tex dosyası açın"))
            return
        content, base_path = editor.text(), editor.file_path
        report = audit_references(content, base_path)

        warnings = []
        for k in report.undefined_refs:
            loc = find_key_usage(content, base_path, k, "ref")
            warnings.append(self._audit_item(_("Tanımsız \\ref"), k, loc))
        for k in report.undefined_cites:
            loc = find_key_usage(content, base_path, k, "cite")
            warnings.append(self._audit_item(_("Tanımsız \\cite"), k, loc))
        suggestions = []
        for k in report.unused_bib_keys:
            loc = find_cite_location(content, base_path, k)
            suggestions.append(self._audit_item(_("Kullanılmayan .bib girdisi"), k, loc))

        self._output_panel.show_audit(warnings, suggestions)
        total = len(warnings) + len(suggestions)
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
