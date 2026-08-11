"""latex_lexer önbellek testleri.

QScintilla'nın QsciLexerCustom.styleText(start, end) çağrısı artımlı (incremental)
yapılır: yalnızca kirli (dirty) bölge için çağrılır. LatexLexer satır-bazlı
``in_math`` durumunu ``self._line_states`` önbelleğinde tutar; bir sonraki çağrıda
güvenli bir satırdan (math modunda olmayan) devam etmek için kullanır.

Bu testler iki regression'ı korur (ikisi de düzeltildi):
1. Düz metin akışı ``\n`` dışında durmadığı için satır durumları kaydedilmiyor,
   önbellek dolmuyordu.
2. ``self._line_states = new_states`` tüm önbelleği değiştiriyordu; ``new_states``
   yalnızca ``[line_start, EOF]`` aralığını içerdiğinden artımlı çağrılar önceki
   satırların doğru durumlarını siliyordu. Sonuç: güvenli satır araması line 0'a
   kadar inip tüm belgeyi yeniden tarıyordu (büyük belgelerde her tuş vuruşunda
   tam reparse).
"""

import os
import sys

# Headless (ekransız) çalıştır — CI / WSL ortamı için
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

# pytest.importorskip("PyQt6.Qsci") noktalı-ad formu bazı bağlamlarda atlayabiliyor;
# direkt import + allow_module_level skip daha sağlam.
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.Qsci import QsciScintilla
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / PyQt6.Qsci gerekli", allow_module_level=True)

# desktop/ altındaki syntax.latex_lexer import edilebilir olsun
# (test_imports.py ile aynı konvensiyon; desktop bir paket değil)
_DESKTOP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "desktop"))
if _DESKTOP not in sys.path:
    sys.path.insert(0, _DESKTOP)

from syntax.latex_lexer import LatexLexer


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_editor():
    """Lexer bağlı boş bir QScintilla editörü döndür."""
    editor = QsciScintilla()
    lexer = LatexLexer(editor)
    editor.setLexer(lexer)
    return editor


def _byte_offset_of_line(text: str, line_no: int) -> int:
    """Verilen satırın (0-based) başlangıcının UTF-8 byte offseti."""
    offset = 0
    parts = text.split("\n")
    for i in range(line_no):
        offset += len(parts[i].encode("utf-8")) + 1  # +1: newline
    return offset


# --- Bug teyidi: artımlı styleText önceki satır önbelleğini silmemeli ---


def test_incremental_style_keeps_earlier_lines_in_cache(qapp):
    """Artımlı (geç bölge) styleText, daha önceki satırların önbelleğini silmemeli.

    Bug: ``self._line_states = new_states`` tüm önbelleği değiştiriyordu;
    geç bir satırın styleText'i sonrası önceki satırların durumları kayboluyordu.
    """
    editor = _make_editor()
    buf = "\n".join(f"line {i} normal text here" for i in range(40))
    editor.setText(buf)
    lexer = editor.lexer()

    # Tam tarama — önbellek tüm satırları içermeli
    lexer.styleText(0, len(buf.encode("utf-8")))
    assert 20 in lexer._line_states
    assert 35 in lexer._line_states

    # Geç bir bölge (satır 35) için artımlı styleText simüle et
    start = _byte_offset_of_line(buf, 35)
    lexer.styleText(start, start + 10)

    # DÜZELTME SONRASI beklenen: önceki satırların durumları korunmalı.
    # Bug varsa bu assertion başarısız olur (önbellek silindi).
    assert 5 in lexer._line_states, "artımlı styleText önceki satır önbelleğini sildi"
    assert 20 in lexer._line_states


