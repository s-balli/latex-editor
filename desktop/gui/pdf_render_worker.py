"""PDF sayfa render işçisi — render'ı UI thread'inden kaldırır.

Tek uzun ömürlü QThread (synctex_worker deseni). İşçi KENDİ
pypdfium2.PdfDocument'ını açar: pdfium handle'ları iş parçacıkları arasında
paylaşılamaz; UI tarafının dokümanıyla (arama/link/sayfa boyutu) aynı
handle'ı kullanacak olsak veri yarışı doğardı. İki bağımsız handle =
paylaşılan durum yok.

Sıralama: submit() çağrı başına dedup edilir (aynı sayfanın son isteği
kazanır; hızlı scroll'da ara ölçekler boşa render edilmez).
open_document(yeni gen) bekleyenleri temizler. Sonuç `rendered(gen, idx,
scale, invert, QImage)` sinyaliyle döner; UI tarafı bayat gen/scale/invert
sonucunu düşürür (zoom değişmiş, doküman yenilenmiş vs). QImage'ın buferı
.copy() ile ayrıldığından sinyal kuyruğu üzerinden geçişi güvenlidir;
QPixmap oluşturma (GUI thread zorunluluğu) UI tarafında kalır.
"""

import atexit
import threading

import pypdfium2  # type: ignore

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from gui.pdf_render import render_page_to_qimage
from gui.pdfium_lock import pdfium_lock

# Çalışan işçilere güçlü referans: viewer'ı shutdown etmeyen kod (testler,
# eski kullanım) işçiyi GC'ye düşürünce QThread çalışırken yok edilip
# süreç öldürebilirdi. run() bitince kayıttan düşer; süreç çıkışında
# atexit kalanları durdurur.
_alive_workers: set["PdfRenderWorker"] = set()

# Acilis kac kez yeniden denensin (bkz. _run_loop).
_MAX_ACILIS_DENEMESI = 3


def _stop_all_at_exit():
    for w in list(_alive_workers):
        try:
            w.stop()
            # Uç zoomda tek sayfa render'ı ~3sn sürebilir; stop iş başına
            # denetlendiğinden en kötü durum bir işin bitmesidir
            w.wait(6000)
        except Exception:
            pass


atexit.register(_stop_all_at_exit)


class PdfRenderWorker(QThread):
    """Arka planda sayfa render eden işçi; kendi doküman handle'ını yönetir.

    Parent'sız yaratılır (viewer'a bağlanmaz): viewer silinmesi işçiyi
    etkilemez; ömrü run() döngüsü ve açıkça stop() ile yönetilir.
    """

    rendered = pyqtSignal(int, int, float, bool, QImage)

    def __init__(self):
        super().__init__()
        self._cond = threading.Condition()
        self._stop = False
        # idx -> (gen, scale, invert); dedup: aynı sayfanın son isteği kalır
        self._pending: dict[int, tuple[int, float, bool]] = {}
        self._wanted: tuple[str, int] | None = None   # (path, gen)
        # Doküman handle'ına yalnızca run() dokunur (kilitsiz alan)
        self._doc = None
        self._doc_key: tuple[str, int] | None = None
        # Acilis basarisiz olursa SINIRLI kez yeniden denenir. `_doc_key`i bos
        # birakip dongune birakmak ISE YARAMAZ: bekleme kosulu
        # `_wanted == _doc_key` oldugu icin isci %100 CPU ile doner.
        self._acilis_denemesi = 0

    # --- UI thread'inden çağrılır ---

    def open_document(self, path: str, gen: int):
        """Render edilecek dokümanı bildir; boş path işçinin handle'ını kapatır."""
        with self._cond:
            self._wanted = (path, gen)
            self._pending.clear()
            self._cond.notify_all()

    def submit(self, gen: int, idx: int, scale: float, invert: bool):
        with self._cond:
            self._pending[idx] = (gen, scale, invert)
            self._cond.notify_all()

    def stop(self):
        with self._cond:
            self._stop = True
            self._cond.notify_all()

    # --- işçi thread ---

    def run(self):
        _alive_workers.add(self)
        try:
            self._run_loop()
        finally:
            _alive_workers.discard(self)

    def _run_loop(self):
        while True:
            with self._cond:
                while (not self._stop and not self._pending
                       and self._wanted == self._doc_key):
                    self._cond.wait()
                if self._stop:
                    return
                jobs = self._pending
                self._pending = {}
                wanted = self._wanted

            if wanted != self._doc_key:
                self._swap_document(wanted)

            # Windows'ta derleme PDF'i YERINDE yeniden yaziyor; o ana denk
            # gelen acilis basarisiz oluyordu ve `_doc_key` zaten atandigi
            # icin bir daha DENENMIYORDU: isci o nesil boyunca olu kaliyor,
            # kullanici bir sonraki derlemeye kadar bos sayfa goruyordu.
            # Yeniden deneme yalnizca IS VARKEN ve sinirli: bos dongude
            # tetiklenmedigi icin CPU yakmiyor.
            if (self._doc is None and jobs
                    and self._acilis_denemesi < _MAX_ACILIS_DENEMESI):
                self._swap_document(wanted)

            if self._doc is None:
                continue

            for idx in sorted(jobs):
                # stop'u İŞ BAŞINA denetle: uzun partilerde (offscreen'de tüm
                # sayfalar tek partide gelebilir) stop yalnız parti sonunda
                # görülüyor, kapanış beklemesi doluyor, thread interpreter
                # çıkışında çalışır kalıp süreci çökertiyordu
                if self._stop:
                    break
                gen, scale, invert = jobs[idx]
                try:
                    # Kilit SAYFA BAŞINA: parti boyunca tutulsa UI uzun bir
                    # render dizisi boyunca donardı (bkz. gui/pdfium_lock.py).
                    with pdfium_lock:
                        page = self._doc[idx]
                        img = render_page_to_qimage(page, scale, invert)
                except Exception:
                    continue
                self.rendered.emit(gen, idx, scale, invert, img)

    def _swap_document(self, wanted):
        if self._doc is not None:
            try:
                with pdfium_lock:
                    self._doc.close()
            except Exception:
                pass
            self._doc = None
        if wanted != self._doc_key:
            self._acilis_denemesi = 0     # yeni nesil: sayac sifirlanir
        self._doc_key = wanted
        if wanted and wanted[0]:
            try:
                # Dosyayı belleğe alıp öyle aç: render sürerken kaynak dosya
                # silinir/üstüne yazılırsa (derleme, tmp temizliği) pdfium
                # yarım okuma yapıp süreç öldürebiliyor. PDF boyutu birkaç MB;
                # önizleme zaten yüklenen andaki görüntüyü taşır, derleme
                # bitince load_pdf yeni nesil açıyor.
                with open(wanted[0], "rb") as f:
                    data = f.read()
                with pdfium_lock:
                    self._doc = pypdfium2.PdfDocument(data)
                self._acilis_denemesi = 0
            except Exception:
                self._doc = None
                self._acilis_denemesi += 1
