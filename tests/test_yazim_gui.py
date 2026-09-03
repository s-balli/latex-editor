# -*- coding: utf-8 -*-
"""Yazım denetimi arayüz katmanı: panel sekmesi ve mixin bağlantısı.

GERÇEK MainWindow KURULMUYOR: bu depoda o yol CI'ı çökertti (pencere close()
ile yok olmuyor, sonra başka bir testin içinde çöp toplama sırasında SIGABRT).
Paylaşımlı StubMain kullanılıyor.

Sözlük de yüklenmiyor: Denetleyici sahte bir sözlük nesnesiyle besleniyor,
böylece testler spylls ve 9 MB'lık tr_TR olmadan da koşuyor (CI'da ikisi de
yok).
"""

from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
    from gui.mixins.yazim_ops import (YazimOpsMixin, _sozluk_dizini_gerekli_mi,
                                      kullanici_sozlugu_yolu, sozluk_dizini)
    from core.yazim import Bulgu, Denetleyici
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _SahteThread:
    """Sözlük yükleyen iş parçacığının yerine geçer; hiçbir şey başlatmaz."""

    baslatilan = []

    def __init__(self, dil, ikinci, parent=None):
        _SahteThread.baslatilan.append((dil, ikinci))
        self.yuklendi = SimpleNamespace(connect=lambda f: None)
        self.hata = SimpleNamespace(connect=lambda f: None)

    def isRunning(self):
        return False

    def start(self):
        pass


@pytest.fixture(autouse=True)
def kullanilabilir(monkeypatch):
    """Özellik VAR sayılsın, ortamdan bağımsız olarak.

    Menü öğesi ve panel sekmesi `spylls` kuruluysa ekleniyor. CI'da spylls
    YOK, o yüzden gerçek çağrı False dönüyor ve sekmeyi bekleyen testler
    düşüyordu (birebir yaşandı: Windows'ta yerelde geçip CI'da düştü).
    Testler o kararı değil, kararın SONUCUNU sınamalı.

    Yokluk hâlini sınayan test bunu kendisi False'a çeviriyor.
    """
    monkeypatch.setattr("gui.mixins.yazim_ops.yazim_kullanilabilir",
                        lambda: True)


@pytest.fixture(autouse=True)
def sahte_thread(monkeypatch):
    """HİÇBİR testte gerçek QThread başlamasın.

    Gerçeğini başlatmak testi ÇÖKERTİYOR: test biterken iş parçacığı hâlâ
    koşuyor, yok edilince süreç exit 9 ile ölüyor ve o noktadan sonraki
    testler hiç koşmuyor. Bu depoda aynı sınıf hata bir kez CI'ı düşürdü;
    bu dosyayı yazarken de iki kez yaşandı. Tek tek yamamak yerine modül
    genelinde kapatılıyor.
    """
    _SahteThread.baslatilan = []
    monkeypatch.setattr("gui.mixins.yazim_ops.YazimYukleThread", _SahteThread)
    yield _SahteThread


class _SahteSozluk:
    def __init__(self, dogrular):
        self.dogrular = set(dogrular)

    def lookup(self, k):
        return k in self.dogrular

    def suggest(self, k):
        return iter(["oneri1", "oneri2"])


class _Stub(YazimOpsMixin, StubMain):
    """Mixin + paylaşımlı stub.

    Editör `editors=` ile VERİLMİYOR: StubMain onları gerçek QWidget sanıp
    QTabWidget'a ekliyor. Handler'ın tek ihtiyacı `_current_editor()`, o
    yüzden doğrudan o geçersiz kılınıyor.
    """

    def __init__(self, editor=None, **kw):
        StubMain.__init__(self, **kw)
        self._sahte_editor = editor
        self._init_yazim()

    def _current_editor(self):
        return self._sahte_editor


def _editor(metin, yol="C:/x/main.tex"):
    return SimpleNamespace(text=lambda: metin, file_path=yol,
                           display_name="main.tex",
                           setText=lambda s: None,
                           getCursorPosition=lambda: (0, 0))


def _hazir_stub(metin, dogrular=(), **kw):
    s = _Stub(editor=_editor(metin), **kw)
    d = Denetleyici()
    d._sozluk = _SahteSozluk(dogrular)
    s._yazim_denetleyici = d
    s._yazim_anahtar = ("tr_TR", "")
    return s


# =====================================================================
# Panel sekmesi
# =====================================================================


def test_yazim_sekmesi_var(qapp):
    p = OutputPanel(theme=THEMES["dark"])
    assert p._tabs.tabText(p._yazim_tab_index) == "Yazım"


def test_spylls_yoksa_sekme_EKLENMEZ(qapp, monkeypatch):
    """Çalışamayacak bir sekme göstermek kullanıcıyı yanıltır.

    Menü öğesi de aynı koşula bağlı. `spylls` bir bağımlılık olarak
    eklenmeden paketlenirse özellik hiç görünmez.
    """
    monkeypatch.setattr("gui.mixins.yazim_ops.yazim_kullanilabilir",
                        lambda: False)
    p = OutputPanel(theme=THEMES["dark"])
    assert p._yazim_tab_index == -1
    assert "Yazım" not in [p._tabs.tabText(i) for i in range(p._tabs.count())]
    # sekme yokken sonuç göstermek çökmemeli
    p.show_yazim([Bulgu("x", 1, 0, 0)], "C:/x/main.tex", 10)


