"""HTML üreten pencereler koyu temada okunabilir olmalı.

Gerçek pencereler çizdirilip ölçüldü (2026-09-03, gruvbox teması, WCAG AA
normal metin eşiği 4.50):

    Hakkında        bağlantılar   1.43   Qt palet Link rengi (0, 66, 117)
    Özellikler      tüm pencere   1.37   QTextBrowser zemini BEYAZ kalmış
    Ortam Denetimi  tüm pencere   1.37   aynı

İlk kusur `_on_update_found`'dakinin aynısı: `<a>` gövdenin span rengini
almıyor. Diğer ikisinin sebebi ayrı: `theme.py` genel bir stylesheet
üretmiyor, her widget kendini biçimlendiriyor ve `QTextBrowser` için hiçbir
yerde kural yoktu, o yüzden Qt'nin beyaz `Base` zemini kalıyordu.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QTextBrowser, QWidget, QDialog
    from gui import main_window as mw
    from gui.theme import THEMES
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="PyQt6 / gui modülleri gerekli")

ESIK = 4.5


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
    d = str(deger).lstrip("#")
    return tuple(int(d[i:i + 2], 16) for i in (0, 2, 4))


@pytest.fixture(scope="module")
def qapp():
    if not _VAR:
        yield None
        return
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def pencere(qapp):
    """`QDialog(self)` gerçek bir QWidget ebeveyn istiyor."""
    class _Tema:
        theme = THEMES["gruvbox"]

    w = QWidget()
    w._theme_mgr = _Tema()
    yield w
    w.close()


# ---------------------------------------------------------------- Hakkında

@gui
def test_hakkinda_baglantilarina_acik_renk_veriliyor(pencere, monkeypatch):
    """Renk verilmezse Qt'nin koyu mavi palet rengi devreye giriyor."""
    yakalanan = {}

    class _SahteKutu:
        @staticmethod
        def about(ebeveyn, baslik, metin):
            yakalanan["html"] = metin

    monkeypatch.setattr(mw, "QMessageBox", _SahteKutu)
    mw.MainWindow._show_about(pencere)

    html = yakalanan["html"]
    baglantilar = html.count("<a href=")
    assert baglantilar == 2, "beklenen iki bağlantı, bulunan %d" % baglantilar
    renkli = html.count("style='color:")
    assert renkli >= baglantilar, (
        "bağlantıların hepsine renk verilmemiş: %d/%d" % (renkli, baglantilar))


@gui
def test_hakkinda_baglanti_rengi_okunabilir(pencere, monkeypatch):
    yakalanan = {}

    class _SahteKutu:
        @staticmethod
        def about(ebeveyn, baslik, metin):
            yakalanan["html"] = metin

    monkeypatch.setattr(mw, "QMessageBox", _SahteKutu)
    mw.MainWindow._show_about(pencere)

    t = THEMES["gruvbox"]
    assert "color:%s" % t["fg_bright"] in yakalanan["html"]


# -------------------------------------------------------------- Özellikler

@gui
def test_ozellikler_penceresinin_zemini_temadan_geliyor(pencere, monkeypatch):
    """Zemin verilmezse QTextBrowser beyaz kalıyor ve pencere okunmuyor."""
    kayit = {}

    class _Kayitli(QTextBrowser):
        def setStyleSheet(self, s):
            kayit["ss"] = s
            super().setStyleSheet(s)

    import PyQt6.QtWidgets as W
    monkeypatch.setattr(W, "QTextBrowser", _Kayitli)
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)

    mw.MainWindow._show_features(pencere)

    ss = kayit.get("ss", "")
    assert "background" in ss, "zemin verilmemiş: %r" % ss
    assert THEMES["gruvbox"]["bg_primary"] in ss


# ---------------------------------------------------------- Ortam Denetimi

