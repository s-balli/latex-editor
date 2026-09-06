"""Panodan resim yapıştırma testleri (Ctrl+V → media/'a kaydet + figure akışı)."""

import re

import pytest
from types import SimpleNamespace

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage, QColor, QKeyEvent
    from PyQt6.QtCore import QEvent, Qt
    from gui.editor import EditorWidget
    from gui.mixins.image_ops import ImageOpsMixin
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _red_image(w=4, h=4):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    return img


class _StubEditor:
    def __init__(self, path):
        self.file_path = path


class _StubMain(ImageOpsMixin):
    """MainWindow yerine: _current_editor/_insert_image/_status stub."""
    def __init__(self, tex_path):
        self._editor = _StubEditor(str(tex_path))
        self._status = SimpleNamespace(showMessage=self._set_msg)
        self.inserted = []
        self.msg = ""

    def _current_editor(self):
        return self._editor

    def _insert_image(self, path):
        self.inserted.append(path)

    def _set_msg(self, m):
        self.msg = m


def test_paste_image_saves_png_and_inserts(tmp_path, qapp):
    tex = tmp_path / "doc.tex"
    tex.write_text("\\documentclass{article}\n", encoding="utf-8")
    QApplication.clipboard().setImage(_red_image())
    m = _StubMain(tex)
    m._paste_image()
    saved = list((tmp_path / "media").glob("image_*.png"))
    assert saved, "media/image_*.png kaydedilmeli"
    assert m.inserted == [str(saved[0])]      # _insert_image kaydedilen yolla çağrıldı
    assert QImage(str(saved[0])).size().width() == 4   # geçerli PNG


def test_paste_image_collision_increment(tmp_path, qapp):
    tex = tmp_path / "doc.tex"
    tex.write_text("x", encoding="utf-8")
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "image_1.png").write_bytes(b"x")   # image_1 dolu
    QApplication.clipboard().setImage(_red_image())
    m = _StubMain(tex)
    m._paste_image()
    assert m.inserted == [str(tmp_path / "media" / "image_2.png")]


def test_paste_no_editor(tmp_path, qapp):
    m = _StubMain(tmp_path / "doc.tex")
    m._editor = None
    m._paste_image()
    assert m.inserted == []
    assert m.msg                            # "Önce bir .tex dosyası açın"


def test_ctrl_v_with_image_emits(qapp):
    QApplication.clipboard().setImage(_red_image())
    ed = EditorWidget()
    received = []
    ed.image_paste_requested.connect(lambda: received.append(1))
    ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V,
                               Qt.KeyboardModifier.ControlModifier))
    assert received == [1]


def test_ctrl_v_without_image_not_emitted(qapp):
    QApplication.clipboard().clear()       # panoda resim yok
    ed = EditorWidget()
    received = []
    ed.image_paste_requested.connect(lambda: received.append(1))
    ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V,
                               Qt.KeyboardModifier.ControlModifier))
    assert received == []                   # resim yok → sinyal çıkmaz (metin yapıştırma akışı)


# --- Üretilen figure kodu: hiçbir şablon aynı \label'ı iki kez basmamalı ---

_SABLONLAR = ["standard", "two_column", "ieee_access", "mnras", "elsevier",
              "frontiers", "subfigure", "minimal"]


@pytest.mark.parametrize("sablon", _SABLONLAR)
def test_sablon_ayni_etiketi_tekrarlamiyor(sablon):
    """Aynı anahtarın iki kez basılması LaTeX'te 'multiply defined' uyarısıdır.

    'subfigure' şablonu \\label'ı hem \\subfloat içinde hem \\caption sonrasında
    basıyordu: editör, kendi log_parser'ının desenle yakaladığı bir uyarıyı
    üreten kod çıkarıyordu (2026-08-31, G5).
    """
    kod = ImageOpsMixin._build_figure_snippet(
        sablon, "media/g.png", "0.45\\textwidth", "Baslik", "fig:g")
    etiketler = re.findall(r"\\label\{([^}]*)\}", kod)
    assert len(etiketler) == len(set(etiketler)), f"{sablon}: tekrar eden \\label"


@pytest.mark.parametrize("sablon", _SABLONLAR)
def test_sablon_kume_dengesi(sablon):
    """Etiket çıkarılırken \\subfloat argümanının kapanışı bozulmasın."""
    kod = ImageOpsMixin._build_figure_snippet(
        sablon, "media/g.png", "0.45\\textwidth", "Baslik", "fig:g")
    assert kod.count("{") == kod.count("}"), f"{sablon}: küme dengesi bozuk"


