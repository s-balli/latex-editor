# -*- coding: utf-8 -*-
"""gui/synctex_worker.py — uzun ömürlü SyncTeX arama işçisinin sözleşmesi.

Bu modülün HİÇ testi yoktu. Tüketicisi `synctex_ops` iyi test edilmiş ama
hep SAHTE bir işçiye karşı (`tests/test_tex_root_and_jump.py` içinde
`_RecWorker`); gerçek QThread hiç koşmuyordu.

Köprü (`forward_search`/`reverse_search`) taklit ediliyor: sınanan şey
SyncTeX değil, işçinin kendi değişmezleri — istek birleştirme, context'in
doğru taşınması, istisnada hayatta kalma, temiz kapanma.

DİKKAT: her test işçiyi durdurup BEKLEMEK zorunda. Bu depoda yarıda kalan
bir QThread bir kez süreci exit 9 ile öldürdü ve o noktadan sonraki testler
hiç koşmadı.
"""

import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    import gui.synctex_worker as sw
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isci(qapp, monkeypatch):
    """(fabrika, yayınlar) — fabrika(ileri=..., geri=...) işçiyi başlatır."""
    tutulan = []
    yayin = []

    def fabrika(ileri=None, geri=None):
        if ileri is not None:
            monkeypatch.setattr(sw, "forward_search", ileri)
        if geri is not None:
            monkeypatch.setattr(sw, "reverse_search", geri)
        w = sw.SyncTexWorker()
        tutulan.append(w)
        w.done.connect(lambda k, r, c: yayin.append((k, r, c)))
        w.start()
        return w

    yield fabrika, yayin

    for w in tutulan:
        w.stop()
        assert w.wait(4000), "işçi kapanmadı; yarıda kalan QThread süreci öldürür"


def _bekle(qapp, kosul, saniye=5.0):
    son = time.monotonic() + saniye
    while time.monotonic() < son and not kosul():
        qapp.processEvents()
        time.sleep(0.005)
    return kosul()


def test_istek_sonucu_KENDI_contextiyle_donuyor(qapp, isci):
    """Sonuç daima isteğin kendi etiketine uygulanmalı."""
    fabrika, yayin = isci
    w = fabrika(ileri=lambda *a: ("ileri", a[1]))
    ctx = ("a.tex", 5, False)

    w.submit("forward", ("a.tex", 5, 1, "a.pdf"), "/sd", context=ctx)

    assert _bekle(qapp, lambda: len(yayin) == 1)
    assert yayin[0] == ("forward", ("ileri", 5), ctx)


def test_reverse_argumanlari_dogru_acılıyor(qapp, isci):
    """`args` demeti köprünün imzasıyla eşleşmeli.

    Tüketici hep sahte işçiyle sınandığı için gerçek çağrı hiç koşmuyordu;
    imza kayması sessizce fark edilmezdi.
    """
    fabrika, yayin = isci
    gelen = []
    w = fabrika(geri=lambda *a: gelen.append(a) or ("geri", a[0]))

    w.submit("reverse", (3, 1.5, 2.5, "a.pdf"), "/sd", context=3)

    assert _bekle(qapp, lambda: len(yayin) == 1)
    assert gelen == [(3, 1.5, 2.5, "a.pdf", "/sd")]
    assert yayin[0] == ("reverse", ("geri", 3), 3)


def test_hizli_istekler_SONUNCUDA_birlesiyor(qapp, isci):
    """Kuyruk tek istek tutuyor; aradakiler eziliyor ama SONUNCU işlenmeli.

    Gereksiz WSL süreçlerinin çoğalmaması bu birleştirmeye bağlı. Sonuncunun
    işlenmesi ise doğruluk şartı: kullanıcının son tıkladığı yer.
    """
    fabrika, yayin = isci
    islenen = []

    def yavas(*a):
        islenen.append(a[1])
        time.sleep(0.15)
        return ("ileri", a[1])

    w = fabrika(ileri=yavas)
    for i in range(1, 6):
        w.submit("forward", ("a.tex", i, 1, "a.pdf"), "/sd", context=i)
        time.sleep(0.01)

    # Bekleme SİNYALE bağlanmalı, `islenen`e değil: `islenen` işlemenin
    # BAŞINDA doluyor, o an `done` henüz yayılmamış oluyor.
    assert _bekle(qapp, lambda: 5 in [c for _k, _r, c in yayin]), \
        "son istek işlenmedi"
    assert len(islenen) < 5, "her istek ayrı ayrı işlendi, birleştirme yok"
    assert [c for _k, _r, c in yayin] == islenen, "context sırası kaydı"


def test_koprudeki_ISTISNA_isciyi_oldurmuyor(qapp, isci):
    """İşçi ölseydi sonraki bütün SyncTeX aramaları sessizce ölürdü.

    Tek uzun ömürlü thread var; o giderse yeniden başlatan da yok.
    """
    fabrika, yayin = isci
    sayac = {"n": 0}

    def patlayan(*a):
        sayac["n"] += 1
        if sayac["n"] == 1:
            raise RuntimeError("köprü patladı")
        return ("ileri", "ikinci")

    w = fabrika(ileri=patlayan)
    w.submit("forward", ("a.tex", 1, 1, "a.pdf"), "/sd", context="ilk")
    assert _bekle(qapp, lambda: len(yayin) >= 1)
    assert yayin[0] == ("forward", None, "ilk"), "istisnada da sonuç yayılmalı"

    w.submit("forward", ("a.tex", 2, 1, "a.pdf"), "/sd", context="ikinci")
    assert _bekle(qapp, lambda: len(yayin) >= 2), "işçi istisnadan sonra öldü"
    assert yayin[1] == ("forward", ("ileri", "ikinci"), "ikinci")
    assert w.isRunning()


def test_bilinmeyen_kind_sessizce_yutulmuyor(qapp, isci):
    """Sonuç yayılmasaydı çağıran sonsuza dek beklerdi."""
    fabrika, yayin = isci
    w = fabrika()

    w.submit("hicbiri", (), "/sd", context="x")

    assert _bekle(qapp, lambda: len(yayin) == 1)
    assert yayin[0] == ("hicbiri", None, "x")


def test_bostaki_isci_stop_ile_HEMEN_cikiyor(qapp, isci):
    """Kapanış beklemesi kullanıcıyı bekletmemeli."""
    fabrika, _yayin = isci
    w = fabrika()

    baslangic = time.monotonic()
    w.stop()
    assert w.wait(3000)
    assert (time.monotonic() - baslangic) < 1.0


def test_stop_SONRASI_submit_is_baslatmiyor(qapp, isci):
    """Kapanmış işçiye gelen istek sessizce düşmeli, sonuç yaymamalı."""
    fabrika, yayin = isci
    w = fabrika(ileri=lambda *a: ("ileri", 1))
    w.stop()
    assert w.wait(3000)

    w.submit("forward", ("a.tex", 1, 1, "a.pdf"), "/sd", context="ölü")

    assert not _bekle(qapp, lambda: len(yayin) >= 1, saniye=0.4)
