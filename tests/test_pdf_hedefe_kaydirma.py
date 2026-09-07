# -*- coding: utf-8 -*-
"""Yakınlaştırılmış belgede hedefi görüntüye getirme: DİKEY ve YATAY.

`scroll_to_position` (SyncTeX ileri araması) ve `_show_search_result` (metin
araması) yalnız dikey kaydırıyordu. ÖLÇÜLDÜ (2026-09-07), %300'de 612 pt'lik
sayfa 2754 px, görüntü penceresi 404 px: sağ kenara yakın hedefte ikisi de
doğru satıra iniyor ama hedef yatayda ekranın 1850 px dışında kalıyor.
Kullanıcının gördüğü şey "hiçbir şey olmadı".

Metin aramasında yatay konum zaten hesaplanıyor, sonra atılıyordu (`_mx`).

Bu dosya kasten GERÇEK PdfViewer kuruyor: kusur widget geometrisinde ve
kaydırma çubuğu aralığında yaşıyor, sahte nesnenin arkasında görünmüyor.
"""

import os

import pytest

try:
    from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QTimer
    from PyQt6.QtWidgets import QApplication
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES
    from gui.pdf_donusum import geometri, gorsele, synctex_kutusu
    from gui.pdfium_lock import pdfium_lock
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="PyQt6 / gui modülleri gerekli")

# Hedefin sayfa içindeki yeri. 612 pt genişliğinde sayfada 500 pt SAĞ kenara
# yakın: %300'de görüntü penceresine sığmıyor, kusurun göründüğü yer orası.
METIN_X_PT = 500
METIN_Y_PT = 700
ZOOM = 3.0


@pytest.fixture(scope="module")
def qapp():
    if not _VAR:
        yield None
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QApplication.instance() or QApplication([])


def _pdf_yaz(yol, x_pt=METIN_X_PT, y_pt=METIN_Y_PT):
    """Tek sayfalık PDF; tek karakter istenen noktada."""
    icerik = b"BT /F1 12 Tf %d %d Td (Z) Tj ET" % (x_pt, y_pt)
    nesneler = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
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
    with open(yol, "wb") as f:
        f.write(bytes(out))
    return str(yol)


def _dongu(ms=30):
    """Gerçek olay döngüsü.

    `processEvents` tek başına yetmiyor: Qt'de `deleteLater` DeferredDelete
    olayı gönderiyor ve olay döngüsü dışında işlenmiyor. Bu ölçüm bir kez
    o yüzden yanlış sonuç verdi.
    """
    d = QEventLoop()
    QTimer.singleShot(ms, d.quit)
    d.exec()


@pytest.fixture
def gorucu(qapp, tmp_path):
    v = PdfViewer(theme=THEMES["dark"])
    v.resize(420, 520)
    v.show()
    assert v.load_pdf(_pdf_yaz(tmp_path / "sag_kenar.pdf"))
    _dongu()
    yield v
    v.shutdown()
    v.close()
    QApplication.instance().sendPostedEvents(
        None, QEvent.Type.DeferredDelete)


def _yakinlastir(v, zoom=ZOOM):
    v._zoom = zoom
    v._update_page_sizes()
    _dongu()
    assert v._scroll.horizontalScrollBar().maximum() > 0, \
        "kapı boş koşuyor: sayfa görüntüye sığıyor, yatay kaydırma yok"


def _yatay_bant(v):
    c = v._scroll.horizontalScrollBar()
    return c.value(), c.value() + v._scroll.viewport().width()


def _mutlak_x(v, etiket, x_ic):
    return etiket.mapTo(v._pages_widget, QPoint(0, 0)).x() + int(x_ic)


# =====================================================================
# SyncTeX ileri araması
# =====================================================================


@gui
def test_ileri_arama_vurguyu_YATAY_olarak_goruntuye_getiriyor(gorucu):
    """Kırılırsa: kullanıcı derleyip PDF'e atlıyor ve doğru satırı görüyor
    ama vurgulanan kelime ekranın dışında kalıyor."""
    v = gorucu
    _yakinlastir(v)
    v.scroll_to_position(1, 0.0, 92.0, float(METIN_X_PT), 60.0, 14.0)
    _dongu()
    hl = v._highlight_label
    assert hl is not None, "vurgu kurulmadı"
    x = hl.mapTo(v._pages_widget, QPoint(0, 0)).x()
    sol, sag = _yatay_bant(v)
    assert sol <= x < sag, (
        "vurgu yatayda görüntü dışında: x=%d, bant %d..%d" % (x, sol, sag))


@gui
def test_ileri_arama_DIKEY_kaydirmayi_bozmuyor(gorucu):
    """Aşırı düzeltme kapısı: yatay eklenirken dikey ortalama kaybolmasın."""
    v = gorucu
    _yakinlastir(v)
    v.scroll_to_position(1, 0.0, 92.0, float(METIN_X_PT), 60.0, 14.0)
    _dongu()
    hl = v._highlight_label
    y = hl.mapTo(v._pages_widget, QPoint(0, 0)).y()
    dikey = v._scroll.verticalScrollBar()
    pencere = v._scroll.viewport().height()
    assert dikey.value() <= y < dikey.value() + pencere


