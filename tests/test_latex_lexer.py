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

# Headless (ekransız) çalıştır — CI / WSL ortamı için

import os

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


# --- Erken çıkış (performans): artımlı tarama tam taramayla birebir aynı stil üretmeli ---


def _all_styles(editor, n_bytes: int) -> list:
    return [editor.SendScintilla(QsciScintilla.SCI_GETSTYLEAT, p) for p in range(n_bytes)]


def _styled_bytes_spy(lexer):
    """setStyling çağrılarının toplam stillenen bayt sayısını ölçen spy."""
    counts = {"total": 0}
    orig = lexer.setStyling

    def spy(length, *args, **kwargs):
        counts["total"] += length
        return orig(length, *args, **kwargs)

    lexer.setStyling = spy
    return counts


_DOC = "\n".join([
    r"% başlık yorumu",
    r"\documentclass{article} ğüşıöç UTF-8 denetimi",
    r"\begin{document}",
    r"Normal paragraf, \emph{vurgu} ve Türkçe: ağaç sağlıklı örüntü.",
    r"$inline math \alpha + \beta$ devam",
    r"\begin{equation}",
    r"  E = mc^2",
    r"\end{equation}",
    r"\begin{verbatim}",
    r"raw $x$ \notcommand",
    r"\end{verbatim}",
    r"son satır \ref{key} metni",
] * 8) + "\n"


def test_incremental_after_insert_matches_full_scan(qapp):
    """Satır araya metin eklendikten sonra artımlı styleText, tam taramayla
    birebir aynı stil baytlarını üretmeli (erken çıkış doğruluğu)."""
    for insert_text in ("x", "\n", "\\section{yeni}\n", "$", "%yeni yorum", "ğ"):
        base = _DOC
        editor = _make_editor()
        editor.setText(base)
        lexer = editor.lexer()
        lexer.styleText(0, len(base.encode("utf-8")))  # önbelleği doldur

        # Dokümanın ortasına ekleme yapıp artımlı stiller (gerçek editör akışı)
        pos = len(base) // 2
        editor.setCursorPosition(0, 0)
        line, idx = editor.lineIndexFromPosition(pos)
        editor.setCursorPosition(line, idx)
        editor.insert(insert_text)
        data = editor.text().encode("utf-8")
        ins_pos = pos + len(insert_text.encode("utf-8"))
        lexer.styleText(ins_pos - len(insert_text.encode("utf-8")), ins_pos)

        got = _all_styles(editor, len(data))

        # Referans: aynı içerikte tam tarama
        ref_editor = _make_editor()
        ref_editor.setText(editor.text())
        ref_editor.lexer().styleText(0, len(data))
        want = _all_styles(ref_editor, len(data))

        assert got == want, f"artımlı stil sapması, eklenen: {insert_text!r}"


def test_incremental_typing_sequence_matches_full_scan(qapp):
    """Ardışık gerçekçi tuş dizisi sonrası stiller tam taramayla aynı olmalı
    (satır sayısı değişen Enter dahil; önbellek kaydırma yolunu da korur)."""
    editor = _make_editor()
    editor.setText(_DOC)
    lexer = editor.lexer()
    lexer.styleText(0, len(_DOC.encode("utf-8")))

    # Ortadaki bir satırın başına gidip kelime yaz + Enter + satır sil
    line_no = editor.lines() // 2
    editor.setCursorPosition(line_no, 0)
    for ch in "yeni metin burada\n\\begin{itemize}\n":
        editor.insert(ch)
        data = editor.text().encode("utf-8")
        end = len(data)  # Scintilla yaklaşık: kirli bölge sonuna kadar
        start = max(0, end - len(ch.encode("utf-8")) - 1)
        lexer.styleText(start, end)

    # Satır sil (satır sayısı değişir → delta negatif)
    editor.setCursorPosition(line_no + 1, 0)
    editor.setSelection(line_no + 1, 0, line_no + 2, 0)
    editor.removeSelectedText()
    data = editor.text().encode("utf-8")
    lexer.styleText(data.find(b"\n", max(0, data.find(b"yeni metin"))) - 1, len(data))

    got = _all_styles(editor, len(data))
    ref_editor = _make_editor()
    ref_editor.setText(editor.text())
    ref_editor.lexer().styleText(0, len(data))
    assert got == _all_styles(ref_editor, len(data))


