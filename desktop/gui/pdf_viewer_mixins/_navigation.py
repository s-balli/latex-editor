"""PdfViewer navigasyon mixin — sayfa geçişi, zoom, güncelleme."""

import os

from PyQt6.QtCore import Qt, QTimer
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

    def zoom_in(self):
        self._zoom = min(self._zoom + 0.05, 3.0)
        self._cache.clear()
        self._pres_cache.clear()
        self._update_page_sizes()
        QTimer.singleShot(50, self._render_visible)
        self._update_nav()

    def zoom_out(self):
        self._zoom = max(self._zoom - 0.05, 0.05)
        self._cache.clear()
        self._pres_cache.clear()
        self._update_page_sizes()
        QTimer.singleShot(50, self._render_visible)
        self._update_nav()

    def _fit_zoom(self, mode: str):
        """mode: 'width' veya 'page'"""
        if not self._pdf or self._page_count == 0:
            return
        page = self._pdf[0]
        vp_w = self._scroll.viewport().width()
        vp_h = self._scroll.viewport().height()
        if hasattr(self, '_bookmark_tree') and self._bookmark_tree.isVisible():
            vp_w -= self._bookmark_tree.width()
        dual = getattr(self, '_dual_page', False)
        pw = page.get_width() * 1.5
        ph = page.get_height() * 1.5
        if dual:
            pw *= 2
        margin = 20
        fit_w = (vp_w - margin) / pw if pw > 0 else 0.75
        fit_h = (vp_h - margin) / ph if ph > 0 else 0.75
        if mode == "width":
            self._zoom = fit_w
        else:
            self._zoom = min(fit_w, fit_h)
        self._zoom = max(0.05, min(self._zoom, 3.0))
        self._cache.clear()
        self._pres_cache.clear()
        self._update_page_sizes()
        QTimer.singleShot(50, self._render_visible)
        self._update_nav()

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
