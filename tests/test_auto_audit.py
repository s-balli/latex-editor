"""Derleme sonrası otomatik referans denetimi — anahtar, panel ekleme, koruma."""

from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.main_window import MainWindow
    from gui.mixins.compile_ops import CompileOpsMixin
    from gui.mixins.edit_ops import EditOpsMixin
    from core.log_parser import CompileResult, LatexError
    from tests.stub_main import StubMain, FakeSettings
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _StubMain(CompileOpsMixin, EditOpsMixin, StubMain):
    """MainWindow yerine: _maybe_auto_audit ve _toggle_auto_audit arayüzü."""

    def __init__(self, settings=None, target=""):
        super().__init__(settings=settings, target=target)


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
    s = FakeSettings()
    s.d["compile/auto_audit"] = True
    stub = _StubMain(settings=s, target=str(tex))
    MainWindow._maybe_auto_audit(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 1
    assert "fig:yok" in panel._warn_list.item(0).text()


def test_append_preserves_compile_result(qapp, tmp_path):
    """Derleme hataları dururken denetim bulguları ÜSTÜNE eklenir, silinmez."""
    tex = _broken_doc(tmp_path)
    s = FakeSettings()
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
    s = FakeSettings()
    s.d["compile/auto_audit"] = "true"             # QSettings string'i
    assert MainWindow._auto_audit_enabled(s) is True
    assert MainWindow._auto_audit_enabled(FakeSettings()) is False


def test_toggle_persists(qapp):
    stub = _StubMain()
    MainWindow._toggle_auto_audit(stub, True)
    assert stub._settings.d["compile/auto_audit"] is True
    assert "aç" in stub._status.msg
    MainWindow._toggle_auto_audit(stub, False)
    assert stub._settings.d["compile/auto_audit"] is False


def test_missing_target_noop(qapp):
    s = FakeSettings()
    s.d["compile/auto_audit"] = True
    stub = _StubMain(settings=s, target="/yok/bulunmayan.tex")
    MainWindow._maybe_auto_audit(stub)             # hata vermez, sessiz geçer
    assert stub._output_panel._warn_list.count() == 0


# --- durum çubuğu özeti ---


def test_summary_appended_to_compile_message(qapp, tmp_path):
    """Derleme mesajı korunur, özet sonuna ' · ' ile eklenir."""
    tex = _broken_doc(tmp_path)
    s = FakeSettings()
    s.d["compile/auto_audit"] = True
    stub = _StubMain(settings=s, target=str(tex))
    stub._status.msg = "Başarılı (1.2s) | 3 uyari"
    MainWindow._maybe_auto_audit(stub)
    assert stub._status.msg.startswith("Başarılı (1.2s) | 3 uyari  ·  ")
    assert "Denetim:" in stub._status.msg
    assert "1 tanımsız ref" in stub._status.msg


def test_summary_skips_zero_categories(qapp, tmp_path):
    """Yalnız kullanılmayan label varsa özet onu içerir, sıfırları yazmaz."""
    tex = tmp_path / "m.tex"
    tex.write_text("\\label{bos}\n", encoding="utf-8")
    s = FakeSettings()
    s.d["compile/auto_audit"] = True
    stub = _StubMain(settings=s, target=str(tex))
    MainWindow._maybe_auto_audit(stub)
    msg = stub._status.msg
    assert "kullanılmayan label" in msg
    assert "tanımsız ref" not in msg and "tanımsız cite" not in msg


def test_summary_without_current_message(qapp, tmp_path):
    """currentMessage'i olmayan durum çubuğunda özet tek başına yazılır."""
    tex = _broken_doc(tmp_path)
    s = FakeSettings()
    s.d["compile/auto_audit"] = True
    stub = _StubMain(settings=s, target=str(tex))
    msgs = []
    stub._status = SimpleNamespace(showMessage=msgs.append)   # currentMessage yok
    MainWindow._maybe_auto_audit(stub)                        # hata vermemeli
    assert any(m.startswith("Denetim:") for m in msgs)


# --- entegrasyon: derleme bitişi otomatik denetimi tetikler ---


class _Viewer:
    """PDF viewer yerine: clear/load_pdf yeterli."""

    def clear(self):
        pass

    def load_pdf(self, path):
        return True


def test_compile_finish_runs_auto_audit(qapp, tmp_path):
    """_on_compile_finished → panelde derleme sonucu DURURKEN denetim bulgusu eklenir."""
    tex = _broken_doc(tmp_path)
    s = FakeSettings()
    s.d["compile/auto_audit"] = True
    stub = _StubMain(settings=s, target=str(tex))
    stub._pdf_viewer = _Viewer()

    from core.log_parser import CompileResult
    MainWindow._on_compile_finished(stub, CompileResult(success=False))

    panel = stub._output_panel
    assert panel._error_list.count() == 0        # hata yok (errors boş)
    assert panel._warn_list.count() == 1         # denetim bulgusu geldi
    assert "fig:yok" in panel._warn_list.item(0).text()
    assert "Denetim:" in stub._status.msg
