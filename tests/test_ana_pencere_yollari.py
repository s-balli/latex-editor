# -*- coding: utf-8 -*-
"""Ana pencere yolları: tek kaynak kuralı ve diyaloglara giren dış değerler.

İkisi de 2026-09-06 turunda kapatılan GİZLİ kırılganlıklar. Hiçbiri o gün
canlı hata üretmiyordu; testler, engelledikleri kırılmayı tutuyor.
"""

import os
import re
import types

import pytest

pytest.importorskip("PyQt6")


def _norm(yol: str) -> str:
    return os.path.normcase(os.path.normpath(yol or ""))


@pytest.fixture(scope="session")
def qapp():
    """QApplication REFERANSI TUTULMALI (bkz. test_menu_actions.py aynı ders)."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# --- Açılabilir uzantı kümesi TEK KAYNAK olmalı ---
#
# `_OPENABLE_EXT` sabitinin yorumu "sürükle-bırakla AYNI küme" diyordu ama
# `_handle_dropped_urls` sabiti kullanmıyor, kendi düz demetini taşıyordu.
# İkisi aynıydı, yani hata yoktu; kırılma bir sonraki uzantı eklendiğinde
# geliyordu. Ölçüldü (2026-09-06): sabite `.ltx` eklendiğinde "Birlikte Aç"
# açıyor, sürükle-bırak görmezden geliyordu.


@pytest.fixture
def pencere(ana_pencere, tmp_path):
    """Dosya açma/görsel ekleme çağrılarını yakalayan gerçek MainWindow."""
    from PyQt6.QtCore import QUrl

    w = ana_pencere()
    acilan, gorsel = [], []
    w._open_file_in_editor = lambda yol, *a, **k: acilan.append(yol)
    w._insert_image = lambda yol: gorsel.append(yol)

    def _dosya(ad):
        y = tmp_path / ad
        y.write_text("x\n", encoding="utf-8")
        return str(y)

    def _iki_yol(yol):
        """(Birlikte Aç açtı mı, sürükle-bırak açtı mı)"""
        acilan.clear()
        w.open_from_other_instance(yol)
        birlikte = bool(acilan)
        acilan.clear()
        w._handle_dropped_urls([QUrl.fromLocalFile(yol)])
        return birlikte, bool(acilan)

    w.dosya = _dosya
    w.iki_yol = _iki_yol
    w.gorsel = gorsel
    return w


def test_uzanti_kumesi_TEK_KAYNAK(pencere, monkeypatch):
    """Sabite eklenen uzantıyı İKİ yol da tanımalı."""
    from gui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_OPENABLE_EXT",
                        MainWindow._OPENABLE_EXT + (".ltx",))
    birlikte, surukle = pencere.iki_yol(pencere.dosya("belge.ltx"))
    assert birlikte, "ön koşul: 'Birlikte Aç' yeni uzantıyı açmalı"
    assert surukle, (
        "sürükle-bırak sabiti kullanmıyor: uzantı kümesi tek kaynak değil")


def test_sabite_eklenmeyen_uzanti_IKI_YOLDA_da_reddediliyor(pencere):
    """AŞIRI DÜZELTME KAPISI: kapı 'her şeyi kabul et'e dönmemeli."""
    birlikte, surukle = pencere.iki_yol(pencere.dosya("belge.ltx"))
    assert not birlikte and not surukle
    birlikte, surukle = pencere.iki_yol(pencere.dosya("baska.txt"))
    assert not birlikte and not surukle


def test_desteklenen_uzanti_IKI_YOLDA_da_aciliyor(pencere):
    birlikte, surukle = pencere.iki_yol(pencere.dosya("normal.tex"))
    assert birlikte and surukle


def test_gorsel_surukle_birak_yolu_bozulmadi(pencere):
    """Görsel demeti ayrı ve tek kullanımlık; değişiklik ona dokunmamalı."""
    from PyQt6.QtCore import QUrl

    pencere.gorsel.clear()
    pencere._handle_dropped_urls([QUrl.fromLocalFile(pencere.dosya("r.png"))])
    assert pencere.gorsel


# --- Güncelleme diyaloğuna giren dış değerler KAÇIŞLI olmalı ---
#
# `tag`, `url` ve `notes` üçü de GitHub Releases yanıtından geliyor. Ders
# `notes` için öğrenilmiş ve gerekçesi koda yazılmıştı, ama aynı f-string'deki
# `tag` ile `url` dışarıda kalmıştı. Ölçüldü (2026-09-06): `<...>` içeren bir
# etiket yutuluyor, tek tırnak içeren bir url `href` özniteliğini erken
# kapatıp bağlantı hedefini kırpıyordu.

TEMEL = {"tag": "v1.0.21", "url": "https://example.org/r", "notes": "not"}


@pytest.fixture
def guncelleme_diyalogu(qapp, monkeypatch):
    """`_on_update_found`u koştur; (HTML, tarayıcıya giden ham url) döndür."""
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import QMessageBox, QWidget
    from gui.main_window import MainWindow
    from gui.theme import THEMES

    class _Vekil(QWidget):
        def __init__(self):
            super().__init__()
            self._theme_mgr = types.SimpleNamespace(theme=THEMES["dark"])
            self._status = types.SimpleNamespace(
                showMessage=lambda *a, **k: None)

    def _calistir(info, tikla=False):
        yak = {}
        dugmeler = []
        asil_add = QMessageBox.addButton

        def _add(self, *a, **k):
            b = asil_add(self, *a, **k)
            dugmeler.append(b)
            return b

        monkeypatch.setattr(QMessageBox, "setText",
                            lambda self, h: yak.setdefault("h", h))
        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        monkeypatch.setattr(QMessageBox, "addButton", _add)
        monkeypatch.setattr(
            QMessageBox, "clickedButton",
            lambda self: (dugmeler[0] if tikla and dugmeler else None))
        monkeypatch.setattr(
            QDesktopServices, "openUrl",
            staticmethod(lambda u: yak.setdefault("url", u.toString())))

        MainWindow._on_update_found(_Vekil(), info)
        assert len(yak.get("h", "")) > 100, "kapı boşa düşmesin, gövde yok"
        return yak.get("h", ""), yak.get("url")

    return _calistir


def _gorunen(html):
    """Qt'ye çizdirip kullanıcının GÖRDÜĞÜ düz metni al."""
    from PyQt6.QtWidgets import QTextBrowser

    tb = QTextBrowser()
    tb.setHtml(html)
    metin = tb.toPlainText()
    tb.deleteLater()
    return metin


