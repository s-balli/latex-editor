# -*- coding: utf-8 -*-
"""gui/doi_fetch.py — DOI getirme işçisi ve onay diyaloğu.

Bu modülün HİÇ testi yoktu, oysa ağ çağrısı yapıp sonucu `.bib` dosyasına
yazılacak bir akışı besliyor ve arka plan iş parçacığı kullanıyor.

Ağa çıkılmıyor: `doi_getir` taklit ediliyor. Sınanan şey ağ değil, işçinin
kendi sözleşmesi (meşgul koruması, hata kodunun taşınması).
"""

import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    import gui.doi_fetch as df
    from core.bibtex import DoiHatasi
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


HAM = ("@article{smith_2020_bir,"
       " author={Smith, John}, title={Bir Calisma},"
       " journal={Dergi}, year={2020}, pages={10--20}}")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def kosucu(qapp, monkeypatch):
    """(runner, yayınlar) — `done` sinyali listeye toplanır."""
    r = df.DoiRunner()
    yayin = []
    r.done.connect(lambda ok, metin, anahtar, hata:
                   yayin.append((ok, anahtar, hata)))
    yield r, yayin
    r.wait(3000)


def _bekle(qapp, kosul, saniye=6.0):
    """İş parçacığından gelen sinyal teslim edilene kadar olay döngüsünü çevir."""
    son = time.monotonic() + saniye
    while time.monotonic() < son and not kosul():
        qapp.processEvents()
        time.sleep(0.01)
    return kosul()


def _yavas(doi, ac=None):
    time.sleep(0.4)
    return HAM


def _hizli(doi, ac=None):
    return HAM


def test_SUREN_IS_VARKEN_ikinci_istek_reddediliyor(qapp, kosucu, monkeypatch):
    """Aksi hâlde .bib'e AYNI ANAHTARLI iki girdi giriyor.

    Ağ çağrısı ~0.5 sn ama zaman aşımı 8 sn; kullanıcı "bir şey olmadı"
    sanıp komutu tekrar veriyor. Ölçüldü: korumasız hâlde iki `done`
    sinyali yayılıyor ve ikisi de aynı anahtarı taşıyor, çünkü
    `mevcut_anahtarlar` her iki çağrıda da ilk yazımdan ÖNCE okunuyor.
    BibTeX mükerrer anahtarda sessizce ilkini alıyor.

    Kardeş işçilerde (`_ExportRunner`, `_SnapshotRunner`) bu koruma
    çağıranda duruyor; burada hiç yoktu.
    """
    r, yayin = kosucu
    monkeypatch.setattr(df, "doi_getir", _yavas)

    ilk = r.start("10.1000/x", ["baska2019"])
    ilk_thread = r._thread
    time.sleep(0.05)
    ikinci = r.start("10.1000/x", ["baska2019"])

    assert (ilk, ikinci) == (True, False)
    assert r._thread is ilk_thread, "izlenen iş parçacığı ezildi"

    assert _bekle(qapp, lambda: len(yayin) >= 1)
    time.sleep(0.3)                 # ikincisi bir şey yayacaksa görülsün
    qapp.processEvents()
    assert len(yayin) == 1, "ikinci istek de sonuç yaydı"


def test_is_bitince_yeni_istek_kabul_ediliyor(qapp, kosucu, monkeypatch):
    """Koruma kalıcı kilit olmamalı."""
    r, yayin = kosucu
    monkeypatch.setattr(df, "doi_getir", _hizli)

    assert r.start("10.1000/a", []) is True
    assert _bekle(qapp, lambda: len(yayin) >= 1)
    assert _bekle(qapp, lambda: not r._thread.is_alive())

    assert r.start("10.1000/b", []) is True
    assert _bekle(qapp, lambda: len(yayin) >= 2)


def test_HATA_ile_biten_isten_sonra_da_kilit_aciliyor(qapp, kosucu, monkeypatch):
    """Hata yolunda kilit açık kalsaydı özellik oturum boyunca ölürdü."""
    r, yayin = kosucu

    def patlar(doi, ac=None):
        raise DoiHatasi("bulunamadi")

    monkeypatch.setattr(df, "doi_getir", patlar)
    r.start("10.1000/yok", [])
    assert _bekle(qapp, lambda: len(yayin) >= 1)
    assert yayin[0] == (False, "", "bulunamadi"), "hata KODU taşınmadı"

    assert _bekle(qapp, lambda: not r._thread.is_alive())
    monkeypatch.setattr(df, "doi_getir", _hizli)
    assert r.start("10.1000/var", []) is True
    assert _bekle(qapp, lambda: len(yayin) >= 2)


def test_beklenmedik_istisna_ag_hatasina_cevriliyor(qapp, kosucu, monkeypatch):
    """`DoiHatasi` olmayan istisna iş parçacığını sessizce öldürmemeli.

    Öldürseydi `done` hiç yayılmaz, durum çubuğu "DOI getiriliyor..."da
    kalır ve meşgul koruması nedeniyle sonraki istekler de reddedilirdi.
    """
    r, yayin = kosucu

    def bozuk(doi, ac=None):
        raise RuntimeError("beklenmedik")

    monkeypatch.setattr(df, "doi_getir", bozuk)
    r.start("10.1000/x", [])

    assert _bekle(qapp, lambda: len(yayin) >= 1), "hiç sonuç yayılmadı"
    assert yayin[0] == (False, "", "ag")


def test_onay_diyalogu_metni_kirpip_veriyor(qapp):
    """Düzenlenebilir metin; dosyaya giden tam olarak ekranda görünen."""
    dlg = df.DoiOnayDialog("  @article{k,\n title={X},\n}  \n", "refs.bib")
    assert dlg.girdi() == "@article{k,\n title={X},\n}"
    dlg.deleteLater()
