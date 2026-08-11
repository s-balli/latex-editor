"""EditorWidget tamamlama + margin testleri (C.6, C.7, C.10).

C.6: \\begin{ / \\end{ sonrası ortam adı tamamlama.
C.7: Ctrl+Space manuel tamamlama (kısa kelimede de çalışır).
C.10: satır numarası margin'i satır sayısına göre dinamik genişler.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import bisect

import pytest

_DESKTOP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "desktop"))
if _DESKTOP not in sys.path:
    sys.path.insert(0, _DESKTOP)

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    from PyQt6.Qsci import QsciScintilla
    from gui.editor import EditorWidget, _LATEX_ENVIRONMENTS
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


def _autoc_active(ed):
    return bool(ed.SendScintilla(QsciScintilla.SCI_AUTOCACTIVE))


# --- C.6: ortam adı tamamlama ---


def test_env_list_has_common_environments():
    assert "equation" in _LATEX_ENVIRONMENTS
    assert "equation*" in _LATEX_ENVIRONMENTS
    assert "itemize" in _LATEX_ENVIRONMENTS
    assert "document" in _LATEX_ENVIRONMENTS
    assert _LATEX_ENVIRONMENTS == sorted(_LATEX_ENVIRONMENTS)  # bisect için sıralı


def test_env_bisect_finds_equation():
    typed = "equa"
    lo = bisect.bisect_left(_LATEX_ENVIRONMENTS, typed)
    hi = bisect.bisect_left(_LATEX_ENVIRONMENTS, typed[:-1] + chr(ord(typed[-1]) + 1))
    matches = [e for e in _LATEX_ENVIRONMENTS[lo:hi] if e != typed]
    assert "equation" in matches
    assert "equation*" in matches


def test_env_completion_popup_after_begin(qapp):
    r"""`\begin{equa` -> popup açılır."""
    ed = _editor()
    ed.setText("\\begin{equa")
    ed.setCursorPosition(0, len("\\begin{equa"))
    ed._check_autocomplete()
    assert _autoc_active(ed)


def test_env_completion_auto_needs_at_least_one_char(qapp):
    r"""Auto modda `\begin{` (harfsiz) -> popup çıkmaz."""
    ed = _editor()
    ed.setText("\\begin{")
    ed.setCursorPosition(0, len("\\begin{"))
    ed._check_autocomplete()
    assert not _autoc_active(ed)


def test_env_completion_manual_shows_all(qapp):
    r"""Manuel modda `\begin{` (harfsiz) -> tüm ortamlar listelenir."""
    ed = _editor()
    ed.setText("\\begin{")
    ed.setCursorPosition(0, len("\\begin{"))
    ed._check_autocomplete(manual=True)
    assert _autoc_active(ed)


def test_env_completion_selects_equation(qapp):
    r"""`\begin{equa` tamamlama -> `\begin{equation` (ilk eşleşme)."""
    ed = _editor()
    ed.setText("\\begin{equa")
    ed.setCursorPosition(0, len("\\begin{equa"))
    ed._check_autocomplete()
    ed.SendScintilla(QsciScintilla.SCI_AUTOCCOMPLETE)
    qapp.processEvents()
    assert _line(ed, 0) == "\\begin{equation"


def test_env_completion_does_not_trigger_for_command(qapp):
    r"""`\frac` komut bağlamında env tamamlaması çıkmaz (komut tamamlaması çalışır)."""
    ed = _editor()
    ed.setText("\\fra")
    ed.setCursorPosition(0, 4)
    ed._check_autocomplete()
    assert _autoc_active(ed)  # komut tamamlaması


# --- C.7: Ctrl+Space manuel tamamlama ---


def test_auto_completion_requires_min_length(qapp):
    r"""Auto: `\f` (2 karakter) -> popup çıkmaz (eşik \+2 harf)."""
    ed = _editor()
    ed.setText("\\f")
    ed.setCursorPosition(0, 2)
    ed._check_autocomplete()  # auto
    assert not _autoc_active(ed)


def test_manual_completion_short_word(qapp):
    r"""Manuel: `\f` (2 karakter) -> popup çıkar (eşik gevşek)."""
    ed = _editor()
    ed.setText("\\f")
    ed.setCursorPosition(0, 2)
    ed._check_autocomplete(manual=True)
    assert _autoc_active(ed)


def test_ctrl_space_keypress_triggers_manual(qapp):
    r"""Ctrl+Space tuş olayı manuel tamamlamayı tetikler."""
    ed = _editor()
    ed.setText("\\fra")
    ed.setCursorPosition(0, 4)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                   Qt.KeyboardModifier.ControlModifier)
    ed.keyPressEvent(ev)
    assert _autoc_active(ed)


def test_ctrl_space_does_not_type_space(qapp):
    r"""Ctrl+Space boşluk karakteri yazmamalı (olay tüketilir)."""
    ed = _editor()
    ed.setText("\\fra")
    ed.setCursorPosition(0, 4)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                   Qt.KeyboardModifier.ControlModifier)
    ed.keyPressEvent(ev)
    assert _line(ed, 0) == "\\fra"  # boşluk eklenmedi


# --- C.10: dinamik margin genişliği ---


def test_margin_width_formula_small_doc(qapp):
    """Az satırlı belgede minimum 4 hane."""
    ed = _editor()
    ed.setText("\n".join("x" for _ in range(10)))
    assert max(4, len(str(ed.lines()))) == 4


def test_margin_width_formula_large_doc(qapp):
    """12345 satır -> 5 hane."""
    ed = _editor()
    ed.setText("\n".join("x" for _ in range(12345)))
    assert max(4, len(str(ed.lines()))) == 5


def test_update_margin_width_sets_correct_digits(qapp, monkeypatch):
    """_update_margin_width, satır sayısının basamak sayısını setMarginWidth'e verir."""
    ed = _editor()
    captured = {}
    orig = ed.setMarginWidth

    def spy(margin, width):
        captured["width"] = width
        return orig(margin, width)

    monkeypatch.setattr(ed, "setMarginWidth", spy)
    ed.setText("\n".join("x" for _ in range(12345)))
    ed._update_margin_width()
    assert len(captured["width"]) == 5  # 12345 satır -> "00000"


