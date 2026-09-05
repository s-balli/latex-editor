# -*- coding: utf-8 -*-
"""PDF metin seçimi: seçilen metin ve EKRANDA GÖRÜNEN vurgu.

Seçim yolunun hiç testi yoktu. Buradaki testler iki ayrı şeyi soruyor:
seçilen METİN doğru mu (sağ tık > Kopyala bunu veriyor) ve seçim EKRANDA
görünüyor mu. İkisi ayrışabiliyor; ölçülen iki kusur da tam o ayrışmaydı.

  /Rotate 180   metin doğru, vurgu gereken alanın %11'i (yalnız ilk karakter)
  render'dan
  önce seçim    metin doğru, vurgu HİÇ yok ve render gelince de gelmiyor

TEX GEREKMİYOR: belge elle kuruluyor, döndürülmüş sürümler pypdfium2'nin
`set_rotation`ıyla üretiliyor. Böylece testler matris işlerinde de koşuyor,
yalnız `derle` işinde değil.
"""

import os
import time

import pytest

try:
    import pypdfium2 as pdfium
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication
    from gui.pdf_donusum import geometri, gorsele
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

pytestmark = pytest.mark.skipif(not _VAR, reason="PyQt6 / pypdfium2 gerekli")

_METIN = "ABCDEFGHIJ"


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def _pdf_yaz(yol, metin=_METIN, boyut=(612, 792)):
    """Seçilebilir tek satır metin taşıyan asgari PDF (dış araç gerekmez)."""
    icerik = ("BT /F1 24 Tf 72 700 Td (%s) Tj ET" % metin).encode("latin-1")
    nesneler = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        ("<</Type/Page/Parent 2 0 R/MediaBox[0 0 %d %d]"
         "/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>"
         % boyut).encode("latin-1"),
        b"<</Length " + str(len(icerik)).encode() + b">>stream\n" + icerik
        + b"\nendstream",
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


def _dondur(kaynak, hedef, donme):
    pdf = pdfium.PdfDocument(kaynak)
    pdf[0].set_rotation(donme)
    pdf.save(str(hedef))
    pdf.close()
    return str(hedef)


def _viewer(qapp, yol, render_bekle=True):
    v = PdfViewer(theme=THEMES["dark"])
    v.resize(1200, 900)
    v.show()
    qapp.processEvents()
    assert v.load_pdf(yol)
    qapp.processEvents()
    v._pages_widget.adjustSize()
    qapp.processEvents()
    if render_bekle:
        v._request_render(0)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 15:
            qapp.processEvents()
            pm = v._page_labels[0].pixmap()
            if pm is not None and not pm.isNull():
                break
            time.sleep(0.01)
    return v


def _surukle(qapp, v, ilk=0, son=9):
    """Karakter `ilk`ten `son`a sürükle; (metin, kutu_sayısı, kapsam_oranı)."""
    sayfa = v._pdf[0]
    tp = sayfa.get_textpage()
    g = geometri(sayfa)
    olcek = v._olcek(0)

    def ekran(i):
        left, bottom, right, top = tp.get_charbox(i, loose=True)
        vx, vy = gorsele(g, (left + right) / 2, (bottom + top) / 2, olcek)
        return QPoint(int(vx), int(vy))

    et = v._page_labels[0]
    v._selection_press(ekran(ilk), et)
    v._selection_move(ekran(son), et)
    v._selection_release(ekran(son), et)
    qapp.processEvents()

    # Seçilen karakterlerin ekranda GERÇEKTEN kapladığı dikdörtgen
    kutular = []
    for i in range(ilk, son + 1):
        left, bottom, right, top = tp.get_charbox(i, loose=True)
        x1, y1 = gorsele(g, left, top, olcek)
        x2, y2 = gorsele(g, right, bottom, olcek)
        kutular.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
    gereken = ((max(k[2] for k in kutular) - min(k[0] for k in kutular))
               * (max(k[3] for k in kutular) - min(k[1] for k in kutular)))
    kapsanan = sum(h.geometry().width() * h.geometry().height()
                   for h in v._selection_highlights)
    return (v._selected_text, len(v._selection_highlights),
            100.0 * kapsanan / gereken if gereken else 0.0)


@pytest.fixture
def duz_pdf(tmp_path):
    return _pdf_yaz(tmp_path / "duz.pdf")