# =====================================================================
# Metin araması
# =====================================================================


@gui
def test_metin_aramasi_eslesmeyi_YATAY_olarak_goruntuye_getiriyor(gorucu):
    """Yatay konum hesaplanıyordu ve atılıyordu; kırılırsa yine atılıyor."""
    v = gorucu
    _yakinlastir(v)
    etiket = v._page_labels[0]
    with pdfium_lock:
        sayfa = v._pdf[0]
        tp = sayfa.get_textpage()
        left, _b, _r, top = tp.get_charbox(0, loose=True)
        mx, _my = gorsele(geometri(sayfa), left, top, v._olcek(0))

    v._search_results = [(0, 0, 1)]
    v._search_index = 0
    v._show_search_result(0)
    _dongu()

    x = _mutlak_x(v, etiket, mx)
    sol, sag = _yatay_bant(v)
    assert sol <= x < sag, (
        "eşleşme yatayda görüntü dışında: x=%d, bant %d..%d" % (x, sol, sag))


# =====================================================================
# Aşırı düzeltme kapıları
# =====================================================================


@gui
def test_sayfa_SIGIYORSA_yatay_kaydirma_yapilmiyor(gorucu):
    """Normal görünümde yatay çubuk yok; kaydırmaya çalışmak anlamsız."""
    v = gorucu
    v._zoom = 0.2
    v._update_page_sizes()
    _dongu()
    assert v._scroll.horizontalScrollBar().maximum() == 0
    v.scroll_to_position(1, 0.0, 92.0, float(METIN_X_PT), 60.0, 14.0)
    _dongu()
    assert v._scroll.horizontalScrollBar().value() == 0


@gui
def test_hedef_ZATEN_gorunuyorsa_yatay_kaydirma_degismiyor(gorucu):
    """Ardışık eşleşmelerde görüntü sarsılmasın: hedef bandın içindeyse
    yatay konuma dokunulmamalı."""
    v = gorucu
    _yakinlastir(v)
    v.scroll_to_position(1, 0.0, 92.0, float(METIN_X_PT), 60.0, 14.0)
    _dongu()
    ilk = v._scroll.horizontalScrollBar().value()
    v.scroll_to_position(1, 0.0, 92.0, float(METIN_X_PT), 60.0, 14.0)
    _dongu()
    assert v._scroll.horizontalScrollBar().value() == ilk


@gui
def test_hedef_pencereden_GENISSE_sol_kenari_gorunuyor(gorucu):
    """Kutu görüntüden genişse başı kesilmemeli: okuma soldan başlıyor."""
    v = gorucu
    _yakinlastir(v)
    etiket = v._page_labels[0]
    genis = v._scroll.viewport().width() * 3
    v._hedefe_kaydir(etiket, 1500, 100, genis, 2)
    _dongu()
    sol, sag = _yatay_bant(v)
    x = _mutlak_x(v, etiket, 1500)
    assert sol <= x < sag, "kutunun SOL kenarı görüntü dışında kaldı"


# =====================================================================
# Vurgu kutusunun hizası
# =====================================================================


@gui
def test_vurgu_kutusu_kelimenin_IKI_kenarini_da_kapsiyor(gorucu):
    """Dolgu tek kenara uygulanıyordu: kutu 4 px sola kayıp kelimenin sağını
    kesiyordu (ölçüldü: sol -4, sağ -4). İki kenar da dışa taşmalı."""
    v = gorucu
    _dongu()
    idx = 0
    etiket = v._page_labels[idx]
    with pdfium_lock:
        g = geometri(v._pdf[idx])
    bx, by, bw, bh = synctex_kutusu(g, 100.0, 150.0, 60.0, 14.0, v._olcek(idx))

    v.scroll_to_position(1, 0.0, 150.0, 100.0, 60.0, 14.0)
    _dongu()
    kutu = v._highlight_label.geometry()
    assert kutu.x() < int(bx), "sol kenara dolgu uygulanmamış"
    assert kutu.x() + kutu.width() > int(bx) + int(bw), \
        "sağ kenara dolgu uygulanmamış: kutu kelimenin sağını kesiyor"
    assert kutu.x() + kutu.width() < etiket.width(), \
        "genişlik verildiği hâlde satır sonuna kadar uzamış"


@gui
def test_vurgu_GENISLIK_verilmeyince_satir_sonuna_kadar_gidiyor(gorucu):
    """Genişlik yoksa davranış korunmalı: sayfanın sağ kenarına kadar."""
    v = gorucu
    _dongu()
    etiket = v._page_labels[0]
    v.scroll_to_position(1, 0.0, 150.0, 100.0)
    _dongu()
    kutu = v._highlight_label.geometry()
    assert kutu.x() + kutu.width() == etiket.width()
