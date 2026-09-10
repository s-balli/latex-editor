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
    from gui.editor import EditorWidget
    from gui.mixins.edit_ops import EditOpsMixin
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


class _Stub(YazimOpsMixin, EditOpsMixin, StubMain):
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


def test_tr_TR_icin_dizin_IKI_dosya_VARSA_verilir(qapp, tmp_path,
                                                  monkeypatch):
    """`.dic` tek başına YETMİYOR.

    Eskiden yalnız `.dic`e bakılıyordu. ÖLÇÜLDÜ (2026-09-07): `.aff` eksikken
    dizin döndürülüyor ve spylls `FileNotFoundError` ile patlıyor, üstelik
    `.aff` bir daha hiç açılmıyordu.
    """
    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(tmp_path))
    assert _sozluk_dizini_gerekli_mi("tr_TR") == ""      # dosya yok
    (tmp_path / "tr_TR.dic").write_text("1\nkelime\n", encoding="utf-8")
    assert _sozluk_dizini_gerekli_mi("tr_TR") == "", ".aff yokken dizin verildi"
    (tmp_path / "tr_TR.aff").write_text("SET UTF-8\n", encoding="utf-8")
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


# =====================================================================
# Öneri uygulama: belge BOZULMAMALI
#
# `_yazim_degistir` düz `metin.replace(eski, yeni)` yapıyordu ve
# `str.replace` kelime sınırı tanımıyor. Ölçüldü: `sec` -> `seç` düzeltmesi
# `\section`ı `\seçtion` yapıp belgeyi DERLENEMEZ hâle getiriyordu.
# Tarayıcı komutların ve verbatim'in içini bilerek hiç denetlemiyor, yani
# oralarda bir bulgu hiç oluşmuyor; değişim de oralara girmemeli.
# =====================================================================


def _yazan_editor(metin, yol="C:/x/main.tex"):
    """GERÇEK editör.

    Sahte bir editör bu testleri geçirir ama hiçbir şey ölçmez: imleç,
    kaydırma ve geri alma yığını yalnız QsciScintilla'da var. Öneri uygulama
    kusuru (bkz. aşağıdaki "kullanıcının yeri" bölümü) tam da bu yüzden
    sahtenin arkasında saklanıyordu.
    """
    ed = EditorWidget()
    ed.setText(metin)
    ed._file_path = yol
    return ed


def _oneri_stub(metin):
    s = _Stub(editor=_yazan_editor(metin))
    d = Denetleyici()
    d._sozluk = _SahteSozluk([])
    s._yazim_denetleyici = d
    s._yazim_anahtar = ("tr_TR", "")
    return s


def _oneri_uygula(metin, eski, yeni):
    s = _oneri_stub(metin)
    s._yazim_degistir(eski, yeni)
    return s._current_editor().text()


def test_oneri_LATEX_KOMUTUNU_bozmuyor(qapp):
    """`sec` -> `seç` düzeltmesi `\\section`a dokunmamalı.

    Bozulduğunda belge derlenmiyor ve sebep öneri diyaloğundan çok uzakta
    olduğu için kullanıcı bağlantıyı kuramıyor.
    """
    sonuc = _oneri_uygula("\\section{Giris}\nBu sec kelimesi yanlis.\n",
                          "sec", "seç")
    assert sonuc == "\\section{Giris}\nBu seç kelimesi yanlis.\n"
    assert "\\section" in sonuc


def test_oneri_VERBATIM_icine_girmiyor(qapp):
    """Verbatim bloğu aynen kalmalı, dışındaki kelime değişmeli.

    `verbatim` _ATLANACAK_ORTAM'da: içi hiç denetlenmiyor, yani orada bir
    bulgu hiç olmuyor. Değişimin oraya sızması kullanıcının kod örneğini
    sessizce bozardı.
    """
    sonuc = _oneri_uygula(
        "\\begin{verbatim}\nsec kod\n\\end{verbatim}\nsec metin\n",
        "sec", "seç")
    assert sonuc == "\\begin{verbatim}\nsec kod\n\\end{verbatim}\nseç metin\n"


