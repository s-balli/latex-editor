"""PdfViewer render mixin — PDF yükleme, sayfa render, placeholder yönetimi."""

import os

import pypdfium2  # type: ignore

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout, QSpacerItem, QSizePolicy

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("PdfViewer", s)

from core.log import get_logger
from gui.pdf_render_worker import PdfRenderWorker
from gui.pdfium_lock import pdfium_lock

_logger = get_logger("pdf_viewer")


class PdfRenderMixin:

    # Sayfa pixmap'lerinin saklayıcısı LABEL'lardır (QLabel.setPixmap).
    # Burada ayrıca bir `self._cache` sözlüğü vardı: yazılıyor ve
    # sıfırlanıyordu ama HİÇBİR YERDEN OKUNMUYORDU — 20 girdi / 256 MB
    # sınırlı, ölü bir ikinci referans. Ölçüldü (2026-08-31, F2): normal
    # scroll'da label'ların tuttuklarının aynısını tuttuğu için ek maliyeti
    # sıfırdı, ama zoom sonrasında label'ın bıraktığı 7 pixmap'i tek başına
    # ayakta tutuyordu — küçük bir A4 belgesinde 19.3 MB, zoom 3.0'ta sayfa
    # başına ~40 MB'a çıkabilen görsellerde 256 MB tavanına kadar. Kaldırıldı.

    def _init_render_worker(self):
        """Arka plan render işçisini kur (PdfViewer.__init__ çağırır).

        Render UI thread'inde senkron koşuyordu: hızlı scroll/zoom'da
        görünür alana giren her sayfa bloklayıcı render edilip arayüzü
        kilitliyordu. İşçi kendi pypdfium2 handle'ını kullanır (bkz.
        pdf_render_worker docstring'i).
        """
        self._render_gen = 0
        # Parent'sız: viewer silinse bile işçi kayıt (pdf_render_worker)
        # tutar; ömrü shutdown()/stop() ile yönetilir
        self._render_worker = PdfRenderWorker()
        self._render_worker.rendered.connect(self._on_render_result)
        self._render_worker.start()

    def load_pdf(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        try:
            if self._pdf:
                with pdfium_lock:
                    self._pdf.close()
                self._pdf = None
            # Dosyayı belleğe alıp öyle aç. pypdfium2 yol üzerinden açılan
            # dokümanın sayfa verisini ihtiyaç anında TEMBEL okuyor; kullanıcının
            # main.pdf'i her derlemede yerinde truncate+yeniden yazılıyor
            # (derle.sh'nin mv'si ayrı dosya sistemine kopya+unlink'e düşüyor).
            # Panelde gezinirken eski handle yarım yazılmış dosyadan okuyunca
            # pdfium C++ tarafında süreci düşürebiliyor. İki arka plan işçisi
            # (pdf_render_worker, pdf_search_worker) bu kalıba çoktan geçmişti;
            # UI handle'ı dışarıda kalmıştı.
            with open(path, "rb") as f:
                veri = f.read()
            with pdfium_lock:
                self._pdf = pypdfium2.PdfDocument(veri)
                self._page_count = len(self._pdf)
            self._sayfa_pt.clear()
            self._pdf_path = path
            self._current_page = 0
            self._render_gen += 1
            self._pres_cache.clear()
            self._render_worker.open_document(path, self._render_gen)
            self._search_worker.open_document(path, self._render_gen)
            self._create_placeholders()
            self.update_bookmarks()
            self._clear_search()
            self._restore_search()      # açık arama derlemeyi atlatsın
            self._update_nav()
            QTimer.singleShot(50, self._render_visible)
            self._btn_save.setEnabled(True)
            _logger.info("PDF yüklendi: %s (%d sayfa)", path, self._page_count)
            return True
        except Exception:
            _logger.error("PDF yüklenemedi: %s", path, exc_info=True)
            # TAM temizlik: eskiden burada yalnız `_clear_pages()` vardı, o da
            # sadece etiketleri ve yerleşimi atıyordu. ÖNCEKİ belgenin durumu
            # kalıyordu (ölçüldü): sayfa sayacı "Sayfa 1 / 3" demeye devam
            # ediyor ve "Farklı Kaydet" etkin kalıp ÖNCEKİ PDF'i kaydediyordu.
            # `clear()` belgeyi de kapatıyor; `_pdf` yarı yolda açılmış
            # kalmışsa (istisna `len(self._pdf)` sırasında geldiyse) burada
            # sızmadan kapanıyor.
            self.clear()
            self._show_message(_("PDF açılamadı, derleme başarısız olmuş veya dosya bozuk olabilir."))
            return False

    def refresh(self):
        if self._pdf_path and os.path.exists(self._pdf_path):
            self.load_pdf(self._pdf_path)

    def _toggle_dual_page(self, checked: bool):
        self._dual_page = checked
        if self._pdf:
            self._pres_cache.clear()
            self._create_placeholders()
            QTimer.singleShot(50, self._render_visible)
            self._update_nav()

    def clear(self):
        # ÖNCE sunumdan çık. `enter_presentation` "belge var ve sayfa var"ı
        # girişte şart koşuyor; `clear()` o değişmezi sonradan çiğniyordu:
        # sunum penceresi ayrı bir tam ekran üst düzey pencere ve buraya
        # dokunulmadığı için AÇIK KALIYORDU. Ölçüldü 2026-09-06: uygulamanın
        # artık sahip olmadığı belgenin bayat karesi tam ekranda duruyor,
        # `_page_count` 0 olduğu için sağa/sola/Home sessizce hiçbir şey
        # yapmıyor (sunum donmuş görünüyor); `End` ise beş tuş dalından tek
        # sınırsız olanı olduğu için `_current_page`i -1 yapıp araç çubuğunu
        # "Sayfa 0 / 0"a düşürüyor.
        # Ulaşılabilir yol: sunum sürerken arka planda bir derleme başarısız
        # olur (compile_ops: PDF gösterilemezse clear()); ayrıca tab_ops
        # (tümünü kapat / son sekme) ve file_ops de buraya geliyor.
        # Ayrı bir yıkım kopyası YAZILMIYOR, var olan çıkış yolu çağrılıyor
        # (bkz. aşağıdaki close_pdf notu: ikinci kopya bakımda tuzak).
        if self._presentation_mode:
            self.exit_presentation()
        if self._pdf:
            with pdfium_lock:
                self._pdf.close()
            self._pdf = None
        self._sayfa_pt.clear()
        self._pdf_path = ""
        self._btn_save.setEnabled(False)
        self.update_bookmarks()
        # Sayfa etiketleri birazdan yok edilecek: vurgu onların çocuğu, arama
        # sonuçları da eski dokümanın ofsetleri. İkisi de burada bırakılırsa
        # canlı kalıp ölü doküman üzerinde çalışıyordu.
        self._clear_highlight()
        self._clear_search()
        self._clear_selection()
        self._page_count = 0
        self._current_page = 0
        self._render_gen += 1
        self._render_worker.open_document("", self._render_gen)
        self._search_worker.open_document("", self._render_gen)
        self._pres_cache.clear()
        self._page_labels.clear()
        for i in reversed(range(self._pages_layout.count())):
            item = self._pages_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
            self._pages_layout.removeItem(item)
        self._update_nav()

    # close_pdf kaldırıldı (2026-08-30, F3): hiçbir yerden çağrılmıyordu ve
    # clear()'ın neredeyse birebir kopyasıydı. İki kopya bulunması bakımda
    # tuzaktı — bu turda B1/B2 düzeltmeleri ikisine de ayrı ayrı eklenmişti.
    # Belge kapatmak isteyen clear() kullanmalı.

    def shutdown(self):
        """Uygulama kapanışı: render işçisini durdur ve bekle (QThread
        yok edilirken çalışıyor kalması 'destroyed while running' çökmesi)."""
        w = getattr(self, "_render_worker", None)
        if w is not None:
            w.stop()
            if w.isRunning():
                w.wait(6000)   # uç zoomda tek sayfa ~3sn; stop iş başına denetlenir
        sw = getattr(self, "_search_worker", None)
        if sw is not None:
            sw.stop()
            if sw.isRunning():
                sw.wait(6000)

    # Tek karo olarak render edilen sayfa icin ust sinir. Olculdu (2026-09-02):
    # A0 afis 3x yakinlastirmada 162.7 megapiksel ve +1031 MB; /MediaBox'i
    # 20000x20000 olan bozuk bir PDF 900 megapiksel ve +4614 MB istiyordu.
    # 1 KB'lik bir dosya boyle bir ayirma tetikleyebiliyordu.
    #
    # 40 MP ~ 160 MB. A4 (10.1 MP) ve A3 (20.3 MP) en yuksek yakinlastirmada
    # bile sinirin altinda kaliyor, yani gundelik belgede hicbir sey degismiyor.
    # A0 gibi buyuk boylar sinira dayaninca daha fazla buyumuyor.
    _MAX_PIKSEL = 40_000_000

    def _tavanli_olcek(self, w_pt: float, h_pt: float) -> float:
        """Istenen olcek, piksel tavaniyla sinirli (en-boy orani korunur)."""
        olcek = 1.5 * self._zoom
        if w_pt > 0 and h_pt > 0:
            piksel = w_pt * h_pt * olcek * olcek
            if piksel > self._MAX_PIKSEL:
                olcek = (self._MAX_PIKSEL / (w_pt * h_pt)) ** 0.5
        return olcek

    def _olcek(self, index: int) -> float:
        """Sayfanin efektif olcegi. Render, yer tutucu boyutu ve TUM koordinat
        donusumleri (arama vurgusu, secim, SyncTeX) bunu kullanmali; biri
        tavansiz olceye donerse buyuk sayfalarda koordinatlar kayar.

        Boyut onbellekte yoksa tavan uygulanmiyor: onbellek her yuklemede ve her
        yakinlastirmada _create_placeholders -> _get_page_size yolundan doluyor.
        """
        boyut = self._sayfa_pt.get(index)
        return self._tavanli_olcek(*boyut) if boyut else 1.5 * self._zoom

    def _get_page_size(self, index: int):
        if not self._pdf or index >= self._page_count:
            return (100, 100)
        # Bozuk bir sayfada pdfium istisna atiyor. Eskiden bu, zoom
        # dongusunun (_update_page_sizes) ORTASINDA kaciyordu: bir kisim
        # etiket yeni olcekte, kalani eskisinde kaliyordu ve olcek/koordinat
        # eslesmesi bozuldugu icin arama vurgusu, secim ve SyncTeX kayiyordu.
        # Simdi o sayfa onceki boyutunu (yoksa varsayilani) koruyor, dongu
        # devam ediyor.
        try:
            with pdfium_lock:
                page = self._pdf[index]
                w_pt, h_pt = page.get_width(), page.get_height()
        except Exception:
            _logger.warning("Sayfa boyutu okunamadi: %d", index, exc_info=True)
            w_pt, h_pt = self._sayfa_pt.get(index, (612.0, 792.0))
        self._sayfa_pt[index] = (w_pt, h_pt)
        scale = self._tavanli_olcek(w_pt, h_pt)
        return (max(int(w_pt * scale), 50), max(int(h_pt * scale), 50))

    # Yer tutucu kenarlığı `border_input`: `_ui_setup.apply_theme` de aynı
    # anahtarı kullanıyor. Eskiden burada `border_separator` yazıyordu ve
    # kenarlık, tema yeniden uygulanır uygulanmaz renk değiştiriyordu (yedi
    # temanın altısında; dört temada kurulumda kenarlık zeminle aynı olduğu
    # için hiç görünmüyor, sonra beliriyordu).

    def _create_placeholders(self):
        # Sayfa etiketleri yenileniyor: vurgu eskisinin çocuğuydu. Çift-sayfa
        # geçişi bu yoldan geliyor ve tek başına _clear_highlight çağırmıyordu.
        self._clear_highlight()
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
                label.setStyleSheet(f"background: {self._theme['bg_pdf_placeholder']}; border: 1px solid {self._theme['border_input']};")
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
                    label.setStyleSheet(f"background: {self._theme['bg_pdf_placeholder']}; border: 1px solid {self._theme['border_input']};")
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

    def _request_render(self, index: int):
        """Sayfayı arka planda render et; sonuç _on_render_result'a düşer.

        Label'lar yükleme anında doğru boyutla kurulduğu için scroll/konum
        hesapları pixmapi beklemez; placeholder üstünde çalışır, görsel
        gelince dolar.
        """
        if not self._pdf or index >= self._page_count:
            return
        self._render_worker.submit(self._render_gen, index,
                                   self._olcek(index), self._invert_colors)

    def _on_render_result(self, gen: int, index: int, scale: float,
                          invert: bool, image: QImage):
        if gen != self._render_gen or not self._pdf:
            return                      # doküman değişti/yenilendi: bayat sonuç
        if scale != self._olcek(index) or invert != self._invert_colors:
            return                      # zoom/renk tercihi değişti: bayat sonuç
        if index >= len(self._page_labels):
            return
        label = self._page_labels[index]
        if label.pixmap() is None or label.pixmap().isNull():
            label.setPixmap(QPixmap.fromImage(image))
            label.setStyleSheet("")

    def _ilk_gorunur_aday(self, scroll_y: int) -> int:
        """Görünür pencerenin BAŞLADIĞI etiketi ikili aramayla bul.

        Etiketler belge sırasında ve dikey yerleşimde, yani `label_y` azalmıyor;
        `label_y + yükseklik >= scroll_y - 200` yordamı bu sırada tek yerde
        False'tan True'ya dönüyor. Doğrusal tarama bunu sayfa 0'dan başlayarak
        buluyordu: 500 sayfalık PDF'in sonunda scroll başına 500 mapTo çağrısı.

        TEK İSTİSNA çift sayfa modu: bir satırdaki iki etiketin `label_y`si
        EŞİT ama yükseklikleri farklı olabilir, dolayısıyla yordam o satırda
        True→False dönebilir. Bu yüzden bulunan indisten bir geri gidilir —
        satırda en çok iki etiket var. Fazladan bakılan etiket zararsız:
        döngü görünürlüğü zaten yeniden sınıyor.
        """
        esik = scroll_y - 200
        lo, hi = 0, min(len(self._page_labels), self._page_count)
        while lo < hi:
            mid = (lo + hi) // 2
            lb = self._page_labels[mid]
            if lb.mapTo(self._pages_widget, QPoint(0, 0)).y() + lb.height() >= esik:
                hi = mid
            else:
                lo = mid + 1
        return max(0, lo - 1)

    def _render_visible(self):
        if not self._page_labels:
            return
        viewport_height = self._scroll.viewport().rect().height()
        scroll_y = self._scroll.verticalScrollBar().value()

        bas = self._ilk_gorunur_aday(scroll_y)
        for i in range(bas, len(self._page_labels)):
            label = self._page_labels[i]
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

            # Görünür pencerenin ALT ucu. Üst ucu _ilk_gorunur_aday hallediyor;
            # ikisi birlikte döngüyü O(sayfa) yerine O(görünür sayfa) yapıyor.
            if label_top > viewport_height + 200:
                break

            if visible and (label.pixmap() is None or label.pixmap().isNull()):
                self._request_render(i)

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
            label.setStyleSheet(f"background: {self._theme['bg_pdf_placeholder']}; border: 1px solid {self._theme['border_input']};")

        # Arama vurgusu yeni ölçekte YENİDEN çizilir. Yukarıdaki
        # `_clear_search_highlights()` onu siliyordu ve kimse geri
        # getirmiyordu: sonuç listesi ve "N / M" sayacı duruyor ama ekranda
        # vurgu yok (ölçüldü 2026-09-05, zoom_in ve zoom_out'ta 5 -> 0).
        # Vurgu, etiketlerin YENİ boyutu kurulduktan SONRA çiziliyor; sıra
        # değişirse eski ölçekte konumlanır. `_draw_search_highlight` artık
        # pixmap beklemiyor (bkz. _search.py), yani render'ı da beklemiyor.
        #
        # KOŞUL YOK: `_draw_search_highlight` boş sonuç listesinde zaten
        # erken dönüyor. Buraya bir `if _search_results` konmuştu, mutasyonla
        # ölü çıktı (kaldırıldığında hiçbir test düşmüyordu).
        self._draw_search_highlight(self._search_index)
