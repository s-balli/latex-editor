"""pdf_viewer bookmark helper'ları — pypdfium2 API sürüm uyumu testleri.

pypdfium2 get_toc() çıktısı sürümler arası değişti: eski PdfBookmark
(get_title/get_dest metodları) → yeni PdfOutlineItem (.title/.page_index).
Helper'lar her iki formu da handle etmeli.
"""

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from gui.pdf_viewer_mixins._bookmarks import _bm_title, _bm_level, _bm_page_index


class _Dest:
    def __init__(self, idx):
        self._idx = idx

    def get_index(self):
        return self._idx


class _OldApiBM:
    """Eski pypdfium2 PdfBookmark: get_title()/get_dest() metodları."""

    def __init__(self, title, level, page_idx):
        self._title = title
        self.level = level
        self._dest = _Dest(page_idx)

    def get_title(self):
        return self._title

    def get_dest(self):
        return self._dest


class _NewApiBM:
    """Yeni pypdfium2 PdfOutlineItem: .title/.level/.page_index (get_* yok)."""

    def __init__(self, title, level, page_idx):
        self.title = title
        self.level = level
        self.page_index = page_idx


class TestBookmarkHelpers:
    def test_eski_api(self):
        bm = _OldApiBM("Bölüm 1", 0, 3)
        assert _bm_title(bm) == "Bölüm 1"
        assert _bm_level(bm) == 0
        assert _bm_page_index(bm) == 3

    def test_yeni_api(self):
        bm = _NewApiBM("Section 2", 1, 7)
        assert _bm_title(bm) == "Section 2"
        assert _bm_level(bm) == 1
        assert _bm_page_index(bm) == 7

    def test_bos_baslik(self):
        assert _bm_title(_OldApiBM("", 0, 0)) == ""
        assert _bm_title(_NewApiBM(None, 0, 0)) == ""

    def test_sayfa_indeksi_yoksa_none(self):
        class NoPage:
            level = 0

            def get_title(self):
                return "x"

        assert _bm_page_index(NoPage()) is None


# --- Gerçek PdfViewer, anahatlı PDF (2026-09-25 ölçümleri) ---

# Alt yer iminin hedefi 2. sayfanın ALT kısmında (PDF y=100, üstten 692 pt):
# sayfa başı gösterildiğinde hedef görüntünün dışında kalıyor.
_HEDEF_X, _HEDEF_Y = 72, 100


def _anahatli_pdf(yol):
    """İki sayfa; "Ana" (2. sayfa başı) altında "Alt" (2. sayfanın altı)."""
    icerik = b"BT /F1 12 Tf 72 100 Td (Z) Tj ET"
    nesneler = [
        b"<</Type/Catalog/Pages 2 0 R/Outlines 7 0 R>>",
        b"<</Type/Pages/Kids[3 0 R 4 0 R]/Count 2>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 6 0 R>>>>/Contents 5 0 R>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 6 0 R>>>>/Contents 5 0 R>>",
        b"<</Length " + str(len(icerik)).encode() + b">>stream\n" + icerik
        + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        b"<</Type/Outlines/First 8 0 R/Last 8 0 R/Count 2>>",
        b"<</Title(Ana)/Parent 7 0 R/First 9 0 R/Last 9 0 R/Count 1"
        b"/Dest[4 0 R/XYZ 72 792 0]>>",
        b"<</Title(Alt)/Parent 8 0 R/Dest[4 0 R/XYZ %d %d 0]>>"
        % (_HEDEF_X, _HEDEF_Y),
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


def _gorunen_viewer(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtTest import QTest
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES
    v = PdfViewer(theme=THEMES["dark"])
    v.resize(900, 600)
    v.show()
    yol = _anahatli_pdf(tmp_path / "anahat.pdf")
    assert v.load_pdf(yol)
    QTest.qWait(200)
    return v, yol


def test_YER_IMI_hedefin_KONUMUNA_goturuyor(tmp_path):
    r"""Tıklama hedefin konumuna iniyor, iç bağlantı gibi; sayfa başına değil.

    ÖLÇÜLDÜ (2026-09-25, gerçek hyperref PDF'i): sayfanın alt yarısındaki
    alt bölümün yer imi sayfa başını gösteriyordu, başlık görüntünün
    dışında kalıyordu; aynı hedefe giden içindekiler bağlantısı başlığa
    iniyordu.
    """
    from PyQt6.QtCore import QPoint
    from gui.pdf_donusum import geometri, gorsele
    from gui.pdfium_lock import pdfium_lock
    v, _yol = _gorunen_viewer(tmp_path)
    ana = v._bookmark_tree.topLevelItem(0)
    v._on_bookmark_clicked(ana.child(0), 0)
    ust = v._page_labels[1].mapTo(v._pages_widget, QPoint(0, 0)).y()
    with pdfium_lock:       # canlı görüntüleyicinin işçisi aynı anda pdfium'da
        g = geometri(v._pdf[1])
    hedef = ust + gorsele(g, _HEDEF_X, _HEDEF_Y, v._olcek(1))[1]
    sb = v._scroll.verticalScrollBar().value()
    assert sb <= hedef <= sb + v._scroll.viewport().height()


def test_KAPATILAN_yer_imi_yeniden_yuklemede_KAPALI_kaliyor(tmp_path):
    """Yeniden derlemede (otomatik derlemede her Ctrl+S) kapatılan düğüm
    yeniden açılıyordu; anahat paneli aynı durumda kapalı tutuyordu."""
    v, yol = _gorunen_viewer(tmp_path)
    assert v._bookmark_tree.topLevelItem(0).isExpanded()     # ilk açılış
    v._bookmark_tree.topLevelItem(0).setExpanded(False)
    assert v.load_pdf(yol)
    assert not v._bookmark_tree.topLevelItem(0).isExpanded()
