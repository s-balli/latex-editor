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
        """Vurguyu kaldır — ebeveyn sayfa etiketi silinmiş olsa bile.

        Vurgu QLabel'ı sayfa etiketinin ÇOCUĞU, zamanlayıcı ise viewer'ın
        çocuğu: sayfa etiketleri (load_pdf, clear, çift-sayfa geçişi) 3 sn
        dolmadan yok edilirse zamanlayıcı yaşamaya devam ediyor ve ölü
        sarmalayıcıda deleteLater() RuntimeError atıyordu. İstisna bir
        sonraki satırı atladığı için alan None'lanmıyor, sonraki HER çağrı
        aynı yerde patlıyordu: zoom, sayfaya sığdır ve tüm SyncTeX atlamaları
        oturum boyunca ölüyordu. Kardeş _clear_search_highlights bu korumayı
        zaten taşıyor.
        """
        if self._highlight_label:
            try:
                self._highlight_label.deleteLater()
            except RuntimeError:
                pass          # ebeveyniyle birlikte çoktan yok edilmiş
            self._highlight_label = None
        if self._highlight_timer:
            try:
                self._highlight_timer.stop()
                self._highlight_timer.deleteLater()
            except RuntimeError:
                pass
            self._highlight_timer = None
