"""PdfViewer render mixin — PDF yükleme, sayfa render, placeholder yönetimi."""

import os

import pypdfium2  # type: ignore

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout, QSpacerItem, QSizePolicy

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("PdfViewer", s)

from core.log import get_logger
from gui.pdf_render_worker import PdfRenderWorker

_logger = get_logger("pdf_viewer")


class PdfRenderMixin:

    # Cache sınırları: sayfa görselleri paylaşımlı QPixmap (label ile aynı
    # veri), ama yine de üst sınır şart: zoom 3.0'ta A4 ~40MB/sayfa; 20
    # görsel ~800MB'a çıkardı. 256MB bayt sınırı bunu keser.
    _CACHE_MAX_COUNT = 20
    _CACHE_MAX_BYTES = 256 * 1024 * 1024

    def _init_render_worker(self):
        """Arka plan render işçisini kur (PdfViewer.__init__ çağırır).

        Render UI thread'inde senkron koşuyordu: hızlı scroll/zoom'da
        görünür alana giren her sayfa bloklayıcı render edilip arayüzü
        kilitliyordu. İşçi kendi pypdfium2 handle'ını kullanır (bkz.
        pdf_render_worker docstring'i).
        """
        self._render_gen = 0
        self._cache_bytes = 0
        # Parent'sız: viewer silinse bile işçi kayıt (pdf_render_worker)
        # tutar; ömrü shutdown()/stop() ile yönetilir
        self._render_worker = PdfRenderWorker()
        self._render_worker.rendered.connect(self._on_render_result)
        self._render_worker.start()

    def load_pdf(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        try:
            if self._pdf:
                self._pdf.close()
                self._pdf = None
            self._pdf = pypdfium2.PdfDocument(path)
            self._pdf_path = path
            self._page_count = len(self._pdf)
            self._current_page = 0
            self._render_gen += 1
            self._cache_reset()
            self._pres_cache.clear()
            self._render_worker.open_document(path, self._render_gen)
            self._search_worker.open_document(path, self._render_gen)
            self._create_placeholders()
            self.update_bookmarks()
            self._clear_search()
            self._update_nav()
            QTimer.singleShot(50, self._render_visible)
            self._btn_save.setEnabled(True)
            _logger.info("PDF yüklendi: %s (%d sayfa)", path, self._page_count)
            return True
        except Exception:
            _logger.error("PDF yüklenemedi: %s", path, exc_info=True)
            self._pdf = None
            self._render_gen += 1
            self._render_worker.open_document("", self._render_gen)
            self._search_worker.open_document("", self._render_gen)
            self._clear_pages()
            self._show_message(_("PDF açılamadı — derleme başarısız olmuş veya dosya bozuk olabilir."))
            return False

    def refresh(self):
        if self._pdf_path and os.path.exists(self._pdf_path):
            self.load_pdf(self._pdf_path)

    def _toggle_dual_page(self, checked: bool):
        self._dual_page = checked
        if self._pdf:
            self._cache_reset()
            self._pres_cache.clear()
            self._create_placeholders()
            QTimer.singleShot(50, self._render_visible)
            self._update_nav()

    def clear(self):
        if self._pdf:
            self._pdf.close()
            self._pdf = None
        self._pdf_path = ""
        self._btn_save.setEnabled(False)
        self.update_bookmarks()
        self._clear_selection()
        self._page_count = 0
        self._current_page = 0
        self._render_gen += 1
        self._render_worker.open_document("", self._render_gen)
        self._search_worker.open_document("", self._render_gen)
        self._cache_reset()
        self._pres_cache.clear()
        self._page_labels.clear()
        for i in reversed(range(self._pages_layout.count())):
            item = self._pages_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
            self._pages_layout.removeItem(item)
        self._update_nav()

    def close_pdf(self):
        if self._pdf:
            self._pdf.close()
            self._pdf = None
        self._clear_highlight()
        self._clear_pages()
        self._render_gen += 1
        self._render_worker.open_document("", self._render_gen)
        self._search_worker.open_document("", self._render_gen)
        self._cache_reset()
        self._pres_cache.clear()
        self._page_count = 0
        self._current_page = 0
        self._update_nav()

    def shutdown(self):
        """Uygulama kapanışı: render işçisini durdur ve bekle (QThread
        yok edilirken çalışıyor kalması 'destroyed while running' çökmesi)."""
        w = getattr(self, "_render_worker", None)
        if w is not None:
            w.stop()
            if w.isRunning():
                w.wait(6000)   # uç zoomda tek sayfa ~3sn; stop iş başına denetlenir
        sw = getattr(self, "_search_worker", None)
        if sw is not None:
            sw.stop()
            if sw.isRunning():
                sw.wait(6000)

    def _get_page_size(self, index: int):
        if not self._pdf or index >= self._page_count:
            return (100, 100)
        page = self._pdf[index]
        scale = 1.5 * self._zoom
        w = int(page.get_width() * scale)
        h = int(page.get_height() * scale)
        return (max(w, 50), max(h, 50))

    def _create_placeholders(self):
        self._clear_pages()
        if not self._pdf:
            return
        if self._dual_page:
            self._create_dual_placeholders()
        else:
            for i in range(self._page_count):
                w, h = self._get_page_size(i)
                label = QLabel()
                label.setFixedSize(w, h)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet(f"background: {self._theme['bg_pdf_placeholder']}; border: 1px solid {self._theme['border_separator']};")
                label.setMouseTracking(True)
                label.installEventFilter(self)
                self._page_labels.append(label)
                self._pages_layout.addWidget(label)

    def _create_dual_placeholders(self):
        i = 0
        while i < self._page_count:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            for j in range(2):
                if i + j < self._page_count:
                    w, h = self._get_page_size(i + j)
                    label = QLabel()
                    label.setFixedSize(w, h)
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    label.setStyleSheet(f"background: {self._theme['bg_pdf_placeholder']}; border: 1px solid {self._theme['border_separator']};")
                    label.setMouseTracking(True)
                    label.installEventFilter(self)
                    self._page_labels.append(label)
                    row.addWidget(label)
                else:
                    row.addSpacerItem(QSpacerItem(50, 50, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
            row_widget = QWidget()
            row_widget.setLayout(row)
            self._pages_layout.addWidget(row_widget)
            i += 2

    def _request_render(self, index: int):
        """Sayfayı arka planda render et; sonuç _on_render_result'a düşer.

        Label'lar yükleme anında doğru boyutla kurulduğu için scroll/konum
        hesapları pixmapi beklemez; placeholder üstünde çalışır, görsel
        gelince dolar.
        """
        if not self._pdf or index >= self._page_count:
            return
        self._render_worker.submit(self._render_gen, index,
                                   1.5 * self._zoom, self._invert_colors)

    def _on_render_result(self, gen: int, index: int, scale: float,
                          invert: bool, image: QImage):
        if gen != self._render_gen or not self._pdf:
            return                      # doküman değişti/yenilendi: bayat sonuç
        if scale != 1.5 * self._zoom or invert != self._invert_colors:
            return                      # zoom/renk tercihi değişti: bayat sonuç
        if index >= len(self._page_labels):
            return
        pixmap = QPixmap.fromImage(image)
        self._cache_put(index, pixmap)
        label = self._page_labels[index]
        if label.pixmap() is None or label.pixmap().isNull():
            label.setPixmap(pixmap)
            label.setStyleSheet("")

    def _cache_put(self, index: int, pixmap: QPixmap):
        """Cache'e koy; sayı VE bayt sınırını aşınca en eskisini at.

        Label'lar pixmapi paylaşımlı tuttuğundan asıl saklayıcı onlardır;
        bu cache yalnızca sınırlı bir ikinci referans tutar.
        """
        if index in self._cache:
            del self._cache[index]
        self._cache[index] = pixmap
        self._cache_bytes += pixmap.width() * pixmap.height() * 4
        while (len(self._cache) > self._CACHE_MAX_COUNT
               or (self._cache_bytes > self._CACHE_MAX_BYTES
                   and len(self._cache) > 1)):
            oldest = next(iter(self._cache))
            dropped = self._cache.pop(oldest)
            self._cache_bytes -= dropped.width() * dropped.height() * 4

    def _cache_reset(self):
        self._cache.clear()
        self._cache_bytes = 0

    def _render_visible(self):
        if not self._page_labels:
            return
        viewport_height = self._scroll.viewport().rect().height()
        scroll_y = self._scroll.verticalScrollBar().value()

        for i, label in enumerate(self._page_labels):
            if i >= self._page_count:
                break
            label_y = label.mapTo(self._pages_widget, QPoint(0, 0)).y()
            label_top = label_y - scroll_y
            label_bottom = label_top + label.height()

            label_bottom_abs = label_y + label.height()
            if label_y <= scroll_y < label_bottom_abs:
                if self._current_page != i:
                    self._current_page = i
                    self._update_nav()

            visible = label_bottom >= -200 and label_top <= viewport_height + 200

            # Etiketler dikey sıralı: viewport altına düşen ilk etiketten
            # sonrakiler de görünmez — büyük PDF'lerde döngü başına yüzlerce
            # mapTo çağrısından kurtulur.
            if label_top > viewport_height + 200:
                break

            if visible and (label.pixmap() is None or label.pixmap().isNull()):
                self._request_render(i)

    def _on_scroll(self):
        self._render_visible()

    def _clear_pages(self):
        self._page_labels.clear()
        # Tum widget'lari ve row widget'larini temizle
        while self._pages_layout.count():
            item = self._pages_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            del item

    def _update_page_sizes(self):
        self._clear_highlight()
        self._clear_search_highlights()
        self._clear_selection()
        for i, label in enumerate(self._page_labels):
            if i >= self._page_count:
                break
            w, h = self._get_page_size(i)
            label.setFixedSize(w, h)
            label.setPixmap(QPixmap())
            label.setStyleSheet(f"background: {self._theme['bg_pdf_placeholder']}; border: 1px solid {self._theme['border_separator']};")
