"""PDF sayfa çizimi Pillow'suz: renk sırası doğru ve Pillow'a dönülmüyor.

2026-09-30'a kadar `render_page_to_qimage` sayfayı `bitmap.to_pil()` ile
çeviriyordu; Pillow'un uygulamadaki tek işi buydu (1.2.1 exe'sinde 6.1 MB,
pakete giren 11.3.0 için 13 güvenlik danışması). Artık PDFium RGB sırasında
çiziyor ve ham tampon doğrudan QImage'e gidiyor. Bu yolun iki sessiz kusur
sınıfı var:

  1. Renk sırası: `rev_byteorder` unutulursa kırmızı ile mavi yer değiştirir.
     Siyah-beyaz metin sayfası bunu HİÇ göstermez; kapı bu yüzden iki renkli
     bir sayfa kuruyor.
  2. Pillow'a geri dönüş: `to_pil` geri gelirse Pillow'suz pakette önizleme
     "No module named 'PIL'" ile düşer. Test ortamında Pillow kurulu
     (kehanet olarak), üstelik pypdfium2 `PIL.Image`i ilk kullanımda
     önbelleğe alıyor; yani yalnız `sys.modules`i engellemek sıraya bağlı
     olarak boş geçer. Kapı `to_pil`in kendisini yasaklıyor.

Üçüncü test bağımsız kehanet: Pillow kuruluysa PDFium'un kendi `to_pil`
çıktısıyla satır satır karşılaştırma (satır adımı ve dolgu hatası sınıfı).
"""

import glob
import os
import sys

import pytest

try:
    import pypdfium2 as pdfium
    from PyQt6.QtWidgets import QApplication
    from gui.pdf_render import render_page_to_qimage
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / pypdfium2 gerekli", allow_module_level=True)

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _kucuk_pdf(icerik: bytes) -> bytes:
    """100x100 pt tek sayfalık PDF, geçerli xref'le (PDFium onarıma gitmesin)."""
    nesneler = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] "
        b"/Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(icerik), icerik),
    ]
    govde = b"%PDF-1.4\n"
    konumlar = []
    for i, nesne in enumerate(nesneler, 1):
        konumlar.append(len(govde))
        govde += b"%d 0 obj\n%s\nendobj\n" % (i, nesne)
    xref = len(govde)
    govde += b"xref\n0 %d\n0000000000 65535 f \n" % (len(nesneler) + 1)
    for k in konumlar:
        govde += b"%010d 00000 n \n" % k
    govde += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
              % (len(nesneler) + 1, xref))
    return govde


# Sol yarı saf kırmızı, sağ yarı saf mavi.
_IKI_RENK = _kucuk_pdf(b"1 0 0 rg 0 0 50 100 re f 0 0 1 rg 50 0 50 100 re f")


def _renk(img, x, y):
    c = img.pixelColor(x, y)
    return c.red(), c.green(), c.blue()


def test_RENK_SIRASI_dogru(qapp):
    img = render_page_to_qimage(pdfium.PdfDocument(_IKI_RENK)[0], 1.0)
    assert (img.width(), img.height()) == (100, 100)
    assert _renk(img, 25, 50) == (255, 0, 0), "sol yarı kırmızı olmalı"
    assert _renk(img, 75, 50) == (0, 0, 255), "sağ yarı mavi olmalı"


def test_KOYU_KIP_renkleri_tersine_ceviriyor(qapp):
    img = render_page_to_qimage(pdfium.PdfDocument(_IKI_RENK)[0], 1.0,
                                invert=True)
    assert _renk(img, 25, 50) == (0, 255, 255)
    assert _renk(img, 75, 50) == (255, 255, 0)


def test_PILLOW_YASAKKEN_ciziyor(qapp, monkeypatch):
    """Pillow'suz paketteki durum: `to_pil` ve `PIL` ikisi de kullanılamaz."""
    def _yasak(*_a, **_k):
        raise AssertionError("çizim yolu Pillow'a döndü (to_pil)")

    monkeypatch.setattr(pdfium.PdfBitmap, "to_pil", _yasak)
    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setitem(sys.modules, "PIL.Image", None)
    img = render_page_to_qimage(pdfium.PdfDocument(_IKI_RENK)[0], 1.37)
    assert not img.isNull()
    assert _renk(img, img.width() // 4, img.height() // 2) == (255, 0, 0)


def test_PDFIUM_KEHANETIYLE_satir_satir_ayni(qapp):
    """Bağımsız kehanet: aynı sayfanın PDFium'un kendi Pillow köprüsüyle hâli."""
    pytest.importorskip("PIL")
    yollar = sorted(glob.glob(os.path.join(_KOK, "tests", "veri", "*.pdf")))
    assert yollar, "tests/veri altında PDF yok"
    farkli = []
    for yol in yollar:
        belge = pdfium.PdfDocument(yol)
        for i in range(len(belge)):
            for olcek in (0.75, 1.37):
                img = render_page_to_qimage(belge[i], olcek)
                pil = belge[i].render(scale=olcek).to_pil().convert("RGB")
                w, h = pil.size
                ham = pil.tobytes()
                ayni = (img.width(), img.height()) == (w, h) and all(
                    img.constScanLine(y).asstring(w * 3)
                    == ham[y * w * 3:(y + 1) * w * 3]
                    for y in range(h))
                if not ayni:
                    farkli.append("%s s.%d x%.2f" % (
                        os.path.basename(yol), i + 1, olcek))
    assert not farkli, "Pillow köprüsünden farklı çıkanlar: %s" % farkli
