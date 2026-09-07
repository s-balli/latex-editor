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

import ctypes
import os
import time

import pytest

try:
    from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QTimer
    from PyQt6.QtWidgets import QApplication
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES
    from gui.pdf_donusum import geometri, gorsele, synctex_kutusu
    from gui.pdfium_lock import pdfium_lock
    from pypdfium2 import raw as praw
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


def _dongu(ms=5):
    """Gerçek olay döngüsü.

    `processEvents` tek başına yetmiyor: Qt'de `deleteLater` DeferredDelete
    olayı gönderiyor ve olay döngüsü dışında işlenmiyor. Bu ölçüm bir kez
    o yüzden yanlış sonuç verdi.
    """
    d = QEventLoop()
    QTimer.singleShot(ms, d.quit)
    d.exec()


def _bekle(kosul, saniye=3.0):
    """Koşul sağlanana kadar olay döngüsünü çevir; sağlandı mı döndür.

    SABİT süreli bekleme kırılgan: yeni yerleşim eşzamanlı hazır olmuyor ve
    ne kadar süreceği makine yüküne bağlı. ÖLÇÜLDÜ (2026-09-07): buradaki
    testler `sys.settrace` altında koşan kapsam ölçümünde ve 0 ms'lik
    döngüyle düşüyordu. Artık beklenen ŞEY yazılıyor, süre değil.
    """
    bitis = time.monotonic() + saniye
    while not kosul() and time.monotonic() < bitis:
        _dongu(5)
    return kosul()


def _bekle_kararli(v, saniye=3.0):
    """Yerleşim DURULANA kadar bekle: iki turda aynı geometri.

    "Aralık değişti" ya da "maximum > 0" gibi koşullar ARA bir durumda da
    sağlanıyor. ÖLÇÜLDÜ (2026-09-07): %300 yakınlaştırmada yatay maximum
    2368 olacakken koşul 302'de geçti ve test yanlış geometriyle koştu.
    """
    onceki = None
    bitis = time.monotonic() + saniye
    while time.monotonic() < bitis:
        if not v._page_labels:
            return False
        simdi = (v._page_labels[0].width(), v._page_labels[0].height(),
                 v._scroll.horizontalScrollBar().maximum(),
                 v._scroll.verticalScrollBar().maximum())
        if simdi == onceki:
            return True
        onceki = simdi
        _dongu(10)
    return False


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
    assert _bekle_kararli(v), "yerleşim durulmadı"
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
    assert _bekle_kararli(v), "yerleşim durulmadı"
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
    v._hedefe_kaydir(etiket, 1500, 100, genis,
                     v._scroll.viewport().height() // 2)
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


# =====================================================================
# PDF iç bağlantısı (\ref, \cite, içindekiler)
#
# `resolve_dest_scroll_y` XYZ hedefinin x'ini `gorsele` ile HESAPLIYOR ve
# yalnız y'yi döndürüyordu. Ölçüldü (2026-09-07): hedef x=500 pt olan bir
# XYZ bağlantısında %300'de yatay kaydırma 0'da kalıyor, hedef 0..404
# bandının çok dışında. İki sütunlu şablonda sağ sütuna giden her `\ref`
# tam bu duruma düşüyor.
# =====================================================================


def _ic_baglanti_pdf(yol, hedef_x=500, hedef_y=700):
    """İki sayfa; 1. sayfadaki bağlantı 2. sayfanın SAĞ üstüne gidiyor."""
    ic1 = b"BT /F1 12 Tf 50 700 Td (git) Tj ET"
    ic2 = b"BT /F1 12 Tf %d %d Td (HEDEF) Tj ET" % (hedef_x, hedef_y)
    nesneler = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R 5 0 R]/Count 2>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Annots[7 0 R]"
        b"/Resources<</Font<</F1 6 0 R>>>>/Contents 4 0 R>>",
        b"<</Length " + str(len(ic1)).encode() + b">>stream\n" + ic1 +
        b"\nendstream",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 6 0 R>>>>/Contents 8 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        b"<</Type/Annot/Subtype/Link/Rect[50 695 150 715]/Border[0 0 0]"
        b"/Dest[5 0 R/XYZ %d %d 0]>>" % (hedef_x, hedef_y),
        b"<</Length " + str(len(ic2)).encode() + b">>stream\n" + ic2 +
        b"\nendstream",
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


@pytest.fixture
def ic_gorucu(qapp, tmp_path):
    v = PdfViewer(theme=THEMES["dark"])
    v.resize(420, 520)
    v.show()
    assert v.load_pdf(_ic_baglanti_pdf(tmp_path / "ic.pdf"))
    _dongu()
    yield v
    v.shutdown()
    v.close()
    QApplication.instance().sendPostedEvents(
        None, QEvent.Type.DeferredDelete)


def _ilk_dest(v):
    poz = ctypes.c_int(0)
    link = praw.FPDF_LINK()
    with pdfium_lock:
        ok = praw.FPDFLink_Enumerate(v._pdf[0].raw, ctypes.byref(poz),
                                     ctypes.byref(link))
        assert ok, "kapı boş koşuyor: PDF'te bağlantı yok"
        return praw.FPDFLink_GetDest(v._pdf.raw, link)


@gui
def test_ic_baglanti_hedefi_YATAY_olarak_goruntuye_getiriyor(ic_gorucu):
    """Kırılırsa: sağ sütundaki bir `\ref`e tıklayan kullanıcı doğru satıra
    iniyor ama sol sütuna bakıyor."""
    v = ic_gorucu
    _yakinlastir(v)
    v._goto_dest(_ilk_dest(v))
    _dongu()
    etiket = v._page_labels[1]
    with pdfium_lock:
        hx = gorsele(geometri(v._pdf[1]), 500.0, 700.0, v._olcek(1))[0]
    x = _mutlak_x(v, etiket, hx)
    sol, sag = _yatay_bant(v)
    assert v._current_page == 1, "hedef sayfaya gidilmedi"
    assert sol <= x < sag, (
        "hedef yatayda görüntü dışında: x=%d, bant %d..%d" % (x, sol, sag))


@gui
def test_ic_baglanti_DIKEY_payi_korunuyor(ic_gorucu):
    """Aşırı düzeltme kapısı: iç bağlantı hedefi 20 px pay bırakıyordu,
    ortalamaya geçmemeli."""
    v = ic_gorucu
    _yakinlastir(v)
    v._goto_dest(_ilk_dest(v))
    _dongu()
    etiket = v._page_labels[1]
    with pdfium_lock:
        hy = gorsele(geometri(v._pdf[1]), 500.0, 700.0, v._olcek(1))[1]
    ust = etiket.mapTo(v._pages_widget, QPoint(0, 0)).y() + int(hy)
    assert v._scroll.verticalScrollBar().value() == max(0, ust - 20)
