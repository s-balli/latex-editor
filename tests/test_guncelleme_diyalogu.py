"""Güncelleme diyaloğunda sürüm notları doğru gösterilmeli.

`_on_update_found` notları HTML'e gömüyor. Gerçek v1.0.19 yanıtı Qt'ye
çizdirilerek ölçüldü (2026-09-02):

    ham notlarda dolu satır : 4
    diyalogda çizilen satır : 1

Yani satır sonları HTML'de boşluğa çöküyordu ve 13 madde tek paragrafa
yapışıyordu. Notlar ayrıca kaçışsız gömülüyordu: sürüm notuna bir `<`
girdiği gün gösterim bozulurdu.

Testler pencereyi (`yardim_penceresi`) değiştirip GERÇEK `_on_update_found`'u
çağırıyor. İlk probum HTML'i kendisi kurmuştu, yani düzeltilen kodu değil
kendi kopyasını ölçüyordu ve düzeltmeden sonra da "bozuk" diyordu.
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


class _Yakalayici:
    """`yardim_penceresi` yerine: gelen HTML'i yakala, pencere açma."""

    metin = ""

    @staticmethod
    def ac(ebeveyn, tema, baslik, html, *a, **k):
        _Yakalayici.metin = html
        return False            # "Daha Sonra"


class _SahtePencere:
    class _Durum:
        def showMessage(self, s):
            pass

    class _Tema:
        theme = {"fg_primary": "#cccccc", "fg_bright": "#ffffff"}

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
    monkeypatch.setattr(mw, "yardim_penceresi", _Yakalayici.ac)

    def calistir(bilgi):
        _Yakalayici.metin = ""      # önceki testten kalan gövde sayılmasın
        mw.MainWindow._on_update_found(_SahtePencere(), bilgi)
        belge = QTextDocument()
        belge.setHtml(_Yakalayici.metin)
        return belge.toPlainText()

    return calistir


@pytest.fixture
def ham_html(qapp, monkeypatch):
    """(bilgi) -> diyaloğa verilen HAM HTML."""
    monkeypatch.setattr(mw, "yardim_penceresi", _Yakalayici.ac)

    def calistir(bilgi):
        _Yakalayici.metin = ""
        mw.MainWindow._on_update_found(_SahtePencere(), bilgi)
        return _Yakalayici.metin

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


@gui
@pytest.mark.parametrize("dugme, acilmali", [("Tarayıcıda Aç", True),
                                              ("Daha Sonra", False)])
def test_GERCEK_pencerede_dugmeler_dogru_isliyor(qapp, monkeypatch, dugme,
                                                acilmali):
    """Pencere yamalanmadan: düğmeye gerçekten basılıyor.

    Bildirim QMessageBox'tan kaydırılabilir pencereye taşındı (bkz.
    `yardim_penceresi`); yukarıdaki kapılar pencereyi yamalıyor, yani hangi
    düğmeye basıldığının `_on_update_found`a doğru dönmesini görmüyorlar.
    Soru düğmelerin üstünde durmalı, Enter eskisi gibi Tarayıcıda Aç olmalı.
    """
    import types
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QLabel,
                                 QMessageBox, QWidget)
    from gui.theme import THEMES

    goren, acilan = {}, []

    def bas(dlg):
        kutu = dlg.findChild(QDialogButtonBox)
        goren["varsayilan"] = [b.text() for b in kutu.buttons() if b.isDefault()]
        goren["etiketler"] = [e.text() for e in dlg.findChildren(QLabel)]
        next(b for b in kutu.buttons() if b.text() == dugme).click()
        return dlg.result()

    monkeypatch.setattr(QDialog, "exec", bas)
    # Eski yola dönülürse test modal döngüde kilitlenmesin, düşsün
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr("core.paths.xdg_open",
                        lambda u: acilan.append(u) or True)
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda u: acilan.append(u.toString())))
    pencere = QWidget()
    pencere._theme_mgr = types.SimpleNamespace(theme=THEMES["dark"])
    pencere._status = types.SimpleNamespace(showMessage=lambda *a: None)

    mw.MainWindow._on_update_found(pencere, _bilgi("- madde"))

    assert acilan == (["https://ornek/releases"] if acilmali else []), acilan
    assert goren["varsayilan"] == ["Tarayıcıda Aç"], goren
    assert "Şimdi indirip kurmak ister misiniz?" in goren["etiketler"], goren


# ---------------------------------------------------------------------------
# Bağlantının OKUNABİLİRLİĞİ. `<a>` gövdenin span rengini almıyor, Qt kendi
# sabit palet Link rengini (0, 66, 117) kullanıyor. Gerçek uygulamada ölçüldü
# (2026-09-02): yedi temanın beşinde karşıtlık 1.21 ile 1.62 arasında, WCAG AA
# eşiği ise 4.50. Aynı diyalogda gövde metni 9.25 ile 13.94 arasındaydı.
# ---------------------------------------------------------------------------

