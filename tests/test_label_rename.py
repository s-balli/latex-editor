"""F2 \\label yeniden adlandırma — editör sinyali ve MainWindow handler testleri.

İki katman:
- gui.editor.EditorWidget: F2 imleç altındaki anahtarı yakalar
- gui.mixins.edit_ops: anahtarı doküman + \\input zincirinde toplu değiştirir
  (sekme arabellekleri seç-değiştir ile, disk dosyaları atomik yazar)
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QTabWidget
    from gui.editor import EditorWidget
    from gui.main_window import MainWindow
    from gui.mixins.edit_ops import EditOpsMixin
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# --- EditorWidget: F2 imleç altındaki anahtarı yakalar ---


def test_f2_on_label_arg(qapp):
    ed = EditorWidget()
    ed.setText("\\label{fig:a}\n")
    caught = []
    ed.rename_label_requested.connect(caught.append)
    ed.setCursorPosition(0, len("\\label{fig:a") - 2)
    ed._request_rename_label()
    assert caught == ["fig:a"]


def test_f2_on_ref_arg(qapp):
    ed = EditorWidget()
    ed.setText("bkz \\ref{fig:a} burada\n")
    caught = []
    ed.rename_label_requested.connect(caught.append)
    ed.setCursorPosition(0, len("bkz \\ref{fig:a") - 1)
    ed._request_rename_label()
    assert caught == ["fig:a"]


def test_f2_elsewhere_no_signal(qapp):
    ed = EditorWidget()
    ed.setText("\\label{fig:a}\ndüz metin\n")
    caught = []
    ed.rename_label_requested.connect(caught.append)
    ed.setCursorPosition(1, 3)
    ed._request_rename_label()
    assert caught == []


# --- MainWindow handler: zincirde toplu değiştirme ---


class _StubMain(EditOpsMixin):
    """MainWindow yerine: _on_rename_label'in ihtiyaç duyduğu arayüz."""

    def __init__(self, editors):
        self._editor_tabs = QTabWidget()
        for ed in editors:
            self._editor_tabs.addTab(ed, ed.display_name)
        self._cur = editors[0] if editors else None
        self.messages = []
        self._status = SimpleNamespace(showMessage=self.messages.append)

    def _current_editor(self):
        return self._cur

    def sender(self):
        return None


def test_rename_updates_tab_and_disk(qapp, tmp_path):
    """Ana dosya sekmede (arabellek), çocuk diskte → ikisi de değişir."""
    ch = tmp_path / "ch.tex"
    ch.write_text("metin \\ref{fig:a} ve \\cref{fig:a, tab:b}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\input{ch}\n\\ref{fig:a}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain([ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("fig:yeni", True)):
        MainWindow._on_rename_label(stub, "fig:a")

    buf = ed.text()
    assert buf.count("fig:yeni") == 2      # \label + \ref
    assert "fig:a" not in buf
    disk = ch.read_text(encoding="utf-8")
    assert disk == "metin \\ref{fig:yeni} ve \\cref{fig:yeni, tab:b}\n"
    assert any("2 dosya" in m for m in stub.messages)


def test_rename_child_open_in_tab(qapp, tmp_path):
    """Çocuk da sekmedeyse arabelleği değişir, disk dokunulmaz (kullanıcı kaydeder)."""
    ch = tmp_path / "ch.tex"
    ch.write_text("\\ref{fig:a}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\input{ch}\n", encoding="utf-8")
    ed_main = EditorWidget(); ed_main._file_path = str(main)
    ed_main.setText(main.read_text(encoding="utf-8"))
    ed_ch = EditorWidget(); ed_ch._file_path = str(ch)
    ed_ch.setText(ch.read_text(encoding="utf-8"))

    stub = _StubMain([ed_main, ed_ch])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("fig:yeni", True)):
        MainWindow._on_rename_label(stub, "fig:a")

    assert "fig:yeni" in ed_ch.text()
    assert ch.read_text(encoding="utf-8") == "\\ref{fig:a}\n"   # disk değişmedi
    assert ed_ch.isModified()


def test_rename_undo_restores(qapp, tmp_path):
    """Sekme değişikliği tek undo adımıyla geri alınabilir."""
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\ref{fig:a}\n", encoding="utf-8")
    ed = EditorWidget(); ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain([ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("fig:yeni", True)):
        MainWindow._on_rename_label(stub, "fig:a")
    assert "fig:yeni" in ed.text()
    ed.undo()
    assert ed.text() == main.read_text(encoding="utf-8")


def test_rename_duplicate_blocked(qapp, tmp_path):
    """Yeni ad projede varsa engellenir, hiçbir şey değişmez."""
    ch = tmp_path / "ch.tex"
    ch.write_text("\\ref{fig:b}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n\\label{fig:b}\n\\input{ch}\n", encoding="utf-8")
    ed = EditorWidget(); ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain([ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("fig:b", True)), \
         patch("gui.mixins.edit_ops.QMessageBox.warning") as warn:
        MainWindow._on_rename_label(stub, "fig:a")

    warn.assert_called_once()
    assert ed.text() == main.read_text(encoding="utf-8")
    assert ch.read_text(encoding="utf-8") == "\\ref{fig:b}\n"


def test_rename_invalid_chars_blocked(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{fig:a}\n", encoding="utf-8")
    ed = EditorWidget(); ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain([ed])
    with patch("gui.mixins.edit_ops.QInputDialog.getText", return_value=("boşluk lu", True)):
        MainWindow._on_rename_label(stub, "fig:a")
    assert ed.text() == main.read_text(encoding="utf-8")
    assert any("Geçersiz" in m for m in stub.messages)
