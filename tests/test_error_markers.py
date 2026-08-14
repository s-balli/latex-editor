"""Derleme hatalarının gutter'da işaretlenmesi + F4/Shift+F4 dolaşma testleri.

İki katman:
- gui.editor.EditorWidget: clear_error_markers / add_error_marker (Scintilla marker)
- gui.mixins.compile_ops.CompileOpsMixin: _goto_error index cycling mantığı
"""

from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.mixins.compile_ops import CompileOpsMixin
    from core.log_parser import LatexError
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / core / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


_ERR_BIT = 1 << 10  # EditorWidget._ERR_MARKER = 10


def _markers(editor, line_0based: int) -> int:
    return editor.SendScintilla(EditorWidget.SCI_MARKERGET, line_0based)


# =====================================================================
# EditorWidget — gutter marker add/clear
# =====================================================================


def test_add_error_marker_marks_line(qapp):
    ed = EditorWidget()
    ed.setText("a\nb\nc\nd\ne\n")
    ed.add_error_marker(3)  # 1-based satır 3
    assert _markers(ed, 2) & _ERR_BIT, "hata satırı işaretli olmalı"
    assert _markers(ed, 0) & _ERR_BIT == 0, "diğer satırlar boş olmalı"
    assert _markers(ed, 4) & _ERR_BIT == 0


def test_add_error_marker_out_of_range_ignored(qapp):
    ed = EditorWidget()
    ed.setText("a\nb\n")
    ed.add_error_marker(99)  # aralık dışı — sessizce atlanmalı
    for ln in range(ed.lines()):
        assert _markers(ed, ln) & _ERR_BIT == 0


def test_clear_error_markers(qapp):
    ed = EditorWidget()
    ed.setText("a\nb\nc\n")
    ed.add_error_marker(1)
    ed.add_error_marker(3)
    assert _markers(ed, 0) & _ERR_BIT
    assert _markers(ed, 2) & _ERR_BIT
    ed.clear_error_markers()
    for ln in range(ed.lines()):
        assert _markers(ed, ln) & _ERR_BIT == 0


def test_clear_error_markers_when_empty(qapp):
    ed = EditorWidget()
    ed.setText("a\n")  # hiç işaret yokken clear güvenli olmalı
    ed.clear_error_markers()


# =====================================================================
# CompileOpsMixin — F4/Shift+F4 index cycling
# =====================================================================


class _StubMain(CompileOpsMixin):
    """MainWindow yerine: _goto_error'nin ihtiyaç duyduğu minimum arayüz.

    _refresh_error_markers gerçek mixin metodu; _current_editor None döndüğünden
    erken döner (marker yan etkisi olmadan yalnızca index mantığı test edilir).
    """
    def __init__(self, errors):
        self._last_errors = errors
        self._err_index = -1
        self._status = SimpleNamespace(showMessage=self._set_msg)
        self._goto_calls = []
        self.msg = ""

    def _set_msg(self, m):
        self.msg = m

    def _goto_line(self, path, line):
        self._goto_calls.append((path, line))

    def _current_editor(self):
        return None


def _errs(tmp_path, lines):
    out = []
    for i, ln in enumerate(lines):
        f = tmp_path / f"b{i}.tex"
        f.write_text("x\n" * max(ln, 1))
        out.append(LatexError(line_number=ln, message=f"err{i}", file_path=str(f)))
    return out


def test_next_cycles_forward_and_wraps(tmp_path, qapp):
    errs = _errs(tmp_path, [5, 7, 9])
    s = _StubMain(errs)
    s._goto_next_error()
    s._goto_next_error()
    s._goto_next_error()
    s._goto_next_error()  # wrap → ilk hataya
    assert [c[1] for c in s._goto_calls] == [5, 7, 9, 5]
    assert s._err_index == 0


def test_prev_from_start_goes_to_last(tmp_path, qapp):
    errs = _errs(tmp_path, [5, 7, 9])
    s = _StubMain(errs)
    s._goto_prev_error()
    assert s._err_index == 2
    assert s._goto_calls[-1][1] == 9


def test_empty_errors_shows_message(tmp_path, qapp):
    s = _StubMain([])
    s._goto_next_error()
    assert s._goto_calls == []
    assert "Hata yok" in s.msg


def test_unresolvable_path_shows_not_found(tmp_path, qapp):
    errs = [LatexError(line_number=3, message="x", file_path=str(tmp_path / "yok.tex"))]
    s = _StubMain(errs)
    s._goto_next_error()
    assert s._goto_calls == []
    assert "konumu bulunamadı" in s.msg