def test_subfigure_sablonu_beklenen_yapida():
    kod = ImageOpsMixin._build_figure_snippet(
        "subfigure", "media/g.png", "0.45\\textwidth", "Baslik", "fig:g")
    assert ("\\subfloat[Baslik]{\\includegraphics[width=0.45\\textwidth]"
            "{media/g.png}}") in kod
    assert kod.count("\\label{fig:g}") == 1


# --- Şablon tespiti: yalnız \documentclass bildirimine bakmalı ---

@pytest.mark.parametrize("govde,beklenen", [
    # Yanlış pozitifler: bunlar düz 'article', gövde metni şablonu değiştirmemeli
    ("\\documentclass{article}\nKaynak: Frontiers in Neuroscience.\n", "standard"),
    ("\\documentclass{article}\nBurada twocolumn secenegi tartisiliyor.\n", "standard"),
    ("\\documentclass{article}\nmnras dergisine gonderildi.\n", "standard"),
    ("\\documentclass{article}\nOrnek: cas-dc sinifi.\n", "standard"),
    ("\\documentclass{article}\nDuz metin.\n", "standard"),
    # Gerçek tespitler bozulmamalı
    ("\\documentclass{frontiersinSCNS_ENG_HUMS}\n", "frontiers"),
    ("\\documentclass{IEEEtran}\n", "two_column"),
    ("\\documentclass[twocolumn]{article}\n", "two_column"),
    ("\\documentclass{mnras}\n", "mnras"),
    ("\\documentclass{cas-dc}\n", "elsevier"),
    ("\\documentclass{ieeeaccess}\n", "ieee_access"),
    # Belgede GERÇEKTEN kullanılan komutlar niyeti doğrudan gösterir: kalsın
    ("\\documentclass{article}\n\\Figure[t!]{x}{y}\n", "ieee_access"),
    ("\\documentclass{article}\n\\begin{figure*}\n", "two_column"),
    ("\\documentclass{article}\n\\subfloat[a]{b}\n", "subfigure"),
])
def test_sablon_tespiti(govde, beklenen):
    assert ImageOpsMixin._detect_figure_template(govde) == beklenen


# ==========================================================================
# Dosya adi DOGRUDAN LaTeX'e giriyordu
#
# `_insert_image` caption'i ve etiketi dosya adindan turetiyor ve ikisini de
# ham geciriyordu. OLCULDU (2026-09-06, pdflatex): `sonuc_grafik.png` eklemek
# `\caption{sonuc_grafik}` yaziyor ve derleme "! Missing $ inserted." ile
# duruyor. Yani editor DERLENMEYEN belge uretiyordu. Ayni ders tablo
# sihirbazinda bir kez alinmisti (`escape_cell`, 21ca9ab).
#
# Caption tipografik metin -> kacirilir. Etiket anahtar -> sadelestirilir;
# olculdu, etiket icinde yalniz `%` ve `#` derlemeyi kiriyor, `_ & $ ^`
# kirmiyor ve `fig:sonuc_grafik` LaTeX'te dogru bir anahtar.
# ==========================================================================

from core.latex_tables import escape_cell        # noqa: E402
from core.latex_utils import label_key           # noqa: E402


def _varsayilanlar(dosya_adi):
    """`_insert_image`in caption/etiket varsayilanlarini uretme yolu."""
    import os
    name = os.path.splitext(os.path.basename(dosya_adi))[0]
    return escape_cell(name), "fig:" + label_key(name)


# LaTeX'te metin kipinde kacirilmadan gecemeyen karakterler.
_TEHLIKELI = ("_", "%", "&", "#", "$", "^")


@pytest.mark.parametrize("dosya", [
    "sonuc_grafik.png", "kar%orani.png", "AT&T_logo.png",
    "maliyet#2.png", "fiyat$.png", "R^2_egrisi.png",
])
def test_CAPTION_varsayilani_KACIRILIYOR(dosya):
    caption, _label = _varsayilanlar(dosya)
    kod = ImageOpsMixin._build_figure_snippet(
        "standard", "media/" + dosya, "0.8\\textwidth", caption, "fig:a")
    satir = [s for s in kod.splitlines() if "\\caption" in s][0]
    for k in _TEHLIKELI:
        if k in satir:
            assert "\\" + k in satir or "\\^{}" in satir, (k, satir)


def test_DUZ_ad_gereksiz_yere_bozulmuyor():
    """Asiri kacirma kapisi: sade bir ad oldugu gibi kalmali."""
    caption, label = _varsayilanlar("duz-ad.png")
    assert caption == "duz-ad"
    assert label == "fig:duz-ad"


