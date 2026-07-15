"""PdfViewer render mixin — PDF yükleme, sayfa render, placeholder yönetimi."""

import os

import pypdfium2  # type: ignore

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout, QSpacerItem, QSizePolicy

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("PdfViewer", s)

from core.log import get_logger
from gui.pdf_render import render_page_to_pixmap

_logger = get_logger("pdf_viewer")


class PdfRenderMixin:

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
            self._cache.clear()
            self._pres_cache.clear()
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
            self._clear_pages()
            self._show_message(_("PDF açılamadı — derleme başarısız olmuş veya dosya bozuk olabilir."))
            return False

    def refresh(self):
        if self._pdf_path and os.path.exists(self._pdf_path):
            self.load_pdf(self._pdf_path)

    def _toggle_dual_page(self, checked: bool):
        self._dual_page = checked
        if self._pdf:
            self._cache.clear()
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
        self._cache.clear()
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
        self._cache.clear()
        self._pres_cache.clear()
        self._page_count = 0
        self._current_page = 0
        self._update_nav()

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

    def _render_page(self, index: int) -> QPixmap:
        if index in self._cache:
            return self._cache[index]
        if not self._pdf or index >= self._page_count:
            return QPixmap()

        page = self._pdf[index]
        scale = 1.5 * self._zoom
        pixmap = render_page_to_pixmap(page, scale, self._invert_colors)
        self._cache[index] = pixmap
        while len(self._cache) > 20:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        return pixmap

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

            if visible and (label.pixmap() is None or label.pixmap().isNull()):
                pixmap = self._render_page(i)
                if not pixmap.isNull():
                    label.setPixmap(pixmap)
                    label.setStyleSheet("")

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
