"""EditorWidget otomatik tamamlama kapanış testleri (A.2).

Popup'tan seçilen \\cmd{ / \\cmd[ girdisi SCN_AUTOCCOMPLETED ile geldiğinde,
keyPressEvent atlandığı için normal autopair tetiklenmez. _on_autoc_completed
karşılık gelen } / ] ekler; böylece elle yazılan komutla popup'tan seçilen
aynı komut tutarlı olur (ikisi de çiftlenmiş ayraç verir).
"""

import pytest

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


# --- Boşluk filtresi tek kaynakta (2026-08-30 denetimi, F5) ---

def _gosterilen(ed, monkeypatch) -> list[str]:
    """_popup_goster'in Scintilla'ya verdiği aday listesini yakala."""
    yakalanan = []
    orij = ed.SendScintilla

    def sahte(mesaj, *a):
        if mesaj == QsciScintilla.SCI_AUTOCSHOW and a:
            yakalanan.append(a[-1].decode("utf-8").split(" "))
            return 0
        return orij(mesaj, *a)

    monkeypatch.setattr(ed, "SendScintilla", sahte)
    return yakalanan


def test_bosluklu_aday_tum_tamamlamalarda_eleniyor(qapp, monkeypatch):
    r"""Liste ayırıcısı boşluk: adında boşluk geçen aday listeyi bozuyor.

    Filtre eskiden 6 popup çağrısının yalnız 2'sinde vardı; \label{fig: bir}
    gibi bir etiket \ref tamamlamasında listeyi iki sahte öğeye bölüyordu.
    Artık filtre _popup_goster içinde, yani hepsinde.
    """
    ed = _editor()
    ed.setText("\\label{fig:temiz}\n\\label{fig: bosluklu}\n")
    yakalanan = _gosterilen(ed, monkeypatch)

    ed._show_ref_completion("fig:")
    assert yakalanan, "popup hiç gösterilmedi"
    adaylar = yakalanan[0]
    assert "fig:temiz" in adaylar
    assert not any(" " in a for a in adaylar)
    assert not any("bosluklu" in a for a in adaylar), adaylar


def test_bosluklu_adaylarin_hepsi_elenince_popup_acilmiyor(qapp, monkeypatch):
    """Filtre sonrası liste boşalırsa popup hiç gösterilmemeli."""
    ed = _editor()
    yakalanan = _gosterilen(ed, monkeypatch)
    ed._popup_goster(["bir tane", "iki tane"], "b")
    assert yakalanan == [], "boş listeyle popup açıldı"


def test_tek_popup_cagri_yeri_kaldi():
    """6 kopya tek yardımcıya indi; yenisi eklenirse filtre yine atlanmasın."""
    import io
    import os
    yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "desktop", "gui", "editor.py")
    kaynak = io.open(yol, encoding="utf-8").read()
    assert kaynak.count("SCI_AUTOCSHOW") == 1, (
        "editor.py'de birden fazla SCI_AUTOCSHOW çağrısı var — "
        "popup gösterimi _popup_goster üzerinden yapılmalı (boşluk filtresi orada)")
