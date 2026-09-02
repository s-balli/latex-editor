"""PdfViewer arama mixin — PDF içinde metin arama ve vurgulama.

Arama arka plan işçisinde koşar (pdf_search_worker): eskiden tüm doküman
UI thread'inde senkron taranıyordu; 500 sayfalık PDF'te arayüz saniyelerce
kilitleniyordu. Sonuçlar yalnız koordinat taşır (page_idx, start, count);
vurgu ve zıplama anında UI tarafı KENDİ dokümanından textpage yaratır —
işçinin handle'ları iş parçacıkları arasında paylaşılmaz.
"""

from PyQt6.QtWidgets import QLabel

from gui.pdfium_lock import pdfium_lock
from gui.pdf_donusum import geometri, gorsele, kutu_gorsele
from PyQt6.QtCore import QCoreApplication, QPoint
_ = lambda s: QCoreApplication.translate("PdfViewer", s)

from gui.pdf_search_worker import PdfSearchWorker


class PdfSearchMixin:

    def _init_search_state(self):
        self._search_results = []
        self._search_index = 0
        self._search_highlights = []
        self._search_id = 0
        self._search_atla = True
        self._search_worker = PdfSearchWorker()
        self._search_worker.found.connect(self._on_search_done)
        self._search_worker.start()

    def _do_search(self, query: str, *, atla: bool = True):
        self._clear_search_highlights()
        self._search_results = []
        self._search_id += 1          # uçuştaki arama da geçersizleşir
        self._search_atla = atla
        if not query or not self._pdf:
            self._update_search_nav(0, 0)
            return
        if hasattr(self, '_search_count_label'):
            self._search_count_label.setText(_("Aranıyor..."))
        self._search_worker.search(self._search_id, query)

    def _on_search_done(self, search_id: int, results: list):
        if search_id != self._search_id:
            return                      # bayat sonuç: yeni sorgu/nesil geldi
        self._search_results = results
        self._search_index = 0
        if results and self._search_atla:
            self._show_search_result(0)
        self._update_search_nav(1 if results else 0, len(results))

    def _restore_search(self):
        """Belge yeniden yüklendikten sonra açık aramayı sessizce tekrarla.

        load_pdf HER derlemede çağrılıyor ve `_clear_search` sonuçları siliyor.
        Silmek ŞART (aşağıdaki docstring: eski dokümanın ofsetleri yeni belgeye
        uygulanıyordu), ama kullanıcı açısından bedeli şuydu: arama çubuğu açık,
        sorgu hâlâ kutuda, sayaç "bulunamadı". Yaz–derle–bak döngüsünde her
        turda Enter'a basmak gerekiyordu.

        KAYDIRMA YOK (atla=False). Derlemeden sonra compile_ops imleç
        konumuna SyncTeX ileri-araması yapıyor; ikisi de asenkron döndüğü için
        kaydıran bir geri yükleme o zıplamayı yarışta ezebilirdi. Geri gelen
        şey sonuç listesi ve "N / M" sayacı: ileri/geri tuşları anında çalışır.
        """
        bar = getattr(self, "_search_bar_widget", None)
        if bar is None or not bar.isVisible():
            return
        query = self._search_input.text().strip()
        if query:
            self._do_search(query, atla=False)

    def _show_search_result(self, idx):
        self._clear_search_highlights()
        if idx >= len(self._search_results):
            return

        page_idx, start, count = self._search_results[idx]
        label = self._page_labels[page_idx] if page_idx < len(self._page_labels) else None
        if not label:
            return

        # textpage'i UI tarafında, ihtiyaç anında yarat (işçi sonuçları
        # yalnız koordinat taşır; iş parçacıkları arası handle yok)
        scale = self._olcek(page_idx)
        try:
            with pdfium_lock:
                sayfa = self._pdf[page_idx]
                textpage = sayfa.get_textpage()
                left, bottom, right, top = textpage.get_charbox(start, loose=True)
                # `get_charbox` DONDURULMEMIS kullanici uzayinda, `get_height()`
                # ise GORSEL boyutu veriyor; ikisini karistirmak /Rotate'li
                # sayfada koordinati bozuyordu (bkz. gui/pdf_donusum.py).
                _mx, match_y = gorsele(geometri(sayfa), left, top, scale)
        except Exception:
            match_y = 0

        # Eşleşme konumuna scroll
        # Dual modda pos() satıra göredir; _events/_synctex ile aynı mapTo yolu
        abs_y = label.mapTo(self._pages_widget, QPoint(0, 0)).y() + int(match_y)
        viewport_height = self._scroll.viewport().height()
        self._scroll.verticalScrollBar().setValue(max(0, abs_y - viewport_height // 3))
        self._current_page = page_idx
        self._update_nav()

        self._draw_search_highlight(idx)

        # Render isteği EN SONA. Artık gui/pdfium_lock.py tüm eşzamanlı
        # erişimi serileştiriyor, yani doğruluk için ŞART değil; ama sıra
        # yine de anlamlı: UI'ın pdfium işi bitmeden işçiyi uyandırmak onu
        # boşuna kilitte bekletirdi. Davranış değişmiyor — istek asenkron,
        # pixmap birkaç satır sonra gelmiyor.
        if label.pixmap() is None or label.pixmap().isNull():
            self._request_render(page_idx)

    def _draw_search_highlight(self, idx):
        self._clear_search_highlights()
        if idx >= len(self._search_results):
            return

        page_idx, start, count = self._search_results[idx]
        label = self._page_labels[page_idx] if page_idx < len(self._page_labels) else None
        if not label or label.pixmap() is None or label.pixmap().isNull():
            return

        scale = self._olcek(page_idx)
        t = self._theme

        # Geometriler ÖNCE kilit altında hesaplanır, Qt widget'ları sonra
        # kurulur: kilit yalnız pdfium çağrıları boyunca tutulsun (render
        # işçisi bu sürede beklemek zorunda kalıyor).
        kutular = []
        try:
            with pdfium_lock:
                sayfa = self._pdf[page_idx]
                textpage = sayfa.get_textpage()
                g = geometri(sayfa)
                for ci in range(start, start + count):
                    try:
                        left, bottom, right, top = textpage.get_charbox(ci, loose=True)
                    except Exception:
                        continue
                    # PDF koordinatları: origin sol-alt ve y yukarı; Qt'de
                    # sol-üst ve y aşağı. /Rotate varsa eksenler de takas
                    # oluyor (bkz. gui/pdf_donusum.py).
                    kutular.append(kutu_gorsele(g, left, bottom, right, top,
                                                scale))
        except Exception:
            return

        for x, y, w, h in kutular:
            hl = QLabel(label)
            hl.setStyleSheet(
                f"background-color: {t['pdf_hl_bg']}; "
                f"border: 1px solid {t['pdf_hl_border']}; "
                "border-radius: 1px;"
            )
            hl.setGeometry(int(x), int(y), max(int(w), 2), max(int(h), 4))
            hl.show()
            hl.raise_()
            self._search_highlights.append(hl)

    def _search_next(self):
        if not self._search_results:
            return
        self._search_index = (self._search_index + 1) % len(self._search_results)
        self._show_search_result(self._search_index)
        self._update_search_nav(self._search_index + 1, len(self._search_results))

    def _search_prev(self):
        if not self._search_results:
            return
        self._search_index = (self._search_index - 1) % len(self._search_results)
        self._show_search_result(self._search_index)
        self._update_search_nav(self._search_index + 1, len(self._search_results))

    def _clear_search_highlights(self):
        for hl in self._search_highlights:
            try:
                hl.deleteLater()
            except RuntimeError:
                pass
        self._search_highlights = []

    def _clear_search(self):
        """Arama sonuçlarını temizle ve UÇUŞTAKİ aramayı da geçersiz kıl.

        Bayatlık damgası yalnız _do_search'te artıyordu; _clear_search onu
        atlıyordu. Derleme bitip load_pdf yeni PDF'i yüklediğinde süren arama
        aynı damgayla dönüyor, _on_search_done guard'ından geçiyor ve ESKİ
        dokümanın karakter ofsetleri yeni doküman üzerinde kullanılıyordu:
        yanlış sayfaya kaydırma, yanlış vurgu kutusu, yanlış "N / M" sayacı.
        get_charbox istisnası yutulduğu için hepsi sessizdi.
        """
        self._search_id += 1
        self._clear_search_highlights()
        self._search_results = []
        self._search_index = 0
        self._update_search_nav(0, 0)

    def _update_search_nav(self, current, total):
        if hasattr(self, '_search_count_label'):
            self._search_count_label.setText(f"{current} / {total}" if total > 0 else _("bulunamadı"))

    def _toggle_search_bar(self):
        visible = self._search_bar_widget.isVisible()
        if visible:
            self._close_search()
        else:
            self._search_bar_widget.show()
            self._search_input.setFocus()
            self._search_input.selectAll()

    def _close_search(self):
        self._search_bar_widget.hide()
        self._clear_search()

    def _on_search_return(self):
        query = self._search_input.text().strip()
        if not query:
            return
        if query == getattr(self, '_last_search_query', None) and self._search_results:
            self._search_next()
        else:
            self._last_search_query = query
            self._do_search(query)

    def _apply_search_theme(self, t):
        if not hasattr(self, '_search_input'):
            return
        self._search_input.setStyleSheet(
            f"QLineEdit {{ background: {t['bg_secondary']}; color: {t['fg_primary']}; border: 1px solid {t['border_input']}; border-radius: 3px; padding: 2px 6px; font-size: 11px; }}"
        )
        for btn in (self._search_prev_btn, self._search_next_btn, self._search_close_btn):
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {t['fg_muted']}; border: none; }}"
                f"QPushButton:hover {{ color: {t['fg_primary']}; }}"
            )
        self._search_count_label.setStyleSheet(f"color: {t['fg_muted']}; font-size: 11px;")
        self._btn_search.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t['fg_muted']}; border: none; border-radius: 3px; padding: 4px; }}"
            # hover'da metin de parlaklasmali (bkz. _ui_setup.py).
            f"QPushButton:hover {{ background: {t['bg_hover']}; color: {t['fg_bright']}; }}"
            f"QPushButton:disabled {{ opacity: 0.3; }}"
        )
