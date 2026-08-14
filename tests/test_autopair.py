"""EditorWidget otomatik parantezleme + \\begin/\\end kapanışı testleri.

Açma karakterine ((, [, {, $) kapanışı otomatik ekler; \\begin{ad}'e \\end{ad}
kapanışı yerleştirir. Kapanış karakteri imleç sağındakiyle aynıysa üzerine yazıp
çiftlemek yerine atlar (skip-over).
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui.editor import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeEvent:
    """QKeyEvent.text() taklidi — _handle_autopair event.text() kullanır."""
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


def _editor():
    return EditorWidget()


def _cursor_end(ed):
    """İmleci (tek satır) satır sonuna koy."""
    ed.setCursorPosition(0, len(ed.text(0)))


def _line(ed, n):
    """text(n) son satır değilse trailing newline içerir — temizle."""
    return ed.text(n).rstrip("\n")


# --- Auto-pair: açma → çift, imleç arada ---


def test_pair_paren(qapp):
    ed = _editor()
    ed.setText("ab")
    _cursor_end(ed)
    assert ed._handle_autopair(_FakeEvent("(")) is True
    assert ed.text(0) == "ab()"
    assert ed.getCursorPosition() == (0, 3)  # ( ve ) arası


def test_pair_bracket(qapp):
    ed = _editor()
    ed.setText("x")
    _cursor_end(ed)
    assert ed._handle_autopair(_FakeEvent("["))
    assert ed.text(0) == "x[]"
    assert ed.getCursorPosition() == (0, 2)


def test_pair_brace(qapp):
    ed = _editor()
    ed.setText("a")
    _cursor_end(ed)
    ed._handle_autopair(_FakeEvent("{"))
    assert ed.text(0) == "a{}"
    assert ed.getCursorPosition() == (0, 2)


def test_pair_dollar(qapp):
    ed = _editor()
    ed.setText("a")
    _cursor_end(ed)
    ed._handle_autopair(_FakeEvent("$"))
    assert ed.text(0) == "a$$"
    assert ed.getCursorPosition() == (0, 2)


# --- Skip-over: kapanış imleç sağındaysa atla ---


def test_skip_over_paren(qapp):
    ed = _editor()
    ed.setText("ab()")
    ed.setCursorPosition(0, 3)  # imleç ')' önünde
    assert ed._handle_autopair(_FakeEvent(")")) is True
    assert ed.text(0) == "ab()"            # metin değişmedi
    assert ed.getCursorPosition() == (0, 4)  # ')' sonrasına atladı


def test_skip_over_dollar(qapp):
    # "$x$" senaryosu: x$$, imleç 2. $ önünde → $ yaz → atla
    ed = _editor()
    ed.setText("x$$")
    ed.setCursorPosition(0, 2)
    ed._handle_autopair(_FakeEvent("$"))
    assert ed.text(0) == "x$$"
    assert ed.getCursorPosition() == (0, 3)


# --- \begin / \end kapanışı ---


def test_brace_not_paired_after_begin(qapp):
    r"""\\begin sonrası '{' çiftlenmez — \\end tetikleyicisine izin ver."""
    ed = _editor()
    ed.setText("\\begin")
    _cursor_end(ed)
    assert ed._handle_autopair(_FakeEvent("{")) is False


def test_brace_not_paired_after_end(qapp):
    r"""\\end sonrası da '{' çiftlenmez (simetri)."""
    ed = _editor()
    ed.setText("\\end")
    _cursor_end(ed)
    assert ed._handle_autopair(_FakeEvent("{")) is False


def test_begin_end_close(qapp):
    r"""\\begin{ad} + '}' → \\end{ad} bloğu; gövde girintili, imleç gövdede (C.9)."""
    ed = _editor()
    ed.setText("\\begin{equation")
    _cursor_end(ed)
    assert ed._handle_autopair(_FakeEvent("}")) is True
    assert _line(ed, 0) == "\\begin{equation}"
    # C.9: gövde satırı girintili (yalnızca girinti boşluğu içerir)
    assert _line(ed, 1).strip() == "" and _line(ed, 1) != ""
    assert _line(ed, 2) == "\\end{equation}"
    line, idx = ed.getCursorPosition()
    assert line == 1                        # imleç gövde satırında
    assert idx == len(_line(ed, 1))         # girinti sonunda (tab/space bağımsız)


def test_begin_end_starred(qapp):
    """Yıldızlı ortam (equation*) da kapanmalı."""
    ed = _editor()
    ed.setText("\\begin{equation*")
    _cursor_end(ed)
    ed._handle_autopair(_FakeEvent("}"))
    assert _line(ed, 0) == "\\begin{equation*}"
    assert _line(ed, 2) == "\\end{equation*}"


def test_normal_brace_no_begin_trigger(qapp):
    r"""\\begin bağlamı dışında '}' normal eklenir (\\end tetiklenmez)."""
    ed = _editor()
    ed.setText("\\frac{a")
    _cursor_end(ed)
    assert ed._handle_autopair(_FakeEvent("}")) is False


# --- Seçim varken çiftleme yok ---


def test_no_pair_with_selection(qapp):
    ed = _editor()
    ed.setText("foo")
    ed.selectAll()
    assert ed._handle_autopair(_FakeEvent("(")) is False