@pytest.mark.parametrize("dosya,beklenen", [
    ("sonuc_grafik.png", "fig:sonuc_grafik"),   # alt cizgi ANAHTARDA mesru
    ("kar%orani.png", "fig:kar-orani"),         # yuzde derlemeyi kiriyordu
    ("maliyet#2.png", "fig:maliyet-2"),         # kare de kiriyordu
    ("sekil 1.png", "fig:sekil-1"),
])
def test_ETIKET_varsayilani_SADELESTIRILIYOR(dosya, beklenen):
    """Etiket KACIRILMAMALI: `fig:sonuc\\_grafik` anahtari degistirirdi."""
    _caption, label = _varsayilanlar(dosya)
    assert label == beklenen


def test_ETIKET_kacis_yerine_sadelestirme(quiet=None):
    """Kirilirsa: etiket `escape_cell`den geciriliyor demektir.

    O zaman anahtar `fig:sonuc\\_grafik` olur; kullanicinin `\\ref` ile
    yazacagi ad tutmaz ve deponun `\\label{...}` tarayicilari (anahat, F2
    yeniden adlandirma, referans denetimi) baska bir dize gorur.
    """
    _caption, label = _varsayilanlar("sonuc_grafik.png")
    assert "\\" not in label, label


def test_TAMAMEN_gecersiz_ad_bos_etiket_uretmiyor():
    _caption, label = _varsayilanlar("%%%.png")
    assert label == "fig:etiket", label


# ==========================================================================
# Sablon tespiti YORUMA ALINMIS bildirimi okuyordu
#
# Dergi sablonlari alternatif `\documentclass` satirini yoruma alinmis
# dagitiyor ve `re.search` ILK eslesmeyi aliyordu. Olculdu (2026-09-06):
# ustunde `% \documentclass[twocolumn]{article}` olan duz bir article
# "two_column", yorumdaki `%\documentclass{mnras}` ise "mnras" cikiyordu.
# `core.engine_detector` ayni bildirime bakarken `strip_comments`i zaten
# cagiriyordu; iki yer ayrismisti.
# ==========================================================================

class TestSablonTespitiYorumlar:

    @pytest.mark.parametrize("icerik,beklenen", [
        ("% \\documentclass[twocolumn]{article}\n\\documentclass{article}\n",
         "standard"),
        ("%\\documentclass{mnras}\n\\documentclass{article}\n", "standard"),
        ("\\documentclass{article}\n% ornek: \\begin{figure*}\n", "standard"),
        ("\\documentclass{article}\n% \\subfloat[a]{b} ornegi\n", "standard"),
        ("\\documentclass{article}\n% \\Figure[t!]{x} ornegi\n", "standard"),
    ])
    def test_YORUMDAKI_kanit_sayilmiyor(self, icerik, beklenen):
        assert ImageOpsMixin._detect_figure_template(icerik) == beklenen

    @pytest.mark.parametrize("icerik,beklenen", [
        ("\\documentclass[twocolumn]{article}\n", "two_column"),
        ("\\documentclass{mnras}\n", "mnras"),
        ("\\documentclass[cas-dc]{elsarticle}\n", "elsevier"),
        ("\\documentclass{IEEEtran}\n", "two_column"),
        ("\\documentclass{article}\n\\begin{figure*}\\end{figure*}\n",
         "two_column"),
        ("\\documentclass{article}\n\\subfloat[a]{b}\n", "subfigure"),
        ("\\documentclass{article}\n\\Figure[t!]{x}\n", "ieee_access"),
    ])
    def test_GERCEK_kanit_hala_goruluyor(self, icerik, beklenen):
        """Asiri ayiklama kapisi: yorum temizligi gercek satiri yutmamali."""
        assert ImageOpsMixin._detect_figure_template(icerik) == beklenen

    def test_KACIRILMIS_yuzde_satiri_yutmuyor(self):
        """`\\%` yorum degil; strip_comments onu koruyor, kapi da bunu bekliyor."""
        icerik = ("\\documentclass[twocolumn]{article}\n"
                  "Kar 100\\% artti.\n")
        assert ImageOpsMixin._detect_figure_template(icerik) == "two_column"


# ==========================================================================
# ASIL CAGRI YERI: `_insert_image`in KENDISI
#
# Yukaridaki testler `escape_cell` + `label_key` bilesimini sinar; o bilesim
# `_insert_image` icinde kullanilmazsa hicbiri dusmez. Bu sinif diyalogu
# sahte kabul ederek gercek metodu kosturuyor ve editore GERCEKTEN ne
# yazildigina bakiyor.
# ==========================================================================

