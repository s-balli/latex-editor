"""PDF görüntüleyici — mixin kompozisyonu ile modüler yapı."""

from PyQt6.QtCore import pyqtSignal, QTimer
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

# Burada bir global Qt mesaj handler'ı vardı: "scroll sırasında üretilen
# mapFrom uyarısını sustur". Kaldırıldı — İKİ nedenle de işlevsizdi:
#
#   1) Süzgeç `"mapFrom" in msg` diyordu, ama bu kodun ürettiği çağrı
#      mapTo ve Qt6'nın metni "QWidget::mapTo(): parent must be in parent
#      hierarchy" (ölçüldü, Qt 6.11). İçinde "mapFrom" GEÇMİYOR; ayrı bir
#      "QWidget::mapFrom(): ..." metni var ama bu kod mapFrom hiç çağırmıyor.
#      Yani süzgeç, üretilmesi mümkün olmayan bir dizgeyi arıyordu.
#   2) Uyarının kendisi de çıkmıyor: bastırıcı devre dışıyken 181 sayfalık
#      PDF üzerinde 10 senaryo (100 adım scroll, arama + gezinme, belge
#      ortasında değişen arama, synctex 20 konum, aralık dışı konum, fare
#      seçimi, çift sayfa, sunum modu, zoom uçları, clear sonrası geç sinyal)
#      koşuldu: mapTo/mapFrom uyarısı SIFIR.
#
# Bedeli sıfır değildi: modül import edilir edilmez SÜRECİN TAMAMI için Qt
# mesaj yolunu kendi üstüne alıyordu — testler ve başka modüller dahil.
# Etiketler yükleme anında sabit boyutla ve doğru ebeveynle kuruluyor
# (_create_placeholders), mapTo zinciri hep geçerli.


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
        # Sayfa boyutlari (nokta): olcek tavani her karede yeniden
        # pdfium'a sormasin diye belge basina onbellekleniyor.
        self._sayfa_pt: dict[int, tuple[float, float]] = {}
        self._current_page = 0
        self._zoom = 0.75
        self._page_labels: list[QLabel] = []
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

    def closeEvent(self, event):
        """Kapanırken işçileri durdur.

        `shutdown()` yalnız MainWindow.closeEvent'ten çağrılıyordu; viewer
        başka bir yoldan yok edilirse (açılışta hata, GC) render ve arama
        iş parçacıkları koşar kalıyor ve QThread çalışırken yok edilince
        süreç SIGABRT ile ölüyordu. Ölçüldü (2026-09-02, dış güvenlik raporu
        4. bulgu): `close()` tek başına 6 koşudan 6'sında çökertiyordu,
        `shutdown()` eklenince 0. Bu, BAŞKA bir hatanın izini de aborta
        çevirdiği için tek başına önemli.

        shutdown() yeniden çağrılabilir: durmuş işçide stop/wait zararsız.
        """
        self.shutdown()
        super().closeEvent(event)

    def __del__(self):
        """close() cagrilmadan yok edilen viewer da isciyi durdursun.

        closeEvent yalniz close() yolunda tetikleniyor. Viewer close() olmadan
        GC ye duserse (ornegin MainWindow.__init__ arada hata verirse) surec
        yine SIGABRT ile oluyordu: 6 kosudan 6 (olculdu 2026-09-02). Bu, ASIL
        hatanin izini de siliyordu, cunku abort geriye traceback birakmiyor.

        Yorumlayici kapanirken modul durumu yarim olabilir; her sey yutuluyor.
        """
        try:
            self.shutdown()
        except Exception:
            pass

    @property
    def in_presentation(self) -> bool:
        return self._presentation_mode
