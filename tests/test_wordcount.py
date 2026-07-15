"""_latex_wordcount testleri — matematik içeriği kelime sayımını şişirmemeli.

tab_ops._latex_wordcount eskiden `$...$` / `$$...$$` matematik bölgelerini
temizlemiyordu (_RE_MATH_ENV tanımlıydı ama kullanılmıyordu — dead code). Sonuç:
matematik ağırlıklı belgelerde kelime sayısı şişiyordu (ör. "$x^2 + y^2$" →
3 kelime sayılıyordu).
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

# desktop/ path'e ekle (gui/syntax için); core pytest'in rootdir'inden gelir
_DESKTOP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "desktop"))
if _DESKTOP not in sys.path:
    sys.path.insert(0, _DESKTOP)

try:
    from gui.mixins.tab_ops import _latex_wordcount
except ImportError:  # pragma: no cover
    pytest.skip("gui.mixins.tab_ops import edilemiyor (PyQt6/desktop gerekli)",
                allow_module_level=True)


def words(text: str) -> int:
    return _latex_wordcount(text)[0]


# --- Matematik sayılmamalı (bug teyidi) ---


def test_inline_math_excluded():
    """$...$ satır içi matematik içeriği kelime olarak sayılmamalı."""
    assert words("$x^2 + y^2$ hello") == 1


def test_display_math_excluded():
    """$$...$$ görüntü matematik sayılmamalı.

    Regression: $$ alternatifinin $...$'tan ÖNCE denenmesi gerekir, yoksa
    `$$a$$` boş satır içi math olarak yanlış eşlenir.
    """
    assert words("$$a + b$$ hello") == 1


def test_math_environment_content_excluded():
    r"""\\begin{equation}...\\end{equation} içeriği (tag'ler değil) sayılmamalı."""
    assert words("\\begin{equation}x + y\\end{equation} hello") == 1


def test_math_environment_starred_excluded():
    r"""\\begin{align*} gibi yıldızlı ortamlar da sayılmamalı."""
    assert words("\\begin{align*}a \\\\ b\\end{align*} done") == 1


def test_bracket_math_excluded():
    r"""\\[...\\] ve \\(...\\) matematik gösterimleri de sayılmamalı."""
    assert words("\\[a + b\\] metin") == 1
    assert words("\\(a + b\\) metin") == 1


def test_math_with_commands_excluded():
    r"""Math içindeki \\komutlar dahil tüm matematik bloğu sayılmamalı."""
    assert words("$\\alpha + \\beta$ metin") == 1


def test_multiline_display_math_excluded():
    """Birden çok satıra yayılan görüntü matematik sayılmamalı."""
    text = "$$\na^2 + b^2\n= c^2\n$$\nsonuc"
    assert words(text) == 1


# --- Mevcut doğru davranış korunmalı (regresyon) ---


def test_plain_text_counted():
    assert words("bir iki üç dört") == 4


def test_command_arg_counted():
    r"""Komut argümanı görünür metin olarak sayılmalı (ör. \\section başlığı)."""
    assert words("\\section{Baslik} ve yazi") == 3


def test_comment_excluded():
    """Yorumlar (% sonrası) sayılmamalı."""
    assert words("kelime % $x$ yorum") == 1


# --- Bileşik gerçekçi belge ---


def test_mixed_document():
    """Matematik + komut + düz metin karışımı gerçekçi belge."""
    text = (
        "\\section{Giris}\n"
        "Bu bir denklemdir $E = mc^2$ ve onemli.\n"
        "\\begin{equation}\n"
        "a^2 + b^2 = c^2\n"
        "\\end{equation}\n"
        "Sonuc budur.\n"
    )
    # Görünür kelimeler: Giris Bu bir denklemdir ve onemli. Sonuc budur. = 8
    assert words(text) == 8