# =====================================================================
# Öneri uygulama: KULLANICININ YERİ ve GEÇMİŞİ durmalı
#
# `_yazim_degistir` belgeyi `setText` ile baştan yazıyordu. Ölçüldü
# (2026-09-07), 400 satırlık belgede 302. satırda çalışan kullanıcı için:
#   imleç (302, 25) -> (403, 0), görünüm 265. satırdan 0'a atlıyor
#   `isUndoAvailable` True -> False: öneri geri alınamıyor, üstelik o
#   oturumda ELLE yazılmış her şeyin geçmişi de siliniyor
# Kural zaten aynı depoda yazılıydı: `_replace_in_editor` "undo korunur,
# tek adım" diyor. Değişim artık oradan geçiyor.
# =====================================================================


UZUN_BELGE = "\n".join(
    ["\\documentclass{article}", "\\begin{document}"]
    + ["Bu satirda yanlis yazilmis bir kelme var." if i in (40, 300)
       else "Siradan bir metin satiri %d." % i for i in range(400)]
    + ["\\end{document}", ""])
HATA_SATIRI = 302        # iki geçiş var: 42. ve 302. satır


def _uzun_stub(imlec_sutun=25, ilk_gorunen=265):
    s = _oneri_stub(UZUN_BELGE)
    ed = s._current_editor()
    ed.setCursorPosition(HATA_SATIRI, imlec_sutun)
    ed.setFirstVisibleLine(ilk_gorunen)
    return s, ed


def test_oneri_IMLECI_yerinde_birakiyor(qapp):
    """Kullanıcı panelde çalışıyor, belgede bir yere gitmek istemedi."""
    s, ed = _uzun_stub()
    s._yazim_degistir("kelme", "kelime")
    assert ed.getCursorPosition() == (HATA_SATIRI, 25)


def test_oneri_KAYDIRMAYI_bozmuyor(qapp):
    """Görünüm kaymamalı.

    `setCursorPosition` görünümü imlece çekiyor (ölçüldü: 265 -> 269), yani
    imleci geri koymak tek başına yetmiyor; ilk görünen satır da geri
    kurulmak zorunda.
    """
    s, ed = _uzun_stub()
    s._yazim_degistir("kelme", "kelime")
    assert ed.firstVisibleLine() == 265


def test_oneri_TEK_undo_ile_geri_aliniyor(qapp):
    """Yanlış öneri seçmek geri alınabilmeli."""
    s, ed = _uzun_stub()
    onceki = ed.text()
    s._yazim_degistir("kelme", "kelime")
    assert ed.text() != onceki
    ed.undo()
    assert ed.text() == onceki


def test_oneri_ONCEKI_GECMISI_silmiyor(qapp):
    """Asıl zarar bu: `setText` yalnız öneriyi değil, kullanıcının o oturumda
    yazdığı HER ŞEYİ geri alınamaz yapıyordu."""
    s, ed = _uzun_stub()
    ed.insertAt("ELLE YAZILAN. ", 5, 0)
    assert ed.isUndoAvailable()
    s._yazim_degistir("kelme", "kelime")
    assert ed.isUndoAvailable()
    ed.undo()          # öneriyi geri al
    ed.undo()          # elle yazılanı geri al
    assert "ELLE YAZILAN" not in ed.text()


def test_oneri_degisikligi_ISARETLIYOR(qapp):
    """Kaydedilmemiş değişiklik göstergesi yanmalı, yoksa kullanıcı
    düzeltmeyi kaydetmeden çıkar."""
    s, ed = _uzun_stub()
    ed.setModified(False)
    s._yazim_degistir("kelme", "kelime")
    assert ed.isModified()


@pytest.mark.parametrize("sutun, beklenen", [
    (4, 4),      # kelimeden ÖNCE: kaymamalı
    (13, 14),    # kelimeden SONRA: kelime uzadı, imleç aynı metin yerinde kalmalı
])
def test_oneri_AYNI_SATIRDA_imleci_kaydiriyor(qapp, sutun, beklenen):
    """Aynı satırda imleçten önce değişen geçiş sütunu kaydırıyor."""
    s = _oneri_stub("bir kelme iki\nikinci satir\n")
    ed = s._current_editor()
    ed.setCursorPosition(0, sutun)
    s._yazim_degistir("kelme", "kelime")
    assert ed.text().startswith("bir kelime iki")
    assert ed.getCursorPosition() == (0, beklenen)


def test_oneri_setText_ILE_yazmiyor(qapp):
    """Kural tek kaynakta kalsın: değişim `_replace_in_editor`dan geçmeli.

    Belgeyi baştan yazan her yol (setText) geri alma yığınını siler; bu testi
    bir davranış testi değil, o yola dönüşü engelleyen bir kapı olarak koydum.
    """
    s, ed = _uzun_stub()
    cagrildi = []
    ed.setText = lambda m: cagrildi.append(m)
    s._yazim_degistir("kelme", "kelime")
    assert cagrildi == []