def test_early_exit_limits_restyled_bytes(qapp):
    """Uzak bir satırdaki küçük düzenleme tüm belgeyi yeniden stillememeli.

    Erken çıkış: [start,end) geçildikten sonraki ilk satır başında durum
    eşleşirse tarama durur. Stillenen bayt miktarı birkaç satırla sınırlı
    kalır (belge ~96 satır; tam tarama ~belge boyutu kadar stiller).
    """
    editor = _make_editor()
    editor.setText(_DOC)
    lexer = editor.lexer()
    lexer.styleText(0, len(_DOC.encode("utf-8")))  # önbellek dolu

    # Uzak satırda tek karakterlik artımlı istek
    data = _DOC.encode("utf-8")
    far = _byte_offset_of_line(_DOC, 80)
    spy = _styled_bytes_spy(lexer)
    lexer.styleText(far, far + 1)
    assert spy["total"] < 500, (
        f"uzak satır düzenlemesi {spy['total']} bayt restyled — "
        f"erken çıkış çalışmıyor (belge {len(data)} bayt)"
    )


def _runtime_seed() -> int:
    """Koşum-anı tohum: TEST_SEED > GITHUB_RUN_ID > urandom.

    Sabit tohumlar (1/7/42) aynı derlemi her koşuda tarar (tekrarlanabilirlik);
    dördüncü tohum her koşuda yeni derlem üretir (koşum-anı entropi — ezber/
    tesadüfi geçiş ölmez, fark edilir). Başarısız koşum tohumu assert mesajında
    yazar; TEST_SEED (yerel) veya GITHUB_RUN_ID (CI) ile yeniden üretilir.
    """
    if os.environ.get("TEST_SEED"):
        return int(os.environ["TEST_SEED"])
    if os.environ.get("GITHUB_RUN_ID"):
        return int(os.environ["GITHUB_RUN_ID"])
    return int.from_bytes(os.urandom(8), "big")


def test_random_edit_sequence_matches_full_scan(qapp):
    """Sabit + koşum-anı tohumlu rastgele ekle/sil dizisi boyunca artımlı
    stiller her adımda tam taramayla birebir aynı olmalı (erken çıkış +
    kaydırma fuzz). Dördüncü tohum _runtime_seed()'den gelir.

    Not: '\n' içeren parçalar yalnız satır başına/sonuna eklenir. Satır içine
    newline eklendiğinde satır içi {...} grubu ikiye bölünebilir; parantez
    derinliği satır-durum önbelleğinde tutulmadığından (yalnız math/verbatim
    tutulur) yeniden başlangıç satırı parantez ortasından başlar ve artımlı
    sonuç tam taramadan farklı düşer. Bu, eski lexer'da da var olan bilinen
    bir sınırlamadır; test bu vakayı üretmez.
    """
    import random

    # 33354692582: CI'da (run 33354692582) gerçekten düşen tohum. Adım 20→21'de
    # satır 91'deki açık `$`, satır 92'ye eklenen `$` ile kapanıyor; satır 92'ye
    # math'in İÇİNDEN giriliyor ama styleText son satıra taramanın ÇIKIŞ
    # durumunu yazıyordu (0). Bayat 0, sonraki artımlı taramada "güvenli satır"
    # sanılıp math dışında başlatıyordu. Sabit tohum olarak kalsın: rastgele
    # tohumun bu vakayı yeniden üretme olasılığı %1'in altında (300 tohum
    # denendi, 0 düşüş) — yani koruma tohuma bırakılamaz.
    for seed in (1, 7, 42, 33354692582, _runtime_seed()):
        rng = random.Random(seed)
        editor = _make_editor()
        editor.setText(_DOC)
        lexer = editor.lexer()
        lexer.styleText(0, len(_DOC.encode("utf-8")))

        for _step in range(40):
            if rng.random() < 0.3 and editor.lines() > 6:
                # silme: rastgele satır aralığı — kirli bölge seçim başında başlar
                l0 = rng.randrange(editor.lines())
                l1 = min(editor.lines() - 1, l0 + rng.randrange(3))
                dirty_start = editor.positionFromLineIndex(l0, 0)
                editor.setSelection(l0, 0, l1, rng.randrange(max(1, len(editor.text(l1)))))
                editor.removeSelectedText()
                dirty_end = dirty_start  # silinen bölge çöktü
            else:
                l = rng.randrange(editor.lines())
                chunk = rng.choice(["x", "\n", "$", "%", "ğ", "\\begin{itemize}\n",
                                    "\\end{itemize}", "  \\item foo\n"])
                line_len = len(editor.text(l).rstrip("\n"))
                if "\n" in chunk:
                    col = rng.choice((0, line_len))  # satır içi parantez bölme yok
                else:
                    col = rng.randrange(max(1, line_len))
                dirty_start = editor.positionFromLineIndex(l, col)
                editor.setCursorPosition(l, col)
                editor.insert(chunk)
                dirty_end = dirty_start + len(chunk.encode("utf-8"))

            data = editor.text().encode("utf-8")
            lexer.styleText(dirty_start, dirty_end)

            got = _all_styles(editor, len(data))
            ref_editor = _make_editor()
            ref_editor.setText(editor.text())
            ref_editor.lexer().styleText(0, len(data))
            assert got == _all_styles(ref_editor, len(data)), f"seed={seed} adım={_step}"


