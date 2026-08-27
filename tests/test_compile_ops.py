"""CompileOpsMixin — derleme meşgul guard testleri.

Regression: sürmekte olan derleme varken Ctrl+S/Ctrl+B, compile() çağrısından
ÖNCE yazılan durumları (hedef yolu, panel temizliği, imleç bağlamı) eski
derlemenin sonucunu zehirliyordu; compile() False döner ama atamalar çoktan
yapılmış olurdu. Guard bunları atamalardan önce kesmeli.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.mixins.compile_ops import CompileOpsMixin
    from gui.mixins.tab_ops import TabOpsMixin
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeCompiler:
    def __init__(self, busy):
        self._busy = busy
        self.calls = []

    def is_busy(self):
        return self._busy

    def compile(self, path, engine):
        self.calls.append((path, engine))
        return True


class _Stub(CompileOpsMixin, TabOpsMixin, StubMain):
    def __init__(self, editors, busy=False):
        StubMain.__init__(self, editors=editors)
        self._compiler = _FakeCompiler(busy)


def _tex(tmp_path):
    p = tmp_path / "ana.tex"
    p.write_text("\\begin{document}\nmerhaba\n\\end{document}\n", encoding="utf-8")
    return str(p)


def _dirty_editor(tex):
    ed = EditorWidget()
    assert ed.open_file(tex)
    return ed


def test_compile_busy_iken_durum_dokunulmaz(qapp, tmp_path, monkeypatch):
    tex = _tex(tmp_path)
    ed = _dirty_editor(tex)
    stub = _Stub([ed], busy=True)
    stub._compile_target = "eski/hedef.tex"
    stub._compile_cursor_ctx = ("eski.tex", 3, 1)
    cleared = []
    monkeypatch.setattr(stub._output_panel, "clear", lambda: cleared.append(1))

    stub._compile()

    assert stub._compiler.calls == []                  # yeni derleme başlamadı
    assert stub._compile_target == "eski/hedef.tex"    # bayat hedef ezilmedi
    assert stub._compile_cursor_ctx == ("eski.tex", 3, 1)
    assert cleared == []                               # süren derlemenin çıktısı duruyor
    assert "sürüyor" in stub._status.msg


def test_compile_bos_iken_normal_akis(qapp, tmp_path):
    tex = _tex(tmp_path)
    ed = _dirty_editor(tex)
    stub = _Stub([ed], busy=False)

    stub._compile()

    assert stub._compiler.calls == [(tex, "lualatex")]
    assert stub._compile_target == tex
    assert stub._compile_cursor_ctx is not None
    assert "sürüyor" not in stub._status.msg


def test_compile_file_busy_iken_derlemez(qapp, tmp_path):
    tex = _tex(tmp_path)
    stub = _Stub([], busy=True)
    stub._compile_target = "eski/hedef.tex"

    stub._compile_file(tex)

    assert stub._compiler.calls == []
    assert stub._compile_target == "eski/hedef.tex"
    assert "sürüyor" in stub._status.msg
