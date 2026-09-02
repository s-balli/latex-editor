"""Düzenleme işlemleri mixin — geri al, yinele, bul, değiştir, yorum, satıra git, F2 etiket rename."""

import os
import re

from PyQt6.QtWidgets import QDialog, QInputDialog, QApplication, QMessageBox
from PyQt6.QtCore import QCoreApplication

from core.log import get_logger

_ = lambda s: QCoreApplication.translate("EditOpsMixin", s)

_logger = get_logger("edit_ops")


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
        # `_` OLAMAZ: bu modülde `_` çeviri fonksiyonu ve Python'da fonksiyon
        # içinde bir kez atanan ad TÜM gövde boyunca yereldir — aşağıdaki
        # _("Satıra Git") bu int'i çağırmaya kalkıyordu ve Ctrl+G
        # "TypeError: 'int' object is not callable" ile HİÇ AÇILMIYORDU.
        line, _sutun = editor.getCursorPosition()
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
            audit_references, bib_key_locations, find_bib_path,
            key_usage_locations, label_locations,
        )
        from core.bibtex import dosyayi_denetle
        report = audit_references(content, base_path)
        # .bib dosyasının KENDİ tutarlılığı: yukarıdaki denetim .tex ile .bib
        # arasındaki bağa bakıyor (tanımsız cite, kullanılmayan girdi), bu ise
        # .bib'in içine. Yol bulunamazsa boş denetim döner.
        bib_yolu = find_bib_path(content, base_path)
        bib = dosyayi_denetle(bib_yolu)

        # Konumlar TOPLU çıkarılır. Eskiden her bulgu için ayrı arama yapılıyor,
        # her arama \input zincirini diskten baştan okuyordu: 30 bölümlü bir
        # tezde 495 arama = 1.7 sn ve bu süre boyunca UI donuyordu (derleme
        # sonrası denetim açıksa her derlemede). Şimdi zincir bir kez okunuyor.
        # Sözlükler yalnız o kolda bulgu VARSA kuruluyor — temiz belgede
        # (olağan hâl) tek bir fazladan okuma bile yapılmıyor.
        ref_kon = key_usage_locations(content, base_path, "ref") if report.undefined_refs else {}
        cite_kon = key_usage_locations(content, base_path, "cite") if report.undefined_cites else {}
        bib_kon = bib_key_locations(content, base_path) if report.unused_bib_keys else {}
        label_kon = label_locations(content, base_path) if report.unused_labels else {}

        warnings = []
        for k in report.undefined_refs:
            warnings.append(EditOpsMixin._audit_item(_("Tanımsız \\ref"), k, ref_kon.get(k)))
        for k in report.undefined_cites:
            warnings.append(EditOpsMixin._audit_item(_("Tanımsız \\cite"), k, cite_kon.get(k)))
        # Mükerrer anahtar UYARI, çünkü belgeyi sessizce BOZUYOR: BibTeX hiç
        # şikâyet etmeden ilk tanımı alıyor, kullanıcı ikinciyi düzeltip
        # çıktının değişmemesine anlam veremiyor. İlk satıra atlıyoruz;
        # ötekiler metinde yazılı.
        for anahtar, satirlar in bib.mukerrer:
            warnings.append(EditOpsMixin._audit_item(
                _("Mükerrer .bib anahtarı (satır {s})").format(
                    s=", ".join(str(x) for x in satirlar)),
                anahtar, (bib_yolu, satirlar[0])))
        suggestions = []
        # Eksik zorunlu alan ÖNERİ: derleme durmuyor, kaynakça eksik basılıyor
        # (ör. plain.bst "Warning--empty journal" deyip alanı atlıyor).
        for anahtar, satir, alanlar in bib.eksik:
            suggestions.append(EditOpsMixin._audit_item(
                _("Eksik zorunlu alan ({a})").format(a=", ".join(alanlar)),
                anahtar, (bib_yolu, satir)))
        for k in report.unused_bib_keys:
            suggestions.append(
                EditOpsMixin._audit_item(_("Kullanılmayan .bib girdisi"), k, bib_kon.get(k)))
        for k in report.unused_labels:
            suggestions.append(
                EditOpsMixin._audit_item(_("Kullanılmayan label"), k, label_kon.get(k)))
        counts = {
            "r": len(report.undefined_refs),
            "c": len(report.undefined_cites),
            "b": len(report.unused_bib_keys),
            "l": len(report.unused_labels),
            "m": len(bib.mukerrer),
            "e": len(bib.eksik),
        }
        return warnings, suggestions, counts

    @staticmethod
    def _audit_summary(c: dict) -> str:
        """Denetim sayılarından sıfırları atlayan tek satır özet üret.

        Sayıları üreten `_collect_audit_items`in yanında duruyor. Önce
        compile_ops'taydı ve edit_ops kendi kopyasını taşıyordu; kategori
        eklenince ikisi ayrışıyor, üstelik edit_ops'un compile_ops'a
        bağımlı olması test sahnelerini de kırıyordu.

        Sıfırları atlamak şart: altı kategori her seferinde sıralanınca
        gerçek bulgu sıfırların arasında kayboluyor.
        """
        parts = []
        if c["r"]:
            parts.append(_("{n} tanımsız ref").format(n=c["r"]))
        if c["c"]:
            parts.append(_("{n} tanımsız cite").format(n=c["c"]))
        if c.get("m"):
            parts.append(_("{n} mükerrer .bib anahtarı").format(n=c["m"]))
        if c["b"]:
            parts.append(_("{n} kullanılmayan .bib").format(n=c["b"]))
        if c.get("e"):
            parts.append(_("{n} eksik zorunlu alan").format(n=c["e"]))
        if c["l"]:
            parts.append(_("{n} kullanılmayan label").format(n=c["l"]))
        return _("Denetim: ") + ", ".join(parts)

    @staticmethod
    def _bib_yok_nedeni(icerik: str, yol: str) -> str:
        """Kaynakça listelenemiyorsa NEDEN listelenemediğini söyle."""
        from core.latex_refs import bib_declaration, has_manual_bibliography

        ad = bib_declaration(icerik, yol)
        if ad:
            # Bildirim duruyor, dosya yok. Aranan adı yaz: kullanıcı ya adı
            # düzeltir ya dosyayı koyar.
            if not ad.endswith(".bib"):
                ad += ".bib"
            return _("'{ad}' bulunamadı (klasörde yok)").format(ad=ad)
        if has_manual_bibliography(icerik, yol):
            # Buraya ancak kaynakça ortamı VAR ama İÇİ BOŞ ise düşülüyor:
            # `\bibitem` bulunsaydı çağıran onları listelemişti.
            return _("Kaynakça ortamı boş (\\begin{thebibliography} içinde \\bibitem yok)")
        return _("Bu belgede \\bibliography veya \\addbibresource yok")

    def _show_bibliography(self):
        """Kaynakça sekmesini .bib girdileriyle doldur.

        Salt görüntüleme: tıklayınca .bib'in o satırına gidiyor, düzenleme
        yok. BibTeX'i yeniden yazmak yorumları, `@string` makrolarını ve
        büyük harf koruma parantezlerini bozma riski taşıyor; dosyayı
        editörde açmak zaten mümkün.
        """
        from core.bibtex import ozet, parse_entries
        from core.latex_refs import find_bib_path, parse_bibitems
        from core.project_search import coz

        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._output_panel.show_bibliography([], _("Önce bir .tex dosyası açın"))
            return

        yol = find_bib_path(editor.text(), editor.file_path)
        if yol:
            try:
                with open(yol, "rb") as f:
                    ham = f.read()
            except OSError as e:
                _logger.warning("Kaynakça okunamadı: %s | %s", yol, e)
                self._output_panel.show_bibliography(
                    [], _("Kaynakça dosyası okunamadı"))
                return
            girdiler = parse_entries(coz(ham))
            self._output_panel.show_bibliography(
                [(ozet(g), yol, g.satir) for g in girdiler],
                _("kaynakçada girdi yok"))
            self._status.showMessage(
                _("Kaynakça: {n} girdi · {d}").format(
                    n=len(girdiler), d=os.path.basename(yol)))
            return

        # .bib yok: kaynakça ELLE yazılmış olabilir. 38 şablonun 13'ü böyle
        # (213 kaynak) ve o kullanıcılar sekmeyi hiç göremiyordu.
        elle = parse_bibitems(editor.text(), editor.file_path)
        if elle:
            self._output_panel.show_bibliography(
                [self._bibitem_satiri(x) for x in elle])
            self._status.showMessage(
                _("Kaynakça: {n} girdi (elle yazılmış)").format(n=len(elle)))
            return

        # ÜÇ AYRI durum, üçü de ayrı cümleyi hak ediyor. Hepsine aynı mesajı
        # vermek yanlış yönlendiriyordu (bkz. _bib_yok_nedeni).
        self._output_panel.show_bibliography(
            [], self._bib_yok_nedeni(editor.text(), editor.file_path))

    # --- DOI ile kaynak ekleme ---

    def _add_by_doi(self):
        """DOI sor, arka planda getir, onaylat, .bib'in sonuna ekle.

        Yazma hedefi belgenin KENDİ .bib'i: `\\bibliography` bildirimi yoksa
        nereye ekleneceği belirsiz ve rastgele bir dosya yaratmak kullanıcıyı
        şaşırtır.
        """
        from core.latex_refs import find_bib_path

        editor = self._current_editor()
        if not editor or not editor.file_path:
            self._status.showMessage(_("Önce bir .tex dosyası açın"))
            return
        yol = find_bib_path(editor.text(), editor.file_path)
        if not yol:
            QMessageBox.information(
                self, _("DOI ile Kaynak Ekle"),
                _("Bu belgenin bir .bib dosyası yok.") + "\n\n"
                + self._bib_yok_nedeni(editor.text(), editor.file_path))
            return

        doi, ok = QInputDialog.getText(
            self, _("DOI ile Kaynak Ekle"),
            _("DOI (tam URL de olur):"))
        if not ok or not doi.strip():
            return

        if getattr(self, "_doi_runner", None) is None:
            from gui.doi_fetch import DoiRunner
            self._doi_runner = DoiRunner(self)
            self._doi_runner.done.connect(self._on_doi_fetched)
        self._doi_bib_yolu = yol
        self._status.showMessage(_("DOI getiriliyor..."))
        from core.latex_refs import collect_cite_keys
        self._doi_runner.start(doi, collect_cite_keys(editor.text(), editor.file_path))

    def _on_doi_fetched(self, ok: bool, metin: str, anahtar: str, hata: str):
        if not ok:
            mesajlar = {
                "gecersiz": _("Bu bir DOI'ye benzemiyor (10. ile başlamalı)"),
                "bulunamadi": _("Bu DOI bulunamadı"),
                "ayristirilamadi": _("Gelen kayıt okunamadı"),
            }
            self._status.showMessage("")
            QMessageBox.warning(
                self, _("DOI ile Kaynak Ekle"),
                mesajlar.get(hata, _("Bağlantı kurulamadı")))
            return

        from gui.doi_fetch import DoiOnayDialog
        yol = getattr(self, "_doi_bib_yolu", "")
        dlg = DoiOnayDialog(metin, os.path.basename(yol), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self._status.showMessage("")
            return

        from core.bibtex import bibe_ekle
        try:
            bibe_ekle(yol, dlg.girdi())
        except OSError as e:
            _logger.error("Kaynakçaya yazılamadı: %s", yol, exc_info=True)
            QMessageBox.warning(self, _("DOI ile Kaynak Ekle"),
                                _("Kaynakçaya yazılamadı: {e}").format(e=e))
            return
        self._status.showMessage(
            _("Eklendi: {a} · {d}").format(a=anahtar, d=os.path.basename(yol)))
        # Sekme açıksa taze listeyi göster; kapalıysa zaten açılınca dolacak.
        if self._output_panel._bib_table.rowCount():
            self._show_bibliography()

    @staticmethod
    def _bibitem_satiri(girdi) -> tuple:
        """`\\bibitem` girdisini tablo satırına çevir.

        YAZAR sütunu BİLEREK boş: `\\bibitem` gövdesi serbest metin, alanlara
        ayrılmış değil. Yazarı oradan çıkarmak tahmin olurdu ve doğruluğunu
        sınayacak bir kaynak yok. Metnin tamamı Başlık sütununda duruyor,
        süzgeç de orayı tarıyor; yazar araması yine çalışıyor.

        YIL yalnız metinde TEK yıl adayı varsa doluyor (bkz.
        latex_refs._bibitem_yili).
        """
        from core.latex_refs import _bibitem_yili

        anahtar, dosya, satir, metin = girdi
        return ((anahtar, "bibitem", "", _bibitem_yili(metin), metin),
                dosya, satir)

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
            # Özet biçimi compile_ops._audit_summary'de, TEK kaynak: burada
            # kendi kopyası vardı ve kategori eklenince ikisi ayrışıyordu.
            self._status.showMessage(self._audit_summary(c))

    # --- F2: yeniden adlandırma (label + cite) — ortak altyapı ---

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

    def _apply_renamings(self, paths, span_fn, new_key: str) -> tuple[int, list[str]]:
        """``paths`` içindeki dosyalarda ``span_fn(text)`` aralıklarını değiştir.

        Sekmede açık dosyanın arabelleğinde seç-değiştir (undo geçmişi korunur,
        tek adım); disktekinden atomik yeniden yazılır (kodlama round-trip
        güvenli).

        ``(değişen_sayısı, dokunulamayan_yollar)`` döndürür. Okunamayan/
        yazılamayan dosya sessizce atlanırsa yeniden adlandırma YARIM kalıyor
        (\\ref'ler '??', \\cite'lar '[?]' basıyor) ama kullanıcı başarı mesajı
        görüyordu — salt okunur .bib ya da ağ sürücüsü bunun için yeterli.
        Çağıran, liste doluysa kullanıcıyı uyarmak zorunda.
        """
        from gui.editor import EditorWidget, _decode_bytes
        changed = 0
        failed: list[str] = []
        for path in paths:
            target = self._editor_by_path(path)
            if target is not None:
                spans = span_fn(target.text())
                if spans:
                    self._replace_in_editor(target, spans, new_key)
                    changed += 1
            else:
                try:
                    with open(path, "rb") as f:
                        raw = f.read()
                except OSError as exc:
                    _logger.warning("Yeniden adlandırma — okunamadı: %s — %s", path, exc)
                    failed.append(path)
                    continue
                t, enc = _decode_bytes(raw)
                spans = span_fn(t)
                if spans:
                    for s, e in sorted(spans, reverse=True):
                        t = t[:s] + new_key + t[e:]
                    try:
                        EditorWidget._write_atomic(path, t, enc)
                        changed += 1
                    except (OSError, UnicodeError) as exc:
                        _logger.warning("Yeniden adlandırma — yazılamadı: %s — %s", path, exc)
                        failed.append(path)
        return changed, failed

    def _report_rename(self, changed: int, failed: list[str], key: str,
                       new_key: str, basari_sablonu: str):
        """Yeniden adlandırma sonucunu bildir; kısmi başarıda diyalogla uyar.

        Kısmi başarı sessiz geçemez: belge tutarsız kaldığı için kullanıcının
        hangi dosyaların elde kaldığını bilmesi gerekiyor.
        """
        if failed:
            QMessageBox.warning(
                self, _("Yeniden Adlandırma"),
                _("'{o}' → '{n}': {c} dosya değiştirildi, {f} dosya değiştirilemedi.\n\n"
                  "{liste}\n\n"
                  "Referanslar tutarsız kaldı. Bu dosyalara yazma izni verip "
                  "işlemi tekrarlayın ya da elle düzeltin.").format(
                      o=key, n=new_key, c=changed, f=len(failed),
                      liste="\n".join(failed)),
            )
            return
        if changed:
            self._status.showMessage(basari_sablonu.format(o=key, n=new_key, c=changed))
        else:
            self._status.showMessage(_("Değişiklik yok: {k}").format(k=key))

    # F2 rename üçlüsünün ortak girişi. Üç handler da aynı 18 satırı
    # taşıyordu: editörü bul, yeni adı sor, boş/aynı/geçersiz olanı ele.
    # Kopya olması yalnız uzunluk sorunu değildi — anahtar karakter kümesi
    # ÜÇ ayrı regex'te duruyordu, biri değişirse diğerleri sessizce ayrışırdı.
    _GECERLI_ANAHTAR = re.compile(r'[A-Za-z0-9_:.-]+')

    def _rename_ister(self, key: str, baslik: str, gecersiz_msg: str,
                      gosterim: str = ""):
        """Editörü bul + yeni adı sor + doğrula.

        Dönüş: ``(editor, yeni_ad)``. İptal, boş giriş, aynı ad ya da geçersiz
        karakter durumunda ``(None, "")`` — çağıran sessizce dönmeli.
        ``gosterim`` diyalogda anahtarın nasıl yazılacağı (label için
        etiket komutuyla birlikte, diğerlerinde anahtarın kendisi).
        """
        from gui.editor import EditorWidget

        ed = self.sender()
        if not isinstance(ed, EditorWidget):
            ed = self._current_editor()
        if not ed or not ed.file_path or not key:
            return None, ""

        yeni, ok = QInputDialog.getText(
            self, baslik, (gosterim or key) + " → " + _("yeni ad:"))
        if not ok:
            return None, ""
        yeni = yeni.strip()
        if not yeni or yeni == key:
            return None, ""
        if not self._GECERLI_ANAHTAR.fullmatch(yeni):
            self._status.showMessage(gecersiz_msg)
            return None, ""
        return ed, yeni

    def _on_rename_label(self, key: str):
        r"""F2 (label): \label anahtarını doküman + \input zincirinde değiştir.

        Yeni ad projede zaten varsa engellenir.
        """
        from core.latex_refs import collect_labels, input_chain_paths, label_rename_spans

        ed, new_key = self._rename_ister(
            key, _("Etiketi Yeniden Adlandır"),
            _("Geçersiz etiket adı (harf, rakam, : . _ - kullanın)"),
            gosterim=f"\\label{{{key}}}")
        if ed is None:
            return
        content = ed.text()
        if new_key in collect_labels(content, ed.file_path):
            QMessageBox.warning(
                self, _("Etiketi Yeniden Adlandır"),
                _("'{k}' adlı etiket projede zaten var.").format(k=new_key),
            )
            return

        paths = [ed.file_path] + input_chain_paths(content, ed.file_path)
        changed, failed = self._apply_renamings(
            paths, lambda t: label_rename_spans(t, key), new_key)

        self._report_rename(
            changed, failed, key, new_key,
            _("Etiket yeniden adlandırıldı: {o} → {n} ({c} dosya)"))

    def _on_rename_cite(self, key: str):
        r"""F2 (cite): .bib girdi anahtarını tüm \cite kullanımlarıyla değiştir.

        .tex'ten tetiklenirse o dosyanın \input zinciri + .bib; .bib
        editöründen tetiklenirse anahtarı kullanan ilk .tex'in zinciri + .bib
        (kullanım hiç yoksa yalnız .bib girdisi değişir). Çift anahtar
        engellenir.
        """
        from core.latex_refs import (
            bib_key_rename_spans, cite_rename_spans,
            find_bib_path, find_cite_usage, input_chain_paths,
        )

        title = _("Kaynakça Anahtarını Yeniden Adlandır")
        ed, new_key = self._rename_ister(
            key, title, _("Geçersiz anahtar adı (harf, rakam, : . _ - kullanın)"))
        if ed is None:
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
            bib_ed = self._editor_by_path(bib_path)
            bib_text = bib_ed.text() if bib_ed else (self._read_text(bib_path) or "")
        if bib_text and bib_key_rename_spans(bib_text, new_key):
            QMessageBox.warning(
                self, title,
                _("'{k}' anahtarı .bib'te zaten var.").format(k=new_key),
            )
            return

        paths = []
        if base_path:
            base_ed = self._editor_by_path(base_path)
            base_content = base_ed.text() if base_ed else self._read_text(base_path)
            if base_content is not None:
                paths.append(base_path)
                paths += input_chain_paths(base_content, base_path)
        if bib_path:
            paths.append(bib_path)

        # span_fn iki deseni de kapsar: .tex'te \cite kullanımı, .bib'te girdi
        changed, failed = self._apply_renamings(
            paths,
            lambda t: cite_rename_spans(t, key) + bib_key_rename_spans(t, key),
            new_key)

        self._report_rename(
            changed, failed, key, new_key,
            _("Kaynakça anahtarı yeniden adlandırıldı: {o} → {n} ({c} dosya)"))

    def _on_rename_bibitem(self, key: str):
        r"""F2 (bibitem): thebibliography anahtarını tüm \cite kullanımlarıyla değiştir.

        El ile kaynakça (.bib'siz) belgeler için; zincirdeki \bibitem girdisi
        ve tüm \cite kullanımları birlikte değişir. Çift anahtar engellenir.
        """
        from core.latex_refs import (
            bibitem_rename_spans, cite_rename_spans,
            find_bibitem_location, input_chain_paths,
        )

        title = _("Kaynakça Anahtarını Yeniden Adlandır")
        ed, new_key = self._rename_ister(
            key, title, _("Geçersiz anahtar adı (harf, rakam, : . _ - kullanın)"))
        if ed is None:
            return
        content = ed.text()
        if find_bibitem_location(content, ed.file_path, new_key) is not None:
            QMessageBox.warning(
                self, title,
                _("'{k}' adlı etiket projede zaten var.").format(k=new_key),
            )
            return

        paths = [ed.file_path] + input_chain_paths(content, ed.file_path)
        changed, failed = self._apply_renamings(
            paths,
            lambda t: cite_rename_spans(t, key) + bibitem_rename_spans(t, key),
            new_key)

        self._report_rename(
            changed, failed, key, new_key,
            _("Kaynakça anahtarı yeniden adlandırıldı: {o} → {n} ({c} dosya)"))
