"""Referans denetimi — edit_ops handler ve OutputPanel tıklanabilir bulgu testleri.

İki katman:
- gui.mixins.edit_ops: _audit_references bulguları (metin, dosya, satır) üretir
- gui.output_panel: show_audit listeleri doldurur, tıklama error_clicked üretir
"""

import pytest

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.main_window import MainWindow
    from gui.mixins.edit_ops import EditOpsMixin
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _StubMain(EditOpsMixin, StubMain):
    """MainWindow yerine: _audit_references'in ihtiyaç duyduğu arayüz.

    EditOpsMixin'den miras alır — handler self._collect_audit_items çağırır.
    """

    def __init__(self, editor):
        super().__init__(editors=[editor])


# --- handler: bulgular (metin, dosya, satır) üretir ---


def test_handler_undefined_ref_clickable(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\ref{fig:yok}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._suggest_list.count() == 0
    assert panel._warn_list.count() == 1
    item = panel._warn_list.item(0)
    assert "Tanımsız \\ref" in item.text() and "fig:yok" in item.text()
    assert "m.tex:1" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == (str(main), 1)
    assert "1 tanımsız ref" in stub._status.msg


def test_handler_unused_bib_clickable(qapp, tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{kullanilmayan,}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{a}\n\\ref{a}\n\\bibliography{refs}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    assert panel._suggest_list.count() == 1
    item = panel._suggest_list.item(0)
    assert "Kullanılmayan .bib girdisi" in item.text() and "kullanilmayan" in item.text()
    assert "refs.bib:1" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == (str(bib), 1)


def test_handler_unused_label_clickable(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{bos}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    assert panel._suggest_list.count() == 1
    item = panel._suggest_list.item(0)
    assert "Kullanılmayan label" in item.text() and "bos" in item.text()
    assert "m.tex:1" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == (str(main), 1)
    assert "1 kullanılmayan label" in stub._status.msg


def test_handler_clean_doc(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{a}\n\\ref{a}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    # temiz belgede tek 'Sorun bulunamadı' mesajı Öneriler'de
    assert panel._suggest_list.count() == 1
    assert "Sorun bulunamadı" in panel._suggest_list.item(0).text()
    assert "sorun yok" in stub._status.msg


def test_handler_needs_saved_file(qapp):
    ed = EditorWidget()  # dosya yolu yok
    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    assert panel._suggest_list.count() == 0   # temiz-belge mesajı da yok
    assert ".tex dosyası açın" in stub._status.msg


# --- OutputPanel: show_audit + tıklama ---


def _panel(qapp):
    return OutputPanel(theme=THEMES["dark"])


def test_panel_show_audit_lists_and_tabs(qapp):
    panel = _panel(qapp)
    panel.show_audit(
        [("m.tex:3 — Tanımsız \\ref: fig:yok", "/tmp/m.tex", 3)],
        [("refs.bib:1 — Kullanılmayan .bib girdisi: a", "/tmp/refs.bib", 1)],
    )
    assert panel._warn_list.count() == 1
    assert panel._suggest_list.count() == 1
    assert panel._tabs.currentIndex() == panel._warn_tab_index


def test_panel_audit_click_emits_jump(qapp):
    panel = _panel(qapp)
    jumps = []
    panel.error_clicked.connect(lambda p, l: jumps.append((p, l)))
    panel.show_audit([("m.tex:3 — Tanımsız \\ref: fig:yok", "/tmp/m.tex", 3)], [])
    panel._on_result_click(panel._warn_list.item(0))
    assert jumps == [("/tmp/m.tex", 3)]


def test_panel_audit_click_without_location_no_emit(qapp):
    panel = _panel(qapp)
    jumps = []
    panel.error_clicked.connect(lambda p, l: jumps.append((p, l)))
    panel.show_audit([("Tanımsız \\ref: fig:yok", "", 0)], [])
    panel._on_result_click(panel._warn_list.item(0))
    assert jumps == []


def test_panel_audit_clean_shows_message(qapp):
    panel = _panel(qapp)
    panel.show_audit([], [])
    assert panel._suggest_list.count() == 1
    assert "Sorun bulunamadı" in panel._suggest_list.item(0).text()
    assert panel._tabs.currentIndex() == panel._suggest_tab_index