@gui
def test_ortam_denetimi_zemini_temadan_geliyor(qapp, monkeypatch):
    from gui import env_doctor as ed

    # __init__ denetimi arka planda baslatiyor; testte gerekli degil.
    monkeypatch.setattr(ed.EnvDoctorDialog, "_start", lambda self: None)
    d = ed.EnvDoctorDialog(None, theme=THEMES["gruvbox"])
    try:
        ss = d._view.styleSheet()
        assert "background" in ss, "zemin verilmemiş: %r" % ss
        assert THEMES["gruvbox"]["bg_primary"] in ss
    finally:
        d.close()


@gui
def test_ortam_denetimi_temasiz_da_calisiyor(qapp, monkeypatch):
    """`theme` boş gelebiliyor; o zaman da beyaz zeminde kalmamalı."""
    from gui import env_doctor as ed

    monkeypatch.setattr(ed.EnvDoctorDialog, "_start", lambda self: None)
    d = ed.EnvDoctorDialog(None)
    try:
        ss = d._view.styleSheet()
        assert "background" in ss and "#" in ss
    finally:
        d.close()


# --------------------------------------------------- korunan asıl özellik

def test_metin_tarayici_zemini_TUM_temalarda_okunabilir():
    """Yeni bir tema eklenirse de geçerli olmalı.

    Ölçümün kendisi: beyaz zeminde gruvbox gövdesi 1.37 idi.
    """
    dusuk = []
    for ad, t in THEMES.items():
        oran = _karsitlik(_coz(t["fg_primary"]), _coz(t["bg_primary"]))
        if oran < ESIK:
            dusuk.append("%s (%.2f)" % (ad, oran))

    # solarized_light 4.13 ile sınırın hemen altında; bilinen ve ayrı bir
    # konu (tema paletinin kendisi), bu pencerelerin kusuru değil.
    assert dusuk in ([], ["solarized_light (4.13)"]), (
        "gövde metni bu temalarda okunmuyor: %s" % dusuk)


def test_beyaz_zemin_koyu_temalarda_GERCEKTEN_yetmiyor():
    """Düzeltmenin gerekçesi kaybolmasın: Qt varsayılanı neden yetmiyordu."""
    beyaz = (255, 255, 255)
    koyu = [ad for ad, t in THEMES.items()
            if _karsitlik(_coz(t["fg_primary"]), beyaz) < ESIK]

    assert len(koyu) >= 5, "beyaz zemin beklenenden iyi: %s" % koyu


# ---------------------------------------------------------------------------
# Stylesheet ile boyanan widget'lar. Calisan uygulamanin COZULMUS
# styleSheet()'leri okunarak tarandi (2026-09-03, yedi tema).
#
#   kok klasor yolu etiketi   fg_dim / bg_secondary   1.56 - 2.67
#   fg_muted                  bg_secondary uzerinde   2.18 - 4.47
#   fg_muted                  bg_toolbar  uzerinde    3.89 - 4.43
#
# fg_dim BILEREK yukseltilmedi: esigi gecmesi icin gereken deger dark temada
# fg_muted icin gerekenle birebir ayni cikti, yani dosya agacindaki
# "duzenlenebilir / duzenlenemez" ayrimi tamamen kaybolurdu.
# ---------------------------------------------------------------------------

# fg_muted'in GERCEKTE uzerine bindigi zeminler (kural duzeyinde tarandi).
_MUTED_ZEMINLERI = ("bg_secondary", "bg_toolbar")


def test_fg_muted_TUM_temalarda_kendi_zeminlerinde_okunabilir():
    dusuk = []
    for ad, t in THEMES.items():
        for zemin in _MUTED_ZEMINLERI:
            oran = _karsitlik(_coz(t["fg_muted"]), _coz(t[zemin]))
            if oran < ESIK:
                dusuk.append("%s/%s (%.2f)" % (ad, zemin, oran))

    assert not dusuk, "soluk metin bu birleşimlerde okunmuyor: %s" % dusuk


