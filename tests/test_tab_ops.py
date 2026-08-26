"""TabOpsMixin — sekme kapatma davranışı testleri.

Regression odağı: kayıt başarısız olduğunda dirty sekme kapanmamalı
(kapanırsa kullanıcı "Kaydet" dese bile içerik kaybolur).
"""

from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.mixins.tab_ops import TabOpsMixin
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Stub(TabOpsMixin, StubMain):
    def __init__(self, editors):
        StubMain.__init__(self, editors=editors)
        self._pdf_viewer = SimpleNamespace(clear=lambda: None)
        self._wordcount_editor = None
        self._outline_editor = None
        self._find_bar = None
        self.save_reply = "save"
        self.watch_removed = []

    def _save_dialog(self, name):
        return self.save_reply

    def _file_watch_remove(self, path):
        self.watch_removed.append(path)


def _dirty_editor(tmp_path):
    tex = tmp_path / "ana.tex"
    tex.write_text("\\begin{document}\nmerhaba\n\\end{document}\n", encoding="utf-8")
    ed = EditorWidget()
    assert ed.open_file(str(tex))
    # setModified(True) bu PyQt6.Qsci'de state'i değiştirmiyor; gerçek düzenleme
    # (insert) SCI'da savepoint'i gerçekten düşürür.
    ed.insert("x")
    assert ed.isModified()
    return ed


def test_close_tab_survives_save_failure(qapp, tmp_path, monkeypatch):
    """Kayıt başarısızsa sekme kapanmamalı; izleme de kaldırılmamalı."""
    ed = _dirty_editor(tmp_path)
    stub = _Stub([ed])
    monkeypatch.setattr(EditorWidget, "save_file", lambda self: False)

    assert stub._close_tab_safe(0) is False
    assert stub._editor_tabs.count() == 1           # sekme açık kaldı
    assert stub._editor_tabs.widget(0) is ed
    assert stub.watch_removed == []                 # dosya izlemesi duruyor


def test_close_tab_saves_and_closes(qapp, tmp_path, monkeypatch):
    """Kayıt başarılıysa normal akış: izleme kalkar, sekme kapanır."""
    ed = _dirty_editor(tmp_path)
    stub = _Stub([ed])
    saved = []

    def _ok_save(self):
        saved.append(1)
        return True

    monkeypatch.setattr(EditorWidget, "save_file", _ok_save)

    assert stub._close_tab_safe(0) is True
    assert stub._editor_tabs.count() == 0
    assert saved == [1]
    assert stub.watch_removed == [ed.file_path]
