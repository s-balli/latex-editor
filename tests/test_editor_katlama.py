r"""Kod katlama: \begin/\end ortamları ve bölüm başlıkları.

ÖLÇÜLDÜ (2026-09-27): katlama kenarı ilk sürümden beri açıktı ama hiçbir
satırda katlama noktası yoktu; özel lexer katlama düzeyi koymuyordu.
Beklenen bölgeler belgeden ELLE yazıldı. Görünürlük Scintilla'nın
kendisinden okunuyor (SCI_GETLINEVISIBLE), tıklama ve tuşlar gerçek.
Şablon derleminde (55 belge) kehanet TeX'in kendisiydi: her ortamın ve
başlığın ÇALIŞTIĞI satır. 3548 bölgenin 3541'i aynı; kalan yedisi anahattın
`\addcontentsline`ı başlık sayması ve belgenin kendi tanımladığı sözel ortam.
"""

import pytest

# Yalnız Qt yoksa atlanıyor. `katlama_bolgeleri` korumanın DIŞINDA: içeride
# dursaydı fonksiyon silinince bu dosya düşmez, sessizce atlanırdı (düzeltmesiz
# kodda öyle oldu).
pytest.importorskip("PyQt6.Qsci")
from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from gui.editor import katlama_bolgeleri  # noqa: E402


_BELGE = [
    "\\documentclass{article}",               # 1
    "\\begin{document}",                      # 2
    "\\section{Giris}",                       # 3
    "Giris metni aranankelime burada.",       # 4
    "\\subsection{Alt}",                      # 5
    "\\begin{itemize}",                       # 6
    "\\item bir",                             # 7
    "\\item iki",                             # 8
    "\\end{itemize}",                         # 9
    "% \\begin{figure} yorumdaki",            # 10
    "\\begin{verbatim}",                      # 11
    "\\begin{itemize}",                       # 12
    "\\end{verbatim}",                        # 13
    "Satir \\verb|\\end{itemize}| sonu.",     # 14
    "\\section{Sonuc}",                       # 15
    "Son metin.",                             # 16
    "\\end{document}",                        # 17
]
# (açan satır, son satır), 1 tabanlı. verbatim bir ortam (TeX onu
# çalıştırıyor), içindeki \begin{itemize} değil; yorum ve \verb sayılmıyor.
# \section altındaki \subsection'ı da kapatıyor, \end{document}'tan önce
# bitiyor.
_BEKLENEN = {(2, 17), (3, 14), (5, 14), (6, 9), (11, 13), (15, 16)}


def _bolgeler(metin):
    return {(b + 1, e + 1) for b, e in katlama_bolgeleri(metin)}


@pytest.mark.parametrize("eol", ["\n", "\r\n", "\r"],
                         ids=["lf", "crlf", "yalniz_cr"])
def test_bolgeler_ELLE_yazilan_beklenenle_AYNI(eol):
    assert _bolgeler(eol.join(_BELGE) + eol) == _BEKLENEN


@pytest.mark.parametrize("satirlar, beklenen", [
    # Ortamın içindeki başlık ortam kapanmadan biter (\end dışarıda kalır)
    (["\\begin{document}", "\\begin{appendices}", "\\section{Ek}", "metin",
      "\\end{appendices}", "Son.", "\\end{document}"],
     {(1, 7), (2, 5), (3, 4)}),
    # Önsözdeki tanımın \section'ı (anahat onu başlık sayıyor) \begin{document}
    # önünde biter. Kesseydi Scintilla iki bölgeyi birleştirir, o satıra
    # tıklamak bütün gövdeyi katlardı.
    (["\\documentclass{article}", "\\newcommand{\\bolum}[1]{\\section{#1}}",
      "\\usepackage{x}", "\\begin{document}", "\\section{A}", "metin",
      "\\end{document}"],
     {(2, 3), (4, 7), (5, 6)}),
    # İki satırlık ortam katlanıyor; aynı satırda açılıp kapanan katlanmıyor
    # (başlık bayrağı gövdesiz kalır, tıklanınca hiçbir şey yapmayan işaret).
    (["\\begin{center}", "\\end{center}",
      "a \\begin{tabular}{c}x\\end{tabular} b"],
     {(1, 2)}),
], ids=["ortam_icindeki_baslik", "onsozdeki_tanim", "iki_satir_ve_ayni_satir"])
def test_bolge_KENARLARI(satirlar, beklenen):
    assert _bolgeler("\n".join(satirlar) + "\n") == beklenen