# =====================================================================
# Sozluk acma YARIDA kalirsa kalici olarak bozuk kaliyordu (2026-09-07)
#
# `_sikistirilmisi_ac` ilk satirda "`.dic` var mi" diye bakip donuyordu.
# OLCULDU, iki hal de bir daha HIC acilmiyor:
#   kirpik `.dic` -> spylls HATASIZ yukluyor ve lookup("kelime") False,
#                    yani dogru kelimeler yanlis isaretleniyor; kullanici
#                    hicbir uyari gormuyor
#   `.aff` eksik  -> FileNotFoundError
#
# Iki kural eklendi: yazma ATOMIK (yanina yaz, yerine koy) ve `.dic`
# biciminin KENDI sayacina bakiliyor (ilk satir girdi sayisi).
# =====================================================================


def _xz_kur(dizin, dic=b"2\nkelime\nsozluk\n", aff=b"SET UTF-8\n"):
    import lzma
    (dizin / "tr_TR.dic.xz").write_bytes(lzma.compress(dic))
    (dizin / "tr_TR.aff.xz").write_bytes(lzma.compress(aff))
    return dic, aff


def test_KIRPIK_dic_yeniden_aciliyor(qapp, tmp_path, monkeypatch):
    """Kirilirsa: cokme sonrasi yazim denetimi dogru kelimeleri yanlis
    isaretlemeye baslar ve bir daha kendine gelmez."""
    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(tmp_path))
    dic, aff = _xz_kur(tmp_path)
    assert _sozluk_dizini_gerekli_mi("tr_TR") == str(tmp_path)

    # Cokme taklidi: sayac 2 diyor ama tek satir var
    (tmp_path / "tr_TR.dic").write_bytes(b"2\nkelime\n")

    assert _sozluk_dizini_gerekli_mi("tr_TR") == str(tmp_path)
    assert (tmp_path / "tr_TR.dic").read_bytes() == dic, "kirpik dosya onarilmadi"


def test_AFF_eksikse_yeniden_aciliyor(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(tmp_path))
    _dic, aff = _xz_kur(tmp_path)
    assert _sozluk_dizini_gerekli_mi("tr_TR") == str(tmp_path)
    (tmp_path / "tr_TR.aff").unlink()

    assert _sozluk_dizini_gerekli_mi("tr_TR") == str(tmp_path)
    assert (tmp_path / "tr_TR.aff").read_bytes() == aff


def test_SAGLAM_dosyaya_dokunulmuyor(qapp, tmp_path, monkeypatch):
    """Asiri duzeltme kapisi: her denetimde 9 MB yeniden acilmamali."""
    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(tmp_path))
    _xz_kur(tmp_path)
    assert _sozluk_dizini_gerekli_mi("tr_TR") == str(tmp_path)

    acmalar = []
    monkeypatch.setattr("gui.mixins.yazim_ops._xz_ac",
                        lambda k, c: acmalar.append(c) or True)
    assert _sozluk_dizini_gerekli_mi("tr_TR") == str(tmp_path)
    assert acmalar == [], "saglam sozluk yeniden acildi"


@pytest.mark.parametrize("durum", ["ham yok", "dic kirpik", "aff kirpik",
                                   "aff eksik", "dic uzun", "ikisi tam",
                                   "ayni boyut baska icerik"])
