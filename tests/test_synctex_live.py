"""SyncTeX canlı entegrasyon testleri.

derle.sh ile gerçekten derleyip .synctex.gz üretir, sonra gui.synctex bridge ve
gerçek PdfViewer üzerinden ileri/geri aramayı gerçekçi biçimde sınar. Bu birim
test değil entegrasyon testidir — lualatex + synctex gerektirir; CI'da yoksa tüm
modül skip olur (test_derle_sh.py ile aynı pattern).

Tam MainWindow yerine PdfViewer + bridge kullanılır: SyncTeX davranışını (derleme,
synctex CLI, koordinat→piksel, highlight, reverse round-trip) test eder ama network
(updater) / QSettings yan etkisi içermez — hermetik ve hızlı.
"""

import os
import shutil
import subprocess
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

_DESKTOP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "desktop"))
if _DESKTOP not in sys.path:
    sys.path.insert(0, _DESKTOP)

# lualatex + synctex yoksa tüm modül skip
pytestmark = pytest.mark.skipif(
    not (shutil.which("lualatex") and shutil.which("synctex")),
    reason="lualatex + synctex kurulu değil — TeX Live gerektirir",
)

try:
    from PyQt6.QtWidgets import QApplication
    from gui.theme import THEMES
    from gui.pdf_viewer import PdfViewer
    from gui.synctex import forward_search, reverse_search
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core", "derle.sh"))

# Tanımlı içerikli örnek belge — satır numaraları biliniyor (TARGET_LINE aşağıda)
SAMPLE_TEX = "\n".join([
    r"\documentclass{article}",
    r"\usepackage{amsmath}",
    r"\begin{document}",
    r"\section{Introduction}",
    r"This is the first paragraph with regular text content.",
    r"\section{Methodology}",
    r"Here we describe the methodology used in this study in detail.",
    r"\begin{equation}",
    r"E = mc^2",
    r"\end{equation}",
    r"\section{Results}",
    r"The results are very interesting and clearly significant.",
    r"\end{document}",
]) + "\n"

TARGET_LINE = 7  # "Here we describe the methodology used in this study in detail."


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="module")
def compiled():
    """Derle ve (tex_path, pdf_path, synctex_dir) döndür.

    synctex_dir, .synctex.gz içeren ayrı bir temp dizindir (uygulamanın
    _on_compile_finished'ta .gz'i _synctex_dir'e taşımasının taklidi).
    """
    d = tempfile.mkdtemp(prefix="synctex_src_")
    tex = os.path.join(d, "doc.tex")
    with open(tex, "w") as f:
        f.write(SAMPLE_TEX)
    r = subprocess.run(["bash", _SCRIPT, tex], capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, f"derleme başarısız (exit {r.returncode}):\n{r.stdout[-400:]}"
    pdf = tex[:-4] + ".pdf"
    assert os.path.exists(pdf), "PDF üretilmedi"

    synctex_dir = tempfile.mkdtemp(prefix="synctex_gz_")
    gz = tex[:-4] + ".synctex.gz"
    assert os.path.exists(gz), ".synctex.gz üretilmedi"
    shutil.move(gz, os.path.join(synctex_dir, "doc.synctex.gz"))

    yield tex, pdf, synctex_dir

    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(synctex_dir, ignore_errors=True)


# --- İleri arama (kaynak → PDF) ---


def test_forward_search_resolves_page_and_coords(compiled):
    """forward_search kaynak satırı geçerli bir PDF sayfa/koordinata çözmelidir."""
    tex, pdf, synctex_dir = compiled
    result = forward_search(tex, TARGET_LINE, 1, pdf, synctex_dir)
    assert result is not None, "forward_search eşleşme bulamadı"
    assert result.page >= 1
    assert result.y > 0


def test_forward_creates_pdf_highlight(qapp, compiled):
    """İleri arama PdfViewer'da highlight oluşturmalı ve doğru sayfaya gitmeli."""
    tex, pdf, synctex_dir = compiled
    result = forward_search(tex, TARGET_LINE, 1, pdf, synctex_dir)
    assert result is not None

    viewer = PdfViewer(theme=next(iter(THEMES.values())))
    viewer.resize(800, 1000)
    viewer.show()
    qapp.processEvents()
    assert viewer.load_pdf(pdf)
    qapp.processEvents()

    viewer.scroll_to_position(
        result.page, result.x, result.y,
        result.left, result.width, result.height,
    )
    qapp.processEvents()

    assert viewer._highlight_label is not None, "highlight oluşturulmadı"
    assert viewer._current_page == result.page - 1, "yanlış sayfaya gidildi"


# --- Geri arama (PDF → kaynak) ---


def test_reverse_search_returns_source_file(compiled):
    """reverse_search kaynak dosyasını ve geçerli bir satır döndürmeli."""
    tex, pdf, synctex_dir = compiled
    fwd = forward_search(tex, TARGET_LINE, 1, pdf, synctex_dir)
    rev = reverse_search(fwd.page, fwd.x, fwd.y, pdf, synctex_dir)
    assert rev is not None
    assert rev.file_path.endswith("doc.tex")
    assert rev.line >= 1


def test_forward_reverse_roundtrip_exact(compiled):
    """Kaynak satır → PDF → kaynak: temiz belgede birebir doğru olmalı (off-by 0).

    Regression: bozuk belgede (örn. geçersiz _ karakteri) off-by-one gözlenmişti;
    temiz belgede synctex round-trip tam doğru çalışmalı.
    """
    tex, pdf, synctex_dir = compiled
    fwd = forward_search(tex, TARGET_LINE, 1, pdf, synctex_dir)
    rev = reverse_search(fwd.page, fwd.x, fwd.y, pdf, synctex_dir)
    assert rev is not None
    assert rev.line == TARGET_LINE, f"round-trip kayması: {rev.line} != {TARGET_LINE}"
