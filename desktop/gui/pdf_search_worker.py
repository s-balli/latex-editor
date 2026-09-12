"""PDF metin arama işçisi — aramayı UI thread'inden kaldırır.

pdf_render_worker'ın ikizi (aynı yaşam döngüsü koruması): tek uzun ömürlü
QThread, kendi pypdfium2 handle'ı (bayt olarak bellekten açılır), parent'sız
+ çalışan işçi modül kaydında güçlü referansla tutulur, atexit durdurur.

Farkı: latest-wins TEK slot (aramada yalnız son sorgu anlamlıdır; renderdan
farklı olarak pencere yok). Yeni sorgu gelince süren arama SAYFA SAYFA iptal
edilir (sayfa başında yeni iş denetlenir). Sonuç yalnız koordinat listesi
taşır: (page_idx, start, count). Textpage'ler işçinin dokümanına bağlıdır ve
doküman nesil değiştirince geçersizleşir; UI tarafı vurgu/zıplama anında
KENDİ dokümanından textpage yaratır — iş parçacıkları arası handle taşıma
yok, asılı handle riski yok.
"""

import atexit
import threading

import pypdfium2  # type: ignore

from PyQt6.QtCore import QThread, pyqtSignal

from core.project_search import eslesme_ofsetleri
from gui.pdf_metin import aksanlari_birlestir
from gui.pdfium_lock import pdfium_lock


def _sayfada_bul(ham: str, sorgu: str) -> list[tuple[int, int]]:
    """Sayfa metnindeki eşleşmelerin HAM karakter aralıkları: [(baş, bit)].

    pdfium'un kendi ``textpage.search()``i BIRAKILDI, iki sebeple:

    1. Sayfa metnini ONARMADAN arıyordu. OT1 belgelerde aksanlar ayrı glif
       basılıyor ve `öğrenci` metinde `¨o˘grenci` olarak duruyor; kullanıcı
       ne yazarsa yazsın bulamıyordu. Kopyalama yolu bu onarımı 2026-09-08'den
       beri yapıyor, arama yolu o taşınmanın dışında kalmıştı.
    2. Harf katlaması editörünkinden AYRIYDI. Artık `eslesme_ofsetleri`
       kullanılıyor, yani PDF'te arama ile Ctrl+F ve Projede Ara aynı Türkçe
       katlamayı paylaşıyor (İ/ı ayrımı dahil).

    ÖLÇÜLDÜ (2026-09-12, 58 gerçek PDF + aynı adlı kaynak; kaynakta geçen 642
    Türkçe kelime arandı): pdfium 471'ini buluyordu, bu yol 523'ünü buluyor.
    Kazanç 52, KAYIP 0: pdfium'un bulduğu tek bir kelime bile düşmüyor.

    Dönen aralık HAM metne ait olmak zorunda: vurgu `get_charbox` ile ham
    karakter indisinden çiziliyor. Onarılmış metinde indis kayıyor, o yüzden
    `aksanlari_birlestir` haritayı da veriyor.
    """
    onarilmis, harita = aksanlari_birlestir(ham)
    n = len(sorgu)
    if harita is None:                 # onaracak bir şey yoktu, indisler ham
        return [(j, j + n) for j in eslesme_ofsetleri(onarilmis, sorgu)]
    return [(harita[j][0], harita[j + n - 1][1])
            for j in eslesme_ofsetleri(onarilmis, sorgu)]

_alive_workers: set["PdfSearchWorker"] = set()


def _stop_all_at_exit():
    for w in list(_alive_workers):
        try:
            w.stop()
            w.wait(6000)
        except Exception:
            pass


atexit.register(_stop_all_at_exit)


