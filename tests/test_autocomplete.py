"""EditorWidget otomatik tamamlama kapanış testleri (A.2).

Popup'tan seçilen \\cmd{ / \\cmd[ girdisi SCN_AUTOCCOMPLETED ile geldiğinde,
keyPressEvent atlandığı için normal autopair tetiklenmez. _on_autoc_completed
karşılık gelen } / ] ekler; böylece elle yazılan komutla popup'tan seçilen
aynı komut tutarlı olur (ikisi de çiftlenmiş ayraç verir).
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

_DESKTOP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "desktop"))
if _DESKTOP not in sys.path:
    sys.path.insert(0, _DESKTOP)

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.Qsci import QsciScintilla
    from gui.editor import EditorWidget
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui.editor import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _editor():
    return EditorWidget()


def _line(ed, n):
    return ed.text(n).rstrip("\n")


# --- _on_autoc_completed birim testleri ---


def test_autoclose_brace_on_completed_frac(qapp):
    r"""Seçilen \frac{ -> \frac{}, imleç { ve } arasında (index 6)."""
    ed = _editor()
    ed.setText("\\frac{")
    ed.setCursorPosition(0, 6)
    ed._on_autoc_completed(b"\\frac{", 0, 0, 5)
    assert _line(ed, 0) == "\\frac{}"
    assert ed.getCursorPosition() == (0, 6)  # { ve } arası


def test_autoclose_bracket_on_completed_item(qapp):
    r"""Seçilen \item[ -> \item[], imleç [ ve ] arasında."""
    ed = _editor()
    ed.setText("\\item[")
    ed.setCursorPosition(0, 6)
    ed._on_autoc_completed(b"\\item[", 0, 0, 5)
    assert _line(ed, 0) == "\\item[]"
    assert ed.getCursorPosition() == (0, 6)


def test_no_autoclose_for_begin(qapp):
    r"""\begin{ kapanmamalı: ayracı kasıtlı eşlenmez (begin/end kapanışı ayrı)."""
    ed = _editor()
    ed.setText("\\begin{")
    ed.setCursorPosition(0, 7)
    ed._on_autoc_completed(b"\\begin{", 0, 0, 6)
    assert _line(ed, 0) == "\\begin{"  # değişmedi


def test_no_autoclose_for_end(qapp):
    r"""Simetri: \end{ de kapanmamalı."""
    ed = _editor()
    ed.setText("\\end{")
    ed.setCursorPosition(0, 5)
    ed._on_autoc_completed(b"\\end{", 0, 0, 4)
    assert _line(ed, 0) == "\\end{"


def test_no_autoclose_for_left_paren(qapp):
    r"""\left( ayraç-sözdizimi: regex eşleşmez, kapanış eklenmez."""
    ed = _editor()
    ed.setText("\\left(")
    ed.setCursorPosition(0, 6)
    ed._on_autoc_completed(b"\\left(", 0, 0, 5)
    assert _line(ed, 0) == "\\left("


def test_no_autoclose_for_left_brace(qapp):
    r"""\left\{ ayraç-sözdizimi (\ ile gelir): regex eşleşmez."""
    ed = _editor()
    ed.setText("\\left\\{")
    ed.setCursorPosition(0, 7)
    ed._on_autoc_completed(b"\\left\\{", 0, 0, 6)
    assert _line(ed, 0) == "\\left\\{"


def test_no_double_close_if_already_paired(qapp):
    r"""İmleçten sonra zaten } varsa (manuel autopair akışı) çiftleme."""
    ed = _editor()
    ed.setText("\\frac{}")
    ed.setCursorPosition(0, 6)  # mevcut } önünde
    ed._on_autoc_completed(b"\\frac{", 0, 0, 5)
    assert _line(ed, 0) == "\\frac{}"  # ikinci } eklenmedi


def test_no_close_for_plain_command(qapp):
    r"""Argümansız komut (\sum) -> kapanış yok."""
    ed = _editor()
    ed.setText("\\sum")
    ed.setCursorPosition(0, 4)
    ed._on_autoc_completed(b"\\sum", 0, 0, 4)
    assert _line(ed, 0) == "\\sum"


def test_handles_invalid_text_safely(qapp):
    r"""Geçersiz/bozuk signal argümanı istisna fırlatmamalı."""
    ed = _editor()
    ed.setText("x")
    ed.setCursorPosition(0, 1)
    # Hatalı tipte argüman — bytes() dönüşümü patlarsa yakalanmalı
    ed._on_autoc_completed(object(), 0, 0, 0)
    assert _line(ed, 0) == "x"


# --- Uçtan uca: gerçek SCI_AUTOCCOMPLETE sinyal akışı ---


def test_completion_end_to_end_closes_brace(qapp):
    r"""Gerçek popup tamamlaması (SCI_AUTOCCOMPLETE) kapanışı tetiklemeli."""
    ed = _editor()
    ed.setText("\\frac")
    ed.setCursorPosition(0, 5)
    ed.SendScintilla(QsciScintilla.SCI_AUTOCSETSEPARATOR, ord(' '))
    ed.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, 5, b"\\frac{")
    assert ed.SendScintilla(QsciScintilla.SCI_AUTOCACTIVE)
    ed.SendScintilla(QsciScintilla.SCI_AUTOCCOMPLETE)
    qapp.processEvents()  # SCN_AUTOCCOMPLETED işlensin
    assert _line(ed, 0) == "\\frac{}"
    assert ed.getCursorPosition() == (0, 6)