def test_incremental_style_does_not_rewind_to_line_zero(qapp):
    """Artımlı styleText, önbellek kaybolduğu için tüm belgeyi baştan taramamalı.

    startStyling'a geçilen byte pozisyonu, taramanın nereden başladığını gösterir.
    Bug varsa: geç bölge tarandıktan sonra erken bir bölge isteği line 0'a
    (byte 0) geri döner → tam reparse. Düzeltme sonrası erken bölgenin kendi
    satırından devam eder.
    """
    editor = _make_editor()
    buf = "\n".join(f"line {i} normal" for i in range(60))
    editor.setText(buf)
    lexer = editor.lexer()

    # Tam tarama — önbelleği doldur
    lexer.styleText(0, len(buf.encode("utf-8")))

    # Geç bölgeyi (satır 50) tara
    late = _byte_offset_of_line(buf, 50)
    lexer.styleText(late, late + 5)

    # Şimdi erken bir bölge (satır 10) için styleText iste — nereden başlıyor?
    starts = []
    orig_start_styling = lexer.startStyling

    def spy(pos, *args, **kwargs):
        starts.append(pos)
        return orig_start_styling(pos, *args, **kwargs)

    lexer.startStyling = spy
    try:
        early = _byte_offset_of_line(buf, 10)
        lexer.styleText(early, early + 5)
    finally:
        lexer.startStyling = orig_start_styling

    assert starts, "startStyling hiç çağrılmadı"
    # Erken bölge kendi satırından devam etmeli — line 0'a (byte 0) geri dönmemeli
    assert starts[0] >= early, (
        f"lexer byte {starts[0]}'a geri döndü (tam reparse) — "
        f"{early} (satır 10) civarından devam etmeliydi"
    )


# --- Doğruluk: tam tarama matematik/yorum durumlarını doğru sınıflandırmalı ---


def test_full_style_populates_int_states(qapp):
    """Tam tarama sonrası önbellek int satır durumları içermeli (0/1/2, C.8)."""
    editor = _make_editor()
    buf = "\n".join([
        "% bu bir yorum",        # 0
        "normal metin $x^2$",    # 1 — satır içi math
        "\\section{Başlık}",     # 2
        "daha fazla metin",      # 3
    ])
    editor.setText(buf)
    lexer = editor.lexer()

    lexer.styleText(0, len(buf.encode("utf-8")))

    # Önbellekteki değerler int (0=normal, 1=math, 2=verbatim) olmalı
    for line_no, state in lexer._line_states.items():
        assert isinstance(state, int) and state in (0, 1, 2), \
            f"satır {line_no} durumu geçersiz: {state!r}"
    # En az birkaç satır kaydedilmiş olmalı
    assert len(lexer._line_states) >= 3


def test_incremental_style_after_full_is_stable(qapp):
    """Tam tarama + artımlı tarama karışımı çökmemeli ve önbellek tutarlı kalmalı."""
    editor = _make_editor()
    buf = "\n".join(f"line {i}" for i in range(30))
    editor.setText(buf)
    lexer = editor.lexer()

    lexer.styleText(0, len(buf.encode("utf-8")))
    # Çeşitli bölgelerde artımlı taramalar
    for line_no in (25, 5, 20, 3, 28):
        start = _byte_offset_of_line(buf, line_no)
        lexer.styleText(start, start + 3)

    # Önbellek int durumlar içermeli (0/1/2) ve tutarsızlık olmamalı
    assert all(isinstance(v, int) and v in (0, 1, 2) for v in lexer._line_states.values())


