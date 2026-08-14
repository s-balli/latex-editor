"""EditorWidget akıllı girintileme testleri (C.9).

C.9a: \\begin{X} → \\end{X} bloğunda gövde +1 seviye, \\end \\begin hizasında.
C.9b: Enter'da önceki satır \\begin{X} ile bitiyorsa yeni satır +1 girintilenir.
"""

import pytest

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    from PyQt6.Qsci import QsciScintilla
    from gui.editor import EditorWidget
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui.editor import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp):
    pass


def _editor():
    return EditorWidget()


def _indent(ed, line):
    return ed.SendScintilla(QsciScintilla.SCI_GETLINEINDENTATION, line)


def _line(ed, n):
    return ed.text(n).rstrip("\n")


# --- C.9a: _insert_begin_end hizalama ---


def test_insert_begin_end_toplevel_indent(qapp):
    r"""Üst seviye \begin{X} (indent 0): gövde +4, \end 0."""
    ed = _editor()
    ed.setText("\\begin{equation")
    ed.setCursorPosition(0, len("\\begin{equation"))
    ed._insert_begin_end("equation")
    assert _line(ed, 0) == "\\begin{equation}"
    assert _indent(ed, 1) == 4              # gövde +1 seviye
    assert _indent(ed, 2) == 0              # \end, \begin ile aynı
    assert _line(ed, 2) == "\\end{equation}"


def test_insert_begin_end_nested_indent(qapp):
    r"""İç içe: \begin indent 4 -> gövde 8, \end 4."""
    ed = _editor()
    ed.setText("    \\begin{equation")      # 4 boşluk girintili
    ed.setCursorPosition(0, len("    \\begin{equation"))
    ed._insert_begin_end("equation")
    assert _indent(ed, 1) == 8              # gövde = 4 + 4
    assert _indent(ed, 2) == 4              # \end = begin girintisi


def test_insert_begin_end_cursor_on_body(qapp):
    """İmleç gövde satırında, girintinin sonunda (tab/space bağımsız)."""
    ed = _editor()
    ed.setText("\\begin{a")
    ed.setCursorPosition(0, len("\\begin{a"))
    ed._insert_begin_end("a")
    line, idx = ed.getCursorPosition()
    assert line == 1                        # gövde satırı
    assert idx == len(_line(ed, 1))         # girinti (tab/space) sonunda


def test_insert_begin_end_starred(qapp):
    r"""Yıldızlı ortam: \begin indent 2 -> gövde 6, \end 2."""
    ed = _editor()
    ed.setText("  \\begin{equation*")
    ed.setCursorPosition(0, len("  \\begin{equation*"))
    ed._insert_begin_end("equation*")
    assert _line(ed, 2) == "  \\end{equation*}"   # \begin ile aynı hizada
    assert _indent(ed, 1) == 6              # 2 + 4
    assert _indent(ed, 2) == 2              # \begin girintisi


# --- C.9b: Enter'da akıllı girinti ---


def test_smart_indent_after_begin_toplevel(qapp):
    """Önceki satır \begin{X} -> yeni satır +4 girinti."""
    ed = _editor()
    ed.setText("\\begin{itemize}\n")        # satır 0: begin, satır 1: boş
    ed.setCursorPosition(1, 0)
    ed._smart_indent_after_enter()
    assert _indent(ed, 1) == 4


def test_smart_indent_after_nested_begin(qapp):
    """İç içe: begin indent 4 -> yeni satır 8."""
    ed = _editor()
    ed.setText("    \\begin{itemize}\n")
    ed.setCursorPosition(1, 0)
    ed._smart_indent_after_enter()
    assert _indent(ed, 1) == 8


def test_smart_indent_no_fire_on_content_line(qapp):
    """Önceki satır içerik (begin değil) -> ek girinti yok."""
    ed = _editor()
    ed.setText("\\item some content\n")
    ed.setCursorPosition(1, 0)
    ed._smart_indent_after_enter()
    assert _indent(ed, 1) == 0              # değişmedi


def test_smart_indent_no_fire_on_begin_with_content(qapp):
    """Aynı satırda begin + içerik varsa tetiklemez (bare begin değil)."""
    ed = _editor()
    ed.setText("\\begin{itemize} text after\n")
    ed.setCursorPosition(1, 0)
    ed._smart_indent_after_enter()
    assert _indent(ed, 1) == 0


def test_smart_indent_line0_safe(qapp):
    """İlk satırda (line 0) çökmemeli."""
    ed = _editor()
    ed.setText("")
    ed.setCursorPosition(0, 0)
    ed._smart_indent_after_enter()          # early return


def test_smart_indent_cursor_at_indent_end(qapp):
    """Smart indent sonrası imleç girintinin sonunda (tab/space bağımsız)."""
    ed = _editor()
    ed.setText("\\begin{itemize}\n")
    ed.setCursorPosition(1, 0)
    ed._smart_indent_after_enter()
    line, idx = ed.getCursorPosition()
    assert line == 1
    assert idx == len(_line(ed, 1))         # girinti sonunda


# --- Entegrasyon: gerçek Enter tuşu ---


def test_enter_keypress_indents_after_begin(qapp):
    """Return tuşu begin satırı sonrasında yeni satırı girintiler."""
    ed = _editor()
    ed.setText("\\begin{itemize}")
    ed.setCursorPosition(0, len("\\begin{itemize}"))
    ret = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    ed.keyPressEvent(ret)
    assert ed.lines() >= 2                  # yeni satır oluştu
    assert _indent(ed, 1) == 4              # smart indent uygulandı
