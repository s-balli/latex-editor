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


def test_kapanmamis_blokta_geri_yurumuyor(qapp):
    """Kapanmamış blok varken artımlı tarama belgenin başına geri DÖNMEMELİ.

    Güvenli-satır araması eskiden yalnız durum-0 satır kabul ediyordu. Belgenin
    başında kapanmamış bir `$` varsa (math yazarken olağan ara durum) ondan
    sonraki HER satır durum-1'dir, dolayısıyla her tuş vuruşu o `$`'a kadar
    geri yürüyüp oradan itibaren yeniden tarıyordu. Ölçüldü: 3000 satırlık
    belgede 12.9 ms/tuş (kapanmamış blok yokken 1.2 ms).

    Artık satır durumuyla BİRLİKTE hangi bloğun açık olduğu da saklanıyor
    (_block_ctx), böylece blok ortasındaki bir satırdan devam edilebiliyor.
    """
    satirlar = ["giris metni"]
    satirlar.append("burada math acildi $x + y")     # KAPANMIYOR
    satirlar += ["satir %d duz metin" % i for i in range(2, 400)]
    buf = "\n".join(satirlar) + "\n"

    editor = _make_editor()
    editor.setText(buf)
    lexer = editor.lexer()
    lexer.styleText(0, len(buf.encode("utf-8")))

    hedef = 380
    basladigi = []
    orig = lexer.startStyling

    def spy(pos, *a, **k):
        basladigi.append(pos)
        return orig(pos, *a, **k)

    lexer.startStyling = spy
    try:
        start = _byte_offset_of_line(buf, hedef)
        lexer.styleText(start, start + 3)
    finally:
        lexer.startStyling = orig

    acilis = _byte_offset_of_line(buf, 1)
    assert basladigi, "startStyling çağrılmadı"
    assert basladigi[0] > acilis, (
        f"tarama byte {basladigi[0]}'dan başladı — kapanmamış $'ın bulunduğu "
        f"satır 1'e ({acilis}) kadar geri yürümüş demektir")


def test_blok_ortasindan_devam_dogru_stil_uretiyor(qapp):
    """Blok ortasından başlayan tarama tam taramayla aynı stili vermeli.

    Hız kazancı doğruluğu bozmamalı: devam yolu yepyeni bir kod yolu.
    """
    buf = ("giris\nacik $math basladi\n"
           + "\n".join("icerik satiri %d" % i for i in range(2, 30)) + "\n")
    editor = _make_editor()
    editor.setText(buf)
    lexer = editor.lexer()
    data = buf.encode("utf-8")
    lexer.styleText(0, len(data))

    # Blok ORTASINDAKİ bir satırı artımlı stille
    start = _byte_offset_of_line(buf, 20)
    son = _byte_offset_of_line(buf, 21)
    lexer.styleText(start, son)

    ref = _make_editor()
    ref.setText(buf)
    ref.lexer().styleText(0, len(data))
    assert _all_styles(editor, len(data)) == _all_styles(ref, len(data)), \
        "blok ortasından devam eden tarama tam taramadan sapıyor"


# =====================================================================
# Çok satırlı KOMUT ARGÜMANI satır sayacını kaydırıyordu (2026-09-06)
#
# `_consume_braces` / `_consume_brackets` çok satırlı bir argümanın satır
# sonlarını kendi içinde yutuyor; ana döngünün `\n` dalı onlar için hiç
# çalışmıyor ve `line_no` GERİDE KALIYORDU. Yukarıdaki
# `test_incremental_restyle_inside_verbatim_stays_verbatim` aynı sınıfın
# blok tarayıcılarını kapatmış, argüman tarayıcılarını atlamıştı.
#
# İki sonucu ölçüldü:
#   1. `_commit`e giden `exit_line` eksik oluyor; `base = exit_line -
#      line_delta` negatife düşünce "bölge sonrası kuyruk" süzgeci taranan
#      bölgenin KENDİ bayat girdisini kuyruk sanıp ötelİYOR ve hiçbir
#      taramanın ziyaret etmediği satıra "güvenli" (0) damgası basıyordu.
#      Sonraki artımlı tarama oradan başlayıp argümanın devamını DEFAULT
#      boyuyordu. Gerçek tuş vuruşuyla üretimi: `\be` + Enter, `$` + Enter,
#      `d` + Enter (otomatik tamamlama `\begin{` yapıyor).
#   2. Argüman KAPANSA bile sonraki bütün satır numaraları bir eksik
#      yazılıyordu (`\section{a` + yenisatır + `b}`).
#
# Düzeltme: yutulan satır sonu kadar sayaç ilerliyor ama o satırlara GİRDİ
# YAZILMIYOR (durum modeli 0/1/2 "argüman içindeyim"i ifade edemiyor;
# girdinin yokluğu zaten "burada başlanmaz" demek). `_commit`te
# `_line_states` kuyruk sınırı `k > base` oldu. Aynı değişiklik
# `_offset_states` ve `_block_ctx` için de denendi; 150 oturumluk tuş
# vuruşu fuzz'ıyla hiçbir davranış farkı ölçülemediği için yapılmadı.
# =====================================================================


