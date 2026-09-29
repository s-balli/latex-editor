"""Derleme hatalarının gutter'da işaretlenmesi + F4/Shift+F4 dolaşma testleri.

İki katman:
- gui.editor.EditorWidget: clear_error_markers / add_error_marker (Scintilla marker)
- gui.mixins.compile_ops.CompileOpsMixin: _goto_error index cycling mantığı
"""


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


from tests.stub_main import StubMain


class _StubMain(CompileOpsMixin, StubMain):
    """MainWindow yerine: _goto_error'nin ihtiyaç duyduğu minimum arayüz.

    _refresh_error_markers gerçek mixin metodu; _current_editor None döndüğünden
    erken döner (marker yan etkisi olmadan yalnızca index mantığı test edilir).
    """

    def __init__(self, errors):
        super().__init__(last_errors=errors)


def _errs(tmp_path, lines):
    out = []
    for i, ln in enumerate(lines):
        f = tmp_path / f"b{i}.tex"
        f.write_text("x\n" * max(ln, 1), encoding="utf-8")
        out.append(LatexError(line_number=ln, message=f"err{i}", file_path=str(f)))
    return out


def test_next_cycles_forward_and_wraps(tmp_path, qapp):
    errs = _errs(tmp_path, [5, 7, 9])
    s = _StubMain(errs)
    s._goto_next_error()
    s._goto_next_error()
    s._goto_next_error()
    s._goto_next_error()  # wrap → ilk hataya
    assert [c[1] for c in s.goto_calls] == [5, 7, 9, 5]
    assert s._err_index == 0


def test_prev_from_start_goes_to_last(tmp_path, qapp):
    errs = _errs(tmp_path, [5, 7, 9])
    s = _StubMain(errs)
    s._goto_prev_error()
    assert s._err_index == 2
    assert s.goto_calls[-1][1] == 9


def test_empty_errors_shows_message(tmp_path, qapp):
    s = _StubMain([])
    s._goto_next_error()
    assert s.goto_calls == []
    assert "Hata yok" in s._status.msg


def test_unresolvable_path_shows_not_found(tmp_path, qapp):
    errs = [LatexError(line_number=3, message="x", file_path=str(tmp_path / "yok.tex"))]
    s = _StubMain(errs)
    s._goto_next_error()
    assert s.goto_calls == []
    assert "konumu bulunamadı" in s._status.msg


# =====================================================================
# Gerçek pencere: derlemeden sonra metin değişince F4, işaret ve panel
# =====================================================================

_KAYNAK = ("\\documentclass{article}\n\\begin{document}\nbir\n\n"
           "Burada \\hatabir var.\n\niki\n\nBurada \\hataiki var.\n"
           "\\end{document}\n")


def _cikti(bir, iki):
    """Gerçek derle.sh çıktısının biçimi (2026-09-27, WSL'de pdflatex). Yol
    göreli; `_on_compile_finished` onu derlenen belgenin klasörüne çözüyor."""
    return ("./main.tex:%d: Undefined control sequence.\nl.%d Burada \\hatabir\n"
            "./main.tex:%d: Undefined control sequence.\nl.%d Burada \\hataiki\n"
            % (bir, bir, iki, iki))


def _isaretli(ed):
    return [i + 1 for i in range(ed.lines()) if _markers(ed, i) & _ERR_BIT]


def _satiri(ed, jeton):
    """Kehanet: hatanın METNİ editörün o anki metninde hangi satırda."""
    return [i + 1 for i in range(ed.lines()) if jeton in ed.text(i)][0]


def _derlenmis(ana_pencere, tmp_path):
    from PyQt6.QtWidgets import QApplication
    from core.log_parser import parse_output

    tex = tmp_path / "main.tex"
    tex.write_text(_KAYNAK, encoding="utf-8")
    w = ana_pencere(open_file=str(tex))
    w.show()
    w.activateWindow()
    QApplication.processEvents()
    w._compile_target = str(tex)
    w._on_compile_finished(parse_output(_cikti(5, 9), str(tex)))
    ed = w._current_editor()
    assert _isaretli(ed) == [5, 9]
    return w, ed