def test_incremental_restyle_inside_verbatim_stays_verbatim(qapp):
    """Blok içi satır artımlı restyle'de VERBATIM kalmalı (satır-no senkron bug'ı).

    Çok satırlı \\begin{verbatim} bloğu lexer tarafından tek seferde taranıp aradaki
    satır başları sayılmadığında, ``_line_states`` yanlış satır numarasına state
    yazıyordu. Sonuç: blok içinde bir satır kirli olduğunda artımlı restyle o
    satırı 'güvenli/normal' sanıyor, DEFAULT stilliyordu (komut/math gibi görünür).
    Düzeltme: blok tarayıcılar tükettiği ``\\n`` kadar ``line_no``'yu ilerletir.
    """
    editor = _make_editor()
    buf = "\n".join([
        "before text",        # 0
        "\\begin{verbatim}",  # 1
        "FIRST CODE LINE",    # 2  — blok içi
        "SECOND CODE LINE",   # 3  — blok içi
        "\\end{verbatim}",    # 4
        "after text",         # 5
    ])
    editor.setText(buf)
    lexer = editor.lexer()
    data = buf.encode("utf-8")
    lexer.styleText(0, len(data))  # önbelleği doldur

    # Blok içi bir satırı (satır 2) artımlı restyle et (Scintilla düzenleme sonrası böyle çağırır)
    start = _byte_offset_of_line(buf, 2)
    lexer.styleText(start, start + len("FIRST CODE LINE"))

    # İçerik satırları hâlâ VERBATIM olmalı (DEFAULT değil)
    assert _style_at(editor, _byte_offset_of_line(buf, 2)) == LatexLexer.VERBATIM
    assert _style_at(editor, _byte_offset_of_line(buf, 3)) == LatexLexer.VERBATIM
    # Blok sonrası yine DEFAULT
    assert _style_at(editor, _byte_offset_of_line(buf, 5)) == LatexLexer.DEFAULT


# --- Font taşınabilirliği ---


def test_lexer_uses_mono_font_fallbacks(qapp):
    """Consolas bulunmazsa yedek mono fontlar kullanılmalı (Linux/macOS taşınabilirlik)."""
    from gui.theme import THEMES
    lexer = LatexLexer()
    lexer.apply_theme(next(iter(THEMES.values())))
    fams = lexer.font(LatexLexer.DEFAULT).families()
    # İlk tercih Consolas; yedekler de set edilmeli
    assert "Consolas" in fams
    assert any(f in fams for f in ("DejaVu Sans Mono", "Menlo"))


# --- A.1: \[ ... \] ve \( ... \) math ayracı renklendirme ---


def _style_at(editor, byte_pos: int) -> int:
    """Verilen byte pozisyonundaki stil kodunu döndür (SCI_GETSTYLEAT)."""
    return editor.SendScintilla(QsciScintilla.SCI_GETSTYLEAT, byte_pos)


def _style_text(text: str):
    """Editöre metin yükle, tam tara; (editor, utf-8 byte verisi) döndür."""
    editor = _make_editor()
    editor.setText(text)
    data = text.encode("utf-8")
    editor.lexer().styleText(0, len(data))
    return editor, data


def test_display_math_bracket(qapp):
    r"""\[ ... \] display math: açılış, içerik ve kapanış MATH stillenmeli."""
    editor, data = _style_text(r"\[ a^{2} = b^{2} \]")
    assert _style_at(editor, 0) == LatexLexer.MATH              # '\[' açılış
    assert _style_at(editor, 3) == LatexLexer.MATH              # 'a' (içerik)
    assert _style_at(editor, len(data) - 1) == LatexLexer.MATH  # '\]' kapanış


def test_inline_math_paren(qapp):
    r"""\( ... \) inline math: içerik MATH, komutlar MATH_CMD."""
    editor, data = _style_text(r"\( \alpha + \beta \)")
    assert _style_at(editor, 0) == LatexLexer.MATH              # '\(' açılış
    assert _style_at(editor, 2) == LatexLexer.MATH              # boşluk (math içerik)
    assert _style_at(editor, 3) == LatexLexer.MATH_CMD          # '\alpha'


def test_display_math_multiline(qapp):
    r"""Çok satırlı \[ ... \] — orta satırdaki içerik MATH, kapanış sonrası DEFAULT."""
    buf = "intro\n\\[\nx^2 + y^2\n\\]\npost"
    editor, data = _style_text(buf)
    # 'x' byte 9'da ("intro\n"=6 + "\[\n"=3)
    assert _style_at(editor, 9) == LatexLexer.MATH
    # kapanış sonrası 'post' DEFAULT olmalı
    assert _style_at(editor, data.index(b"post")) == LatexLexer.DEFAULT


