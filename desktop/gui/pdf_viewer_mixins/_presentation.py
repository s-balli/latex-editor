"""PdfViewer sunum modu mixin — tam ekran sunum, tuş/mouse navigasyonu."""

from gui.pdfium_lock import pdfium_lock
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

from gui.pdf_donusum import geometri, kullaniciya
from gui.pdf_links import get_dest_page_index, get_link_at_point
from gui.pdf_render import render_page_to_pixmap, tam_mantiksal_boy
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

# İmleç bu kadar hareketsiz kalınca slaytın üstünden kalkıyor.
_IMLEC_BEKLEME_MS = 3000


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
            self._presentation_widget.setMouseTracking(True)
            self._presentation_label.setMouseTracking(True)
            self._presentation_label.installEventFilter(self)
            self._sunum_teker = 0
            # İmleç slaytın üstünde kalıcı duruyordu. Üç saniye hareketsiz
            # kalınca gizleniyor, fare kıpırdayınca geri geliyor (slayt
            # gösterisi programlarının alışılmış davranışı).
            self._sunum_imlec_konumu = None
            self._sunum_imlec = QTimer(self._presentation_widget)
            self._sunum_imlec.setSingleShot(True)
            self._sunum_imlec.setInterval(_IMLEC_BEKLEME_MS)
            self._sunum_imlec.timeout.connect(self._sunum_imleci_gizle)
            self._sunum_imlec.start()
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

    def _sunum_baglantisi(self, olay, nesne, bekle: bool = True):
        """Sunum karesinde farenin altındaki (bağlantı, sayfa); yoksa None.

        Sayfa da dönüyor, çağıran onu bağlantıyla birlikte tutmalı: FPDF_LINK
        sayfaya ait ve sayfa nesnesi bırakılınca pdfium onu kapatıyor (ana
        görüntüleyicideki `_link_at_pos` da bu yüzden sayfayı döndürüyor).

        Kare etikete TAM oturuyor (etiket karenin mantıksal boyunda), yani
        etiketin koordinatı karenin koordinatı; siyah kenarda bağlantı yok.
        `bekle=False` imleç yolu için: kilit meşgulse beklemeden vazgeçiyor
        (bkz. _events._update_link_cursor).
        """
        if nesne is not self._presentation_label or not self._pdf:
            return None
        if not bekle and not pdfium_lock.acquire(blocking=False):
            return None
        try:
            with pdfium_lock:
                sayfa = self._pdf[self._sunum_sayfasi]
                x, y = kullaniciya(geometri(sayfa), olay.position().x(),
                                   olay.position().y(), self._sunum_olcek)
                link = get_link_at_point(sayfa.raw, x, y)
                return (link, sayfa) if link else None
        except Exception:
            return None                 # bozuk sayfa: bağlantı yok sayılır
        finally:
            if not bekle:
                pdfium_lock.release()

    def _sunum_hedefine(self, dest):
        """Belge içi bağlantının hedef sayfasına git (geçersiz hedefte kal)."""
        with pdfium_lock:
            idx = get_dest_page_index(self._pdf.raw, dest)
        if 0 <= idx < self._page_count:
            self._sunum_git(idx)

    def _sunum_tekerlek(self, delta: int):
        """Tekerleğin bir çentiği (120) bir slayt: aşağı ileri, yukarı geri.

        Dokunmatik yüzey küçük adımlar gönderiyor; çentik dolana kadar
        biriktiriliyor, yoksa her kıpırtı bir slayt atlatırdı.
        """
        self._sunum_teker += delta
        if abs(self._sunum_teker) >= 120:
            adim = 1 if self._sunum_teker < 0 else -1
            self._sunum_teker = 0
            self._sunum_git(self._sunum_sayfasi + adim)

    def _sunum_imleci_goster(self, olay, nesne):
        """Fare kıpırdadı: imleç görünsün (bağlantı üstünde el) ve sayaç baştan.

        Titreme sayılmıyor: son KABUL edilen konumdan 8 pikselden az uzaklaşan
        hareket gizli imleci geri getirmiyor ve sayacı tazelemiyor. ÖLÇÜLDÜ
        (2026-09-26, gerçek pencere): eli faredeki kullanıcıdan beş saniyede
        1-2 piksellik sekiz hareket geldi ve her biri sayacı tazeleyip imleci
        hiç gizletmedi. Yavaş ama gerçek hareket birikip eşiği aşıyor, çünkü
        karşılaştırma son olaya değil son kabul edilen konuma göre. Görünür
        imlecin biçimi (bağlantı üstünde el) her harekette güncelleniyor.
        """
        konum = olay.globalPosition().toPoint()
        onceki = self._sunum_imlec_konumu
        gercek = onceki is None or (konum - onceki).manhattanLength() >= 8
        gizli = (self._presentation_widget.cursor().shape()
                 == Qt.CursorShape.BlankCursor)
        if gizli and not gercek:
            return
        if gercek:
            self._sunum_imlec_konumu = konum
            self._sunum_imlec.start()
        bag = self._sunum_baglantisi(olay, nesne, bekle=False)
        self._presentation_widget.setCursor(
            Qt.CursorShape.PointingHandCursor if bag
            else Qt.CursorShape.ArrowCursor)

    def _sunum_imleci_gizle(self):
        if self._presentation_widget is not None:
            self._presentation_widget.setCursor(Qt.CursorShape.BlankCursor)

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
        self._sunum_olcek = scale           # bağlantı konumu bununla çözülüyor
        # Kare FİZİKSEL pikselde (bkz. _render._cizim_olcegi); etiket boyu ve
        # bağlantı konumu mantıksal ölçekte kalıyor.
        carpan = self._presentation_widget.devicePixelRatioF()

        key = ("pres", idx, scale * carpan, self._invert_colors)
        if key not in self._pres_cache:
            try:
                with pdfium_lock:
                    kare = render_page_to_pixmap(
                        page, scale * carpan, self._invert_colors)
                kare = tam_mantiksal_boy(kare, carpan)
                kare.setDevicePixelRatio(carpan)
                self._pres_cache[key] = kare
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
        self._presentation_label.setFixedSize(
            pixmap.deviceIndependentSize().toSize())

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