def _onsoze_satir_ekle(ed, n=1):
    """Kullanıcının onarımı, gerçek tuşla: `\\documentclass` satırının
    sonunda Enter. İki hata da n satır aşağı kayıyor.

    İmleç satır sonuna DOĞRUDAN konuyor. Önce Ctrl+Home ve End ile
    gidiliyordu; macOS'ta Qt Ctrl'yi Command tuşuna eşliyor, Home ve End de
    orada satır başı ve sonu değil. ÖLÇÜLDÜ (2026-09-29, macos-15): bu
    yardımcıyı kullanan dört testin dördü aşağıdaki denetimde düştü, iki
    hata 5 ve 9'da kaldı, yani Enter onların üstüne düşmedi. Onarım yine
    gerçek Enter tuşu."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    ed.setCursorPosition(0, len(ed.text(0).rstrip("\r\n")))
    for _ in range(n):
        QTest.keyClick(ed, Qt.Key.Key_Return)
    assert (_satiri(ed, "\\hatabir"), _satiri(ed, "\\hataiki")) == (5 + n, 9 + n)


def test_satir_eklenince_F4_ve_isaretler_METINLE_gidiyor(ana_pencere,
                                                         tmp_path):
    """Hatayı onarmak için önsöze satır ekleyen kullanıcı F4'e basıyor.
    ÖLÇÜLDÜ (2026-09-27, gerçek pencere, Ctrl+B ile gerçek derleme):
    işaretler metinle doğru kaydı (6, 10), F4 ise derleme anının satırına
    (9) gitti ve işaretleri 5 ile 9'a geri koydu; sekme gidip gelmek de
    öyle. Kehanet hatanın metni; tuş kısayol eşleştirmesinden geçiyor."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    w, ed = _derlenmis(ana_pencere, tmp_path)
    _onsoze_satir_ekle(ed)
    QTest.keyClick(w, Qt.Key.Key_F4)
    QTest.keyClick(w, Qt.Key.Key_F4)
    assert ed.getCursorPosition()[0] + 1 == _satiri(ed, "\\hataiki")
    assert _isaretli(ed) == [6, 10]

    baska = tmp_path / "baska.tex"
    baska.write_text("x\n", encoding="utf-8")
    w._open_file_in_editor(str(baska))
    w._editor_tabs.setCurrentWidget(ed)
    QApplication.processEvents()
    assert _isaretli(ed) == [6, 10]


def test_panelde_hataya_tiklamak_KAYAN_satira_gidiyor(ana_pencere, tmp_path):
    """Hatalar listesindeki satır derleme anının satırı; tıklama da F4 gibi
    işaretin güncel satırına gitmeli. ÖLÇÜLDÜ (aynı gün): 9'a gidiyordu."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    w, ed = _derlenmis(ana_pencere, tmp_path)
    _onsoze_satir_ekle(ed)
    liste = w._output_panel._error_list
    QTest.mouseClick(liste.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier,
                     liste.visualItemRect(liste.item(1)).center())
    assert ed.getCursorPosition()[0] + 1 == _satiri(ed, "\\hataiki")


def test_diskten_yuklenince_isaretler_DERLEME_satirina_donuyor(ana_pencere,
                                                                tmp_path):
    """`open_file` ("Diskten Yükle") `setText` ile işaretleri SİLİYOR,
    tutamaç -1 dönüyor. İşaret bir kez konup bırakılsaydı bir daha hiç
    görünmezdi: silinmişse derleme anının satırına yeniden konuyor ve F4
    oraya gidiyor (diskteki metin derleme anının metni)."""
    w, ed = _derlenmis(ana_pencere, tmp_path)
    _onsoze_satir_ekle(ed)
    ed.open_file(ed.file_path)
    assert _isaretli(ed) == []
    w._goto_next_error()
    assert ed.getCursorPosition()[0] + 1 == _satiri(ed, "\\hatabir") == 5
    assert _isaretli(ed) == [5, 9]


def test_yeni_derlemede_ARKA_sekmenin_eski_isareti_kullanilmiyor(ana_pencere,
                                                                 tmp_path):
    """Çok dosyalı projede derleme çoğu zaman bölümden başlıyor ve ana belge
    arka sekmede ÖNCEKİ derlemenin işaretleriyle kalıyor. Önsöze dört satır
    eklenince birinci hata 9'a indi; eski derlemenin "9" işareti ise artık
    ikinci hatanın (13) üstünde. Yeni derlemenin F4'ü eski tutamacı
    kullanırsa 9 yerine 13'e gider."""
    from core.log_parser import parse_output

    w, ed = _derlenmis(ana_pencere, tmp_path)
    _onsoze_satir_ekle(ed, 4)
    bolum = tmp_path / "bolum.tex"
    bolum.write_text("x\n", encoding="utf-8")
    w._open_file_in_editor(str(bolum))
    w._on_compile_finished(parse_output(_cikti(9, 13), w._compile_target))
    w._goto_next_error()
    assert w._current_editor() is ed
    assert ed.getCursorPosition()[0] + 1 == _satiri(ed, "\\hatabir") == 9
    assert _isaretli(ed) == [9, 13]
