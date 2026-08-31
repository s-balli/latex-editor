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
