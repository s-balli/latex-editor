"""Çok sayfalı belgede tıklama doğru sayfaya gitmeli.

`label.mapFrom(obj, pos)` KARDEŞ bir etikete çağrılıyordu. Qt'de `mapFrom`
ata-torun ilişkisi bekliyor; kardeşte dönen değer `pos - label.pos()` oluyor
ve eş boyutlu sayfalarda çoğu zaman İLK etiketin dikdörtgenine düşüyor.

Ölçüldü (2026-09-02, dış güvenlik raporu 6. tur; Qt 6.11, iki eş sayfa,
2. sayfanın ortasına tıklama):

    pencere geniş (sayfa yatayda ortalı)   x negatife düşüyor, doğru sayfa
                                           bulunuyor (TESADÜF)
    pencere dar   (ortalama payı yok)      2. sayfaya tıklama 1. sayfaya
                                           çözümleniyor

Yani hata sürüme değil PENCERE GENİŞLİĞİNE bağlıydı: aynı kullanıcı
pencereyi daralttığında SyncTeX geri araması, metin seçimi ve bağlantı
tıklaması yanlış sayfaya gidiyordu. Üç yol da artık tek bir `_pos_to_page`
üzerinden geçiyor.
"""

import os

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QPoint
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="PyQt6 / gui modülleri gerekli")


@pytest.fixture(scope="module")
def qapp():
    if not _VAR:
        yield None
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QApplication.instance() or QApplication([])


def _iki_sayfa(tmp_path):
    """Eş boyutlu iki sayfa: hata tam bu durumda ortaya çıkıyor."""
    icerik = [b"BT /F1 24 Tf 100 650 Td (BIR) Tj ET",
              b"BT /F1 24 Tf 100 650 Td (IKI) Tj ET"]
    nesneler = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R 4 0 R]/Count 2>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 7 0 R>>>>/Contents 5 0 R>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 7 0 R>>>>/Contents 6 0 R>>",
        b"<</Length %d>>stream\n" % len(icerik[0]) + icerik[0] + b"\nendstream",
        b"<</Length %d>>stream\n" % len(icerik[1]) + icerik[1] + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    yerler = []
    for i, n in enumerate(nesneler, start=1):
        yerler.append(len(out))
        out += b"%d 0 obj" % i + n + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(nesneler) + 1)
    for yer in yerler:
        out += b"%010d 00000 n \n" % yer
    out += (b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n"
            % (len(nesneler) + 1, xref))
    yol = tmp_path / "iki.pdf"
    yol.write_bytes(bytes(out))
    return str(yol)


@pytest.fixture
def viewer(qapp, tmp_path):
    v = PdfViewer(theme=THEMES["dark"])
    # DAR pencere: sayfa yatayda ortalanmasın. Geniş pencerede hata tesadüfen
    # görünmüyordu, çünkü ortalama payı x'i negatife düşürüyordu.
    v.resize(500, 800)
    v._zoom = 0.5
    # show() ŞART: düzen hesaplanmadan etiketlerin hepsi (0, 0)'da kalıyor
    # ve her nokta ilk etikete düşüyor. O zaman test kendi kurgusundan
    # dolayı düşer, koddan değil.
    v.show()
    assert v.load_pdf(_iki_sayfa(tmp_path))
    qapp.processEvents()
    v._create_placeholders()
    qapp.processEvents()
    assert v._page_labels[1].pos().y() > v._page_labels[0].pos().y(), (
        "düzen hesaplanmamış: etiketler üst üste")
    yield v
    v.shutdown()
    v.close()


def _ikinci_sayfanin_ortasi(v):
    lb = v._page_labels[1]
    return lb, QPoint(lb.width() // 2, lb.height() // 2)


@gui
def test_ikinci_sayfa_etiketi_dogru_cozumleniyor(viewer):
    lb2, orta = _ikinci_sayfanin_ortasi(viewer)

    idx, nokta = viewer._pos_to_page(orta, lb2)

    assert idx == 1, "2. sayfaya tıklama 1. sayfaya çözümlendi"
    assert nokta == orta, "etiketin kendisinden gelen nokta dönüştürülmemeli"


@gui
def test_geri_arama_dogru_sayfayi_bildiriyor(viewer, tmp_path, qapp):
    lb2, orta = _ikinci_sayfanin_ortasi(viewer)
    viewer._pdf_path = str(tmp_path / "iki.pdf")
    yakalanan = []
    viewer.reverse_search_requested.connect(
        lambda sayfa, x, y, yol: yakalanan.append(sayfa))

    viewer._handle_reverse_click(orta, lb2)
    qapp.processEvents()

    assert yakalanan == [2], "SyncTeX geri araması yanlış sayfayı bildirdi"


@gui
def test_etiket_disindaki_nokta_sayfa_vermiyor(viewer):
    """Etiketin dışına düşen nokta hiçbir sayfaya çözümlenmemeli."""
    lb2 = viewer._page_labels[1]

    idx, _n = viewer._pos_to_page(QPoint(-50, -50), lb2)

    assert idx is None


@gui
def test_kapsayicidan_gelen_nokta_hala_calisiyor(viewer, qapp):
    """`obj` kapsayıcıysa `mapFrom` meşru: o yol bozulmamalı."""
    kapsayici = viewer._pages_widget
    lb2 = viewer._page_labels[1]
    kaps_nokta = lb2.mapTo(kapsayici, QPoint(lb2.width() // 2,
                                             lb2.height() // 2))

    idx, _n = viewer._pos_to_page(kaps_nokta, kapsayici)

    assert idx == 1
