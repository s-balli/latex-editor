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


def test_full_style_populates_boolean_states(qapp):
    """Tam tarama sonrası önbellek Boolean satır durumları içermeli (sağlık kontrolü)."""
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

    # Önbellekteki değerler Boolean olmalı
    for line_no, state in lexer._line_states.items():
        assert isinstance(state, bool), f"satır {line_no} durumu bool değil: {state!r}"
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

    # Önbellek hala Boolean değerler içermeli ve bir tutarsızlık olmamalı
    assert all(isinstance(v, bool) for v in lexer._line_states.values())


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