def test_dil_secenekleri(qapp):
    p = OutputPanel(theme=THEMES["dark"])
    diller = [p._yazim_dil.itemData(i) for i in range(p._yazim_dil.count())]
    assert diller == ["tr_TR", "en_US"]


def test_dil_belgeden_ayarlanabiliyor(qapp):
    p = OutputPanel(theme=THEMES["dark"])
    p.yazim_dili_ayarla("en_US")
    assert p._yazim_dil.currentData() == "en_US"


def test_bilinmeyen_dil_secimi_bozmaz(qapp):
    p = OutputPanel(theme=THEMES["dark"])
    p.yazim_dili_ayarla("de_DE")
    assert p._yazim_dil.currentData() == "tr_TR"


def test_bulgular_listeleniyor_ve_ORAN_yaziliyor(qapp):
    """Çıplak sayı 'çok mu az mı' sorusuna cevap vermiyor.

    Ölçülen gerçekçi bant %2-5; kullanıcı kendi belgesinde nerede durduğunu
    ancak oranla görüyor.
    """
    p = OutputPanel(theme=THEMES["dark"])
    p.show_yazim([Bulgu("yanlis", 3, 5, 40)], "C:/x/main.tex", 200)
    assert p._yazim_list.item(0).text() == "3:5  yanlis"
    assert "200" in p._yazim_durum.text() and "0.5" in p._yazim_durum.text()


def test_bulgu_yoksa_temiz_der(qapp):
    p = OutputPanel(theme=THEMES["dark"])
    p.show_yazim([], "C:/x/main.tex", 200)
    assert p._yazim_durum.text() == "temiz"


def test_bulguya_tiklamak_SATIRA_GITME_yoluna_dusuyor(qapp):
    """UserRole'de (dosya, satır) durur; tıklama mevcut error_clicked yoluna
    düşer ve _goto_line'a gider. Ayrı bir gezinme yolu yazılmadı."""
    p = OutputPanel(theme=THEMES["dark"])
    p.show_yazim([Bulgu("yanlis", 7, 2, 40)], "C:/x/main.tex", 100)
    it = p._yazim_list.item(0)
    assert it.data(Qt.ItemDataRole.UserRole) == ("C:/x/main.tex", 7)
    alinan = []
    p.error_clicked.connect(lambda f, l: alinan.append((f, l)))
    p._on_result_click(it)
    assert alinan == [("C:/x/main.tex", 7)]


def test_denetle_dugmesi_dil_ve_kutuyu_TASIYOR(qapp):
    p = OutputPanel(theme=THEMES["dark"])
    p.yazim_dili_ayarla("en_US")
    p._yazim_ikinci.setChecked(True)
    gelen = []
    p.yazim_denetle_requested.connect(lambda d, i: gelen.append((d, i)))
    p._on_yazim_denetle()
    assert gelen == [("en_US", True)]


def test_kutu_DENETLENMEDEN_sozluk_yuklemesi_baslatmaz(qapp):
    """Kullanıcı henüz 'Denetle' demediyse kutuya dokunmak istek üretmemeli.

    Aksi hâlde kutuyu merak edip tıklayan kişi 3.5 saniyelik sözlük
    yüklemesini başlatmış oluyor.
    """
    p = OutputPanel(theme=THEMES["dark"])
    gelen = []
    p.yazim_denetle_requested.connect(lambda d, i: gelen.append((d, i)))
    p._yazim_ikinci.setChecked(True)
    assert gelen == []


def test_denetlendikten_SONRA_kutu_yeniden_denetletir(qapp):
    p = OutputPanel(theme=THEMES["dark"])
    p.show_yazim([Bulgu("x", 1, 0, 0)], "C:/x/main.tex", 10)
    gelen = []
    p.yazim_denetle_requested.connect(lambda d, i: gelen.append((d, i)))
    p._yazim_ikinci.setChecked(True)
    assert gelen == [("tr_TR", True)]


def test_mesgulken_dugme_kilitli(qapp):
    p = OutputPanel(theme=THEMES["dark"])
    p.yazim_mesgul("sözlük yükleniyor...")
    assert p._yazim_dugme.isEnabled() is False
    p.yazim_mesgul("")
    assert p._yazim_dugme.isEnabled() is True


# =====================================================================
# Sözlük yolu çözümü
# =====================================================================


def test_en_US_icin_dizin_VERILMEZ(qapp):
    """en_US spylls'in İÇİNDE geliyor; dizin verilirse yükleme patlıyor.

    Regression: körü körüne dizin veriliyordu, `<dizin>/en_US.dic` aranıp
    bulunamıyor, hata diyaloğu açılıyor ve ikinci dil kutusu KİLİTLENİYORDU.
    """
    assert _sozluk_dizini_gerekli_mi("en_US") == ""