# =====================================================================
# Döndürülmüş sayfada vurgu
#
# `_draw_selection_highlights` aynı satırdaki karakterleri tek koşuya
# birleştirirken koşuyu YALNIZ SAĞA genişletiyordu; metnin ekranda soldan
# sağa ilerlediğini varsayıyor. /Rotate 180'de görsel x AZALIYOR, yani
# `x + w` hep koşunun solunda kalıyor ve koşu hiç büyümüyordu.
#
# ÖLÇÜLDÜ (2026-09-05, uçtan uca): on karakter seçilince vurgu gereken
# alanın yalnız %11'ini kaplıyordu, yani sadece ilk karakter görünüyordu.
# Metin doğru seçiliyordu; kusur yalnızca GÖRÜNENDE.
# =====================================================================


class TestDonmusSayfadaVurgu:

    @pytest.mark.parametrize("donme", [0, 90, 180, 270])
    def test_vurgu_secimi_kapsiyor(self, qapp, tmp_path, duz_pdf, donme):
        yol = (duz_pdf if donme == 0
               else _dondur(duz_pdf, tmp_path / ("r%d.pdf" % donme), donme))
        v = _viewer(qapp, yol)
        try:
            metin, kutu, oran = _surukle(qapp, v)
            assert metin == _METIN, metin
            assert kutu > 0, "hiç vurgu çizilmemiş"
            assert oran > 60, (
                "/Rotate %d: vurgu seçimin yalnız %%%.0f'ini kaplıyor "
                "(%d kutu)" % (donme, oran, kutu))
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()

    def test_180de_vurgu_TEK_kosuda_birlesiyor(self, qapp, tmp_path, duz_pdf):
        """Kusurun imzası: 180'de birleştirme tetikleniyor ama büyümüyordu.

        90/270'te birleştirme hiç tetiklenmiyor (karakterler farklı görsel
        satırda), o yüzden ayrım yalnız 0 ve 180'de görülüyor.
        """
        v = _viewer(qapp, _dondur(duz_pdf, tmp_path / "r180.pdf", 180))
        try:
            _metin, kutu, oran = _surukle(qapp, v)
            assert kutu == 1, "180'de karakterler tek koşuda birleşmeli"
            assert oran > 90, oran
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()

    def test_duz_sayfada_davranis_degismedi(self, qapp, duz_pdf):
        """Karşı durum: /Rotate 0 tek koşu ve tam kapsam."""
        v = _viewer(qapp, duz_pdf)
        try:
            metin, kutu, oran = _surukle(qapp, v)
            assert (metin, kutu) == (_METIN, 1)
            assert oran > 90, oran
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()


# =====================================================================
# Sayfa çizilmeden yapılan seçim
#
# `_draw_selection_highlights` etiketin pixmap'i yoksa erken dönüyordu ve
# render sonradan gelince vurguyu kimse yeniden çizmiyordu: kullanıcı metni
# seçmiş oluyor (Kopyala çalışıyor) ama ekranda hiçbir şey görmüyor, bir
# daha da gelmiyor. Etiket yükleme anında doğru boyutla kuruluyor
# (`_create_placeholders` -> `setFixedSize`), yani geometri pixmap olmadan
# da doğru; erken dönüşün gerekçesi yoktu.
# =====================================================================


class TestRenderdanOnceSecim:

    def test_pixmap_yokken_de_vurgu_ciziliyor(self, qapp, duz_pdf):
        v = _viewer(qapp, duz_pdf, render_bekle=False)
        try:
            pm = v._page_labels[0].pixmap()
            # ÖNKOŞUL: vaka gerçekten "henüz çizilmemiş" hâli olmalı
            assert pm is None or pm.isNull(), \
                "sayfa zaten çizilmiş, test bir şey ölçmüyor"
            assert v._page_labels[0].width() > 50, \
                "etiket boyutlanmamış, geometri ölçülemez"

            metin, kutu, oran = _surukle(qapp, v)
            assert metin == _METIN, metin
            assert kutu > 0, "metin seçili ama ekranda hiçbir şey yok"
            assert oran > 60, oran
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()

    def test_render_geldikten_sonra_da_vurgu_duruyor(self, qapp, duz_pdf):
        """Vurgu etiketin çocuğu; pixmap gelince altında kalmalı, silinmemeli."""
        v = _viewer(qapp, duz_pdf, render_bekle=False)
        try:
            metin, kutu_once, _o = _surukle(qapp, v)
            assert metin == _METIN and kutu_once > 0

            v._request_render(0)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 15:
                qapp.processEvents()
                pm = v._page_labels[0].pixmap()
                if pm is not None and not pm.isNull():
                    break
                time.sleep(0.01)
            for _ in range(20):
                qapp.processEvents()
                time.sleep(0.01)

            assert len(v._selection_highlights) == kutu_once
            assert v._selected_text == _METIN
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()