class _KaydedenEditor:
    def __init__(self, tex_yolu, icerik="\\documentclass{article}\n"):
        self.file_path = str(tex_yolu)
        self._icerik = icerik
        self.yazilan = ""

    def text(self):
        return self._icerik

    def getCursorPosition(self):
        return (0, 0)

    def insertAt(self, metin, satir, sutun):
        self.yazilan = metin

    def setCursorPosition(self, satir, sutun):
        pass

    def ensureLineVisible(self, satir):
        pass

    def setFocus(self):
        pass


@pytest.fixture
def gercek_ekle(qapp, monkeypatch, tmp_path):
    """`_insert_image`i diyalogu ONAYLANMIS sayarak kosturur, yazilani verir."""
    from PyQt6.QtWidgets import QDialog, QWidget
    from gui.theme import THEMES

    monkeypatch.setattr(QDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted.value)

    class _Ana(QWidget, ImageOpsMixin):
        def __init__(self, ed):
            super().__init__()
            self._ed = ed
            self._status = SimpleNamespace(showMessage=lambda m: None)
            self._theme_mgr = SimpleNamespace(theme=THEMES["dark"])

        def _current_editor(self):
            return self._ed

    def _ac(gorsel_adi, icerik="\\documentclass{article}\n"):
        tex = tmp_path / "belge.tex"
        tex.write_text(icerik, encoding="utf-8")
        ed = _KaydedenEditor(tex, icerik)
        ana = _Ana(ed)
        try:
            ana._insert_image(str(tmp_path / gorsel_adi))
            return ed.yazilan
        finally:
            ana.deleteLater()
            qapp.processEvents()

    return _ac


def test_GERCEK_akista_caption_kacirilmis_giriyor(gercek_ekle):
    """Kirilirsa: `_insert_image` yine ham dosya adini yaziyor demektir."""
    kod = gercek_ekle("sonuc_grafik.png")
    assert "\\caption{sonuc\\_grafik}" in kod, kod


def test_GERCEK_akista_etiket_sadelestirilmis_giriyor(gercek_ekle):
    kod = gercek_ekle("kar%orani.png")
    assert "\\label{fig:kar-orani}" in kod, kod
    # `%` yalnizca ETIKETTEN dusuyor. YOLDA duruyor ve durmali: `graphicx`
    # dosyanin birebir adini istiyor, kacirmak dosyayi bulunamaz yapardi.
    # Yolun kendisi ayri bir kusur, asagida uyari kapisi var.
    assert "{kar%orani.png}" in kod, kod


def test_GERCEK_akista_duz_ad_bozulmuyor(gercek_ekle):
    kod = gercek_ekle("duz-ad.png")
    assert "\\caption{duz-ad}" in kod and "\\label{fig:duz-ad}" in kod, kod


def test_GERCEK_akista_yorumdaki_documentclass_sablonu_secmiyor(gercek_ekle):
    """Yorumdaki twocolumn `figure*` sectirirdi; artik standart figure."""
    kod = gercek_ekle("a.png",
                      "% \\documentclass[twocolumn]{article}\n"
                      "\\documentclass{article}\n")
    assert "\\begin{figure}" in kod and "figure*" not in kod, kod


def test_GERCEK_akista_gercek_twocolumn_hala_figure_yildiz(gercek_ekle):
    """Asiri duzeltme kapisi: gercek bildirim hala goruluyor."""
    kod = gercek_ekle("a.png", "\\documentclass[twocolumn]{article}\n")
    assert "\\begin{figure*}" in kod, kod


# ==========================================================================
# YOLDAKI karakterler: kacirilamaz, ama sessiz kalinmaz
#
# `graphicx` dosyanin birebir adini istiyor, `\%` yazmak onu bulunamaz
# yapiyor. OLCULDU (2026-09-06, pdflatex, `\includegraphics{<ad>}`):
#     %  -> "! File ended while scanning use of \Gin@ii."
#     #  -> "! Illegal parameter number in definition of \@tempb."
# Bosluk, `& $ ^ ~ { }` ise sorunsuz derleniyor. Uygulama satiri yine de
# ekliyor (kullanicinin dosyasini kendiliginden yeniden adlandirmiyor) ama
# sebebini durum cubugunda soyluyor.
# ==========================================================================

