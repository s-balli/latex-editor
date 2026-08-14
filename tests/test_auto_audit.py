"""Derleme sonrası otomatik referans denetimi — anahtar, panel ekleme, koruma."""

from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.main_window import MainWindow
    from gui.mixins.compile_ops import CompileOpsMixin
    from gui.mixins.edit_ops import EditOpsMixin
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
    from core.log_parser import CompileResult, LatexError
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeSettings:
    def __init__(self):
        self.d = {}

    def value(self, key, default=None):
        return self.d.get(key, default)

    def setValue(self, key, val):
        self.d[key] = val


class _StubMain(CompileOpsMixin, EditOpsMixin):
    def __init__(self, settings=None, target=""):
        self._settings = settings or _FakeSettings()
        self._compile_target = target
        self._output_panel = OutputPanel(theme=THEMES["dark"])
        self.messages = []
        self._status = SimpleNamespace(showMessage=self.messages.append)


def _broken_doc(tmp_path):
    tex = tmp_path / "m.tex"
    tex.write_text("\\ref{fig:yok}\n", encoding="utf-8")
    return tex


def test_disabled_noop(qapp, tmp_path):
    tex = _broken_doc(tmp_path)
    stub = _StubMain(target=str(tex))          # anahtar kapalı (varsayılan)
    MainWindow._maybe_auto_audit(stub)
    assert stub._output_panel._warn_list.count() == 0


def test_enabled_appends_findings(qapp, tmp_path):
    tex = _broken_doc(tmp_path)
    s = _FakeSettings()
    s.d["compile/auto_audit"] = True
    stub = _StubMain(settings=s, target=str(tex))
    MainWindow._maybe_auto_audit(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 1
    assert "fig:yok" in panel._warn_list.item(0).text()


def test_append_preserves_compile_result(qapp, tmp_path):
    """Derleme hataları dururken denetim bulguları ÜSTÜNE eklenir, silinmez."""
    tex = _broken_doc(tmp_path)
    s = _FakeSettings()
    s.d["compile/auto_audit"] = True
    stub = _StubMain(settings=s, target=str(tex))
    result = CompileResult(success=False)
    result.errors = [LatexError(line_number=3, message="Undefined control sequence")]
    stub._output_panel.show_result(result)

    MainWindow._maybe_auto_audit(stub)
    panel = stub._output_panel
    assert panel._error_list.count() == 1          # derleme hatası duruyor
    assert panel._warn_list.count() == 1           # denetim bulgusu eklendi
    assert "Uyarılar (1)" in panel._tabs.tabText(panel._warn_tab_index)


def test_enabled_string_true_from_qsettings(qapp):
    s = _FakeSettings()
    s.d["compile/auto_audit"] = "true"             # QSettings string'i
    assert MainWindow._auto_audit_enabled(s) is True
    assert MainWindow._auto_audit_enabled(_FakeSettings()) is False


def test_toggle_persists(qapp):
    stub = _StubMain()
    MainWindow._toggle_auto_audit(stub, True)
    assert stub._settings.d["compile/auto_audit"] is True
    assert any("aç" in m for m in stub.messages)
    MainWindow._toggle_auto_audit(stub, False)
    assert stub._settings.d["compile/auto_audit"] is False


def test_missing_target_noop(qapp):
    s = _FakeSettings()
    s.d["compile/auto_audit"] = True
    stub = _StubMain(settings=s, target="/yok/bulunmayan.tex")
    MainWindow._maybe_auto_audit(stub)             # hata vermez, sessiz geçer
    assert stub._output_panel._warn_list.count() == 0
