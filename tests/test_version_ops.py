"""Sürümleme GUI testleri — Sürümle akışı, Geçmiş sekmesi, geri yükleme.

dulwich yoksa atlar; MainWindow kurulumu yerine StubMain + VersionOpsMixin.
"""

import os
from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.mixins.version_ops import VersionOpsMixin
    from gui.output_panel import OutputPanel
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)

pytest.importorskip("dulwich")

from core import versioning as V  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Stub(VersionOpsMixin, StubMain):
    def __init__(self, editors, root):
        StubMain.__init__(self, editors=editors)
        self._file_tree = SimpleNamespace(_root=root)


def _project(tmp_path):
    (tmp_path / "ana.tex").write_text(
        "\\begin{document}\nmerhaba\n\\end{document}\n", encoding="utf-8")
    return str(tmp_path / "ana.tex")


def _stub_with_editor(tmp_path, monkeypatch, mesaj="deneme sürümü"):
    tex = _project(tmp_path)
    ed = EditorWidget()
    ed.open_file(tex)
    stub = _Stub([ed], str(tmp_path))

    import gui.mixins.version_ops as vo
    monkeypatch.setattr(
        vo.QInputDialog, "getText",
        staticmethod(lambda *a, **k: (mesaj, True)))
    return stub, ed, tex


# --- Sürümle ---


def test_first_snapshot_inits_repo_and_fills_history(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)

    stub._snapshot()
    assert V.is_repo(str(tmp_path))
    assert "Sürüm kaydedildi" in stub._status.msg
    assert stub._output_panel._history_list.count() == 1
    item = stub._output_panel._history_list.item(0)
    assert "deneme sürümü" in item.text()
    assert item.data(0x0100)  # UserRole: sha  (0x0100 = Qt.ItemDataRole.UserRole)


def test_second_snapshot_without_changes_skipped(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    stub._snapshot()

    stub._snapshot()
    assert "Değişiklik yok" in stub._status.msg
    assert stub._output_panel._history_list.count() == 1


def test_snapshot_saves_dirty_editor_first(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    ed.setText(ed.text() + "\n% yeni satır\n")
    ed.setModified(True)

    stub._snapshot()
    assert ed.isModified() is False, "kirli sekme sürümden önce kaydedilmeli"
    assert "% yeni satır" in open(tex, encoding="utf-8").read()


def test_snapshot_without_folder_shows_status(qapp):
    stub = _Stub([], "")
    stub._snapshot()
    assert "klasör açın" in stub._status.msg


# --- Geçmiş eylemleri: geri yükle / fark ---


def test_restore_from_version(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    stub._snapshot()
    sha = V.history(str(tmp_path))[0].sha

    # dosyayı boz
    ed.setText("\\begin{document}\nBOZUK\n\\end{document}\n")
    ed.save_file()

    monkeypatch.setattr(
        "gui.mixins.version_ops.QMessageBox.question",
        staticmethod(lambda *a, **k: 16384))  # QMessageBox.StandardButton.Yes
    stub._on_version_action("restore", sha)

    assert "BOZUK" not in open(tex, encoding="utf-8").read()
    assert "merhaba" in ed.text()
    assert "Geri yüklendi" in stub._status.msg


def test_version_action_without_editor(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    stub._snapshot()
    empty = _Stub([], str(tmp_path))
    empty._on_version_action("restore", "deadbeef")
    assert "Açık dosya yok" in empty._status.msg


# --- Panel: clear() geçmişi korur ---


def test_panel_clear_keeps_history(qapp):
    from gui.theme import THEMES
    panel = OutputPanel(theme=THEMES["dark"])
    panel.show_history([V.VersionEntry(sha="a" * 40, timestamp=0,
                                       message="kayıt", nfiles=2)])
    panel.clear()
    assert panel._history_list.count() == 1


# --- Ctrl+K filtrede ---


def test_ctrl_k_handled_by_app_key_shortcut(qapp):
    from PyQt6.QtCore import Qt, QEvent
    from PyQt6.QtGui import QKeyEvent
    from gui.main_window import MainWindow

    calls = []
    mw = SimpleNamespace(
        _table_wizard=lambda: calls.append("t"),
        _toggle_comment=lambda: calls.append("c"),
        _on_esc=lambda: calls.append("esc"),
        _snapshot=lambda: calls.append("k"),
        _pdf_viewer=SimpleNamespace(in_presentation=False),
        _current_editor=lambda: None,
    )
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_K,
                   Qt.KeyboardModifier.ControlModifier, "k")
    assert MainWindow._handle_app_key_shortcut(mw, ev) is True
    assert calls == ["k"]