def test_tr_TR_icin_dizin_dosya_VARSA_verilir(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(tmp_path))
    assert _sozluk_dizini_gerekli_mi("tr_TR") == ""      # dosya yok
    (tmp_path / "tr_TR.dic").write_text("x", encoding="utf-8")
    assert _sozluk_dizini_gerekli_mi("tr_TR") == str(tmp_path)


def test_taze_kopyada_sozluk_XZ_den_ACILIYOR(qapp, tmp_path, monkeypatch):
    """Depoda yalniz `.xz` var; kaynaktan calistiran ham dosyayi bulamaz.

    Sozluk depoda SIKISTIRILMIS duruyor (ham `.dic` 8.6 MB). Paketlenmis
    uygulamada `.spec` yapim sirasinda aciyor, ama TAZE BIR KOPYADA
    `sozlukler/` icinde yalniz `.xz` bulunuyordu:
    `_sozluk_dizini_gerekli_mi` bos donuyor, Denetleyici dizinsiz
    kuruluyor ve yukleme anlasilmaz bir hata diyaloguyla dusuyordu.
    """
    import lzma
    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(tmp_path))

    (tmp_path / "tr_TR.dic.xz").write_bytes(lzma.compress(b"1\nkelime\n"))
    (tmp_path / "tr_TR.aff.xz").write_bytes(lzma.compress(b"SET UTF-8\n"))
    assert not (tmp_path / "tr_TR.dic").exists()

    assert _sozluk_dizini_gerekli_mi("tr_TR") == str(tmp_path)
    assert (tmp_path / "tr_TR.dic").read_bytes() == b"1\nkelime\n"
    assert (tmp_path / "tr_TR.aff").read_bytes() == b"SET UTF-8\n"


def test_xz_YOKSA_sessizce_geciliyor(qapp, tmp_path, monkeypatch):
    """Acma denemesi, sozluk hic yokken hata vermemeli."""
    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(tmp_path))
    assert _sozluk_dizini_gerekli_mi("tr_TR") == ""
    assert not list(tmp_path.iterdir())


def test_kullanici_sozlugu_dile_gore_ayri(qapp):
    a = kullanici_sozlugu_yolu("tr_TR")
    b = kullanici_sozlugu_yolu("en_US")
    assert a != b and a.endswith("sozluk-tr_TR.txt")


def test_sozluk_dizini_mutlak_yol_dondurur(qapp):
    import os
    assert os.path.isabs(sozluk_dizini())


# =====================================================================
# Mixin davranışı
# =====================================================================


def test_editor_yokken_cokmez(qapp):
    s = _Stub()
    s._on_yazim_denetle_requested("tr_TR", False)
    assert s._output_panel._yazim_list.count() == 0


def test_denetim_sonucu_panele_gidiyor(qapp):
    s = _hazir_stub("dogru yanlis", dogrular=["dogru"])
    s._yazim_calistir()
    p = s._output_panel
    assert p._yazim_list.count() == 1
    assert "yanlis" in p._yazim_list.item(0).text()


def test_ayni_anahtarda_sozluk_YENIDEN_yuklenmiyor(qapp):
    """Aynı dil/ikinci-dil bileşimi için iş parçacığı açılmamalı."""
    s = _hazir_stub("dogru", dogrular=["dogru"])
    s._on_yazim_denetle_requested("tr_TR", False)
    assert s._yazim_thread is None


def test_ikinci_dil_ANAHTARI_degistiriyor(qapp, sahte_thread):
    """Kutu işaretlenince farklı bir bileşim istenir, yeniden yüklenmeli."""
    s = _hazir_stub("dogru", dogrular=["dogru"])
    # ikinci dil isteniyor: anahtar (tr_TR, en_US) -> mevcut (tr_TR, "") değil
    s._on_yazim_denetle_requested("tr_TR", True)
    assert s._yazim_anahtar == ("tr_TR", "en_US")
    assert sahte_thread.baslatilan == [("tr_TR", "en_US")]


def test_menu_eylemi_dili_BELGEDEN_seciyor(qapp):
    s = _hazir_stub("% !TEX spellcheck = en_US\nHello world")
    s._yazim_denetle()
    assert s._output_panel._yazim_dil.currentData() == "en_US"


def test_sozluge_eklemek_bulguyu_dusuruyor(qapp):
    s = _hazir_stub("ablasyon yanlis", dogrular=[])
    s._yazim_calistir()
    once = s._output_panel._yazim_list.count()
    s._on_yazim_sozluge_ekle("ablasyon")
    assert s._output_panel._yazim_list.count() == once - 1


def test_denetleyici_yokken_sozluge_ekleme_cokmez(qapp):
    s = _Stub(editor=_editor("metin"))
    s._on_yazim_sozluge_ekle("kelime")      # patlamamalı
    assert s._yazim_denetleyici is None


def test_cleanup_thread_yokken_cokmez(qapp):
    s = _Stub()
    s._cleanup_yazim()                      # patlamamalı
