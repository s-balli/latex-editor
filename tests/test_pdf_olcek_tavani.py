"""PDF sayfa ölçeğinde piksel tavanı.

Neden var: sayfanın tamamı TEK karo olarak render ediliyor ve `_get_page_size`
yalnızca alt sınır (`max(w, 50)`) koyuyordu. Ölçüldü (2026-09-02): A0 afiş 3x
yakınlaştırmada 162.7 megapiksel ve +1031 MB; `/MediaBox`'ı 20000x20000 olan
1 KB'lık bozuk bir PDF 900 megapiksel ve +4614 MB istiyordu, 999999999'luk bir
sayfa ise 1.5 milyar piksellik yer tutucu üretiyordu.

İkinci tehlike: tavan yalnızca render'a konsaydı arama vurgusu, metin seçimi ve
SyncTeX koordinatları büyük sayfalarda KAYARDI — onların hepsi aynı ölçeği
kullanıyor. Bu yüzden tavan tek kaynakta (`_olcek`) ve testlerden biri kaynak
kodunda tavansız ölçeğin geri gelmediğini denetliyor.
"""

import os
import re

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    PdfViewer = None

gui = pytest.mark.skipif(PdfViewer is None, reason="PyQt6 / gui modülleri gerekli")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIXIN_DIR = os.path.join(_ROOT, "desktop", "gui", "pdf_viewer_mixins")

# Ölçülen gerçek boyutlar (nokta): tavan bunların hangisini kestiğini test ediyor
A4 = (595.0, 842.0)
A3 = (842.0, 1191.0)
A0 = (2384.0, 3370.0)
DEVASA = (20000.0, 20000.0)


@pytest.fixture(scope="module")
def qapp():
    if PdfViewer is None:
        yield None
        return
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def viewer(qapp):
    v = PdfViewer(theme=THEMES["dark"])
    v._zoom = 3.0                      # en yüksek yakınlaştırma (üst sınır 3.0)
    yield v
    # close() YETMİYOR: render/arama işçileri koşar kalıyor ve QThread çalışırken
    # yok edilince süreç düşüyor ("destroyed while running", bkz. _render.shutdown).
    # close()'la bırakıldığında bu dosya beş koşudan birinde çöküyordu.
    v.shutdown()
    v.close()


@gui
def test_gundelik_boylar_tavana_takilmiyor(viewer):
    """A4 ve A3 en yüksek yakınlaştırmada bile sınırın altında."""
    for w, h in (A4, A3):
        assert viewer._tavanli_olcek(w, h) == 1.5 * viewer._zoom


@gui
def test_buyuk_sayfa_tavana_dayaniyor(viewer):
    """A0 afiş ve kötü niyetli devasa sayfa tavanla sınırlanıyor."""
    for w, h in (A0, DEVASA):
        olcek = viewer._tavanli_olcek(w, h)
        assert olcek < 1.5 * viewer._zoom
        piksel = w * h * olcek * olcek
        assert piksel <= viewer._MAX_PIKSEL * 1.001


@gui
def test_tavan_en_boy_oranini_koruyor(viewer):
    """Genişlik ve yükseklik AYRI AYRI kırpılsaydı sayfa çarpılırdı."""
    w, h = 20000.0, 5000.0
    olcek = viewer._tavanli_olcek(w, h)
    assert (w * olcek) / (h * olcek) == pytest.approx(w / h)


@gui
def test_sifir_ve_negatif_boyut_tavani_bozmuyor(viewer):
    """pdfium bozuk /MediaBox'ta sıfır ya da negatif dönebiliyor.

    Davranışı sabitliyor: böyle bir sayfada ölçek olduğu gibi kalmalı.
    Koddaki `w_pt > 0 and h_pt > 0` denetimi bunun için TEK başına gerekli
    değil (piksel çarpımı zaten tavanı aşmıyor, yani bölmeye hiç gelinmiyor);
    denetim kaldırılırsa bu test yine geçer. Yine de sıfıra bölmeye giden
    yolu kapalı tutmak ucuz.
    """
    for w, h in ((0.0, 0.0), (0.0, 500.0), (-100.0, -100.0)):
        assert viewer._tavanli_olcek(w, h) == 1.5 * viewer._zoom


@gui
def test_onbellek_yokken_tavansiz_olcege_dusuyor(viewer):
    """Boyut henüz bilinmiyorsa `_olcek` istenen ölçeği vermeli.

    Önbellek her yüklemede _create_placeholders -> _get_page_size yolundan
    doluyor; bu yol koşmadan da tutarlı bir değer dönmeli.
    """
    viewer._sayfa_pt.clear()
    assert viewer._olcek(0) == 1.5 * viewer._zoom

    viewer._sayfa_pt[0] = A0
    assert viewer._olcek(0) == viewer._tavanli_olcek(*A0)


@gui
def test_belge_degisince_onbellek_bayat_kalmiyor(viewer):
    """Farklı boyutta bir PDF açılınca eski sayfa boyutları temizlenmeli."""
    viewer._sayfa_pt[0] = DEVASA
    viewer.clear()
    assert viewer._sayfa_pt == {}


def test_koordinat_yerleri_tavansiz_olcege_donmemis():
    """Arama/seçim/SyncTeX tavansız ölçeğe dönerse koordinatlar kayar.

    `1.5 * self._zoom` yalnızca tavanı HESAPLAYAN iki satırda kalmalı
    (_render.py); geri kalan her yer `_olcek(index)` kullanmalı.
    """
    kalanlar = []
    for ad in sorted(os.listdir(_MIXIN_DIR)):
        if not ad.endswith(".py"):
            continue
        with open(os.path.join(_MIXIN_DIR, ad), encoding="utf-8") as f:
            for no, satir in enumerate(f, 1):
                if re.search(r"1\.5\s*\*\s*self\._zoom", satir):
                    kalanlar.append("%s:%d" % (ad, no))

    # _render.py'deki iki tanesi tavanın kendi hesabı
    assert len([k for k in kalanlar if not k.startswith("_render.py")]) == 0, kalanlar
    assert len(kalanlar) == 2, kalanlar
