"""PdfViewer SyncTeX mixin — ileri/geri arama koordinat dönüşümü."""

from PyQt6.QtCore import QPoint, QTimer
from gui.pdf_donusum import geometri, gorselden_syncteze, synctex_kutusu
from gui.pdfium_lock import pdfium_lock


class PdfSyncTexMixin:

    def _handle_reverse_click(self, pos, obj):
        if not self._pdf or not self._pdf_path:
            return
        if obj != self._pages_widget and obj not in self._page_labels:
            return
        for i, label in enumerate(self._page_labels):
            if i >= self._page_count:
                break
            scale = self._olcek(i)
            label_pos = label.mapFrom(obj, pos) if obj != label else pos
            if label.rect().contains(label_pos):
                # SyncTeX'in duzlemi /Rotate 0'da ekranla ortusuyor ama
                # dondurulmus sayfada ortusmuyor (bkz. gui/pdf_donusum.py).
                with pdfium_lock:
                    g = geometri(self._pdf[i])
                x_pts, y_pts = gorselden_syncteze(
                    g, label_pos.x(), label_pos.y(), scale)
                self.reverse_search_requested.emit(i + 1, x_pts, y_pts, self._pdf_path)
                return

    def scroll_to_position(self, page_num: int, x: float, y: float,
                           left: float = 0.0, width: float = 0.0, height: float = 0.0):
        idx = page_num - 1
        if idx < 0 or idx >= len(self._page_labels):
            return
        label = self._page_labels[idx]
        scale = self._olcek(idx)
        with pdfium_lock:
            g = geometri(self._pdf[idx])
        x_pixel, y_pixel, w_pixel, h_kutu = synctex_kutusu(
            g, left, y, width, height, scale)

        if label.pixmap() is None or label.pixmap().isNull():
            # Label yüklemede doğru boyutla kurulmuş; pixmap arka planda
            # gelir, vurgu/konum hesabı onu beklemez
            self._request_render(idx)

        h_pixel = h_kutu if height else 20
        self._show_highlight(label, int(x_pixel), int(y_pixel), h_pixel, w_pixel)

        abs_y = label.mapTo(self._pages_widget, QPoint(0, 0)).y() + int(y_pixel)
        viewport_height = self._scroll.viewport().height()
        self._scroll.verticalScrollBar().setValue(max(0, abs_y - viewport_height // 2))
        self._current_page = idx
        self._update_nav()
        QTimer.singleShot(100, self._render_visible)