def _lexer_tam_tara(buf):
    """Boş önbellekle tam tarama; (editor, lexer) döndür."""
    editor = _make_editor()
    editor.setText(buf)
    lexer = editor.lexer()
    lexer.reset_state()
    lexer.invalidate_cache()
    lexer.styleText(0, len(buf.encode("utf-8")))
    return editor, lexer


def test_coklu_satir_argumani_SATIR_NUMARASINI_kaydirmiyor(qapp):
    """Kırılırsa: argüman tarayıcıları yuttukları satırları saymıyor demektir."""
    buf = "\\section{a\nb}\nmetin\n$x$\n"
    editor, lexer = _lexer_tam_tara(buf)
    assert max(lexer._line_states) == buf.count("\n"), \
        f"satır sayacı geride: {dict(lexer._line_states)}"


def test_argumanin_YUTTUGU_satir_onbellege_girmiyor(qapp):
    """Başı argümanın içinde kalan satır 'güvenli' sayılamaz.

    Durum modeli (0/1/2) 'argüman içindeyim'i ifade edemiyor; sahte bir 0
    'buradan başlanabilir' demek olurdu.
    """
    buf = "\\section{a\nb}\nmetin\n"
    editor, lexer = _lexer_tam_tara(buf)
    assert lexer._line_states.get(1) is None, \
        f"argüman içindeki satıra girdi yazıldı: {dict(lexer._line_states)}"
    # Argüman kapandıktan SONRAKİ satırlar normal şekilde önbellekte
    assert lexer._line_states.get(2) == 0
    assert lexer._line_states.get(3) == 0


def test_kapanmamis_arguman_UYDURULMUS_girdi_uretmiyor(qapp):
    """`_commit`in kuyruk süzgeci taranan bölgenin girdisini ötelememeli.

    Kırılırsa: sınır yine `k >= base`, yani çıkış satırının kendisi de
    kuyruk sayılıyor demektir.
    """
    editor = _make_editor()
    lexer = editor.lexer()
    editor.setText("\\begin{")
    lexer.reset_state()
    lexer.invalidate_cache()
    lexer.styleText(0, editor.length())

    editor.setText("\\begin{$\n$")
    lexer.invalidate_cache()
    lexer.styleText(0, editor.length())

    assert lexer._line_states.get(1) is None, \
        f"hiçbir taramanın ziyaret etmediği satıra damga: {dict(lexer._line_states)}"


# --- Gerçek tuş vuruşları: kullanıcının gördüğü yol ---
#
# Doğrudan `setText` ile sınamak GEÇERSİZ: setText bütün stilleri sıfırlıyor,
# oysa gerçek düzenleme dokunulmayan baytların stilini KORUYOR. Kusur da tam
# olarak "korunan stiller ile yeni taramanın çeliştiği" yerde çıkıyor.

