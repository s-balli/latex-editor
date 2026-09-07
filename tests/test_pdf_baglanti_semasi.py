# -*- coding: utf-8 -*-
"""PDF bağlantısındaki adres kabuğa süzgeçsiz gidiyordu.

`_handle_link_click` PDF'in `/URI` alanını doğrudan `webbrowser.open`a
veriyordu. `webbrowser` Windows'ta `os.startfile`a düşüyor (ölçüldü
2026-09-07: `_tryorder`ın ilk kaydı `windows-default`), o da ShellExecute:
adres TEK TIKLAMAYLA program çalıştırıyor.

ÖLÇÜLDÜ (2026-09-07), elle kurulmuş PDF'te `/S /URI` aksiyonu şunları olduğu
gibi geçiriyordu: `file:///C:/Windows/System32/calc.exe`,
`\\\\sunucu\\pay\\kotu.exe`, `ms-msdt:/id PCWDiagnostic`. `javascript:` ise
hyperref'in KENDİ çıktısında da göründü, yani sıradan bir `\\href` yetiyor.

Adres belgeyi yazanın denetiminde, kullanıcının değil: paylaşılan bir .tex
LaTeX dünyasında kural, istisna değil. Uygulama aynı sebeple `\\write18`e de
kapı koyuyor (bkz. core/shell_escape.py); bu yolun açık kalması o duruşla
tutarsızdı.
"""

import ctypes
from types import SimpleNamespace

import pytest

try:
    import pypdfium2 as pdfium
    from pypdfium2 import raw as praw
    from gui.pdf_links import IZINLI_SEMALAR, acilabilir_uri, resolve_link_action
    from gui.pdf_viewer_mixins._events import PdfEventsMixin
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

pdfli = pytest.mark.skipif(not _VAR, reason="pypdfium2 / gui gerekli")


# =====================================================================
# Şema süzgeci
# =====================================================================


@pdfli
@pytest.mark.parametrize("uri", [
    "file:///C:/Windows/System32/calc.exe",
    "file:///bin/sh",
    "FILE:///C:/x.exe",                      # şema büyük harfle de gelebilir
    "javascript:alert(1)",
    "vbscript:msgbox(1)",
    "ms-msdt:/id PCWDiagnostic",             # gerçek bir Windows saldırı yolu
    "search-ms:query=x",
    "smb://sunucu/pay/kotu.exe",
    "data:text/html,<script>x</script>",
    "C:/Windows/System32/calc.exe",          # sürücü harfi şema gibi görünüyor
    "\\\\sunucu\\pay\\kotu.exe",             # UNC
    "/etc/passwd",
    "./yerel.exe",
    "belge\\alt\\x.exe",
])
def test_GUVENSIZ_adres_acilmiyor(uri):
    """Kırılırsa: bu adres tek tıklamayla kabuğa gidiyor demektir."""
    assert acilabilir_uri(uri) is None


@pdfli
@pytest.mark.parametrize("uri, beklenen", [
    ("https://example.com", "https://example.com"),
    ("http://example.com/a?b=1#c", "http://example.com/a?b=1#c"),
    ("mailto:a@b.com", "mailto:a@b.com"),
    ("HTTPS://example.com", "HTTPS://example.com"),
])
def test_MESRU_adres_oldugu_gibi_geciyor(uri, beklenen):
    """Aşırı düzeltme kapısı: süzgeç meşru bağlantıyı kesmemeli."""
    assert acilabilir_uri(uri) == beklenen


@pdfli
@pytest.mark.parametrize("uri, beklenen", [
    ("www.example.com", "https://www.example.com"),
    ("example.com/a", "https://example.com/a"),
])
def test_SEMASIZ_adrese_https_ekleniyor(uri, beklenen):
    """hyperref `\\url{www.example.com}` için şemasız yazıyor (ölçüldü).

    Atmak meşru bağlantıyı kırardı; kabuğa ham vermek de olmaz, çünkü
    `os.startfile` şemasız değeri dosya adı sanıyor.
    """
    assert acilabilir_uri(uri) == beklenen


@pdfli
@pytest.mark.parametrize("uri", ["", "   ", None])
def test_BOS_adres_acilmiyor(uri):
    assert acilabilir_uri(uri) is None


@pdfli
def test_izinli_semalar_LISTESI_beklenen_uc_sema():
    """Liste büyürse bilinçli olsun: `file` ya da `javascript` eklenmesi
    yukarıdaki testleri düşürmeden buraya sızabilirdi."""
    assert set(IZINLI_SEMALAR) == {"http", "https", "mailto"}


# =====================================================================
# PDF'ten uçtan uca
# =====================================================================