def test_display_math_with_commands(qapp):
    r"""Display math içindeki \sum komutu MATH_CMD stillenmeli."""
    editor, data = _style_text(r"\[ \sum_{k=0}^{n} \frac{1}{n} \]")
    sum_bs = data.index(b"sum") - 1   # '\sum' başlangıç backslash'i
    assert _style_at(editor, sum_bs) == LatexLexer.MATH_CMD


def test_unclosed_display_math_styles_rest(qapp):
    r"""Kapanmamış \[ — geri kalan belge math olarak stillenmeli."""
    editor, data = _style_text("\\[\nx^2\n")
    assert _style_at(editor, 3) == LatexLexer.MATH   # 'x' hâlâ MATH


def test_dollar_inline_math_regression(qapp):
    r"""Regression: $...$ inline math hâlâ MATH (A.1 değişikliği bozmamalı)."""
    editor, data = _style_text("$x^2$")
    assert _style_at(editor, 1) == LatexLexer.MATH   # 'x'


def test_stray_close_bracket_is_command(qapp):
    r"""Math dışında yalnız '\]' komut olarak stillenmeli (math kapanışı değil)."""
    editor, data = _style_text("some text \\]")
    assert _style_at(editor, data.index(b"\\]")) == LatexLexer.COMMAND


# --- C.8: verbatim ortamı (içerik komut/math olarak stillenmez) ---


def test_verbatim_content_not_command(qapp):
    r"""verbatim içindeki \section komut gibi değil, VERBATIM stillenmeli."""
    editor, data = _style_text("\\begin{verbatim}\n\\section{x}\n\\end{verbatim}")
    sec_bs = data.index(b"section") - 1   # \section başlangıç backslash'i
    assert _style_at(editor, sec_bs) == LatexLexer.VERBATIM


def test_verbatim_after_close_resumes_command(qapp):
    r"""verbatim kapandıktan sonra \section normal COMMAND stillenmeli."""
    editor, data = _style_text("\\begin{verbatim}\nx\n\\end{verbatim}\n\\section{y}")
    assert _style_at(editor, data.index(b"\\section")) == LatexLexer.COMMAND


def test_verbatim_multiline_content(qapp):
    r"""Çok satırlı verbatim: içerik VERBATIM, kapanış sonrası DEFAULT."""
    buf = "\\begin{verbatim}\nline of code\nmore code\n\\end{verbatim}\nnormal"
    editor, data = _style_text(buf)
    assert _style_at(editor, data.index(b"line of code")) == LatexLexer.VERBATIM
    assert _style_at(editor, data.index(b"normal")) == LatexLexer.DEFAULT


def test_verbatim_math_not_styled(qapp):
    r"""verbatim içinde $x$ math değil, VERBATIM."""
    editor, data = _style_text("\\begin{verbatim}\n$x$\n\\end{verbatim}")
    assert _style_at(editor, data.index(b"$x$")) == LatexLexer.VERBATIM


def test_verbatim_lstlisting(qapp):
    r"""lstlisting ortamı da raw işlenmeli."""
    editor, data = _style_text("\\begin{lstlisting}\nint x = 1;\n\\end{lstlisting}")
    assert _style_at(editor, data.index(b"int x")) == LatexLexer.VERBATIM


def test_verbatim_unclosed_styles_rest(qapp):
    r"""Kapanmamış verbatim — geri kalan VERBATIM, satır durumu 2."""
    editor, data = _style_text("\\begin{verbatim}\ncode here\n")
    assert _style_at(editor, data.index(b"code here")) == LatexLexer.VERBATIM
    assert 2 in editor.lexer()._line_states.values()