class PdfSearchWorker(QThread):
    """Arka planda tam metin araması; sonuçlar search_id ile damgalanır."""

    found = pyqtSignal(int, list)   # search_id, [(page_idx, start, count), ...]

    def __init__(self):
        super().__init__()
        self._cond = threading.Condition()
        self._stop = False
        self._job: tuple[int, str] | None = None      # (search_id, query)
        self._wanted: tuple[str, int] | None = None   # (path, gen)
        # Doküman handle'ına yalnızca run() dokunur (kilitsiz alan)
        self._doc = None
        self._doc_key: tuple[str, int] | None = None

    # --- UI thread'inden ---

    def open_document(self, path: str, gen: int):
        """Aranacak dokümanı bildir; boş path handle'ı kapatır. Yeni nesil
        süren aramayı da geçersiz kılar (eski sonuçlar zaten damgalıdır)."""
        with self._cond:
            self._wanted = (path, gen)
            self._cond.notify_all()

    def search(self, search_id: int, query: str):
        with self._cond:
            self._job = (search_id, query)
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
            # Handle'ı BURADA kapat. `_run_loop` stop görünce dönüyor ve
            # dokümanı kapatan TEK yer `_swap_document`; o da artık hiç
            # çalışmayacağı için handle açık kalıyordu. Ölçüldü 2026-09-06:
            # `stop()` + `wait()` sonrası işçinin `_doc`u hâlâ açık ve
            # kapatmayı pypdfium2'nin weakref finalizer'ı devralıyor, GC'nin
            # denk geldiği thread'de ve `pdfium_lock` TUTULMADAN. Kural açık:
            # belge açma/kapama da kilit ister (bkz. gui/pdfium_lock.py).
            # İKİZ pdf_render_worker bu düzeltmeyi 2026-09-05'te aldı, bu
            # dosya almamıştı; oysa başlığı "aynı yaşam döngüsü koruması"
            # diyor. Kapatma işçi thread'inde kalıyor: `_doc`a yalnız run()
            # dokunur.
            self._swap_document(None)
            _alive_workers.discard(self)

    def _run_loop(self):
        while True:
            with self._cond:
                while (not self._stop and self._job is None
                       and self._wanted == self._doc_key):
                    self._cond.wait()
                if self._stop:
                    return
                job, self._job = self._job, None
                wanted = self._wanted

            if wanted != self._doc_key:
                self._swap_document(wanted)

            if self._doc is None or job is None:
                continue

            results = self._search_all(job[1])
            if results is None:
                continue        # iptal edildi (yeni sorgu geldi)
            self.found.emit(job[0], results)

    def _search_all(self, query: str) -> list[tuple[int, int, int]] | None:
        """Tüm sayfalarda ara. Süren arama iptal edilirse None döner."""
        results: list[tuple[int, int, int]] = []
        if not query:
            return results
        # len(doc) da bir pdfium çağrısıdır (FPDF_GetPageCount) — kilit ister.
        # Döngü dışında bir kez alınıyor: içeride alınsa kilit, hemen ardından
        # gelen `with self._cond` ile iç içe girer ve kilit sırasını bozardı.
        with pdfium_lock:
            sayfa_sayisi = len(self._doc)
        for i in range(sayfa_sayisi):
            if self._stop:
                return None
            with self._cond:
                if self._job is not None:    # yeni sorgu geldi: bu arama öldü
                    return None
            try:
                # Kilit SAYFA BAŞINA (bkz. gui/pdfium_lock.py)
                with pdfium_lock:
                    ham = self._doc[i].get_textpage().get_text_bounded()
                for bas, bit in _sayfada_bul(ham, query):
                    results.append((i, bas, bit - bas))
            except Exception:
                continue
        return results

    def _swap_document(self, wanted):
        if self._doc is not None:
            try:
                with pdfium_lock:
                    self._doc.close()
            except Exception:
                pass
            self._doc = None
        self._doc_key = wanted
        if wanted and wanted[0]:
            try:
                with open(wanted[0], "rb") as f:
                    data = f.read()
                with pdfium_lock:
                    self._doc = pypdfium2.PdfDocument(data)
            except Exception:
                self._doc = None
