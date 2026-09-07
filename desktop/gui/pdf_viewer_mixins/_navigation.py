"""PdfViewer navigasyon mixin — sayfa geçişi, zoom, güncelleme."""

import os

from gui.pdfium_lock import pdfium_lock
from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QWheelEvent

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("PdfViewer", s)


class PdfNavigationMixin:

    def _update_nav(self):
        pages = _("Sayfa {cur} / {total}").format(cur=self._current_page + 1, total=max(self._page_count, 0))
        if self._pdf_path and os.path.exists(self._pdf_path):
            size = os.path.getsize(self._pdf_path)
            pages += f"  ({size / 1024:.0f} KB)"
        self._lbl_page.setText(pages)
        self._lbl_zoom.setText(f"{int(self._zoom * 100)}%")
        self._btn_prev.setEnabled(self._current_page > 0)
        self._btn_next.setEnabled(self._current_page < self._page_count - 1)
        self._btn_save.setEnabled(bool(self._pdf_path and self._page_count > 0))
        self._btn_invert.setEnabled(bool(self._pdf and self._page_count > 0))
        self._btn_present.setEnabled(bool(self._pdf and self._page_count > 0))
        has_bookmarks = self._bookmark_tree.topLevelItemCount() > 0 if hasattr(self, '_bookmark_tree') else False
        self._btn_bookmarks.setEnabled(has_bookmarks)

    def prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._scroll_to_page(self._current_page)
            self._update_nav()

    def next_page(self):
        if self._current_page < self._page_count - 1:
            self._current_page += 1
            self._scroll_to_page(self._current_page)
            self._update_nav()

    def _scroll_to_page(self, index: int):
        if 0 <= index < len(self._page_labels):
            self._scroll.ensureWidgetVisible(self._page_labels[index])
            QTimer.singleShot(100, self._render_visible)

    def _hedefe_kaydir(self, label, x_pixel: int, y_pixel: int,
                       genislik: int = 0, dikey_pay: int = 0):
        """Sayfa içindeki bir noktayı görüntüye getir: dikey VE yatay.

        Çağıranlar yalnız dikey kaydırıyordu. ÖLÇÜLDÜ (2026-09-07), %300
        yakınlaştırmada 612 pt'lik sayfa 2754 px, görüntü penceresi 404 px:
        sağ kenara yakın bir hedefte hem SyncTeX ileri araması hem metin
        araması doğru satıra iniyor ama hedef yatayda 1850 px dışarıda
        kalıyor. Kullanıcının gördüğü şey "hiçbir şey olmadı".

        Metin aramasında yatay konum zaten hesaplanıp atılıyordu.

        Yatayda hedef görünüyorsa DOKUNULMUYOR: her atlamada ortalamak aynı
        bölgedeki ardışık eşleşmelerde görüntüyü sarsardı. Hedef görüntüden
        genişse sol kenarı öncelikli, yani başı kesilmiyor.

        ``dikey_pay``: hedef, görüntünün üstünden bu kadar aşağıda dursun.
        Çağıranların alışkanlığı farklı ve korunuyor: ileri arama ortalıyor,
        metin araması üçte bire koyuyor, iç bağlantı 20 px pay bırakıyor.
        """
        sol_ust = label.mapTo(self._pages_widget, QPoint(0, 0))
        dikey = self._scroll.verticalScrollBar()
        dikey.setValue(max(0, sol_ust.y() + y_pixel - dikey_pay))

        yatay = self._scroll.horizontalScrollBar()
        if yatay.maximum() <= 0:
            return                      # sayfa zaten sığıyor
        pencere_x = self._scroll.viewport().width()
        sol = sol_ust.x() + x_pixel
        sag = sol + max(genislik, 0)
        kenar = 40
        if sol - kenar < yatay.value():
            hedef = sol - kenar
        elif sag + kenar > yatay.value() + pencere_x:
            hedef = min(sag + kenar - pencere_x, sol - kenar)
        else:
            return
        yatay.setValue(max(0, min(hedef, yatay.maximum())))

    def _zoom_capasi_al(self):
        """Görüntünün ORTASINDAKİ (sayfa, sayfa içi oran).

        Ölçek değişince sayfa yükseklikleri büyüyor, kaydırma çubuğunun
        değeri ise duruyor: kullanıcının baktığı yer kayıyor. ÖLÇÜLDÜ
        (2026-09-07, altı sayfalık belge, %75'ten dört adım): görüntünün
        ortası 4. sayfanın %50'sinden 3. sayfanın %77'sine gidiyor, yani
        bir sayfa geriye. Yakınlaştırma da uzaklaştırma da bunu yapıyor.
        """
        dikey = self._scroll.verticalScrollBar()
        orta = dikey.value() + self._scroll.viewport().height() // 2
        for i, etiket in enumerate(self._page_labels):
            ust = etiket.mapTo(self._pages_widget, QPoint(0, 0)).y()
            if ust <= orta < ust + etiket.height():
                return i, (orta - ust) / max(etiket.height(), 1)
        return None

    def _zoom_capasini_uygula(self):
        """Bekleyen çapayı geri koy.

        `verticalScrollBar().rangeChanged`den çağrılıyor, zamanlayıcıdan
        DEĞİL: yeni yerleşim eşzamanlı olarak hazır olmuyor. ÖLÇÜLDÜ
        (2026-09-07), `_update_page_sizes` hemen ardından sayfa konumu hâlâ
        eski; `layout().activate()`, `sendPostedEvents(LayoutRequest)` ve
        `processEvents()` de yetmiyor, 0 ms'lik zamanlayıcı da erken. Buna
        karşılık `rangeChanged` TAM BİR KEZ ve yerleşmiş düzenle geliyor.
        """
        capa = self._bekleyen_zoom_capasi
        self._bekleyen_zoom_capasi = None       # yeniden girmeyi kes
        if capa is None:
            return
        i, oran = capa
        if i >= len(self._page_labels):
            return
        etiket = self._page_labels[i]
        ust = etiket.mapTo(self._pages_widget, QPoint(0, 0)).y()
        hedef = (ust + int(oran * etiket.height())
                 - self._scroll.viewport().height() // 2)
        self._scroll.verticalScrollBar().setValue(max(0, hedef))

    def _zoom_uygula(self, yeni: float):
        """Ölçeği değiştir; kullanıcının baktığı yeri koru.

        Üç çağıran (zoom_in, zoom_out, _fit_zoom) aynı dört satırı
        taşıyordu; çapa da o yüzden üç yerde eklenmek zorunda kalırdı.
        """
        self._bekleyen_zoom_capasi = self._zoom_capasi_al()
        self._zoom = max(0.05, min(yeni, 3.0))
        self._pres_cache.clear()
        self._update_page_sizes()
        QTimer.singleShot(50, self._render_visible)
        self._update_nav()

    def zoom_in(self):
        self._zoom_uygula(self._zoom + 0.05)

    def zoom_out(self):
        self._zoom_uygula(self._zoom - 0.05)

    def _fit_zoom(self, mode: str):
        """mode: 'width' veya 'page'"""
        if not self._pdf or self._page_count == 0:
            return
        # Ölçü BAKILAN sayfadan alınır, 1. sayfadan değil. Karışık boyutlu
        # belgeler istisna değil kural: tezlerde yatay (landscape) ek sayfalar,
        # makalelerde tam sayfa şekil/tablo, ders notlarında araya konan slayt
        # PDF'i. Sayfa 1'i ölçüt almak, o sayfalarda "Genişliğe Sığdır"ı
        # yanlış yapıyordu — yatay bir sayfa görüntü alanının dışına taşıyor,
        # kullanıcı elle zoom'a dönmek zorunda kalıyordu.
        idx = max(0, min(self._current_page, self._page_count - 1))
        with pdfium_lock:
            page = self._pdf[idx]
            pw_ham = page.get_width()
            ph_ham = page.get_height()
        # Yer imi panelinin genişliği BURADAN ÇIKARILMIYOR. Panel `_scroll`in
        # KARDEŞİ (_ui_setup.py: body = QHBoxLayout, önce ağaç sonra scroll),
        # yani düzen onu zaten düşmüş oluyor ve `viewport().width()` kalan
        # genişliği veriyor. Eskiden bir kez daha çıkarılıyordu; ÖLÇÜLDÜ
        # (2026-09-05, 900x700 pencere, 220 px panel): panel açıkken sayfa
        # 664 px'lik alanda 423 px kalıyor, yani %64'ü kullanılıyor ve sağda
        # 241 px boşluk duruyor. Panel kapalıyken aynı ölçüm %98.
        vp_w = self._scroll.viewport().width()
        vp_h = self._scroll.viewport().height()
        dual = getattr(self, '_dual_page', False)
        pw = pw_ham * 1.5
        ph = ph_ham * 1.5
        if dual:
            pw *= 2
        margin = 20
        fit_w = (vp_w - margin) / pw if pw > 0 else 0.75
        fit_h = (vp_h - margin) / ph if ph > 0 else 0.75
        yeni = fit_w if mode == "width" else min(fit_w, fit_h)
        self._zoom_uygula(yeni)

    def fit_width(self):
        self._fit_zoom("width")

    def fit_page(self):
        self._fit_zoom("page")

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
