"""Referans denetimi — edit_ops handler ve rapor satır biçimleme testleri.

İki katman:
- gui.mixins.edit_ops: _audit_lines (RefAudit -> satırlar) ve _audit_references
- stub MainWindow deseni (bkz. test_goto_definition.py)
"""

from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.main_window import MainWindow
    from gui.mixins.edit_ops import EditOpsMixin
    from core.latex_refs import RefAudit
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _StubPanel:
    def __init__(self):
        self.reports = []

    def show_report(self, title, lines):
        self.reports.append((title, lines))


class _StubMain(EditOpsMixin):
    """MainWindow yerine: _audit_references'in ihtiyaç duyduğu arayüz.

    EditOpsMixin'den miras alır — handler self._audit_lines çağırır.
    """

    def __init__(self, editor):
        self._editor = editor
        self._output_panel = _StubPanel()
        self.messages = []
        self._status = SimpleNamespace(showMessage=self.messages.append)

    def _current_editor(self):
        return self._editor


def test_audit_lines_all_categories():
    r = RefAudit(
        undefined_refs=["fig:yok", "tab:yok"],
        undefined_cites=["k2024"],
        unused_bib_keys=["a", "b"],
    )
    lines = MainWindow._audit_lines(r)
    assert any("Tanımsız \\ref" in ln and "2" in ln for ln in lines)
    assert "    fig:yok" in lines
    assert any("Tanımsız \\cite" in ln for ln in lines)
    assert "    k2024" in lines
    assert any("Kullanılmayan .bib" in ln for ln in lines)
    assert "    a" in lines


def test_audit_lines_clean():
    lines = MainWindow._audit_lines(RefAudit())
    assert len(lines) == 1
    assert "Sorun bulunamadı" in lines[0]


def test_handler_reports_findings(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\ref{fig:yok}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    assert len(stub._output_panel.reports) == 1
    title, lines = stub._output_panel.reports[0]
    assert "Referans Denetimi" in title
    assert "    fig:yok" in lines
    assert any("tanımsız ref" in m for m in stub.messages)


def test_handler_clean_doc(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{a}\n\\ref{a}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    _, lines = stub._output_panel.reports[0]
    assert any("Sorun bulunamadı" in ln for ln in lines)
    assert any("sorun yok" in m for m in stub.messages)


def test_handler_needs_saved_file(qapp):
    ed = EditorWidget()  # dosya yolu yok
    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    assert stub._output_panel.reports == []
    assert any(".tex dosyası açın" in m for m in stub.messages)