def _bagil(c):
    def k(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * k(c[0]) + 0.7152 * k(c[1]) + 0.0722 * k(c[2])


def _karsitlik(a, b):
    la, lb = _bagil(a), _bagil(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def _coz(deger):
    d = deger.lstrip("#")
    return tuple(int(d[i:i + 2], 16) for i in (0, 2, 4))


ESIK = 4.5   # WCAG AA, normal metin


@gui
def test_baglantiya_acik_renk_veriliyor(ham_html):
    """Renk verilmezse Qt'nin koyu mavi palet rengi devreye giriyor."""
    html = ham_html(_bilgi("- madde"))

    assert "<a href=" in html
    bag = html[html.index("<a href="):]
    assert "style='color:" in bag[:bag.index(">")], (
        "bağlantıya renk verilmemiş: %s" % bag[:80])


@gui
def test_baglanti_rengi_temadan_geliyor(ham_html):
    html = ham_html(_bilgi("- madde"))

    assert "color:%s" % _SahtePencere._Tema.theme["fg_bright"] in html


def test_secilen_renk_TUM_temalarda_okunabilir():
    """Asıl korunan özellik: yeni bir tema eklenirse de geçerli olmalı.

    Ölçüm sırasında `accent` elenmişti (dark'ta 3.14, light'ta 3.94) ve
    `fg_primary` de solarized_light'ta eşiğin altında kalıyordu (4.13).
    """
    from gui.theme import THEMES

    dusuk = []
    for ad, t in THEMES.items():
        oran = _karsitlik(_coz(t["fg_bright"]), _coz(t["bg_primary"]))
        if oran < ESIK:
            dusuk.append("%s (%.2f)" % (ad, oran))

    assert not dusuk, "bağlantı bu temalarda okunmuyor: %s" % dusuk


def test_qt_varsayilan_link_rengi_koyu_temada_YETMIYOR():
    """Düzeltmenin gerekçesi: ölçüm bir daha kaybolmasın.

    Bu test geçmezse Qt varsayılanı artık yeterli demektir ve `<a>`ya elle
    renk vermek gereksiz hale gelmiş olur.
    """
    from gui.theme import THEMES

    qt_link = (0, 66, 117)      # QPalette.ColorRole.Link, ölçüldü
    koyu = [ad for ad, t in THEMES.items()
            if _karsitlik(qt_link, _coz(t["bg_primary"])) < ESIK]

    assert len(koyu) >= 5, "Qt varsayılanı beklenenden iyi: %s" % koyu


@gui
def test_ACILIS_denetimi_ACILISLAR_ARASINDA_da_24_saatte_bir(ana_pencere,
                                                            monkeypatch):
    """"Açılış kontrolleri 24 saatte bir" açılışlar arasında da tutmalı.

    Önbellek `core.updater`da SÜREÇ içindeydi ve her açılış yeni bir süreç.
    ÖLÇÜLDÜ (2026-09-22): üç açılış, üç API çağrısı. Önbellek kapısı üç
    çağrıyı TEK süreçte yapıp yeşil kalıyordu. Aynı ayar dosyasını paylaşan
    ardışık pencereler burada ardışık açılışlar.

    Aşırı düzeltmeye karşı iki kol ŞART, çünkü bu özellik bozulunca SESSİZ
    kalıyor: kullanıcı güncellemeyi hiç görmez. Ağ hatası zamanı yazmamalı
    (bir sonraki açılış yeniden denesin) ve gelecekteki bir kayıt (saat geri
    alınmış) denetimi engellememeli.
    """
    import time

    denetim = []
    monkeypatch.setattr(mw.UpdateCheckThread, "start",
                        lambda self: denetim.append(1))

    ilk = ana_pencere()
    assert len(denetim) == 1
    ilk._update_thread.finished_no_update.emit()          # başarılı denetim
    ana_pencere()
    assert len(denetim) == 1, "24 saat dolmadan açılışta yeniden denetlendi"

    ayar = ana_pencere.ayar()
    ayar.setValue("update/son_kontrol", 0)
    ayar.sync()
    ag_hatasi = ana_pencere()
    assert len(denetim) == 2
    ag_hatasi._update_thread.finished_network_error.emit()
    ana_pencere()
    assert len(denetim) == 3, "ağ hatasından sonra bir daha denetlenmedi"

    ayar.setValue("update/son_kontrol", int(time.time()) + 10 * 86400)
    ayar.sync()
    ana_pencere()
    assert len(denetim) == 4, "gelecekteki kayıt denetimi engelledi"


@gui
def test_ACILIS_denetimi_KAPATILABILIYOR_elle_denetim_CALISIYOR(ana_pencere,
                                                                 monkeypatch):
    """Açılış denetimi ağa çıkan iki istekten biri ve kapatılamıyordu;
    gizlilik politikası bunu açıkça yazıyordu. Ayar Editör Ayarları'nda,
    varsayılan açık; diyalog ve kaydetme test_settings_dialog'da. Kapalıyken
    Yardım menüsündeki elle denetim YİNE çalışmalı."""
    denetim = []
    monkeypatch.setattr(mw.UpdateCheckThread, "start", lambda self: denetim.append(1))
    ana_pencere()
    assert len(denetim) == 1                                   # varsayılan açık

    ayar = ana_pencere.ayar()
    ayar.setValue("update/acilista_denetle", False)
    ayar.setValue("update/son_kontrol", 0)                     # 24 saat sınırı dışı
    ayar.sync()
    kapali = ana_pencere()
    assert len(denetim) == 1, "kapatılan açılış denetimi yine koştu"
    kapali._check_for_update_manual()
    assert len(denetim) == 2, "elle denetim ayara takıldı"