# =====================================================================
# Seçimin temel sözleşmesi (bu dosyadan önce hiç sınanmamıştı)
# =====================================================================


class TestSecimSozlesmesi:

    def test_kisa_surukleme_de_seciyor(self, qapp, duz_pdf):
        v = _viewer(qapp, duz_pdf)
        try:
            metin, kutu, _o = _surukle(qapp, v, 0, 1)
            assert metin == "AB"
            assert kutu >= 1
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()

    def test_tiklama_secim_URETMIYOR(self, qapp, duz_pdf):
        """Aynı noktaya bas-bırak sürükleme değil tıklama; link açmalı.

        `_selection_move` bunu `delta < 4` ile bilerek eliyor.
        """
        v = _viewer(qapp, duz_pdf)
        try:
            metin, kutu, _o = _surukle(qapp, v, 3, 3)
            assert metin == ""
            assert kutu == 0
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()

    def test_kopyalanan_metin_panoya_gidiyor(self, qapp, duz_pdf):
        v = _viewer(qapp, duz_pdf)
        try:
            _surukle(qapp, v)
            v._copy_selection()
            qapp.processEvents()
            assert QApplication.clipboard().text() == _METIN
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()


# =====================================================================
# Sözleşmenin geri kalanı: sınır denetimi ve kopyalamada normalizasyon
#
# Bu ikisi mutasyonla ölçüldüğünde AÇIKTA kaldı: etiket denetimini ve
# `_normalize_pdf_text` çağrısını kaldırmak hiçbir testi düşürmüyordu.
# =====================================================================


class TestSecimSinirlari:

    def test_aralik_disi_sayfa_indeksi_cokmuyor(self, qapp, duz_pdf):
        """`_page_labels` geçici olarak kısa olabilir (yeniden yükleme).

        Etiket denetimi kalkarsa `QLabel(None)` ekranda başıboş bir pencere
        açar; bu test o denetimi pinler.
        """
        v = _viewer(qapp, duz_pdf)
        try:
            tp = v._pdf[0].get_textpage()
            once = len(v._selection_highlights)
            v._draw_selection_highlights(999, 0, 1, tp)   # patlamamalı
            qapp.processEvents()
            assert len(v._selection_highlights) == once
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()


class TestKopyalamaNormalizasyonu:
    """PDF'ten çıkan metinde aksanlar AYRIK gelebiliyor.

    Bazı PDF'lerde `ş` iki karakter olarak (`s` + cedilla) kodlanıyor;
    olduğu gibi kopyalanırsa kullanıcı Word'e `¸s` yapıştırıyor.
    `_normalize_pdf_text` bunları birleştiriyor.
    """

    @pytest.mark.parametrize("ham,beklenen", [
        ("¸s", "ş"), ("s¸", "ş"), ("¸S", "Ş"), ("S¸", "Ş"),
        ("˘g", "ğ"), ("g˘", "ğ"), ("˘G", "Ğ"),
        ("¸c", "ç"), ("c¸", "ç"), ("¸C", "Ç"),
    ])
    def test_ayrik_aksanlar_birlesiyor(self, ham, beklenen):
        from gui.pdf_viewer_mixins._selection import PdfSelectionMixin
        assert PdfSelectionMixin._normalize_pdf_text(ham) == beklenen

    def test_zaten_dogru_metin_bozulmuyor(self):
        from gui.pdf_viewer_mixins._selection import PdfSelectionMixin
        duz = "Şu çalışmada öğrenci ve kaynakça geçiyor."
        assert PdfSelectionMixin._normalize_pdf_text(duz) == duz

    def test_kopyalama_normalizasyonu_UYGULUYOR(self, qapp, duz_pdf):
        """Panoya giden metin ham değil normalize edilmiş olmalı."""
        v = _viewer(qapp, duz_pdf)
        try:
            v._selected_text = "ba¸slangıc¸"
            v._copy_selection()
            qapp.processEvents()
            assert QApplication.clipboard().text() == "başlangıç"
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()