def _uri_pdf(yol, uri):
    """Tek sayfa, tek Link annot, `/A << /S /URI /URI (uri) >>`."""
    icerik = b"BT /F1 12 Tf 50 700 Td (tikla) Tj ET"
    nesneler = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Annots[5 0 R]"
        b"/Resources<</Font<</F1 6 0 R>>>>/Contents 4 0 R>>",
        b"<</Length " + str(len(icerik)).encode() + b">>stream\n" + icerik +
        b"\nendstream",
        b"<</Type/Annot/Subtype/Link/Rect[50 695 150 715]/Border[0 0 0]"
        b"/A<</Type/Action/S/URI/URI(" + uri.encode("latin-1") + b")>>>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    yerler = []
    for i, n in enumerate(nesneler, start=1):
        yerler.append(len(out))
        out += b"%d 0 obj" % i + n + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(nesneler) + 1)
    for y in yerler:
        out += b"%010d 00000 n \n" % y
    out += (b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n"
            % (len(nesneler) + 1, xref))
    with open(yol, "wb") as f:
        f.write(bytes(out))
    return str(yol)


def _ilk_link_cozumu(yol):
    belge = pdfium.PdfDocument(yol)
    try:
        sayfa = belge[0]
        poz = ctypes.c_int(0)
        link = praw.FPDF_LINK()
        if not praw.FPDFLink_Enumerate(sayfa.raw, ctypes.byref(poz),
                                       ctypes.byref(link)):
            pytest.fail("kapı boş koşuyor: PDF'te link bulunamadı")
        return resolve_link_action(belge.raw, link)
    finally:
        belge.close()


@pdfli
@pytest.mark.parametrize("uri", [
    "file:///C:/Windows/System32/calc.exe",
    "ms-msdt:/id PCWDiagnostic",
    "javascript:alert(1)",
])
def test_PDFTEN_gelen_guvensiz_uri_guvensiz_isaretleniyor(tmp_path, uri):
    """Süzgeç üretim yerinde: çağıran ne yaparsa yapsın adres 'uri' olarak
    çıkmamalı."""
    yol = _uri_pdf(tmp_path / "kotu.pdf", uri)
    kind, data = _ilk_link_cozumu(yol)
    assert kind == "guvensiz_uri"
    assert data == uri, "ham adres kullanıcıya gösterilmek üzere korunmalı"


@pdfli
def test_PDFTEN_gelen_https_acilabilir_geliyor(tmp_path):
    yol = _uri_pdf(tmp_path / "iyi.pdf", "https://example.com")
    assert _ilk_link_cozumu(yol) == ("uri", "https://example.com")


# =====================================================================
# Tıklama dallanması
# =====================================================================


class _Gorucu:
    """Yalnız tıklama dallanmasını koşturan iskelet."""

    _handle_link_click = PdfEventsMixin._handle_link_click
    _guvensiz_baglanti = PdfEventsMixin._guvensiz_baglanti

    def __init__(self):
        self._pdf = SimpleNamespace(raw=object())
        self.gidilen = []

    def _link_at_pos(self, pos, obj):
        return (0, object(), None)

    def _goto_dest(self, dest):
        self.gidilen.append(dest)


@pdfli
@pytest.mark.parametrize("cozum, acilmali", [
    (("uri", "https://example.com"), True),
    (("guvensiz_uri", "file:///C:/x.exe"), False),
])
def test_TIKLAMA_yalniz_guvenli_dalda_kabuga_gidiyor(monkeypatch, cozum,
                                                     acilmali):
    """Süzgeç üretim yerinde ama dallanma da kapıda: ileride 'guvensiz_uri'
    yanlışlıkla `webbrowser.open`a bağlanmasın."""
    acilan = []
    uyari = []
    monkeypatch.setattr("gui.pdf_viewer_mixins._events.webbrowser.open",
                        lambda u: acilan.append(u))
    monkeypatch.setattr("gui.pdf_viewer_mixins._events.QMessageBox.warning",
                        lambda *a, **k: uyari.append(a))
    monkeypatch.setattr("gui.pdf_viewer_mixins._events.resolve_link_action",
                        lambda raw, link: cozum)

    v = _Gorucu()
    v._handle_link_click(None, None)

    assert bool(acilan) is acilmali
    if acilmali:
        assert acilan == [cozum[1]]
        assert uyari == []
    else:
        assert acilan == [], "güvensiz adres kabuğa gitti"
        assert uyari, "kullanıcıya sebep söylenmedi"


@pdfli
def test_TIKLAMA_ic_baglantiyi_bozmuyor(monkeypatch):
    """Aşırı düzeltme kapısı: 'goto'/'dest' yolu değişmemeli."""
    monkeypatch.setattr("gui.pdf_viewer_mixins._events.resolve_link_action",
                        lambda raw, link: ("goto", "HEDEF"))
    v = _Gorucu()
    v._handle_link_click(None, None)
    assert v.gidilen == ["HEDEF"]


@pdfli
def test_guvensiz_uyari_UZUN_adresi_kirpiyor(monkeypatch):
    """Uzun bir /URI alanı diyaloğu ekran dışına taşırmasın."""
    uyari = []
    monkeypatch.setattr("gui.pdf_viewer_mixins._events.QMessageBox.warning",
                        lambda *a, **k: uyari.append(a))
    v = _Gorucu()
    v._guvensiz_baglanti("ms-msdt:" + "x" * 5000)
    assert uyari
    metin = uyari[0][-1]
    assert len(metin) < 400
    assert "..." in metin
