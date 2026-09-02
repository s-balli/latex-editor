"""PDF yollarında bozuk sayfa ve kilit dışı pdfium çağrısı.

Dış güvenlik raporunun "kod okumasıyla güçlü, dosya üreterek tetiklenemedi"
maddeleri. Burada bozuk sayfa DOSYAYLA değil, pdfium çağrısını fırlatacak
şekilde vekille üretiliyor: ölçülmek istenen şey pdfium'un bozuk PDF'i nasıl
karşıladığı değil, uygulamanın istisnayı nasıl karşıladığı.

- Zoom yolu (`_update_page_sizes`) korumasızdı: döngünün ORTASINDA kaçan bir
  istisna etiketlerin bir kısmını yeni ölçekte, kalanını eskisinde bırakıyor
  ve ölçek/koordinat eşleşmesi bozulduğu için arama vurgusu, seçim ve SyncTeX
  kayıyordu.
- Sunum modu (F5) pdfium çağrıları korumasızdı: istisna slot'tan dışarı
  çıkıyor, sunum yarım ekranla kalıyordu.
- Yer imi okumaları kilidin DIŞINDAYDI: `_bm_title` ve `_bm_page_index`
  pdfium'a giriyor ve pdfium küresel durum tuttuğu için render işçisiyle aynı
  anda çağrılmaları segfault sınıfı (bkz. gui/pdfium_lock.py).
"""

import os

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="PyQt6 / gui modülleri gerekli")

_DEMO = r"C:\latex-demo\main.pdf"


@pytest.fixture(scope="module")
def qapp():
    if not _VAR:
        yield None
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QApplication.instance() or QApplication([])


def _pdf_kur(tmp_path):
    """Tek sayfalık, elle kurulmuş geçerli PDF (dış dosyaya bağlı kalmasın)."""
    icerik = b"BT /F1 12 Tf 50 50 Td (x) Tj ET"
    nesneler = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R 5 0 R]/Count 2>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 6 0 R>>>>/Contents 4 0 R>>",
        b"<</Length " + str(len(icerik)).encode() + b">>stream\n" + icerik +
        b"\nendstream",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 400 600]"
        b"/Resources<</Font<</F1 6 0 R>>>>/Contents 4 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    yerler = []
    for i, n in enumerate(nesneler, start=1):
        yerler.append(len(out))
        out += b"%d 0 obj" % i + n + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(nesneler) + 1)
    for y in yerler:
        out += b"%010d 00000 n \n" % y
    out += (b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n"
            % (len(nesneler) + 1, xref))
    yol = tmp_path / "iki_sayfa.pdf"
    yol.write_bytes(bytes(out))
    return str(yol)


class _PatlayanBelge:
    """Belirli bir sayfada fırlatan pdfium belgesi vekili."""

    def __init__(self, gercek, patlayan_index):
        self._gercek = gercek
        self._patlayan = patlayan_index

    def __getitem__(self, i):
        if i == self._patlayan:
            raise RuntimeError("bozuk sayfa")
        return self._gercek[i]

    def __len__(self):
        return len(self._gercek)

    def __getattr__(self, ad):
        return getattr(self._gercek, ad)


@pytest.fixture
def viewer(qapp, tmp_path):
    v = PdfViewer(theme=THEMES["dark"])
    v.resize(900, 700)
    assert v.load_pdf(_pdf_kur(tmp_path))
    yield v
    v.shutdown()
    v.close()


@gui
def test_bozuk_sayfa_zoom_dongusunu_yarida_kesmiyor(viewer):
    """Bir sayfa fırlatsa da diğerlerinin boyutu yeni ölçeğe geçmeli."""
    viewer._zoom = 1.0
    viewer._update_page_sizes()
    ilk_normal = viewer._page_labels[1].size()

    viewer._pdf = _PatlayanBelge(viewer._pdf, 0)
    viewer._sayfa_pt.clear()
    viewer._zoom = 2.0

    viewer._update_page_sizes()          # istisna dışarı çıkmamalı

    # Sağlam sayfa yeni ölçekte
    assert viewer._page_labels[1].width() > ilk_normal.width()
    # Bozuk sayfa da bir boyut aldı (yer tutucu kayboldu, düzen bozulmadı)
    assert viewer._page_labels[0].width() >= 50


@gui
def test_bozuk_sayfa_zoom_dugmesini_oldurmuyor(viewer):
    viewer._pdf = _PatlayanBelge(viewer._pdf, 0)
    viewer._sayfa_pt.clear()
    onceki = viewer._zoom

    viewer.zoom_in()                     # istisna dışarı çıkmamalı

    assert viewer._zoom > onceki


@gui
def test_bozuk_sayfa_sunum_modunu_oldurmuyor(viewer, qapp):
    viewer.enter_presentation()
    qapp.processEvents()
    viewer._pdf = _PatlayanBelge(viewer._pdf, viewer._current_page)
    viewer._pres_cache.clear()

    viewer._presentation_render()        # istisna dışarı çıkmamalı

    viewer.exit_presentation()
    qapp.processEvents()


@gui
def test_yer_imleri_pdfium_KILIDI_altinda_okunuyor(viewer, monkeypatch):
    """Başlık/sayfa okumaları kilidin dışındaydı: render işçisiyle çakışır.

    `pdfium_lock` RLock; sahibi biz olduğumuzda `_is_owned()` True döner.
    Çıkarma döngüsü kilidin dışına taşınırsa bu test düşer.
    """
    import gui.pdf_viewer_mixins._bookmarks as bm
    from gui.pdfium_lock import pdfium_lock

    gorulen = []

    def sahte_title(x):
        gorulen.append(pdfium_lock._is_owned())
        return "yer imi"

    def sahte_index(x):
        gorulen.append(pdfium_lock._is_owned())
        return 0

    monkeypatch.setattr(bm, "_bm_title", sahte_title)
    monkeypatch.setattr(bm, "_bm_page_index", sahte_index)
    monkeypatch.setattr(viewer._pdf, "get_toc", lambda: iter([object()]),
                        raising=False)

    viewer.update_bookmarks()

    assert gorulen, "çıkarma hiç çalışmadı (test boş ölçüm)"
    assert all(gorulen), "pdfium okumaları kilidin DIŞINDA yapıldı"
