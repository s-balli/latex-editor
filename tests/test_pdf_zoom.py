# -*- coding: utf-8 -*-
"""Yakınlaştırma kullanıcının BAKTIĞI yeri kaybediyordu.

Ölçek değişince sayfa yükseklikleri büyüyor, kaydırma çubuğunun değeri ise
duruyor. ÖLÇÜLDÜ (2026-09-07, altı sayfalık belge, %75'ten dört adım):
görüntünün ortası 4. sayfanın %50'sinden 3. sayfanın %77'sine gidiyor, yani
bir sayfa geriye. Yakınlaştırma, uzaklaştırma ve "sığdır" komutları için de
aynı.

Çapa `rangeChanged`den geri konuyor, zamanlayıcıdan DEĞİL: yeni yerleşim
eşzamanlı olarak hazır olmuyor. ÖLÇÜLDÜ, `_update_page_sizes` hemen ardından
sayfa konumu hâlâ eski ve `layout().activate()`, `sendPostedEvents(
LayoutRequest)`, `processEvents()`, hatta 0 ms'lik zamanlayıcı yetmiyor;
`rangeChanged` ise tam bir kez ve yerleşmiş düzenle geliyor.

Bu dosya `_fit_zoom`, `fit_width`, `fit_page` ve `wheelEvent` için de ilk
kapı: dördü de hiç koşmuyordu (ölçüldü 2026-09-07).
"""

import os

import pytest

try:
    from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QPointF, Qt, QTimer
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtWidgets import QApplication
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="PyQt6 / gui modülleri gerekli")

SAYFA_SAYISI = 6


@pytest.fixture(scope="module")
def qapp():
    if not _VAR:
        yield None
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QApplication.instance() or QApplication([])


def _cok_sayfali_pdf(yol, sayfa=SAYFA_SAYISI):
    """Altı sayfalık PDF; her sayfada bir satır metin."""
    nesneler = [b"<</Type/Catalog/Pages 2 0 R>>"]
    kids = " ".join("%d 0 R" % (3 + 2 * i) for i in range(sayfa))
    nesneler.append(("<</Type/Pages/Kids[%s]/Count %d>>"
                     % (kids, sayfa)).encode())
    for i in range(sayfa):
        ic = b"BT /F1 12 Tf 50 700 Td (sayfa %d) Tj ET" % (i + 1)
        nesneler.append(
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
            b"/Resources<</Font<</F1 %d 0 R>>>>/Contents %d 0 R>>"
            % (3 + 2 * sayfa, 4 + 2 * i))
        nesneler.append(b"<</Length " + str(len(ic)).encode()
                        + b">>stream\n" + ic + b"\nendstream")
    nesneler.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
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


def _dongu(ms=50):
    """Gerçek olay döngüsü.

    Yerleşim eşzamanlı hazır olmadığı için ŞART; `processEvents` yetmiyor
    (ölçüldü).
    """
    d = QEventLoop()
    QTimer.singleShot(ms, d.quit)
    d.exec()


@pytest.fixture
def gorucu(qapp, tmp_path):
    v = PdfViewer(theme=THEMES["dark"])
    v.resize(700, 600)
    v.show()
    assert v.load_pdf(_cok_sayfali_pdf(tmp_path / "zoom.pdf"))
    _dongu()
    yield v
    v.shutdown()
    v.close()
    QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _orta_icerik(v):
    """Görüntünün ortasındaki (sayfa, sayfa içi oran)."""
    dikey = v._scroll.verticalScrollBar()
    orta = dikey.value() + v._scroll.viewport().height() // 2
    for i, et in enumerate(v._page_labels):
        ust = et.mapTo(v._pages_widget, QPoint(0, 0)).y()
        if ust <= orta < ust + et.height():
            return i, (orta - ust) / max(et.height(), 1)
    return None, 0.0


