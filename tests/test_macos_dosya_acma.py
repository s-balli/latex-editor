# -*- coding: utf-8 -*-
"""macOS'ta `.tex` dosyasina cift tiklayinca uygulama onu ACIYOR mu.

macOS acilan belgeyi `sys.argv`de VERMIYOR: LaunchServices bir Apple
Event gonderiyor, Qt de onu `QEvent.Type.FileOpen` olarak iletiyor.
Uygulama yalniz `sys.argv` okuyordu, yani Info.plist'teki `.tex`
iliskilendirmesi HICBIR SEY yapmiyordu.

OLCULDU (2026-09-18, macos-15, YAYINLANAN .dmg kurulup
`open -a "LaTeX Editor" deneme.tex` ile): uygulama aciliyor ama
duzenleyici BOS kaliyor; ekran goruntusunde dosya listesi de bos.

Iliskilendirmeyi bu oturumda Info.plist'e BEN ekledim, yani vaadi de
karsiligi olmayan hale getiren bendim.

Kapilar Qt'siz kosuyor: `_Uygulama.event` ve `aliciyi_bagla` saf
mantik, olay nesnesi sahte.
"""

import os
import sys

import pytest

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_KOK, "desktop"))


class _SahteOlay:
    """QFileOpenEvent'in sinanan yuzeyi: `type()` ve `file()`."""

    def __init__(self, tur, yol=""):
        self._tur = tur
        self._yol = yol

    def type(self):
        return self._tur

    def file(self):
        return self._yol


@pytest.fixture
def uygulama(monkeypatch):
    """`_Uygulama`yi QApplication kurmadan ornekle.

    `QApplication.__init__` gercek bir Qt uygulamasi baslatirdi; kapinin
    sinadigi sey o degil, olay yonlendirmesi.
    """
    import main as giris

    nesne = giris._Uygulama.__new__(giris._Uygulama)
    nesne._bekleyen = []
    nesne._alici = None
    # `super().event` cagrilirsa Qt'ye gitmesin.
    monkeypatch.setattr(giris.QApplication, "event",
                        lambda self, olay: "QT_ISLEDI", raising=False)
    return nesne, giris


class TestDosyaAcmaOlayi:

    def test_ALICI_BAGLIYKEN_dogrudan_iletiliyor(self, uygulama):
        nesne, giris = uygulama
        gelenler = []
        nesne.aliciyi_bagla(gelenler.append)
        sonuc = nesne.event(_SahteOlay(giris.QEvent.Type.FileOpen, "/a/b.tex"))
        assert gelenler == ["/a/b.tex"]
        assert sonuc is True

    def test_PENCERE_YOKKEN_kuyruga_alinip_sonra_iletiliyor(self, uygulama):
        r"""Acilista dosyaya cift tiklamak tam olarak bu: olay pencere
        kurulmadan once geliyor. Kuyruk olmasa dosya SESSIZCE duserdi."""
        nesne, giris = uygulama
        nesne.event(_SahteOlay(giris.QEvent.Type.FileOpen, "/a/ilk.tex"))
        nesne.event(_SahteOlay(giris.QEvent.Type.FileOpen, "/a/ikinci.tex"))
        gelenler = []
        nesne.aliciyi_bagla(gelenler.append)
        assert gelenler == ["/a/ilk.tex", "/a/ikinci.tex"]

    def test_KUYRUK_iki_kez_iletmiyor(self, uygulama):
        """Baglama yinelenirse dosya iki kez acilirdi."""
        nesne, giris = uygulama
        nesne.event(_SahteOlay(giris.QEvent.Type.FileOpen, "/a/b.tex"))
        gelenler = []
        nesne.aliciyi_bagla(gelenler.append)
        nesne.aliciyi_bagla(gelenler.append)
        assert gelenler == ["/a/b.tex"]

    def test_BOS_yol_yok_sayiliyor(self, uygulama):
        nesne, giris = uygulama
        gelenler = []
        nesne.aliciyi_bagla(gelenler.append)
        nesne.event(_SahteOlay(giris.QEvent.Type.FileOpen, ""))
        assert gelenler == []

    def test_BASKA_olaylar_Qt_ye_birakiliyor(self, uygulama):
        """KARSI KOL: her olayi yutmak uygulamayi calismaz hale getirirdi."""
        nesne, giris = uygulama
        sonuc = nesne.event(_SahteOlay(giris.QEvent.Type.Close))
        assert sonuc == "QT_ISLEDI"


def test_ACILISTA_BAGLANIYOR():
    """Sinif var olup baglanmazsa hicbir sey degismez.

    Baglamanin pencere KURULDUKTAN sonra olmasi sart: alici pencerenin
    kendi yontemi.
    """
    with open(os.path.join(_KOK, "desktop", "main.py"), encoding="utf-8") as f:
        kaynak = f.read()
    assert "app = _Uygulama(sys.argv)" in kaynak, "ozel uygulama kullanilmiyor"
    assert "app.aliciyi_bagla(window.open_from_other_instance)" in kaynak, \
        "alici baglanmiyor"
    assert kaynak.index("window = MainWindow(") < \
        kaynak.index("app.aliciyi_bagla("), "baglama pencereden ONCE"