# --- gerçek pencere ------------------------------------------------------


def _pencere(ana_pencere, tmp_path):
    yol = tmp_path / "main.tex"
    yol.write_text("\n".join(_BELGE) + "\n", encoding="utf-8")
    w = ana_pencere(open_file=str(yol))
    w.show()
    w.activateWindow()
    QApplication.processEvents()
    ed = w._current_editor()
    _katlama_bitsin(ed)
    return w, ed


def _katlama_bitsin(ed):
    """Yazınca kurulan 300 ms'lik bekleme dolsun (düzeyler o zaman konuyor)."""
    for _ in range(60):
        if not ed._katlama_zamanlayici.isActive():
            break
        QTest.qWait(50)
    QApplication.processEvents()


def _gizliler(ed):
    return [i + 1 for i in range(ed.lines())
            if not ed.SendScintilla(ed.SCI_GETLINEVISIBLE, i)]


def _kenara_tikla(ed, satir):
    """Katlama kenarına (margin 2) gerçek fare tıklaması; satır 1 tabanlı."""
    x = ed.marginWidth(0) + ed.marginWidth(1) + ed.marginWidth(2) // 2
    konum = ed.positionFromLineIndex(satir - 1, 0)
    y = (ed.SendScintilla(ed.SCI_POINTYFROMPOSITION, 0, konum)
         + ed.SendScintilla(ed.SCI_TEXTHEIGHT, satir - 1) // 2)
    QTest.mouseClick(ed.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(x, y))
    QApplication.processEvents()


def test_kenara_tiklamak_KATLIYOR_aciyor_ve_silinen_baslik_satir_GIZLEMIYOR(
        ana_pencere, tmp_path):
    """Tıklama hiçbir şey yapmıyordu. Katlı ortamın `\\begin`i silinince
    başlık bayrağı gidiyor; altındaki satırlar gizli kalsaydı metin
    görünmeden dururdu (QScintilla onları açıyor, burada sınanıyor)."""
    w, ed = _pencere(ana_pencere, tmp_path)
    _kenara_tikla(ed, 3)
    assert _gizliler(ed) == list(range(4, 15))
    _kenara_tikla(ed, 3)
    assert _gizliler(ed) == []

    _kenara_tikla(ed, 6)
    assert _gizliler(ed) == [7, 8, 9]
    ed.setCursorPosition(5, 0)
    QTest.keyClick(ed, Qt.Key.Key_End, Qt.KeyboardModifier.ShiftModifier)
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    _katlama_bitsin(ed)
    assert _gizliler(ed) == []


def test_KATLI_bolumdeki_eslesmeyi_bulma_kutusu_ACIYOR(ana_pencere, tmp_path):
    """Öntanımlı arama (harf duyarsız) eşleşmeyi `setSelection` ile seçiyor
    ve o katlamayı açmıyor; eşleşme gizli satırda seçili kalıyordu."""
    w, ed = _pencere(ana_pencere, tmp_path)
    _kenara_tikla(ed, 3)
    ed.setCursorPosition(0, 0)
    ed.setFocus()
    QTest.keyClick(w, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    kutu = w._find_bar._find_input
    QTest.keyClicks(kutu, "aranankelime")
    QTest.keyClick(kutu, Qt.Key.Key_Return)
    QApplication.processEvents()
    assert ed.getSelection()[0] + 1 == 4
    assert 4 not in _gizliler(ed)


def test_KATLI_bolumde_geri_alma_satiri_GOSTERIYOR(ana_pencere, tmp_path):
    """ÖLÇÜLDÜ (aynı gün, gerçek tuş): katlı bölümdeki bir düzenlemeyi
    Ctrl+Z ile geri almak metni ve imleci gizli satırda bırakıyordu."""
    w, ed = _pencere(ana_pencere, tmp_path)
    ed.setCursorPosition(7, len("\\item iki"))
    ed.setFocus()
    QTest.keyClicks(ed, " ek")
    _katlama_bitsin(ed)
    _kenara_tikla(ed, 3)
    assert 8 in _gizliler(ed)
    QTest.keyClick(ed, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert ed.text(7).rstrip("\r\n") == "\\item iki"
    assert 8 not in _gizliler(ed)
