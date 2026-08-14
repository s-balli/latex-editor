"""Panodan resim yapıştırma testleri (Ctrl+V → media/'a kaydet + figure akışı)."""

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