def test_ACMA_OLCUTU_betikle_AYNI(qapp, tmp_path, monkeypatch, durum):
    r"""Aynı iş iki yerde yazılı; ikisi aynı cevabı vermeli.

        scripts/sozluk_ac.py::ac                  yapımda açar
        gui/mixins/yazim_ops::_sikistirilmisi_ac  çalışma anında açar

    İkisi de aynı dizine yazıyor ve aynı soruyu soruyor. ÖLÇÜT AYRIŞMIŞTI:
    betik iki dosya için de BOYUTA bakıyordu, uygulama `.dic` için bir
    sezgiye (sayaç satırı) ve `.aff` için YALNIZ VARLIĞA. Sonuç (ölçüldü
    2026-09-10, taze bir sözlük dizininde):

        kırpık `.dic`  -> uygulama onarıyor
        kırpık `.aff`  -> uygulama ONARMIYOR; sözlük `make_affix() missing
                          2 required positional arguments` ile hiç
                          yüklenmiyor ve durum KALICI

    Atlanan dosyanın başarısızlığı daha ağır: kullanıcı her "Denetle"de
    anlaşılmaz bir Python hatası görüyor. Düzeltmeden sonra günlük on
    Türkçe kelimenin 10'u da doğru sayılıyor.

    Bu kapı elle liste tutmuyor, İKİSİNİ KARŞILAŞTIRIYOR: aynı başlangıç
    durumundan ikisi de aynı baytları bırakmalı. Son durum ("aynı boyut
    başka içerik") ölçütün BİLİNEN sınırı: ikisi de dokunmuyor, ve bu
    kapının işi o sınırın da AYNI kalmasını sınamak.
    """
    import lzma
    import os as _os
    import sys as _sys
    _betikler = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        "scripts")
    if _betikler not in _sys.path:
        _sys.path.insert(0, _betikler)
    import sozluk_ac

    dic = b"3\nkelime\nsozluk\nkitap\n"
    aff = b"SET UTF-8\nSFX A Y 1\nSFX A 0 lar .\n"

    def dizim(kok):
        kok.mkdir()
        (kok / "tr_TR.dic.xz").write_bytes(lzma.compress(dic))
        (kok / "tr_TR.aff.xz").write_bytes(lzma.compress(aff))
        if durum != "ham yok":
            (kok / "tr_TR.dic").write_bytes(dic)
            (kok / "tr_TR.aff").write_bytes(aff)
        if durum == "dic kirpik":
            (kok / "tr_TR.dic").write_bytes(dic[:8])
        elif durum == "aff kirpik":
            (kok / "tr_TR.aff").write_bytes(aff[:10])
        elif durum == "aff eksik":
            (kok / "tr_TR.aff").unlink()
        elif durum == "dic uzun":
            # Bozulma kirpilma OLMAK ZORUNDA DEGIL: yarim yazma sonrasi
            # eski kuyruk yerinde kalirsa dosya UZUN olur.
            (kok / "tr_TR.dic").write_bytes(dic + b"artik\n")
        elif durum == "ayni boyut baska icerik":
            (kok / "tr_TR.aff").write_bytes(b"X" * len(aff))
        return kok

    uygulama = dizim(tmp_path / "uygulama")
    betik = dizim(tmp_path / "betik")

    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(uygulama))
    _sozluk_dizini_gerekli_mi("tr_TR")

    monkeypatch.setattr(sozluk_ac, "DIZIN", str(betik))
    sozluk_ac.ac(sessiz=True)

    for ad in ("tr_TR.dic", "tr_TR.aff"):
        u = uygulama / ad
        b = betik / ad
        assert u.exists() == b.exists(), (durum, ad)
        if u.exists():
            assert u.read_bytes() == b.read_bytes(), (durum, ad)
    # Onarilmasi gerekenler GERCEKTEN onarilmis olmali (kapi bos kosmasin)
    if durum in ("ham yok", "dic kirpik", "aff kirpik", "aff eksik",
                 "dic uzun"):
        assert (uygulama / "tr_TR.dic").read_bytes() == dic, durum
        assert (uygulama / "tr_TR.aff").read_bytes() == aff, durum


def test_acma_yarida_kesilirse_KIRPIK_dosya_kalmiyor(qapp, tmp_path,
                                                     monkeypatch):
    """Atomik yazimin asil sebebi: hedef ya eski hali ya yeni hali olmali."""
    import gui.mixins.yazim_ops as yo
    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(tmp_path))
    _xz_kur(tmp_path)

    def patlayan_replace(a, b):
        raise OSError("disk doldu")

    monkeypatch.setattr(yo.os, "replace", patlayan_replace)
    assert yo._xz_ac(str(tmp_path / "tr_TR.dic.xz"),
                     str(tmp_path / "tr_TR.dic")) is False
    assert not (tmp_path / "tr_TR.dic").exists(), "kirpik hedef birakildi"
    assert not (tmp_path / "tr_TR.dic.tmp").exists(), "gecici dosya birakildi"