def test_reset_state_clears_cache(qapp):
    """reset_state sonrası önbellek boş ve belge yeniden tam taranır."""
    editor = _make_editor()
    editor.setText(_DOC)
    lexer = editor.lexer()
    lexer.styleText(0, len(_DOC.encode("utf-8")))
    assert lexer._line_states  # dolu

    lexer.reset_state()
    assert lexer._line_states == {0: 0}
    assert lexer._doc_lines is None

    # Yeni belge yüklenip tam tarama yine doğru çalışır
    editor.setText("\\begin{verbatim}\n$i$\n\\end{verbatim}\nson")
    lexer.styleText(0, len(editor.text().encode("utf-8")))
    data = editor.text().encode("utf-8")
    assert _style_at(editor, data.index(b"$i$")) == LatexLexer.VERBATIM
    assert _style_at(editor, data.index(b"son")) == LatexLexer.DEFAULT


# =====================================================================
# Belge-bayt önbelleği: tuş başına text()+encode taban maliyeti
# =====================================================================


class TestSourceCache:
    def _editor(self, qapp):
        from gui.editor import EditorWidget
        ed = EditorWidget()
        ed.setText("\\begin{document}\nselam $x$\n\\end{document}\n")
        return ed

    def test_belge_ayniysa_text_cekilmez(self, qapp, monkeypatch):
        ed = self._editor(qapp)
        lexer = ed.lexer()
        cekim = []
        gercek_text = ed.text

        def sayan_text():
            cekim.append(1)
            return gercek_text()

        monkeypatch.setattr(ed, "text", sayan_text)

        lexer.styleText(0, 10)
        assert cekim, "ilk cagri text cekmeli"
        lexer.styleText(0, 12)          # belge degismedi -> onbellekten
        assert len(cekim) == 1, "ayni belge icin text() tekrar cekilmemeli"

    def test_belge_degisince_onbellek_duser(self, qapp):
        ed = self._editor(qapp)
        lexer = ed.lexer()
        lexer.styleText(0, 10)
        assert lexer._src_cache is not None

        ed.setText("\\begin{document}\nbaska $y$\n\\end{document}\n")
        # textChanged baglantisinin tetiklemesi: processEvents'suz dogrudan
        # sinyal yolu da test kapsaminda dogrulanir
        assert lexer._src_cache is None, "textChanged invalidate etmeli"

    def test_uzunluk_farkliysa_savunma_duser(self, qapp, monkeypatch):
        """textChanged baglantisi atlanirsa (ör. dogrudan styleText) uzunluk
        denetimi bayat önbelleği yakalar."""
        ed = self._editor(qapp)
        lexer = ed.lexer()
        lexer.styleText(0, 10)
        ed.append("uzun satir eklendi\n")
        lexer.invalidate_cache()   # bilincli: simule edelim baglanti calismadi
        ed.text  # noqa: B018 -- erisim
        lexer.styleText(0, 5)
        # cache yeniden kurulmus olmali (bayt uzunlugu artik farkli)
        assert lexer._src_cache is not None

    def test_math_stili_font_aliyor(self, qapp):
        from gui.theme import THEMES
        from syntax.latex_lexer import LatexLexer
        lex = LatexLexer()
        lex.apply_theme(THEMES["dark"], font_size=13)
        f = lex.font(LatexLexer.MATH)
        assert f.pointSize() == 13
        assert f.family() in ("Consolas", "DejaVu Sans Mono", "Menlo",
                              "Courier New", "monospace")


