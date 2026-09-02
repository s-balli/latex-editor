"""Güncelleme diyaloğunda sürüm notları doğru gösterilmeli.

`_on_update_found` notları HTML'e gömüyor. Gerçek v1.0.19 yanıtı Qt'ye
çizdirilerek ölçüldü (2026-09-02):

    ham notlarda dolu satır : 4
    diyalogda çizilen satır : 1

Yani satır sonları HTML'de boşluğa çöküyordu ve 13 madde tek paragrafa
yapışıyordu. Notlar ayrıca kaçışsız gömülüyordu: sürüm notuna bir `<`
girdiği gün gösterim bozulurdu.

Testler QMessageBox'ı değiştirip GERÇEK `_on_update_found`'u çağırıyor.
İlk probum HTML'i kendisi kurmuştu, yani düzeltilen kodu değil kendi
kopyasını ölçüyordu ve düzeltmeden sonra da "bozuk" diyordu.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QTextDocument
    from gui import main_window as mw
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="PyQt6 / gui modülleri gerekli")


class _SahteRol:
    AcceptRole = 0
    RejectRole = 1


class _SahteKutu:
    """QMessageBox yerine: setText'e geleni yakala, exec hiçbir şey yapmasın."""

    son = None
    ButtonRole = _SahteRol

    def __init__(self, *a, **k):
        self.metin = ""
        _SahteKutu.son = self

    def setWindowTitle(self, s):
        pass

    def setText(self, s):
        self.metin = s

    def setInformativeText(self, s):
        pass

    def addButton(self, *a):
        return object()

    def exec(self):
        return 0

    def clickedButton(self):
        return None


class _SahtePencere:
    class _Durum:
        def showMessage(self, s):
            pass

    class _Tema:
        theme = {"fg_primary": "#ffffff"}

    _status = _Durum()
    _theme_mgr = _Tema()


@pytest.fixture(scope="module")
def qapp():
    if not _VAR:
        yield None
        return
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def diyalog(qapp, monkeypatch):
    """(bilgi) -> diyalogda çizilen düz metin."""
    monkeypatch.setattr(mw, "QMessageBox", _SahteKutu)

    def calistir(bilgi):
        mw.MainWindow._on_update_found(_SahtePencere(), bilgi)
        belge = QTextDocument()
        belge.setHtml(_SahteKutu.son.metin)
        return belge.toPlainText()

    return calistir


def _bilgi(notes, kirpildi=False):
    return {"tag": "v9.9.9", "url": "https://ornek/releases",
            "notes": notes, "kirpildi": kirpildi}


@gui
def test_satir_sonlari_korunuyor(diyalog):
    """Maddeler tek paragrafa yapışmamalı."""
    notlar = "- birinci madde\n- ikinci madde\n- ucuncu madde"

    cizilen = diyalog(_bilgi(notlar))

    govde = cizilen.split("notları:")[-1]
    dolu = [s for s in govde.splitlines() if s.strip()]
    assert len(dolu) >= 3, "satır sonları kayboldu: %r" % govde


@gui
def test_html_kacisi_yapiliyor(diyalog):
    """Sürüm notundaki `<b>` etiket olarak işlenmemeli, yazı olarak durmalı."""
    cizilen = diyalog(_bilgi("once <b>kalin</b> & sonra"))

    assert "<b>kalin</b>" in cizilen
    assert "& sonra" in cizilen


@gui
def test_kirpildiginda_kullaniciya_soyleniyor(diyalog):
    """Kesildiğini söylemezsek kullanıcı 13 maddenin 2'sini tamamı sanıyor.

    "Releases" aranmıyor: indirme bağlantısının metninde de geçiyor, o zaman
    uyarı hiç basılmasa bile test geçiyordu (kırılma denemesinde yakalandı).
    """
    cizilen = diyalog(_bilgi("- tek madde", kirpildi=True))

    assert "tamamı" in cizilen


@gui
def test_kirpilmadiginda_uyari_yok(diyalog):
    cizilen = diyalog(_bilgi("- tek madde", kirpildi=False))

    # Bağlantı metninde de "Releases" geçiyor, o yüzden uyarı cümlesine bak
    assert "tamamı" not in cizilen


@gui
def test_notlar_bossa_bolum_hic_yok(diyalog):
    cizilen = diyalog(_bilgi(""))

    assert "notları:" not in cizilen
