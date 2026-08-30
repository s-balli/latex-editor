"""Tablo işlemleri mixin — sihirbaz (Ctrl+T) ve mevcut tabloyu hizalama."""

from PyQt6.QtCore import QCoreApplication

from core.latex_refs import collect_labels
from core.latex_tables import format_tabular, parse_tabular_at
from core.log import get_logger

_ = lambda s: QCoreApplication.translate("TableOpsMixin", s)
_logger = get_logger("table_ops")


class TableOpsMixin:

    @staticmethod
    def _cursor_char_offset(editor) -> int:
        """İmlecin doküman karakter offseti (QScintilla satır/kolon → offset)."""
        line, col = editor.getCursorPosition()
        text = editor.text()
        offset = 0
        lines = text.split("\n")
        for i in range(line):
            offset += len(lines[i]) + 1
        return offset + col

    @staticmethod
    def _char_offset_to_linecol(text: str, pos: int) -> tuple[int, int]:
        line = text.count("\n", 0, pos)
        line_start = text.rfind("\n", 0, pos) + 1
        return line, pos - line_start

    def _replace_char_range(self, editor, start: int, end: int, replacement: str):
        """[start, end) karakter aralığını seç-değiştir ile değiştir (tek undo)."""
        text = editor.text()
        l1, c1 = self._char_offset_to_linecol(text, start)
        l2, c2 = self._char_offset_to_linecol(text, min(end, len(text)))
        editor.beginUndoAction()
        editor.setSelection(l1, c1, l2, c2)
        editor.replaceSelectedText(replacement)
        editor.endUndoAction()

    @staticmethod
    def _table_wrapper_range(text: str, block: dict) -> tuple[int, int] | None:
        """Tabular bloğu bir \\begin{table}...\\end{table} kılıfının içindeyse
        kılıfın (start, end) aralığını, yoksa None döndür.

        Düzenlemede kılıf DAHİL değiştirilir: yalnız tabular aralığını yenisiyle
        değiştirsek sihirbazın ürettiği kılıflı kod, mevcut kılıfın İÇİNE ikinci
        bir \\begin{table} yerleştirirdi (iç içe yüzen ortam = geçersiz LaTeX).
        """
        import re as _re
        for m in _re.finditer(r"\\begin\{(table\*?)\}", text):
            end_m = _re.search(r"\\end\{" + m.group(1) + r"\}", text[m.end():])
            if not end_m:
                continue
            w_start, w_end = m.start(), m.end() + end_m.end()
            if w_start <= block["start"] and block["end"] <= w_end:
                return w_start, w_end
        return None

    def _table_wizard(self):
        """Tablo sihirbazı: yeni tablo üret veya imleçteki tabloyu düzenle."""
        from gui.table_wizard import TableWizardDialog
        from core.latex_tables import extract_caption_label

        editor = self._current_editor()
        if not editor:
            self._status.showMessage(_("Önce bir dosya açın"))
            return
        text = editor.text()
        pos = self._cursor_char_offset(editor)
        block = parse_tabular_at(text, pos)
        wrapper = self._table_wrapper_range(text, block) if block else None

        existing = []
        if editor.file_path:
            try:
                existing = collect_labels(text, editor.file_path)
            except Exception as e:
                # Sihirbaz mevcut etiketleri gösteremeden açılır; sessiz kalırsa
                # kullanıcı "etiketlerim neden listelenmiyor" diye sorar ve logda
                # iz olmaz. Akışı kesmeye değmez, ama kaydı kalsın.
                _logger.warning("Etiketler toplanamadı: %s — %s",
                                editor.file_path, e, exc_info=True)
                existing = []

        dlg = TableWizardDialog(self, existing_labels=existing)
        dlg.apply_theme(self._theme_mgr.theme)
        if block:
            dlg.load_block(block)
            if wrapper:
                # Kılıftaki caption/label'ı da al: yeniden üretimde korunur
                dlg.set_meta(*extract_caption_label(text[wrapper[0]:wrapper[1]]))
            self._status.showMessage(_("Mevcut tablo düzenleniyor — Ekle ile değiştirilir"))

        if dlg.exec() and dlg.result_text():
            code = dlg.result_text()
            if block:
                start, end = wrapper if wrapper else (block["start"], block["end"])
                self._replace_char_range(editor, start, end, code)
            else:
                editor.insert(code)
            editor.setFocus()
            self._status.showMessage(_("Tablo eklendi"))
            _logger.info("Tablo sihirbazı: %s", "mevcut tablo değiştirildi" if block else "yeni tablo eklendi")

    def _align_table(self):
        """İmlecin içindeki tabular bloğunun hücrelerini hizala."""
        editor = self._current_editor()
        if not editor:
            return
        text = editor.text()
        pos = self._cursor_char_offset(editor)
        block = parse_tabular_at(text, pos)
        if block is None:
            self._status.showMessage(_("İmleç bir tablo içinde değil"))
            return
        new_text = format_tabular(text, pos)
        if new_text is None:
            self._status.showMessage(_("Tabloda hizalanacak satır yok"))
            return
        # Çıpa imleç DEĞİL blok başı: hizalama fazla boşlukları kırpıp bloğu
        # kısaltabiliyor. Eski pos ile yeniden ayrıştırınca ya blok dışına
        # düşüp None geliyordu (bir alttaki satırda TypeError, komut sessizce
        # ölüyordu) ya da metindeki BİR SONRAKİ tabloya kayıp onun gövdesini
        # bu tablonun aralığına yazdırıyordu. block["start"] güvenli çünkü
        # format_tabular metnin o noktaya kadarki kısmını aynen koruyor
        # (latex_tables.py: text[:block["start"]] + ...).
        new_block = parse_tabular_at(new_text, block["start"])
        if new_block is None:
            self._status.showMessage(_("Tablo hizalanamadı"))
            _logger.warning("Hizalanan blok yeniden ayrıştırılamadı: start=%d", block["start"])
            return
        self._replace_char_range(editor, block["start"], block["end"],
                                 new_text[new_block["start"]:new_block["end"]])
        editor.setFocus()
        self._status.showMessage(_("Tablo hizalandı"))
