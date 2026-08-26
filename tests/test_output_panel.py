"""OutputPanel — bağlamsal Ortam Denetimi satırı testleri.

Kurulum komutu taşıyan öneriler (eksik paket, motor, WSL, Pygments) Öneriler
sekmesinde doktor satırı getirmeli; motor değiştirme önerisi getirmemeli.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)

from core.log_parser import CompileResult, LatexError, LatexSuggestion


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _panel():
    return OutputPanel(theme=THEMES["dark"])


def _suggest_texts(panel) -> list[str]:
    return [panel._suggest_list.item(i).text()
            for i in range(panel._suggest_list.count())]


def test_kurulum_onerisi_doktor_satiri_getirir(qapp):
    panel = _panel()
    result = CompileResult(success=False)
    result.errors = [LatexError(message="! LaTeX Error: File `minted.sty' not found.")]
    result.suggestions = [LatexSuggestion(
        message="Eksik paket: texlive-latex-extra (minted.sty)",
        install_command="sudo apt-get install texlive-latex-extra")]

    fired = []
    panel.env_check_requested.connect(lambda: fired.append(1))
    panel.show_result(result)

    texts = _suggest_texts(panel)
    assert any("Ortam Denetimi" in t for t in texts)
    # Tıklamayı simüle et: son satır doktor satırı, sinyal fimşe vermeli
    last = panel._suggest_list.item(panel._suggest_list.count() - 1)
    assert "Ortam Denetimi" in last.text()
    panel._on_result_click(last)
    assert fired == [1]


def test_motor_degistirme_onerisi_doktor_satiri_getirmez(qapp):
    """'Bu belge xelatex gerektiriyor' bir ortam sorunu değil."""
    panel = _panel()
    result = CompileResult(success=False)
    result.errors = [LatexError(message="requires XeLaTeX")]
    result.suggestions = [LatexSuggestion(
        message="Bu belge xelatex gerektiriyor. Derleme motorunu değiştirin.")]

    panel.show_result(result)
    assert not any("Ortam Denetimi" in t for t in _suggest_texts(panel))


def test_onerisiz_sonuc_doktor_satiri_getirmez(qapp):
    panel = _panel()
    result = CompileResult(success=True)
    panel.show_result(result)
    assert _suggest_texts(panel) == []