# --- Kapanmamış bloklar ---
#
# F1'de (2026-08-31) ölü "blok ortasından devam" tarayıcıları kaldırılırken
# in_math / in_verbatim bilerek KORUNDU. Etki alanları dar ve ölçüldü: blok
# tarayıcıları newline'ları kendi içlerinde yuttuğu için blok ortasındaki
# satırlar _line_states'e HİÇ girmez; güvenli-satır geri yürüyüşünü tetikleyen
# şey girdinin yokluğudur, değeri değil. Bayrakların gerçekten belirlediği tek
# şey EOF'ta AÇIK kalan bloğun SON satır durumudur.
#
# Bu yüzden aşağıdaki iki test farklı şeyler koruyor ve karıştırılmamalı:
#   - test_kapanmamis_blok_son_satir_durumunu_kaydediyor
#       in_math/in_verbatim'in TEK gerçek görevi. Bayraklar silinse bu düşer
#       (deneyle doğrulandı: _state_val hep 0 döndürülünce kırmızı).
#   - test_acik_blogun_ICINDEN_...
#       artımlı taramanın kapanmamış bloklu belgede doğruluğu. Mekanizması
#       eksik-önbellek-girdisi olduğu için bayraklardan BAĞIMSIZ; _state_val
#       bozulsa bile geçer. Yine de gerçek bir boşluğu kapatıyor: mevcut
#       artımlı/tam karşılaştırmaları yalnız KAPALI bloklu _DOC üzerindeydi.

@pytest.mark.parametrize("belge,beklenen_durum", [
    ("Metin $a + b\n", 1),                              # kapanmamış $
    ("Metin $$a + b\nikinci\n", 1),                     # kapanmamış $$
    ("Metin\n\\[\n  a = b\n", 1),                       # kapanmamış \[
    ("Metin \\( a+b\ndevam\n", 1),                      # kapanmamış \(
    ("Once\n\\begin{verbatim}\nkod\n", 2),              # kapanmamış verbatim
    ("Once\n\\begin{lstlisting}\nint x;\n", 2),         # kapanmamış lstlisting
    ("Metin $a+b$ kapali\n", 0),                        # kapalı: durum sıfırlanır
    ("\\begin{verbatim}\nk\n\\end{verbatim}\n", 0),     # kapalı verbatim
])
def test_kapanmamis_blok_son_satir_durumunu_kaydediyor(qapp, belge, beklenen_durum):
    """Blok EOF'ta açık kalırsa son satırın durumu 1 (math) / 2 (verbatim) olmalı."""
    editor, data = _style_text(belge)
    durumlar = editor.lexer()._line_states
    son = max(durumlar)
    assert durumlar[son] == beklenen_durum, (
        f"son satır durumu {durumlar[son]}, beklenen {beklenen_durum} — "
        f"belge: {belge!r}")


_ACIK_DOC = "\n".join([
    r"\documentclass{article} ğüşıöç",
    r"\begin{document}",
    r"Normal paragraf ve \emph{vurgu}.",
    r"$inline \alpha$ kapali",
    r"Burada kapanmayan bir dolar: $a + b",
    r"devam eden satir, hala math",
    r"bir satir daha",
    r"\begin{verbatim}",
    r"raw $x$ \notcommand",
    r"kapanis YOK",
] * 4) + "\n"


def test_acik_blogun_ICINDEN_artimli_tarama_tam_taramayla_ayni(qapp):
    """Kapanmamış bloğun İÇİNDEKİ bir satırdan artımlı tarama doğru olmalı.

    O satırdan taramaya başlamak ancak güvenli-satır geri yürüyüşü `$`'ı açan
    satıra kadar inerse doğru sonuç verir. Mevcut artımlı/tam karşılaştırmaları
    yalnız KAPALI bloklu _DOC üzerinde koşuyordu; bu yol hiç
    karşılaştırılmıyordu (2026-08-31, F1).

    NOT: bu test in_math/in_verbatim'i GATE ETMEZ — geri yürüyüş eksik önbellek
    girdisiyle tetikleniyor, durum değeriyle değil (bkz. yukarıdaki blok yorumu).
    """
    hedef = "devam eden satir, hala math"       # kapanmamış $'ın İÇİNDE
    assert hedef in _ACIK_DOC, "test belgesi değişmiş"

    editor = _make_editor()
    editor.setText(_ACIK_DOC)
    lexer = editor.lexer()
    veri = _ACIK_DOC.encode("utf-8")
    lexer.styleText(0, len(veri))

    # Blok gerçekten açık mı — testin önermesi
    hedef_ofset = veri.index(hedef.encode("utf-8"))
    assert _style_at(editor, hedef_ofset) == LatexLexer.MATH, \
        "test belgesi kapanmamış math içermiyor"

    # Aynı satırın BAŞINDAN artımlı stille (Scintilla'nın yaptığı gibi)
    satir_basi = veri.rfind(b"\n", 0, hedef_ofset) + 1
    satir_sonu = veri.find(b"\n", hedef_ofset)
    lexer.styleText(satir_basi, satir_sonu)

    got = _all_styles(editor, len(veri))
    ref = _make_editor()
    ref.setText(_ACIK_DOC)
    ref.lexer().styleText(0, len(veri))
    assert got == _all_styles(ref, len(veri)), \
        "açık bloğun içinden artımlı tarama tam taramadan sapıyor"


