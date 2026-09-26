"""PdfViewer sunum modu mixin — tam ekran sunum, tuş/mouse navigasyonu."""

from gui.pdfium_lock import pdfium_lock
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

from gui.pdf_render import render_page_to_pixmap
from core.log import get_logger

_logger = get_logger("pdf_viewer")

# Sunum kumandaları klavye gibi davranıyor ve ileri/geri için PageDown/PageUp
# gönderiyor; Backspace de slayt ve PDF gösterme programlarının ortak "geri"
# tuşu. Üçü de işlenmiyordu. ÖLÇÜLDÜ (2026-09-26, gerçek pencereye
# WM_KEYDOWN VK_NEXT gönderildi): sayfa değişmedi.
_ILERI = (Qt.Key.Key_Right, Qt.Key.Key_Space, Qt.Key.Key_Down,
          Qt.Key.Key_PageDown)
_GERI = (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp,
         Qt.Key.Key_Backspace)


class PdfPresentationMixin:

    def enter_presentation(self):
        if not self._pdf or self._page_count == 0:
            return
        self._presentation_mode = True

        if self._presentation_widget is None:
            # Sunum KENDİ sayfasını tutuyor, `_current_page` ana
            # görüntüleyicinin. Tek değişkendiler ve sunumu dışarıdan oynatan
            # her yol onu yazıyordu. ÖLÇÜLDÜ (2026-09-26, sekiz sayfalık belge,
            # sunum 6. sayfada): arkada biten derleme (`load_pdf`) sayacı 0'a
            # çekti, ekranda ESKİ PDF'in karesi kaldı ve sonraki Sağ tuşu 2.
            # sayfaya gitti; derleme sonrası ileri arama imlecin sayfasına
            # götürdü. İki ekranlı düzende ana görüntüleyicide kaydırmak da
            # aynı değişkeni yazıyor. Çıkışta ana görüntüleyici sunumun
            # kaldığı sayfaya gidiyor.
            #
            # Başlangıç sayfası YALNIZ yeni sunumda alınıyor: sunum sürerken
            # ana pencerede yeniden F5 (iki ekranda erişilebilir) onu ana
            # görüntüleyicinin sayfasına atmasın.
            self._sunum_sayfasi = self._current_page
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
            # Görüntüleyicinin ekranında açılıyor. Konumu verilmeyen yeni üst
            # pencereyi Qt kendisi yerleştiriyordu. ÖLÇÜLDÜ (2026-09-26, iki
            # gerçek ekran, imleç birincil ekranda): uygulama penceresi ikinci
            # ekrandayken sunum birincil ekranda açıldı. Projektörü ikinci
            # ekran olarak bağlayıp pencereyi oraya taşıyan kullanıcı slaytı
            # dizüstünün ekranında buluyordu. Kare de bu ekrana göre
            # çiziliyor: `_presentation_render` pencerenin ekranını okuyor.
            ekran = self.screen()
            if ekran is not None:
                self._presentation_widget.setGeometry(ekran.geometry())

        self._sunum_git(self._sunum_sayfasi)
        self._presentation_widget.showFullScreen()

    def exit_presentation(self):
        self._presentation_mode = False
        if self._presentation_widget:
            self._presentation_widget.close()
            self._presentation_widget.deleteLater()
            self._presentation_widget = None
            self._presentation_label = None
        self._scroll_to_page(self._sunum_sayfasi)

    def _sunum_git(self, hedef: int):
        """Sunumu `hedef` sayfaya götür ve çiz; sınırlarda durur."""
        self._sunum_sayfasi = max(0, min(hedef, self._page_count - 1))
        self._presentation_render()

    def _presentation_render(self):
        if not self._presentation_label or not self._pdf:
            return
        idx = self._sunum_sayfasi
        if idx >= self._page_count:
            return

        # size(), availableSize() DEĞİL. Pencere `showFullScreen()` ile
        # açılıyor ve görev çubuğunun ÜSTÜNÜ de kaplıyor; availableSize ise
        # görev çubuğunu düşüyor. ÖLÇÜLDÜ (2026-09-05, gerçek tam ekran
        # pencere açılıp yüksekliği okundu): ekran 2560x1080, availableSize
        # 2560x1050, pencere 2560x1080. A4 slayt 1080 px'lik pencerede 1030
        # px çiziliyordu, yani altta 50 px kullanılmayan bant ve %2.8 kayıp.
        screen = self._presentation_widget.screen()
        if screen:
            screen_size = screen.size()
        else:
            screen_size = self._presentation_widget.size()

        # Sunum modunda (F5) pdfium cagrilari korumasizdi: bozuk bir sayfada
        # istisna slot'tan disari cikiyor, sunum yarim ekranla kaliyordu.
        try:
            with pdfium_lock:
                page = self._pdf[idx]
                pw, ph = page.get_width(), page.get_height()
        except Exception:
            _logger.warning("Sunum: sayfa acilamadi: %d", idx, exc_info=True)
            return
        if pw <= 0 or ph <= 0:
            return

        # Ölçekte 3.0 tavanı vardı ve küçük sayfalı belgede ekranı
        # doldurtmuyordu. ÖLÇÜLDÜ (2026-09-26, gerçek pdflatex beamer çıktısı,
        # 2560x1080 ekran): 4:3 slayt (363x272 pt) ekran yüksekliğinin
        # %75.6'sını, 16:9 slayt (454x255 pt) %70.9'unu kaplıyordu; 4K'da %38
        # ve %36. A4 tavana hiç varmıyor (kontrol: %98.1), önceki ölçüm onunla
        # yapılmıştı. Kareyi ekran zaten sınırlıyor.
        margin = 20
        max_w = screen_size.width() - margin
        max_h = screen_size.height() - margin
        scale_w = max_w / pw
        scale_h = max_h / ph
        scale = min(scale_w, scale_h)

        key = ("pres", idx, scale, self._invert_colors)
        if key not in self._pres_cache:
            try:
                with pdfium_lock:
                    self._pres_cache[key] = render_page_to_pixmap(
                        page, scale, self._invert_colors)
            except Exception:
                _logger.warning("Sunum: sayfa cizilemedi: %d", idx, exc_info=True)
                return
            # Kare artık ekran boyunda: 16:9 slayt 1080p'de 8.0 MB, 4K'da
            # 32.6 MB. On kare 4K'da 326 MB tutardı (tavanlıyken 42 MB); dört
            # kare 1080p'de 32 MB, 4K'da 130 MB. Önbellekte olmayan kare
            # 1080p'de 16 ms, 4K'da 67 ms'de çiziliyor (ölçüldü, aynı belge).
            while len(self._pres_cache) > 4:
                oldest = next(iter(self._pres_cache))
                del self._pres_cache[oldest]

        pixmap = self._pres_cache[key]
        self._presentation_label.setPixmap(pixmap)
        self._presentation_label.setFixedSize(pixmap.size())

    def _presentation_key_event(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.exit_presentation()
        elif key in _ILERI:
            self._sunum_git(self._sunum_sayfasi + 1)
        elif key in _GERI:
            self._sunum_git(self._sunum_sayfasi - 1)
        elif key == Qt.Key.Key_Home:
            self._sunum_git(0)
        elif key == Qt.Key.Key_End:
            self._sunum_git(self._page_count - 1)
        else:
            super().keyPressEvent(event)