def test_BOZUK_arsiv_uygulamayi_dusurmuyor(qapp, tmp_path, monkeypatch):
    """Docstring'in verdigi soz: ozellik kapali kalir, uygulama calisir."""
    import gui.mixins.yazim_ops as yo
    monkeypatch.setattr("gui.mixins.yazim_ops.sozluk_dizini",
                        lambda: str(tmp_path))
    (tmp_path / "tr_TR.dic.xz").write_bytes(b"bu bir xz arsivi degil")
    (tmp_path / "tr_TR.aff.xz").write_bytes(b"bu da degil")
    assert yo._sozluk_dizini_gerekli_mi("tr_TR") == ""
    assert not (tmp_path / "tr_TR.dic").exists()
    assert not (tmp_path / "tr_TR.dic.tmp").exists()


# =====================================================================
# Öneri HANGİ BELGEYE yazılıyor?
#
# Panel sinyali yalnız kelimeyi taşıyordu ve `_yazim_degistir`
# `_current_editor()`e yazıyordu. ÖLÇÜLDÜ (2026-09-07): A.tex denetlenip
# B.tex sekmesine geçildikten sonra panelde DURAN bulguya sağ tık ->
# "Öneriler..." -> düzeltme B.tex'e gitti, A.tex'e hiç dokunulmadı ve durum
# çubuğu "'yanlis' -> 'yanlisi' değiştirildi" yazdı.
#
# Yol sıradan: bulgu listesi sekme değişiminde temizlenmiyor (`clear()` bile
# ona dokunmuyor, derlemeyi de aşıyor). Dosyayı panel zaten biliyor:
# `show_yazim` onu UserRole'de tutuyor ve SOL tık doğru belgeye atlıyor.
# =====================================================================

BULGULU = "Bu satirda kelme yazilmis.\n"


class _CokBelgeliStub(_Stub):
    """İki GERÇEK editör: düzeltmenin hangisine indiği ölçülebilsin."""

    def __init__(self, editorler, aktif):
        _Stub.__init__(self, editor=aktif, editors=list(editorler))
        d = Denetleyici()
        d._sozluk = _SahteSozluk([])
        self._yazim_denetleyici = d
        self._yazim_anahtar = ("tr_TR", "")


def _iki_belge():
    a = _yazan_editor("A belgesi: " + BULGULU, "C:/x/A.tex")
    b = _yazan_editor("B belgesi: " + BULGULU, "C:/x/B.tex")
    return a, b


def test_oneri_BULGUNUN_belgesine_yaziliyor(qapp):
    """Kırılırsa: kullanıcı görmediği bir belgeyi, haberi olmadan, her
    geçişinde değiştirmiş olur; üstelik durum çubuğu başarı yazar."""
    a, b = _iki_belge()
    try:
        s = _CokBelgeliStub([a, b], aktif=b)   # kullanıcı B.tex sekmesinde

        s._yazim_degistir("kelme", "kelime", "C:/x/A.tex")

        assert "kelime" in a.text(), "bulgunun belgesi düzeltilmedi"
        assert "kelme" in b.text() and "kelime" not in b.text(), \
            "cari belgeye yazıldı: %r" % b.text()
    finally:
        a.deleteLater()
        b.deleteLater()
        qapp.processEvents()


def test_oneri_hedef_SEKMESINE_geciyor(qapp):
    """Değişiklik görünür olmalı. Sol tık da hedef sekmeye geçiyor; sessizce
    başka bir belgeyi değiştirip kullanıcıyı yerinde bırakmak, düzeltmenin
    olup olmadığını belirsiz kılar."""
    a, b = _iki_belge()
    try:
        # B.tex 0. sekme: aksi hâlde A.tex zaten cari olurdu ve kapı boş
        # kalırdı (ilk hâlinde öyleydi, mutasyon yakalamadı).
        s = _CokBelgeliStub([b, a], aktif=b)
        assert s._editor_tabs.currentWidget() is b

        s._yazim_degistir("kelme", "kelime", "C:/x/A.tex")

        assert s._editor_tabs.currentWidget() is a
    finally:
        a.deleteLater()
        b.deleteLater()
        qapp.processEvents()


def test_bulgunun_belgesi_KAPALIYSA_hicbir_belge_degismiyor(qapp):
    """Bulgu bayat olabilir: denetimden sonra sekme kapanmış olabilir.

    Kırılırsa cari belgeye yazılır, yani en kötü hâl: kullanıcı A.tex'i
    kapatmış, B.tex'te çalışıyor ve B.tex bozuluyor.
    """
    _a, b = _iki_belge()
    try:
        s = _CokBelgeliStub([b], aktif=b)      # A.tex sekmesi kapatıldı
        onceki = b.text()

        s._yazim_degistir("kelme", "kelime", "C:/x/A.tex")

        assert b.text() == onceki
        assert "A.tex" in s._status.currentMessage(), \
            "sessiz kaldı: %r" % s._status.currentMessage()
    finally:
        _a.deleteLater()
        b.deleteLater()
        qapp.processEvents()


