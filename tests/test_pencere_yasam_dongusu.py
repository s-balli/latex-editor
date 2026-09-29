# -*- coding: utf-8 -*-
"""`ana_pencere` fixture'inin teardown sozlesmesi.

NE OLDU. Bu fixture'i kullanan BIR test daha eklenince tam takim Windows'ta
butun testler gectikten SONRA, cikista 0xC0000409 (fail-fast, stderr bos) ile
dusuyordu. Kusur YARIS, 6'sar kosuyla olculdu:

    yuk yok (o gunku commit)        0/6 cokme
    yuk var, bosaltma YOK           2/6 cokme
    yuk var, bosaltma VAR           0/6 cokme

Onceki turun 4'er kosusuyla birlikte: bosaltmasiz 4/10, bosaltmali 0/10.

NE OLCULEMEDI. MEKANIZMA. "Pencereler zombi kalip QApplication yikilirken
topluca oluyor" aciklamasini kurup teardown sonrasi 3/3 pencerenin yasadigini
olcmustum; ayni olcumu yineleyince 0/4 cikti, yani aciklama TUTMADI. Yerli
yigin izi (WER/cdb) olmadan mekanizma kurulamiyor.

BU DOSYADAKI KAPI YAPISAL, davranissal DEGIL. Davranissal bir kapi denendi ve
BIRAKILDI: kardes fixture `_sahipsiz_qsci_temizle` de DeferredDelete
kuyrugunu bosaltiyor, o yuzden "pencere teardown sonrasi olmus mu" testi
bosaltma kaldirilsa bile YESIL kaliyordu, yani yanlis nedenle geciyordu
(mutasyonlarin 0/4'unu yakaladi). Yanlis nedenle gecen bir kapi, kapi
degildir.
"""
import pathlib

import pytest


def _conftest_kaynagi() -> str:
    kok = pathlib.Path(__file__).resolve().parents[1]
    return (kok / "tests" / "conftest.py").read_text(encoding="utf-8")


def test_ana_pencere_teardownu_DEFERREDDELETE_bosaltiyor():
    """Kirilirsa: teardown yine yalniz deleteLater cagiriyor demektir."""
    ck = _conftest_kaynagi()
    i = ck.index("def ana_pencere")
    # Yalniz fixture'in kendi govdesi: asagidaki kanca da bosaltiyor ve
    # aramaya girseydi bu satir silinse de kapi yesil kalirdi.
    govde = ck[i:ck.index("def pytest_runtest_teardown")]
    # Sozlesme IKI parcali: once kuyruga al, sonra bosalt. Biri eksikse
    # teardown pencereyi yok etmiyor demektir.
    assert "w.deleteLater()" in govde, (
        "ana_pencere teardown'u pencereyi deleteLater ile kuyruga almiyor")
    assert "sendPostedEvents(None, QEvent.Type.DeferredDelete)" in govde, (
        "ana_pencere teardown'u DeferredDelete kuyrugunu bosaltmiyor; "
        "olculdu: bu satir olmadan yuklu takim 6 kosunun 2'sinde 0xC0000409 "
        "ile dusuyor")


def test_HER_testin_sonunda_bosaltiliyor():
    """Kendi PdfViewer'ini kurup `deleteLater` ile biten testler de. Kosul
    yalniz `ana_pencere`ydi; OLCULDU (2026-09-29, Linux tam takim): bekleyen
    goruntuleyicinin rangeChanged vekili birakilmis lambda'yi cagirip SIGSEGV
    veriyordu (bkz. conftest.pytest_runtest_teardown)."""
    ck = _conftest_kaynagi()
    kanca = ck[ck.index("def pytest_runtest_teardown"):]
    assert "sendPostedEvents(None, QEvent.Type.DeferredDelete)" in kanca
    govde = kanca[kanca.index("finally:"):]
    assert "ana_pencere" not in govde, "bosaltma yine ana_pencere'ye bagli"


def test_kardes_fixture_dersi_TASIMAYA_devam_ediyor():
    """Dersin kaynagi `_sahipsiz_qsci_temizle`; o kaybederse ikisi de kayar."""
    ck = _conftest_kaynagi()
    i = ck.index("def _sahipsiz_qsci_temizle")
    j = ck.index("def ana_pencere")
    assert "sendPostedEvents(None, QEvent.Type.DeferredDelete)" in ck[i:j]


def test_kapi_BOS_KOSMUYOR():
    """Aranan dizge gercekten ayirt edici mi (desen bozulursa test yesil kalir)."""
    ck = _conftest_kaynagi()
    # kardes fixture + ana_pencere sokumu + her testin sonu (pytest_runtest_teardown)
    assert ck.count("sendPostedEvents(None, QEvent.Type.DeferredDelete)") == 3, (
        "beklenen uc gecis (kardes fixture, ana_pencere, runtest_teardown) yok")
    pytest.importorskip("PyQt6")