@pytest.mark.parametrize("alan,deger", [
    ("tag", "v1.0.21-<rc1>"),
    ("notes", "onceki <deneme> surumu duzeltildi"),
])
def test_diyalogda_acili_parantez_yutulmuyor(guncelleme_diyalogu, alan, deger):
    html, _ = guncelleme_diyalogu(dict(TEMEL, **{alan: deger}))
    assert deger in _gorunen(html), f"{alan} alanı yutuldu"


def test_url_oznitelikte_erken_KAPATMIYOR(guncelleme_diyalogu):
    """Öznitelik tek tırnakla açılıyor; url'deki tek tırnak onu kapatırdı."""
    import html as _html

    zor = "https://example.org/r?a='b'&c=<d>"
    html, _ = guncelleme_diyalogu(dict(TEMEL, url=zor))
    m = re.search(r"<a href='([^']*)'", html)
    assert m, "bağlantı bulunamadı"
    # Doğru gösterim kaçışlı olabilir; varlıkları çözüp KARŞILAŞTIR.
    assert _html.unescape(m.group(1)) == zor, (
        "bağlantı hedefi kırpıldı: " + m.group(1))


def test_tarayiciya_giden_url_HAM_kaliyor(guncelleme_diyalogu):
    """AŞIRI DÜZELTME KAPISI: kaçış yalnız işaretlemeye giren kopyada.

    `QDesktopServices.openUrl` ham url'yi almalı; HTML varlıkları oraya
    sızarsa kullanıcı bozuk bir adrese gider.
    """
    _html_govde, ham = guncelleme_diyalogu(dict(TEMEL), tikla=True)
    assert ham == TEMEL["url"]

    zor = "https://example.org/r?a='b'&c=<d>"
    _h, ham2 = guncelleme_diyalogu(dict(TEMEL, url=zor), tikla=True)
    # QUrl kendi normalizasyonunu yapıyor (`<` -> `%3C`), bu kaçışla ilgisiz.
    assert ham2 and "&#x27;" not in ham2 and "&amp;" not in ham2
    assert "?a='b'&c=" in ham2


def test_olagan_degerler_bozulmadan_gorunuyor(guncelleme_diyalogu):
    html, _ = guncelleme_diyalogu(dict(TEMEL))
    duz = _gorunen(html)
    assert "v1.0.21" in duz and "not" in duz