def test_update_margin_width_no_crash_on_empty(qapp):
    ed = _editor()
    ed.setText("")
    ed._update_margin_width()  # boş belgede çalışmalı


# --- C.8: yorum/verbatim içinde tamamlama bastırma ---


def _style_all(ed):
    """Lexer'ı tamamen çalıştır (stil verileri hazır olsun)."""
    ed.lexer().styleText(0, len(ed.text().encode("utf-8")))


def test_no_completion_in_comment(qapp):
    r"""Yorum içinde \fra yazınca popup çıkmaz."""
    ed = _editor()
    ed.setText("% yorum içinde \\fra")
    _style_all(ed)
    ed.setCursorPosition(0, len("% yorum içinde \\fra"))
    ed._check_autocomplete()
    assert not _autoc_active(ed)


def test_no_completion_in_verbatim(qapp):
    r"""verbatim içinde \secti yazınca popup çıkmaz."""
    ed = _editor()
    text = "\\begin{verbatim}\n\\secti\n\\end{verbatim}"
    ed.setText(text)
    _style_all(ed)
    ed.setCursorPosition(1, len("\\secti"))
    ed._check_autocomplete()
    assert not _autoc_active(ed)


def test_manual_suppressed_in_comment(qapp):
    r"""Ctrl+Space (manuel) de yorum içinde bastırılır."""
    ed = _editor()
    ed.setText("% \\fra")
    _style_all(ed)
    ed.setCursorPosition(0, len("% \\fra"))
    ed._check_autocomplete(manual=True)
    assert not _autoc_active(ed)


def test_completion_outside_comment(qapp):
    r"""Yorum dışında (sonraki satır) \fra -> popup çıkar."""
    ed = _editor()
    ed.setText("% comment\n\\fra")
    _style_all(ed)
    ed.setCursorPosition(1, len("\\fra"))
    ed._check_autocomplete()
    assert _autoc_active(ed)


def test_completion_after_verbatim_block(qapp):
    r"""verbatim kapandıktan sonra \fra -> popup çıkar."""
    ed = _editor()
    text = "\\begin{verbatim}\nx\n\\end{verbatim}\n\\fra"
    ed.setText(text)
    _style_all(ed)
    ed.setCursorPosition(3, len("\\fra"))
    ed._check_autocomplete()
    assert _autoc_active(ed)
