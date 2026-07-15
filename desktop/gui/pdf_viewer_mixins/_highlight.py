"""PdfViewer highlight mixin — SyncTeX vurgulama."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QLabel


class PdfHighlightMixin:

    def _show_highlight(self, label: QLabel, x: int, y: int, height: int, width: int = 0):
        self._clear_highlight()
        t = self._theme
        hl = QLabel(label)
        hl.setStyleSheet(
            f"background-color: {t['pdf_hl_bg']}; "
            f"border: 2px solid {t['pdf_hl_border']}; "
            "border-radius: 2px;"
        )
        w = width if width > 0 else label.width() - x + 4
        hl.setGeometry(max(x - 4, 0), y - 2, w, max(height, 20))
        hl.show()
        hl.raise_()
        self._highlight_label = hl
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setSingleShot(True)
        self._highlight_timer.timeout.connect(self._clear_highlight)
        self._highlight_timer.start(3000)

    def _clear_highlight(self):
        if self._highlight_label:
            self._highlight_label.deleteLater()
            self._highlight_label = None
        if self._highlight_timer:
            self._highlight_timer.stop()
            self._highlight_timer.deleteLater()
            self._highlight_timer = None
