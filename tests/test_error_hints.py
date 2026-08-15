"""error_hints + OutputPanel ipucu sunumu testleri."""

import pytest

from core.error_hints import get_hint


# =====================================================================
# Kalıp tanıma (gerçek derleyici çıktısı alıntıları)
# =====================================================================


def test_undefined_control_with_context():
    h = get_hint("Undefined control sequence.", "l.42 \\textbf{x} kalan")
    assert h is not None
    assert h[0] == "undefined_control"
    assert h[1] == {"cmd": "\\textbf"}


def test_undefined_control_without_context():
    assert get_hint("Undefined control sequence.") == ("undefined_control", {})


def test_missing_math():
    assert get_hint("Missing $ inserted.")[0] == "missing_math"
    assert get_hint("LaTeX Error: Display math should end with $$")[0] == "missing_math"


def test_invalid_character():
    assert get_hint("Text line contains an invalid character.")[0] == "invalid_character"


def test_brace_mismatch_variants():
    for msg in ("Missing } inserted", "Too many }'s", "Extra }, or forgotten \\end"):
        assert get_hint(msg)[0] == "brace_mismatch", msg


def test_double_subscript():
    assert get_hint("Double subscript.")[0] == "double_subscript"
    assert get_hint("Double superscript.")[0] == "double_subscript"


def test_env_undefined():
    h = get_hint("LaTeX Error: Environment tikzpicture undefined.")
    assert h == ("env_undefined", {"env": "tikzpicture"})


def test_file_ended_scanning():
    assert get_hint("File ended while scanning use of \\label.")[0] == "file_ended_scanning"


def test_emergency_stop():
    assert get_hint("Emergency stop.")[0] == "emergency_stop"


def test_counter_too_large():
    assert get_hint("LaTeX Error: Counter too large.")[0] == "counter_too_large"


def test_misplaced_noalign():
    assert get_hint("Misplaced \\noalign.")[0] == "misplaced_noalign"
    assert get_hint("Misplaced \\omit.")[0] == "misplaced_noalign"


def test_citation_undefined():
    h = get_hint("Citation `balli2020' undefined on input line 55.")
    assert h[0] == "citation_undefined"


def test_reference_undefined():
    assert get_hint("Reference `fig:sonuc' on page 3 undefined")[0] == "reference_undefined"


def test_rerun_needed():
    assert get_hint("There were undefined references.")[0] == "rerun_needed"
    assert get_hint("Label(s) may have changed. Rerun to get cross-references right.")[0] == "rerun_needed"


def test_duplicate_label():
    h = get_hint("pdfTeX warning (ext4): destination with the same identifier "
                 "(name{fig:sonuc}) has been already used, duplicate ignored")
    assert h[0] == "duplicate_label"


def test_unknown_returns_none():
    assert get_hint("LaTeX Error: File `foo.sty' not found.") is None
    assert get_hint("[babel] something odd") is None
    assert get_hint("") is None


# =====================================================================
# OutputPanel sunumu
# =====================================================================


try:
    from PyQt6.QtWidgets import QApplication
    from gui.output_panel import OutputPanel
    from core.log_parser import LatexError, LatexWarning
    from gui.theme import THEMES
    from tests.stub_main import StubMain  # noqa: F401 — dönüşümlü qapp fixture
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_panel_error_shows_hint(qapp):
    panel = OutputPanel(theme=THEMES["dark"])
    from core.log_parser import CompileResult

    result = CompileResult(success=False)
    result.errors = [LatexError(
        line_number=42, message="Undefined control sequence.",
        context="l.42 \\badcmd{x}", file_path="m.tex")]
    panel.show_result(result)

    item = panel._error_list.item(0)
    text = item.text()
    assert "→" in text
    assert "\\badcmd" in text
    assert "\\usepackage" in text
    assert item.toolTip()


def test_panel_warning_shows_rerun_hint(qapp):
    panel = OutputPanel(theme=THEMES["dark"])
    from core.log_parser import CompileResult

    result = CompileResult(success=False)
    result.warnings = [LatexWarning(
        line_number=55, message="Citation `x' undefined on input line 55.",
        warning_type="LaTeX")]
    panel.show_result(result)

    text = panel._warn_list.item(0).text()
    assert "→" in text
    assert "tekrar derleyin" in text


def test_panel_unknown_error_no_hint(qapp):
    panel = OutputPanel(theme=THEMES["dark"])
    from core.log_parser import CompileResult

    result = CompileResult(success=False)
    result.errors = [LatexError(line_number=3, message="[babel] bilinmeyen hata")]
    panel.show_result(result)

    assert "→" not in panel._error_list.item(0).text()
