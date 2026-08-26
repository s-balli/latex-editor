"""PdfViewer SyncTeX mixin — ileri/geri arama koordinat dönüşümü."""

from PyQt6.QtCore import QPoint, QTimer


class PdfSyncTexMixin:

    def _handle_reverse_click(self, pos, obj):
        if not self._pdf or not self._pdf_path:
            return
        if obj != self._pages_widget and obj not in self._page_labels:
            return
        scale = 1.5 * self._zoom
        for i, label in enumerate(self._page_labels):
            if i >= self._page_count:
                break
            label_pos = label.mapFrom(obj, pos) if obj != label else pos
            if label.rect().contains(label_pos):
                x_pts = label_pos.x() / scale
                y_pts = label_pos.y() / scale
                self.reverse_search_requested.emit(i + 1, x_pts, y_pts, self._pdf_path)
                return

    def scroll_to_position(self, page_num: int, x: float, y: float,
                           left: float = 0.0, width: float = 0.0, height: float = 0.0):
        idx = page_num - 1
        if idx < 0 or idx >= len(self._page_labels):
            return
        label = self._page_labels[idx]
        scale = 1.5 * self._zoom
        y_pixel = (y - height) * scale
        x_pixel = left * scale
        w_pixel = int(width * scale) if width else 0

        if label.pixmap() is None or label.pixmap().isNull():
            # Label yüklemede doğru boyutla kurulmuş; pixmap arka planda
            # gelir, vurgu/konum hesabı onu beklemez
            self._request_render(idx)

        h_pixel = int(height * scale) if height else 20
        self._show_highlight(label, int(x_pixel), int(y_pixel), h_pixel, w_pixel)

        abs_y = label.mapTo(self._pages_widget, QPoint(0, 0)).y() + int(y_pixel)
        viewport_height = self._scroll.viewport().height()
        self._scroll.verticalScrollBar().setValue(max(0, abs_y - viewport_height // 2))
        self._current_page = idx
        self._update_nav()
        QTimer.singleShot(100, self._render_visible)
