"""Tablo sihirbazı GUI + mixin testleri (dialog üretimi, ekleme, hizalama)."""

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QTableWidgetItem
    from gui.editor import EditorWidget
    from gui.mixins.table_ops import TableOpsMixin
    from gui.table_wizard import TableWizardDialog
    from core.latex_tables import parse_tabular_at
    from tests.stub_main import StubMain
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# =====================================================================
# Dialog: grid → kod
# =====================================================================


def _filled_dialog(qapp):
    dlg = TableWizardDialog(existing_labels=["tab:var"])
    dlg._caption.setText("Yöntem Karşılaştırması")
    dlg._grid.setItem(0, 0, QTableWidgetItem("Yöntem"))
    dlg._grid.setItem(0, 1, QTableWidgetItem("Doğruluk %"))
    dlg._grid.setItem(0, 2, QTableWidgetItem("F1"))
    dlg._grid.setItem(1, 0, QTableWidgetItem("CNN"))
    dlg._grid.setItem(1, 1, QTableWidgetItem("91.2"))
    dlg._grid.setItem(1, 2, QTableWidgetItem("0.87"))
    return dlg


def test_dialog_builds_code(qapp):
    dlg = _filled_dialog(qapp)
    code = dlg.result_text()
    assert "\\begin{tabular}{ccc}" in code
    assert "Doğruluk \\%" in code
    assert "\\caption{Yöntem Karşılaştırması}" in code
    # caption'a göre otomatik label, mevcutla çakışmaz
    assert "\\label{tab:yontem-karsilastirmasi}" in code


def test_dialog_label_collision_suffix(qapp):
    dlg = TableWizardDialog(existing_labels=["tab:yontem-karsilastirmasi"])
    dlg._caption.setText("Yöntem Karşılaştırması")
    assert dlg._label.text() == "tab:yontem-karsilastirmasi-2"


def test_dialog_options_live_preview(qapp):
    dlg = _filled_dialog(qapp)
    dlg._cb_vlines.setChecked(True)
    dlg._align_box.itemAt(0).widget().setCurrentIndex(0)  # Sol (l)
    code = dlg.result_text()
    assert "{|l|c|c|}" in code
    assert dlg._preview.toPlainText() == code


def test_dialog_load_block_edits_existing(qapp):
    text = ("\\begin{table}\n\\begin{tabular}{lr}\n\\toprule\n"
            "Ad & Deger \\\\\n\\midrule\na & 1 \\\\\n\\bottomrule\n"
            "\\end{tabular}\n\\end{table}\n")
    block = parse_tabular_at(text, text.index("Deger"))
    dlg = TableWizardDialog()
    dlg.load_block(block)
    cells = dlg.cells()
    assert cells[0] == ["Ad", "Deger"]
    assert cells[1] == ["a", "1"]
    # spec 'lr' → ilk iki hizalama kutusu Sol/Sağ seçili
    assert dlg._align_box.itemAt(0).widget().currentIndex() == 0
    assert dlg._align_box.itemAt(1).widget().currentIndex() == 2
    assert "{lr}" in dlg.result_text()


def test_dialog_empty_preview_hint(qapp):
    dlg = TableWizardDialog()
    assert dlg.result_text() == ""


# =====================================================================
# Mixin: ekle / hizala (stub MainWindow)
# =====================================================================


class _Stub(TableOpsMixin, StubMain):
    def __init__(self, editors):
        StubMain.__init__(self, editors=editors)
        self._theme_mgr = type("M", (), {"theme": THEMES["dark"]})()


def test_wizard_inserts_at_cursor(qapp, monkeypatch):
    import gui.table_wizard as tw

    ed = EditorWidget()
    ed.setText("öncesi\nsonrası\n")
    ed.setCursorPosition(1, 0)
    stub = _Stub([ed])

    code = "\\begin{table}\n\\begin{tabular}{l}x\\end{tabular}\n\\end{table}"

    class FakeDlg:
        def __init__(self, *a, **k):
            pass

        def apply_theme(self, t):
            pass

        def load_block(self, b):
            raise AssertionError("yeni tablo modunda load_block çağrılmamalı")

        def exec(self):
            return True

        def result_text(self):
            return code

    monkeypatch.setattr(tw, "TableWizardDialog", FakeDlg)
    stub._table_wizard()

    assert code in ed.text()
    assert "öncesi\n" in ed.text() and "sonrası" in ed.text()
    assert "Tablo eklendi" in stub._status.msg


def test_wizard_replaces_existing_block(qapp, monkeypatch):
    import gui.table_wizard as tw

    original = ("öncesi\n\\begin{tabular}{ll}\na & b\\\\\n\\end{tabular}\nsonrası\n")
    ed = EditorWidget()
    ed.setText(original)
    ln = ed.text().index("a & b")
    line, col = stub_offset = (2, 0)
    ed.setCursorPosition(2, 0)
    stub = _Stub([ed])

    new_code = "\\begin{tabular}{ll}\nYENİ & TABLO\\\\\n\\end{tabular}"

    class FakeDlg:
        def __init__(self, *a, **k):
            pass

        def apply_theme(self, t):
            pass

        def load_block(self, b):
            self.loaded = b

        def exec(self):
            return True

        def result_text(self):
            return new_code

    monkeypatch.setattr(tw, "TableWizardDialog", FakeDlg)
    stub._table_wizard()

    t = ed.text()
    assert "YENİ & TABLO" in t
    assert "a & b" not in t
    assert t.startswith("öncesi\n") and t.rstrip().endswith("sonrası")


def test_align_table_reformats_editor(qapp):
    original = ("giriş\n\\begin{table}\n    \\begin{tabular}{lll}\n"
                "        \\toprule\n"
                "        uzunhücre & b & c \\\\\n"
                "        x & yy & zzz \\\\\n"
                "        \\bottomrule\n"
                "    \\end{tabular}\n\\end{table}\n")
    ed = EditorWidget()
    ed.setText(original)
    ed.setCursorPosition(4, 10)  # veri satırı içinde
    stub = _Stub([ed])

    stub._align_table()
    t = ed.text()
    assert "Tablo hizalandı" in stub._status.msg
    # & işaretleri hizalanmış kolonlarda
    import re as _re
    data = [ln for ln in t.split("\n") if "&" in ln]
    cols = [[m.start() for m in _re.finditer(r"(?<!\\)&", ln)] for ln in data]
    assert cols[0] == cols[1]


def test_align_table_outside(qapp):
    ed = EditorWidget()
    ed.setText("tablo yok burada\n")
    ed.setCursorPosition(0, 3)
    stub = _Stub([ed])
    stub._align_table()
    assert "tablo içinde değil" in stub._status.msg


def test_cursor_char_offset_unicode(qapp):
    ed = EditorWidget()
    ed.setText(" ascii\nğüş ti öç\nüçüncü\n")
    ed.setCursorPosition(1, 3)  # 'ğüş' → +3 char = ' ti...' başı
    stub = _Stub([ed])
    assert stub._cursor_char_offset(ed) == len(" ascii\nğüş")