def _tus_vurusuyla_stiller(ops):
    """ops'u gerçek tuş vuruşlarıyla uygula; (ekrandaki, taze, metin) döndür."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from gui.editor import EditorWidget
    from gui.theme import THEMES

    app = QApplication.instance()
    ed = EditorWidget()
    ed.apply_theme(THEMES["dark"])
    ed.show()
    ed.setFocus()
    app.processEvents()
    for op in ops:
        if op[0] == "yaz":
            QTest.keyClicks(ed, op[1])
            QTest.keyClick(ed, Qt.Key.Key_Return)
        elif op[0] == "satir_uzerine":
            h = op[1]
            if h < ed.lines():
                ed.setSelection(h, 0, h, len(ed.text(h).rstrip("\n")))
                QTest.keyClicks(ed, op[2])
        app.processEvents()
    ed.repaint()
    app.processEvents()

    metin = ed.text()
    n = len(metin.encode("utf-8"))
    ekrandaki = _all_styles(ed, n)
    ed.deleteLater()
    app.processEvents()

    ref = _make_editor()
    ref.setText(metin)
    ref.lexer().reset_state()
    ref.lexer().invalidate_cache()
    ref.lexer().styleText(0, n)
    return ekrandaki, _all_styles(ref, n), metin


_TUS_VAKALARI = [
    # kesif_BO'nun delta debugging ile bulduğu EN KISA üretim
    ("en kisa uretim", [("yaz", "\\be"), ("yaz", "$"), ("yaz", "d")]),
    ("kapanmamis kose parantez",
     [("yaz", "\\cite["), ("yaz", "a"), ("yaz", "b")]),
    ("ic ice kume satira yayilmis",
     [("yaz", "\\section{a{b"), ("yaz", "c"), ("yaz", "}}")]),
    ("arguman kapaniyor sonra duzenleme",
     [("yaz", "\\section{a"), ("yaz", "b}"), ("yaz", "metin"),
      ("satir_uzerine", 1, "$z$")]),
    ("arguman icinde math",
     [("yaz", "\\section{$x"), ("yaz", "y$}"), ("yaz", "son")]),
    ("verbatim + kapanmamis kume",
     [("yaz", "\\begin{verbatim}"), ("yaz", "\\begin{"), ("yaz", "kod")]),
    ("cok satirli math sonrasi arguman",
     [("yaz", "$$"), ("yaz", "x"), ("yaz", "$$ \\section{a"), ("yaz", "b")]),
    # KONTROL: sözel/math olmayan sıradan düzenleme de sapmamalı
    ("siradan metin", [("yaz", "duz metin"), ("yaz", "ikinci satir"),
                       ("satir_uzerine", 0, "degistirildi")]),
]


@pytest.mark.parametrize("ad,ops", _TUS_VAKALARI, ids=[a for a, _ in _TUS_VAKALARI])
def test_gercek_tus_vurusu_TAZE_taramayla_ayni(qapp, ad, ops):
    """Artımlı renklendirme, aynı metnin sıfırdan renklendirmesiyle aynı olmalı."""
    ekrandaki, taze, metin = _tus_vurusuyla_stiller(ops)
    if ekrandaki != taze:
        i = next(k for k, (x, y) in enumerate(zip(ekrandaki, taze)) if x != y)
        raise AssertionError(
            f"{ad}: belge={metin.encode('utf-8')!r} ilk farklı bayt={i} "
            f"ekranda={ekrandaki[i]} olması gereken={taze[i]}")


def test_onbellek_HALA_is_goruyor(qapp):
    """Aşırı düzeltme kapısı: düzeltme 'her tuşta baştan tara'ya kaçmamalı.

    Kaçsaydı tarama her zaman byte 0'dan başlardı ve büyük belgelerde her
    tuş vuruşu tam reparse olurdu (bu dosyanın en başındaki 2. regresyon).
    """
    editor = _make_editor()
    buf = "\\section{Bolum}\nmetin satiri\n" * 300
    editor.setText(buf)
    lexer = editor.lexer()
    data = buf.encode("utf-8")
    lexer.reset_state()
    lexer.invalidate_cache()
    lexer.styleText(0, len(data))

    baslangiclar = []
    orig = lexer.startStyling

    def spy(pos, *a, **k):
        baslangiclar.append(pos)
        return orig(pos, *a, **k)

    lexer.startStyling = spy
    try:
        gec = _byte_offset_of_line(buf, 580)
        lexer.styleText(gec, gec + 5)
    finally:
        lexer.startStyling = orig

    assert baslangiclar, "styleText hiç startStyling çağırmadı"
    assert min(baslangiclar) > 0, \
        f"tarama belgenin başına döndü: {baslangiclar}"


# =====================================================================
# Verbatim: SINIRLAR komut, ARASI ham metin (2026-09-06)
#
# Iki ayri kusur, ikisi de kullanicidan geldi:
#
# 1. RENK. VERBATIM'in kendi tema anahtari yoktu, `fg_muted`i odunc
#    aliyordu; o her temada "sonuk gri" oldugu icin yorum rengiyle ayni
#    sinifa dusuyordu. Olculdu: yorum ile verbatim arasindaki RGB mutlak
#    fark toplami gruvbox 3, monokai 63, dracula 64 (deponun `sem_*` icin
#    kullandigi ayirt edilebilirlik esigi 40). Lexer DOGRU stilliyordu
#    (VERBATIM=8), kusur renkteydi. `syn_verbatim` anahtari eklendi.
#
# 2. SINIRLAR. `\begin{verbatim}` ve `\end{verbatim}` de VERBATIM
#    stilleniyordu, yani etiket icerikle AYNI renkteydi ve ortamin nerede
#    baslayip bittigi ekranda okunmuyordu. Oysa `\begin`/`\end` birer komut,
#    `{ad}` bir ortam argumani; diger ortamlarda zaten oyle renkleniyorlar.
# =====================================================================


def _stil_haritasi(belge):
    """Satir -> o satirda gecen stil adlari kumesi."""
    editor = _make_editor()
    editor.setText(belge)
    lexer = editor.lexer()
    lexer.reset_state()
    lexer.invalidate_cache()
    lexer.styleText(0, len(belge.encode("utf-8")))
    ad = {LatexLexer.DEFAULT: "DEFAULT", LatexLexer.COMMAND: "COMMAND",
          LatexLexer.CMD_ARG: "CMD_ARG", LatexLexer.BRACKET: "BRACKET",
          LatexLexer.COMMENT: "COMMENT", LatexLexer.MATH: "MATH",
          LatexLexer.MATH_CMD: "MATH_CMD", LatexLexer.ENV_ARG: "ENV_ARG",
          LatexLexer.VERBATIM: "VERBATIM"}
    out, off = {}, 0
    for satir in belge.split("\n"):
        b = satir.encode("utf-8")
        if satir.strip():
            out[satir] = {ad[_style_at(editor, off + k)] for k in range(len(b))}
        off += len(b) + 1
    return out


@pytest.mark.parametrize("env", ["verbatim", "verbatim*", "lstlisting",
                                 "comment", "Verbatim"])
def test_verbatim_SINIRLARI_komut_ARASI_ham(qapp, env):
    """Kirilirsa: sinirlar yine icerikle ayni renkte demektir."""
    belge = ("\\begin{%s}\nham icerik\n\\end{%s}\nsonra\n" % (env, env))
    h = _stil_haritasi(belge)
    assert h["\\begin{%s}" % env] == {"COMMAND", "ENV_ARG"}, h
    assert h["ham icerik"] == {"VERBATIM"}, h
    assert h["\\end{%s}" % env] == {"COMMAND", "ENV_ARG"}, h
    assert h["sonra"] == {"DEFAULT"}, h


def test_verbatim_ICINDEKI_sahte_end_icerik_kaliyor(qapp):
    """Asiri duzeltme kapisi: her `\\end` sinir sayilmamali."""
    belge = ("\\begin{verbatim}\n\\end{baska}\nson\n\\end{verbatim}\ndevam\n")
    h = _stil_haritasi(belge)
    assert h["\\end{baska}"] == {"VERBATIM"}, h
    assert h["\\end{verbatim}"] == {"COMMAND", "ENV_ARG"}, h
    assert h["devam"] == {"DEFAULT"}, h


def test_KAPANMAMIS_verbatimde_de_acilis_komut(qapp):
    belge = "\\begin{verbatim}\nkapanmamis icerik\n"
    h = _stil_haritasi(belge)
    assert h["\\begin{verbatim}"] == {"COMMAND", "ENV_ARG"}, h
    assert h["kapanmamis icerik"] == {"VERBATIM"}, h


def test_verbatim_ICERIGI_komut_olarak_stillenmiyor(qapp):
    """Eski davranis korunuyor: icerikteki `\\section` ham kalmali."""
    belge = "\\begin{verbatim}\n\\section{x} $m$ %y\n\\end{verbatim}\n"
    h = _stil_haritasi(belge)
    assert h["\\section{x} $m$ %y"] == {"VERBATIM"}, h


def test_verbatim_RENGI_yorumdan_ayri(qapp):
    """Kullanicinin bildirdigi asil sikayet: verbatim yorum gibi gorunuyordu."""
    from gui.theme import THEMES

    lexer = LatexLexer()
    for ad, t in THEMES.items():
        lexer.apply_theme(t)
        a, b = lexer.color(LatexLexer.COMMENT), lexer.color(LatexLexer.VERBATIM)
        fark = (abs(a.red() - b.red()) + abs(a.green() - b.green())
                + abs(a.blue() - b.blue()))
        assert fark >= 40, "%s: yorum %s ~ verbatim %s (fark %d)" % (
            ad, a.name(), b.name(), fark)
