"""EditorWidget otomatik parantezleme + \\begin/\\end kapanışı testleri.

Açma karakterine ((, [, {, $) kapanışı otomatik ekler; \\begin{ad}'e \\end{ad}
kapanışı yerleştirir. Kapanış karakteri imleç sağındakiyle aynıysa üzerine yazıp
çiftlemek yerine atlar (skip-over).
"""

import pytest

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from core.fs_ops import lf_ye_indir
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


# --- Gerçek tuş olaylarıyla: kullanıcının yazdığı metin oluşuyor mu ---


@pytest.mark.parametrize("yazilan, beklenen", [
    ("Fiyat \\$5 oldu.", "Fiyat \\$5 oldu."),
    ("$a\\$", "$a\\$$"),          # matematikte düz $: kapanış yutulmuyor
    ("a\\\\$", "a\\\\$$"),        # `\\` satır sonu, ardından matematik çiftlenir
], ids=["kacis", "matematik_ici", "cift_ters_bolu"])
def test_KACISLI_dolar_ne_acilis_ne_kapanis(qapp, yazilan, beklenen):
    r"""`\$` düz dolar işareti: çiftlenmiyor, kapanış yerine de geçmiyor.

    ÖLÇÜLDÜ (2026-09-25, gerçek pdflatex): yazılan `Fiyat \$5 oldu.`
    derleniyor, editörde oluşan `Fiyat \$5 oldu.$` "Missing $ inserted"
    veriyordu.
    """
    ed = _editor()
    QTest.keyClicks(ed, yazilan)
    assert ed.text() == beklenen


def test_YORUMDA_begin_kapanisi_end_EKLEMIYOR(qapp):
    r"""Yorumda `\begin{ad}` + `}`: yalnız `}` yazılıyor.

    Eklenen `\end{ad}` yorumun DIŞINA düşüyordu. ÖLÇÜLDÜ (2026-09-25,
    gerçek pdflatex): "\begin{document} ended by \end{itemize}".
    """
    ed = _editor()
    ed.setText("% not: \\begin{itemize")
    ed.lexer().styleText(0, len(ed.text().encode("utf-8")))
    _cursor_end(ed)
    QTest.keyClicks(ed, "}")
    assert ed.text() == "% not: \\begin{itemize}"


@pytest.mark.parametrize("metin, imlec, yazilan, beklenen", [
    ("a ", 2, "(", "a "),
    ("a ", 2, "[", "a "),
    ("a ", 2, "{", "a "),
    ("a ", 2, "$", "a "),
    ("x \\$$y", 4, "", "x \\$y"),     # `\$` düz karakter: arkasındaki $ çift değil
], ids=["parantez", "koseli", "suslu", "dolar", "kacisli_dolar"])
def test_ACILIS_yazilip_Backspace_ile_silinince_KAPANIS_da_gidiyor(qapp, metin, imlec, yazilan, beklenen):
    r"""Açılış yazılıp hemen silinince kapanış kalıyordu. ÖLÇÜLDÜ (2026-09-25,
    gerçek pdflatex): `$` yazıp silmek tek `$` bırakıyor, "Missing $ inserted"."""
    ed = _editor()
    ed.setText(metin)
    ed.setCursorPosition(0, imlec)
    if yazilan:
        QTest.keyClicks(ed, yazilan)
    QTest.keyClick(ed, Qt.Key.Key_Backspace)
    assert ed.text() == beklenen


@pytest.mark.parametrize("metin, satir, sutun, yeni, beklenen", [
    # Ortamın adı `}` dahil silinip AYNI adla yeniden yazılıyor: ikinci \end yok
    ("\\begin{document}\n\\begin{itemize\n\\item a\n\\end{itemize}\n\\end{document}",
     1, len("\\begin{itemize"), "}",
     ["\\begin{document}", "\\begin{itemize}", "\\item a", "\\end{itemize}",
      "\\end{document}"]),
    # Karşı kol: belgenin İÇİNDE yeni ortam, \end hâlâ ekleniyor
    ("\\begin{document}\n\\begin{center\n\\end{document}",
     1, len("\\begin{center"), "}",
     ["\\begin{document}", "\\begin{center}", "\t", "\\end{center}",
      "\\end{document}"]),
], ids=["ayni_ad_yeniden", "yeni_ortam_karsi_kol"])
def test_ESKI_end_BEKLERKEN_ikincisi_EKLENMIYOR(qapp, metin, satir, sutun, yeni, beklenen):
    r"""ÖLÇÜLDÜ (2026-09-25, gerçek pdflatex): aynı adı yeniden yazmak bile
    ikinci `\end{itemize}` ekleyip `\item`leri ortamın dışına itiyordu
    ("perhaps a missing \item")."""
    ed = _editor()
    ed.setText(metin)
    ed.setCursorPosition(satir, sutun)
    QTest.keyClicks(ed, yeni)
    assert lf_ye_indir(ed.text()).split("\n") == beklenen


@pytest.mark.parametrize("on, yazilan", [
    ("", "\\begin{figure}"),                     # \end bloğu ekleniyor
    ("\\label{fig:abc}\n", "\\ref{fig:abc}"),    # kapanış atlanıyor
], ids=["begin", "ref"])
def test_EDITORUN_eklemesinden_sonra_Enter_listeyi_KABUL_ETMIYOR(qapp, on, yazilan):
    r"""Harf harf yazılan ad `}` ile bitince tamamlama listesi kapanıyor.

    Açık kalan liste sonraki Enter'da kabul ediliyor ve kelimenin başından
    imlece kadar olan her şeyi, `}` ve eklenen gövde satırı dahil, siliyordu.
    ÖLÇÜLDÜ (2026-09-25, görünür gerçek pencere): `\ref{fig:abc}` + Enter
    `\ref{fig:abc`, `\begin{figure}` + Enter `\begin{figure*` oldu.
    """
    ed = _editor()
    ed.setText(on)
    ed.setCursorPosition(ed.lines() - 1, 0)
    QTest.keyClicks(ed, yazilan[:-1])
    assert ed.isListActive()                # kapının ön koşulu
    QTest.keyClicks(ed, "}")
    QTest.keyClick(ed, Qt.Key.Key_Return)
    assert yazilan in lf_ye_indir(ed.text()).split("\n")
