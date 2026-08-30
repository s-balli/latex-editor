"""PdfViewer sunum modu mixin — tam ekran sunum, tuş/mouse navigasyonu."""

from gui.pdfium_lock import pdfium_lock
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

from gui.pdf_render import render_page_to_pixmap


class PdfPresentationMixin:

    def enter_presentation(self):
        if not self._pdf or self._page_count == 0:
            return
        self._presentation_mode = True

        if self._presentation_widget is None:
            self._presentation_widget = QWidget()
            self._presentation_widget.setStyleSheet("background: #000;")
            layout = QVBoxLayout(self._presentation_widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            self._presentation_label = QLabel()
            self._presentation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._presentation_label)
            self._presentation_widget.installEventFilter(self)
            self._presentation_label.setMouseTracking(True)
            self._presentation_label.installEventFilter(self)

        self._presentation_render()
        self._presentation_widget.showFullScreen()

    def exit_presentation(self):
        self._presentation_mode = False
        if self._presentation_widget:
            self._presentation_widget.close()
            self._presentation_widget.deleteLater()
            self._presentation_widget = None
            self._presentation_label = None
        self._scroll_to_page(self._current_page)

    def _presentation_render(self):
        if not self._presentation_label or not self._pdf:
            return
        idx = self._current_page
        if idx >= self._page_count:
            return

        screen = self._presentation_widget.screen()
        if screen:
            screen_size = screen.availableSize()
        else:
            screen_size = self._presentation_widget.size()

        with pdfium_lock:
            page = self._pdf[idx]
            pw, ph = page.get_width(), page.get_height()
        if pw <= 0 or ph <= 0:
            return

        margin = 20
        max_w = screen_size.width() - margin
        max_h = screen_size.height() - margin
        scale_w = max_w / pw
        scale_h = max_h / ph
        scale = min(scale_w, scale_h, 3.0)

        key = ("pres", idx, scale, self._invert_colors)
        if key not in self._pres_cache:
            with pdfium_lock:
                self._pres_cache[key] = render_page_to_pixmap(
                    page, scale, self._invert_colors)
            while len(self._pres_cache) > 10:
                oldest = next(iter(self._pres_cache))
                del self._pres_cache[oldest]

        pixmap = self._pres_cache[key]
        self._presentation_label.setPixmap(pixmap)
        self._presentation_label.setFixedSize(pixmap.size())

    def _presentation_key_event(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.exit_presentation()
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Space, Qt.Key.Key_Down):
            if self._current_page < self._page_count - 1:
                self._current_page += 1
                self._update_nav()
                self._presentation_render()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            if self._current_page > 0:
                self._current_page -= 1
                self._update_nav()
                self._presentation_render()
            return
        if key == Qt.Key.Key_Home:
            self._current_page = 0
            self._update_nav()
            self._presentation_render()
            return
        if key == Qt.Key.Key_End:
            self._current_page = self._page_count - 1
            self._update_nav()
            self._presentation_render()
            return
        super().keyPressEvent(event)