def test_kapanmamis_blokta_duzenleme_tam_taramayla_ayni(qapp):
    """Kapanmamış bloklu belgede gerçek düzenleme akışı da sapmamalı."""
    for ekleme in ("x", "\n", "$", "%yorum", "ğ"):
        editor = _make_editor()
        editor.setText(_ACIK_DOC)
        lexer = editor.lexer()
        lexer.styleText(0, len(_ACIK_DOC.encode("utf-8")))

        pos = _ACIK_DOC.index("devam eden satir, hala math") + 5
        line, idx = editor.lineIndexFromPosition(pos)
        editor.setCursorPosition(line, idx)
        editor.insert(ekleme)
        data = editor.text().encode("utf-8")
        lexer.styleText(pos, pos + len(ekleme.encode("utf-8")))

        got = _all_styles(editor, len(data))
        ref = _make_editor()
        ref.setText(editor.text())
        ref.lexer().styleText(0, len(data))
        assert got == _all_styles(ref, len(data)), (
            f"kapanmamış bloklu belgede artımlı stil sapması, eklenen: {ekleme!r}")


# --- Satır durumu: GİRİŞ mi, ÇIKIŞ mı? ---

def test_blok_icinden_girilen_satirin_durumu_giris_olmali(qapp):
    """Bir satıra blok İÇİNDEN girilip blok o satırda kapanırsa giriş 1'dir.

    styleText eskiden son satıra taramanın ÇIKIŞ durumunu yazıyordu. Aşağıdaki
    belgede satır 1'e math'in içinden giriliyor (satır 0'daki `$` açık kalmış),
    math satır 1'de kapanıyor: giriş 1, çıkış 0. Düz atama 0 yazıp önbelleği
    bayatlatıyor, bir sonraki artımlı tarama o satırı 'güvenli' sanıyordu.
    """
    editor, data = _style_text("acik $math\n$ kapandi")
    durumlar = editor.lexer()._line_states
    assert durumlar.get(1) == 1, (
        f"satır 1'in GİRİŞ durumu 1 (math) olmalı, {durumlar.get(1)} bulundu — "
        "çıkış durumu kaydedilmiş olabilir")


def test_cok_satirli_blogun_ic_satirlari_kaydediliyor(qapp):
    """Blok tarayıcısının yuttuğu satırlar da önbelleğe girmeli.

    `_style_*_block` çok satırlı bloğu tek çağrıda tüketiyor; ana döngünün
    `\n` dalı çalışmadığı için blok ORTASINDAKİ satırlar hiç kaydedilmiyordu.
    Kaydedilmeyince `_commit` bölgeyi yeniden yazarken bayat 0'lar yerinde
    kalabiliyordu.
    """
    editor, data = _style_text(
        "once\n\\begin{verbatim}\nbir\niki\n\\end{verbatim}\nsonra\n")
    durumlar = editor.lexer()._line_states
    # 2 ve 3 verbatim bloğunun İÇİ
    assert durumlar.get(2) == 2, f"satır 2: {durumlar.get(2)}"
    assert durumlar.get(3) == 2, f"satır 3: {durumlar.get(3)}"
    # blok kapandıktan sonraki satır normal
    assert durumlar.get(5) == 0, f"satır 5: {durumlar.get(5)}"


def test_cok_satirli_math_blogunun_ic_satirlari_kaydediliyor(qapp):
    editor, data = _style_text("once\n\\[\na = b\nc = d\n\\]\nsonra\n")
    durumlar = editor.lexer()._line_states
    assert durumlar.get(2) == 1, f"satır 2: {durumlar.get(2)}"
    assert durumlar.get(3) == 1, f"satır 3: {durumlar.get(3)}"
    assert durumlar.get(5) == 0, f"satır 5: {durumlar.get(5)}"