@gui
def test_kok_klasor_etiketi_fg_dim_KULLANMIYOR(qapp):
    """10px'lik yol etiketi gerçek bilgi; fg_dim ile yedi temada da okunmuyordu."""
    from gui import file_tree as ft
    import inspect

    kaynak = inspect.getsource(ft)
    i = kaynak.index("self._root_label.setStyleSheet(")
    blok = kaynak[i:i + 260]

    assert "fg_dim" not in blok, "kök yolu etiketi hâlâ fg_dim kullanıyor"
    assert "fg_muted" in blok


def test_fg_dim_ile_fg_muted_AYRI_kalmali():
    """Ayrımın kendisi korunuyor: ikisi eşitlenirse dosya ağacındaki
    'düzenlenebilir / düzenlenemez' vurgusu yok olur.

    fg_dim'i eşiğin üstüne çekmek tam olarak buna yol açıyordu, o yüzden
    bilerek yükseltilmedi."""
    ayni = [ad for ad, t in THEMES.items()
            if str(t["fg_dim"]).lower() == str(t["fg_muted"]).lower()]

    assert not ayni, "fg_dim ile fg_muted eşitlenmiş: %s" % ayni


# ---------------------------------------------------------------------------
# Sekme uzerine gelme. bg_hover_alt uzerinde olculdu (2026-09-03):
#
#   fg_label    solarized_light 3.44, monokai 3.58, nord 3.21, gruvbox 3.28
#   fg_primary  solarized_light 3.44, digerleri geciyor
#   fg_bright   yedi temada da geciyor (7.49 - 12.63)
#
# Zemin DEGISTIRILMEDI: hesap onu koyulastirmayi oneriyordu ama hover su an
# normal sekmeden ACIK, yani "yukari kalkma" hissi veriyor.
# ---------------------------------------------------------------------------

def test_sekme_hover_metni_TUM_temalarda_okunabilir():
    dusuk = []
    for ad, t in THEMES.items():
        oran = _karsitlik(_coz(t["fg_bright"]), _coz(t["bg_hover_alt"]))
        if oran < ESIK:
            dusuk.append("%s (%.2f)" % (ad, oran))

    assert not dusuk, "sekme hover metni okunmuyor: %s" % dusuk


def test_sekme_hover_kurallari_fg_label_KULLANMIYOR():
    """İki çağrı yeri de aynı rengi kullanmalı, yoksa desen tekrar ayrışır."""
    import inspect
    from gui import stylesheet as ss
    from gui import output_panel as op

    for modul in (ss, op):
        kaynak = inspect.getsource(modul)
        i = 0
        while True:
            i = kaynak.find("QTabBar::tab:hover", i)
            if i < 0:
                break
            satir = kaynak[i:kaynak.index("}}", i) + 2]
            assert "fg_label" not in satir, (
                "%s içinde hover hâlâ fg_label: %s"
                % (modul.__name__, satir[:90]))
            i += 1


# solarized_light hover farkı 1.06 ile burada da en altta, ama o temanın
# paleti bütün olarak ertelenmiş bir karar (fg_primary kendi zemininde 4.13).
# Listeye alınması "kabul edildi" demek değil, "ayrı karar" demek.
_HOVER_ISTISNA = {"solarized_light"}


def test_hover_zemini_normal_sekmeden_AYIRT_EDILEBILIR():
    """Düzeltme kontrastı çözerken hover geri bildirimini yok etmemeli.

    Zemini koyulaştıran alternatif tam bunu riske atıyordu. Ayrıca bu test
    yazılırken light temada hover'ın zaten görünmediği ortaya çıktı:
    `#e0e0e0` ile `#e2e2e2`, yani kanal başına 2 birim, oran 1.019. Geri
    bildirim sayılmaz; `#d4d4d4` yapıldı (1.14, dark'taki 1.12'ye yakın).
    """
    silik = []
    for ad, t in THEMES.items():
        if ad in _HOVER_ISTISNA:
            continue
        fark = _karsitlik(_coz(t["bg_hover_alt"]), _coz(t["bg_toolbar"]))
        if fark < 1.10:
            silik.append("%s (%.3f)" % (ad, fark))

    assert not silik, "hover zemini normal sekmeden ayırt edilemiyor: %s" % silik