def _ortala(v, sayfa=3):
    """Görüntüyü verilen sayfanın ortasına getir."""
    et = v._page_labels[sayfa]
    v._scroll.verticalScrollBar().setValue(
        et.mapTo(v._pages_widget, QPoint(0, 0)).y() + et.height() // 2
        - v._scroll.viewport().height() // 2)
    _dongu()
    i, oran = _orta_icerik(v)
    assert i == sayfa, "kapı boş koşuyor: görüntü istenen sayfaya gelmedi"
    return i, oran


# =====================================================================
# Çapa
# =====================================================================


@gui
@pytest.mark.parametrize("islem, adim", [
    ("zoom_in", 4),
    ("zoom_out", 4),
])
def test_ZOOM_bakilan_yeri_koruyor(gorucu, islem, adim):
    """Kırılırsa: kullanıcı yakınlaştırınca okuduğu yeri kaybediyor."""
    v = gorucu
    sayfa, oran = _ortala(v)
    for _ in range(adim):
        getattr(v, islem)()
        _dongu()          # gerçek kullanımda her adım ayrı bir olay
    yeni_sayfa, yeni_oran = _orta_icerik(v)
    assert yeni_sayfa == sayfa, (
        "sayfa kaydı: %s -> %s" % (sayfa, yeni_sayfa))
    assert abs(yeni_oran - oran) < 0.05, (
        "sayfa içinde kaydı: %%%.0f -> %%%.0f" % (oran * 100, yeni_oran * 100))


@gui
def test_GENISLIGE_SIGDIR_bakilan_yeri_koruyor(gorucu):
    """Sığdırma da bir ölçek değişikliği; yer korunmalı."""
    v = gorucu
    sayfa, oran = _ortala(v)
    v.fit_width()
    _dongu()
    yeni_sayfa, yeni_oran = _orta_icerik(v)
    assert yeni_sayfa == sayfa
    assert abs(yeni_oran - oran) < 0.05


@gui
def test_capa_SAYFA_YOKKEN_cokmuyor(qapp):
    """Belge yüklenmemişken de zoom çağrılabiliyor (araç çubuğu düğmeleri)."""
    v = PdfViewer(theme=THEMES["dark"])
    try:
        assert v._page_labels == []
        v.zoom_in()
        v.zoom_out()
        v._zoom_capasini_uygula()          # bekleyen çapa yok
    finally:
        v.shutdown()
        v.close()


@gui
def test_capa_UYGULANDIKTAN_sonra_temizleniyor(gorucu):
    """Bayrak kalırsa sonraki sıradan kaydırmalar da çapaya çekilirdi."""
    v = gorucu
    _ortala(v)
    v.zoom_in()
    _dongu()
    assert v._bekleyen_zoom_capasi is None


# =====================================================================
# Sığdırma ve sınırlar: bu yollar hiç koşmuyordu
# =====================================================================


@gui
def test_GENISLIGE_SIGDIR_sayfayi_goruntuye_sigdiriyor(gorucu):
    v = gorucu
    v._zoom = 2.0
    v._update_page_sizes()
    _dongu()
    assert v._scroll.horizontalScrollBar().maximum() > 0, \
        "kapı boş koşuyor: sayfa zaten sığıyor"

    v.fit_width()
    _dongu()

    pencere = v._scroll.viewport().width()
    en = v._page_labels[0].width()
    assert en <= pencere, "sayfa hâlâ taşıyor"
    assert v._scroll.horizontalScrollBar().maximum() == 0
    # "Sığdır" ile "küçült" aynı şey değil: genişliğin KULLANILMASI gerekiyor.
    # Kenar payı 20 px (bkz. _fit_zoom). Bu satır olmadan yüksekliğe göre
    # sığdıran bir hata testi geçiyordu (mutasyon yakaladı).
    assert en >= pencere - 30, (
        "genişlik kullanılmıyor: sayfa %d px, görüntü %d px" % (en, pencere))


@gui
def test_SAYFAYA_SIGDIR_sayfanin_TAMAMINI_sigdiriyor(gorucu):
    v = gorucu
    v.fit_page()
    _dongu()
    et = v._page_labels[0]
    assert et.width() <= v._scroll.viewport().width()
    assert et.height() <= v._scroll.viewport().height()


@gui
def test_zoom_TAVANI_gecmiyor(gorucu):
    v = gorucu
    for _ in range(60):
        v.zoom_in()
    assert v._zoom == pytest.approx(3.0)


@gui
def test_zoom_TABANIN_altina_dusmuyor(gorucu):
    v = gorucu
    for _ in range(60):
        v.zoom_out()
    assert v._zoom == pytest.approx(0.05)


# =====================================================================
# Ctrl + tekerlek: bu yol da hiç koşmuyordu
# =====================================================================


def _tekerlek(v, delta, ctrl=True):
    ev = QWheelEvent(
        QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier if ctrl
        else Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False)
    v.wheelEvent(ev)
    return ev


@gui
def test_CTRL_tekerlek_yakinlastiriyor(gorucu):
    v = gorucu
    onceki = v._zoom
    _tekerlek(v, 120)
    assert v._zoom > onceki


@gui
def test_CTRL_tekerlek_geri_yonde_uzaklastiriyor(gorucu):
    v = gorucu
    onceki = v._zoom
    _tekerlek(v, -120)
    assert v._zoom < onceki


@gui
def test_CTRL_YOKKEN_tekerlek_zoom_yapmiyor(gorucu):
    """Aşırı düzeltme kapısı: sıradan tekerlek kaydırma olmalı."""
    v = gorucu
    onceki = v._zoom
    _tekerlek(v, 120, ctrl=False)
    assert v._zoom == onceki