def test_dosya_VERILMEZSE_cari_belge_duzeltiliyor(qapp):
    """Aşırı düzeltme kapısı: konumsuz çağrı eski davranışı sürdürmeli."""
    a, b = _iki_belge()
    try:
        s = _CokBelgeliStub([a, b], aktif=b)

        s._yazim_degistir("kelme", "kelime")

        assert "kelime" in b.text()
        assert "kelime" not in a.text()
    finally:
        a.deleteLater()
        b.deleteLater()
        qapp.processEvents()


def test_panel_sag_tik_DOSYAYI_da_yayiyor(qapp):
    """Panel tarafındaki kapı: sinyal kelimeyi tek başına taşımamalı.

    Handler doğru olsa bile panel dosyayı yaymazsa kusur geri gelir.
    """
    from PyQt6.QtWidgets import QMenu

    p = OutputPanel(theme=THEMES["dark"])
    p.show_yazim([Bulgu("kelme", 1, 10, 10)], "C:/x/A.tex", 5)
    yayilan = []
    p.yazim_oneri_requested.connect(lambda k, d: yayilan.append((k, d)))

    asil = QMenu.exec

    def _oneriyi_tetikle(self, *a, **k):
        for act in self.actions():
            if act.text().startswith("Öneriler"):
                act.trigger()
                return act
        return None

    QMenu.exec = _oneriyi_tetikle
    try:
        p._on_yazim_context_menu(
            p._yazim_list.visualItemRect(p._yazim_list.item(0)).center())
    finally:
        QMenu.exec = asil

    assert yayilan == [("kelme", "C:/x/A.tex")], "yayılan: %r" % (yayilan,)


# =====================================================================
# İki sessiz kol: sözlüğe ekleme düşerse, öneri hedefi bulunamazsa
#
# ÖLÇÜLDÜ (2026-09-08, aynı stub ile):
#   kullaniciya_ekle False dönünce   -> durum çubuğu DEĞİŞMİYOR
#   kelime belgede bulunamayınca     -> durum çubuğu DEĞİŞMİYOR
#
# Birincisinde kullanıcı kelimeyi sözlüğe ekliyor, kelime bulgularda
# KALIYOR ve sebebini öğrenemiyor. `kullaniciya_ekle` yazamadığında False
# dönüyor (salt okunur profil, dolu disk) ama çağıran bunu yok sayıyordu.
# =====================================================================


def test_SOZLUGE_EKLENEMEZSE_kullaniciya_soyleniyor(qapp, monkeypatch):
    """Kırılırsa kelime listede kalıyor ve hiçbir açıklama yok."""
    s = _hazir_stub("bu yanlis kelime var\n", dogrular={"bu", "var"})
    monkeypatch.setattr(type(s._yazim_denetleyici), "kullaniciya_ekle",
                        lambda self, k: False)
    s._status.msg = "ONCEKI"

    s._on_yazim_sozluge_ekle("yanlis")

    assert "eklenemedi" in s._status.msg
    assert "yanlis" in s._status.msg


def test_SOZLUGE_EKLENDIYSE_hata_mesaji_YOK(qapp, monkeypatch):
    """Aşırı düzeltme kapısı: başarılı ekleme hata gibi görünmemeli."""
    s = _hazir_stub("bu yanlis kelime var\n", dogrular={"bu", "var"})
    monkeypatch.setattr(type(s._yazim_denetleyici), "kullaniciya_ekle",
                        lambda self, k: True)

    s._on_yazim_sozluge_ekle("yanlis")

    assert "eklendi" in s._status.msg
    assert "eklenemedi" not in s._status.msg


def test_ONERI_hedefi_belgede_YOKSA_soyleniyor(qapp):
    """Bulgu bayat olabilir: kullanıcı arada kelimeyi kendisi düzeltmiştir.
    Kırılırsa "öneriyi seçtim, hiçbir şey olmadı" görünüyor."""
    s = _hazir_stub("bambaska bir metin\n", dogrular={"bir"})
    s._status.msg = "ONCEKI"

    s._yazim_degistir("yanlis", "dogru")

    assert "bulunamadı" in s._status.msg
