"""PDF görüntüleyici — mixin kompozisyonu ile modüler yapı."""

from PyQt6.QtCore import pyqtSignal, qInstallMessageHandler, QtMsgType, QTimer
from PyQt6.QtGui import QPixmap, QKeySequence
from PyQt6.QtWidgets import QWidget, QLabel

from gui.pdf_viewer_mixins import (
    PdfBookmarksMixin,
    PdfSearchMixin,
    PdfSelectionMixin,
    PdfHighlightMixin,
    PdfSyncTexMixin,
    PdfUISetupMixin,
    PdfRenderMixin,
    PdfNavigationMixin,
    PdfPresentationMixin,
    PdfEventsMixin,
)

# Qt'nin scroll sırasında ürettiği mapFrom uyarısını sustur
_qt_msg_handler = qInstallMessageHandler(None)
def _quiet_mapfrom(msg_type, context, msg):
    if msg_type == QtMsgType.QtWarningMsg and "mapFrom" in msg:
        return
    if _qt_msg_handler:
        _qt_msg_handler(msg_type, context, msg)
qInstallMessageHandler(_quiet_mapfrom)


class PdfViewer(
    PdfSelectionMixin,
    PdfSearchMixin,
    PdfBookmarksMixin,
    PdfUISetupMixin,
    PdfRenderMixin,
    PdfNavigationMixin,
    PdfPresentationMixin,
    PdfEventsMixin,
    PdfSyncTexMixin,
    PdfHighlightMixin,
    QWidget,
):
    reverse_search_requested = pyqtSignal(int, float, float, str)  # page, x, y, pdf_path

    def __init__(self, parent=None, *, theme: dict = None):
        super().__init__(parent)
        self._pdf = None
        self._pdf_path = ""
        self._highlight_label: QLabel | None = None
        self._highlight_timer: QTimer | None = None
        self._page_count = 0
        self._current_page = 0
        self._zoom = 0.75
        self._page_labels: list[QLabel] = []
        self._cache: dict[int, QPixmap] = {}
        self._cache_bytes = 0
        self._render_gen = 0
        self._pres_cache: dict[tuple, QPixmap] = {}
        self._invert_colors = False
        self._dual_page = False
        self._presentation_mode = False
        self._presentation_widget: QWidget | None = None
        self._presentation_label: QLabel | None = None
        self._theme = theme or {}
        self._setup_ui()
        self._init_selection_state()
        self._init_render_worker()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
            return
        super().keyPressEvent(event)

    @property
    def in_presentation(self) -> bool:
        return self._presentation_mode