@pytest.fixture
def ekle_ve_mesaj(qapp, monkeypatch, tmp_path):
    """`_insert_image`i kosturur, (yazilan_kod, durum_mesaji) verir."""
    from PyQt6.QtWidgets import QDialog, QWidget
    from gui.theme import THEMES

    monkeypatch.setattr(QDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted.value)

    class _Ana(QWidget, ImageOpsMixin):
        def __init__(self, ed):
            super().__init__()
            self._ed = ed
            self.mesaj = ""
            self._status = SimpleNamespace(showMessage=self._yaz)
            self._theme_mgr = SimpleNamespace(theme=THEMES["dark"])

        def _yaz(self, m):
            self.mesaj = m

        def _current_editor(self):
            return self._ed

    def _ac(gorsel_adi):
        tex = tmp_path / "belge.tex"
        tex.write_text("\\documentclass{article}\n", encoding="utf-8")
        ed = _KaydedenEditor(tex)
        ana = _Ana(ed)
        try:
            ana._insert_image(str(tmp_path / gorsel_adi))
            return ed.yazilan, ana.mesaj
        finally:
            ana.deleteLater()
            qapp.processEvents()

    return _ac


@pytest.mark.parametrize("ad,karakter", [("kar%orani.png", "%"),
                                         ("sekil#2.png", "#")])
def test_YOLDAKI_kirici_karakter_KULLANICIYA_soyleniyor(ekle_ve_mesaj, ad,
                                                        karakter):
    kod, mesaj = ekle_ve_mesaj(ad)
    assert mesaj, "derlenmeyecek satir sessizce eklendi"
    assert karakter in mesaj, mesaj
    assert ad in kod, "satir yine de eklenmeli"


def test_IKI_karakter_birden_ikisini_de_soyluyor(ekle_ve_mesaj):
    _kod, mesaj = ekle_ve_mesaj("kar%sekil#2.png")
    assert "%" in mesaj and "#" in mesaj, mesaj


@pytest.mark.parametrize("ad", ["duz.png", "alt_cizgi.png", "ve&li.png",
                               "dolar$li.png", "supap^li.png",
                               "bosluk li.png", "tilde~li.png"])
def test_DERLENEN_adlarda_uyari_YOK(ekle_ve_mesaj, ad):
    """Asiri uyari kapisi: olculdu, bu adlarin hepsi sorunsuz derleniyor."""
    _kod, mesaj = ekle_ve_mesaj(ad)
    assert mesaj == "", (ad, mesaj)


@pytest.fixture
def bosaltip_ekle(qapp, monkeypatch, tmp_path):
    """Kullanici alanlari BOSALTIP onaylarsa ne yaziliyor.

    Bu yol ayri bir kapi istiyor: alanlar dolu onaylandiginda okunan deger
    `QLineEdit`in metni, bos onaylandiginda ise `or` geri donusu. Ikisi ayri
    ayri ham dosya adina dusebilir; mutasyon sinamasinda ikinci yol kapisiz
    kalinca kacti (2026-09-06).
    """
    from PyQt6.QtWidgets import QDialog, QLineEdit, QWidget
    from gui.theme import THEMES

    def _bosalt_ve_onayla(self):
        for le in self.findChildren(QLineEdit):
            le.clear()
        return QDialog.DialogCode.Accepted.value

    monkeypatch.setattr(QDialog, "exec", _bosalt_ve_onayla)

    class _Ana(QWidget, ImageOpsMixin):
        def __init__(self, ed):
            super().__init__()
            self._ed = ed
            self._status = SimpleNamespace(showMessage=lambda m: None)
            self._theme_mgr = SimpleNamespace(theme=THEMES["dark"])

        def _current_editor(self):
            return self._ed

    def _ac(gorsel_adi):
        tex = tmp_path / "belge.tex"
        tex.write_text("\\documentclass{article}\n", encoding="utf-8")
        ed = _KaydedenEditor(tex)
        ana = _Ana(ed)
        try:
            ana._insert_image(str(tmp_path / gorsel_adi))
            return ed.yazilan
        finally:
            ana.deleteLater()
            qapp.processEvents()

    return _ac


def test_BOS_birakilan_caption_da_kacirilmis_dusuyor(bosaltip_ekle):
    kod = bosaltip_ekle("sonuc_grafik.png")
    assert "\\caption{sonuc\\_grafik}" in kod, kod


def test_BOS_birakilan_etiket_de_sadelestirilmis_dusuyor(bosaltip_ekle):
    kod = bosaltip_ekle("kar%orani.png")
    assert "\\label{fig:kar-orani}" in kod, kod


def test_BOS_birakilan_genislik_varsayilana_donuyor(bosaltip_ekle):
    kod = bosaltip_ekle("duz.png")
    assert "width=0.8\\textwidth" in kod, kod
