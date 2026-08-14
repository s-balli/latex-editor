"""Düzenleme işlemleri mixin — geri al, yinele, bul, değiştir, yorum, satıra git, F2 etiket rename."""

import os
import re

from PyQt6.QtWidgets import QInputDialog, QApplication, QMessageBox
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

    @staticmethod
    def _collect_audit_items(content: str, base_path: str) -> tuple[list, list, dict]:
        """İçerikten tıklanabilir denetim bulguları üret.

        Dönüş: (warnings, suggestions, counts). Hem Düzenle > Referansları
        Denetle hem derleme sonrası otomatik denetim (compile_ops) kullanır.
        Tanımsız \\ref/\\cite kullanıldığı satıra, kullanılmayan .bib/label
        kendi satırına atlar.
        """
        from core.latex_refs import (
            audit_references, find_cite_location, find_key_usage, find_label_location,
        )
        report = audit_references(content, base_path)

        warnings = []
        for k in report.undefined_refs:
            loc = find_key_usage(content, base_path, k, "ref")
            warnings.append(EditOpsMixin._audit_item(_("Tanımsız \\ref"), k, loc))
        for k in report.undefined_cites:
            loc = find_key_usage(content, base_path, k, "cite")
            warnings.append(EditOpsMixin._audit_item(_("Tanımsız \\cite"), k, loc))
        suggestions = []
        for k in report.unused_bib_keys:
            loc = find_cite_location(content, base_path, k)
            suggestions.append(EditOpsMixin._audit_item(_("Kullanılmayan .bib girdisi"), k, loc))
        for k in report.unused_labels:
            loc = find_label_location(content, base_path, k)
            suggestions.append(EditOpsMixin._audit_item(_("Kullanılmayan label"), k, loc))
        counts = {
            "r": len(report.undefined_refs),
            "c": len(report.undefined_cites),
            "b": len(report.unused_bib_keys),
            "l": len(report.unused_labels),
        }
        return warnings, suggestions, counts

    def _audit_references(self):
        """Düzenle > Referansları Denetle — derlemeden bağımsız lokal analiz."""
        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Önce bir .tex dosyası açın"))
            return
        warnings, suggestions, c = self._collect_audit_items(editor.text(), editor.file_path)
        self._output_panel.show_audit(warnings, suggestions)
        if not warnings and not suggestions:
            self._status.showMessage(_("Referans denetimi: sorun yok"))
        else:
            self._status.showMessage(
                _("Referans denetimi: {r} tanımsız ref, {c} tanımsız cite, {b} kullanılmayan .bib, {l} kullanılmayan label").format(**c)
            )

    # --- F2: yeniden adlandırma (label + cite) — ortak altyapı ---

    def _tab_editor(self, path: str):
        """``path`` açık sekmedeyse editörünü, yoksa None döndür."""
        from gui.editor import EditorWidget
        for i in range(self._editor_tabs.count()):
            w = self._editor_tabs.widget(i)
            if isinstance(w, EditorWidget) and w.file_path == os.path.normpath(path):
                return w
        return None

    @staticmethod
    def _read_text(path: str) -> str | None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def _replace_in_editor(self, target, spans, new_key: str):
        """Aralıkları alttan üste seç-değiştir: undo korunur, tek adım."""
        full = target.text()
        first_line, first_col = 0, 0
        target.beginUndoAction()
        try:
            for s, e in sorted(spans, reverse=True):
                line = full.count('\n', 0, s)
                line_start = full.rfind('\n', 0, s) + 1
                col_s, col_e = s - line_start, e - line_start
                first_line, first_col = line, col_s
                target.setSelection(line, col_s, line, col_e)
                target.replaceSelectedText(new_key)
        finally:
            target.endUndoAction()
        target.setCursorPosition(first_line, first_col + len(new_key))

    def _apply_renamings(self, paths, span_fn, new_key: str) -> int:
        """``paths`` içindeki dosyalarda ``span_fn(text)`` aralıklarını değiştir.

        Sekmede açık dosyanın arabelleğinde seç-değiştir (undo geçmişi korunur,
        tek adım); disktekinden atomik yeniden yazılır (kodlama round-trip
        güvenli). Değişen dosya sayısını döndürür.
        """
        from gui.editor import EditorWidget, _decode_bytes
        changed = 0
        for path in paths:
            target = self._tab_editor(path)
            if target is not None:
                spans = span_fn(target.text())
                if spans:
                    self._replace_in_editor(target, spans, new_key)
                    changed += 1
            else:
                try:
                    with open(path, "rb") as f:
                        raw = f.read()
                except OSError:
                    continue
                t, enc = _decode_bytes(raw)
                spans = span_fn(t)
                if spans:
                    for s, e in sorted(spans, reverse=True):
                        t = t[:s] + new_key + t[e:]
                    try:
                        EditorWidget._write_atomic(path, t, enc)
                        changed += 1
                    except (OSError, UnicodeError):
                        pass
        return changed

    def _on_rename_label(self, key: str):
        """F2 (label): \label anahtarını doküman + \input zincirinde değiştir.

        Yeni ad projede zaten varsa engellenir.
        """
        from core.latex_refs import collect_labels, input_chain_paths, label_rename_spans
        from gui.editor import EditorWidget

        ed = self.sender()
        if not isinstance(ed, EditorWidget):
            ed = self._current_editor()
        if not ed or not ed.file_path or not key:
            return

        new_key, ok = QInputDialog.getText(
            self, _("Etiketi Yeniden Adlandır"),
            f"\\label{{{key}}} → " + _("yeni ad:"),
        )
        if not ok:
            return
        new_key = new_key.strip()
        if not new_key or new_key == key:
            return
        if not re.fullmatch(r'[A-Za-z0-9_:.-]+', new_key):
            self._status.showMessage(_("Geçersiz etiket adı (harf, rakam, : . _ - kullanın)"))
            return
        content = ed.text()
        if new_key in collect_labels(content, ed.file_path):
            QMessageBox.warning(
                self, _("Etiketi Yeniden Adlandır"),
                _("'{k}' adlı etiket projede zaten var.").format(k=new_key),
            )
            return

        paths = [ed.file_path] + input_chain_paths(content, ed.file_path)
        changed = self._apply_renamings(
            paths, lambda t: label_rename_spans(t, key), new_key)

        if changed:
            self._status.showMessage(
                _("Etiket yeniden adlandırıldı: {o} → {n} ({c} dosya)").format(
                    o=key, n=new_key, c=changed)
            )
        else:
            self._status.showMessage(_("Değişiklik yok: {k}").format(k=key))

    def _on_rename_cite(self, key: str):
        """F2 (cite): .bib girdi anahtarını tüm \cite kullanımlarıyla değiştir.

        .tex'ten tetiklenirse o dosyanın \input zinciri + .bib; .bib
        editöründen tetiklenirse anahtarı kullanan ilk .tex'in zinciri + .bib
        (kullanım hiç yoksa yalnız .bib girdisi değişir). Çift anahtar
        engellenir.
        """
        from gui.editor import EditorWidget
        from core.latex_refs import (
            bib_key_rename_spans, cite_rename_spans,
            find_bib_path, find_cite_usage, input_chain_paths,
        )

        ed = self.sender()
        if not isinstance(ed, EditorWidget):
            ed = self._current_editor()
        if not ed or not ed.file_path or not key:
            return

        title = _("Kaynakça Anahtarını Yeniden Adlandır")
        new_key, ok = QInputDialog.getText(self, title, f"{key} → " + _("yeni ad:"))
        if not ok:
            return
        new_key = new_key.strip()
        if not new_key or new_key == key:
            return
        if not re.fullmatch(r'[A-Za-z0-9_:.-]+', new_key):
            self._status.showMessage(_("Geçersiz anahtar adı (harf, rakam, : . _ - kullanın)"))
            return

        if ed.file_path.endswith('.bib'):
            bib_path = ed.file_path
            usage = find_cite_usage(bib_path, key)
            base_path = usage[0] if usage else ""
        else:
            base_path = ed.file_path
            bib_path = find_bib_path(ed.text(), base_path)

        # çift anahtar kontrolü: .bib (sekmeyse arabellekten, değilse diskten)
        bib_text = ""
        if bib_path:
            bib_ed = self._tab_editor(bib_path)
            bib_text = bib_ed.text() if bib_ed else (self._read_text(bib_path) or "")
        if bib_text and bib_key_rename_spans(bib_text, new_key):
            QMessageBox.warning(
                self, title,
                _("'{k}' anahtarı .bib'te zaten var.").format(k=new_key),
            )
            return

        paths = []
        if base_path:
            base_ed = self._tab_editor(base_path)
            base_content = base_ed.text() if base_ed else self._read_text(base_path)
            if base_content is not None:
                paths.append(base_path)
                paths += input_chain_paths(base_content, base_path)
        if bib_path:
            paths.append(bib_path)

        # span_fn iki deseni de kapsar: .tex'te \cite kullanımı, .bib'te girdi
        changed = self._apply_renamings(
            paths,
            lambda t: cite_rename_spans(t, key) + bib_key_rename_spans(t, key),
            new_key)

        if changed:
            self._status.showMessage(
                _("Kaynakça anahtarı yeniden adlandırıldı: {o} → {n} ({c} dosya)").format(
                    o=key, n=new_key, c=changed)
            )
        else:
            self._status.showMessage(_("Değişiklik yok: {k}").format(k=key))
