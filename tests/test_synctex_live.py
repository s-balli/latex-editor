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

import pytest

from tests.kabuk import calisan_bash

# Derleme `bash` ile yapılıyor; Windows'ta düz "bash" WSL shim'ine gidip
# `C:\...` yolunu açamıyor ve bu dosya 7 HATA veriyordu (tests/kabuk.py).
BASH = calisan_bash()


def _wsl_araclari_var() -> bool:
    """WSL'de lualatex ve synctex var mı (Windows kolu oradan koşuyor)."""
    if not shutil.which("wsl"):
        return False
    try:
        r = subprocess.run(
            ["wsl", "-e", "bash", "-lc",
             "command -v lualatex >/dev/null && command -v synctex >/dev/null"],
            capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


# Araçlar hangi tarafta aranacak PLATFORMA bağlı: Windows'ta uygulama hem
# derlemeyi hem `synctex`i WSL'in içinde çalıştırıyor, yerli MiKTeX'in
# varlığı bu testler için bir şey söylemiyor.
if sys.platform == "win32":
    _ATLAMA = ("" if _wsl_araclari_var()
               else "WSL'de lualatex + synctex yok, Windows kolu oradan koşuyor")
else:
    _ATLAMA = ("çalışan bash yok" if not BASH
               else "" if (shutil.which("lualatex") and shutil.which("synctex"))
               else "lualatex + synctex kurulu değil, TeX Live gerektirir")
pytestmark = pytest.mark.skipif(bool(_ATLAMA), reason=_ATLAMA)

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


def _derleme_komutu(tex: str) -> list:
    r"""Belgeyi UYGULAMANIN o platformda kullandigi yoldan derleyen komut.

    Windows'ta uygulama `derle.sh`i WSL'in ICINDE kosturuyor
    (`compiler._start_windows`) ve `gui.synctex` de `wsl -e synctex`
    cagiriyor. Test ise Git Bash + yerli MiKTeX ile derliyordu: `.synctex.gz`
    Windows yollariyla yaziliyor, sorgu ise `/mnt/c/...` ile geliyordu ve
    adlar eslesmedigi icin `forward_search` BOS donuyordu (yedi test).

    Kusur urunde degil, olcumun kurdugu KARMA takimda: uygulama hicbir zaman
    Git Bash + MiKTeX ile derlemiyor. Komut artik uygulamayla ayni koldan
    gidiyor; boylece SyncTeX'in Windows kolu (yol cevirisi dahil) ilk kez
    gercekten olculuyor.
    """
    if sys.platform == "win32":
        from core.paths import windows_to_wsl
        return ["wsl", "-e", "bash", windows_to_wsl(_SCRIPT),
                windows_to_wsl(tex)]
    return [BASH, _SCRIPT, tex]


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
    with open(tex, "w", encoding="utf-8") as f:
        f.write(SAMPLE_TEX)
    r = subprocess.run(_derleme_komutu(tex), capture_output=True, text=True,
                       timeout=180, encoding="utf-8")
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


def test_AYRI_DIZIN_bayragi_olmadan_bulunamiyor(compiled):
    r"""KARŞI KOL: `.synctex.gz` ayrı dizindeyken `-d` VERİLMEZSE arama
    başarısız olmalı.

    Bu dosyadaki öbür testler `.gz`yi ayrı bir dizine taşıyıp `synctex_dir`
    geçiyor, yani uygulamanın gerçek düzenini taklit ediyor. Ama `-d`
    gerçekten yük taşıyor mu, bunu hiçbiri göstermiyordu: synctex dosyayı
    başka bir yoldan bulsaydı testler yine geçerdi.

    ÖLÇÜLDÜ (2026-09-12, taze derlenmiş bir belgeyle üç hâl):
        gz PDF'in yanında, -d yok   -> sayfa 1, ters arama satır 7
        gz ayrı dizinde,  -d YOK    -> sonuç YOK
        gz ayrı dizinde,  -d VAR    -> sayfa 1, ters arama satır 7
    """
    tex, pdf, synctex_dir = compiled
    # önce -d ile çalıştığı sabitleniyor (kapı boş koşmasın)
    assert forward_search(tex, TARGET_LINE, 1, pdf, synctex_dir) is not None

    assert forward_search(tex, TARGET_LINE, 1, pdf, "") is None, \
        "-d olmadan da bulundu: bayrak yük taşımıyor ya da .gz hâlâ yanında"


# --- Sembolik bagli yol (macOS: /var -> /private/var) ---


class TestSembolikBagliYol:
    r"""Proje sembolik bag altindaysa SyncTeX calismali.

    macOS'ta `/tmp` ve `/var` birer sembolik bag (`/private/...`) ve
    gecici dizinler orada duruyor. Derleyici belgeyi bir yol bicimiyle
    kaydediyor; `synctex` oteki bicimle sorulunca ADI ESLESTIREMIYOR ve
    BOS donuyor. Hata yok, cikis kodu 0, sonuc yok.

    OLCULDU (2026-09-18, macos-15, ayni belge ayni komutla, yalniz yol
    bicimi degiserek):

        /var/folders/.../tmp.X       Page satiri: 0   (bulamiyor)
        /private/var/folders/.../X   Page satiri: 1   (buluyor)

    Bes canli SyncTeX testinin besi de macOS'ta bu yuzden dusuyordu.

    Kapi Linux'ta da anlamli: kullanici projesini sembolik bag altinda
    tutabiliyor. Burada bag ELLE kuruluyor, yani platformdan bagimsiz.
    """

    def test_BAG_altindaki_projede_ileri_arama_calisiyor(self, compiled,
                                                         tmp_path):
        tex, pdf, synctex_dir = compiled
        gercek_dizin = os.path.dirname(tex)
        bag = tmp_path / "bagli"
        try:
            os.symlink(gercek_dizin, bag)
        except (OSError, NotImplementedError):
            pytest.skip("sembolik bag kurulamiyor")

        bagli_tex = os.path.join(str(bag), os.path.basename(tex))
        bagli_pdf = os.path.join(str(bag), os.path.basename(pdf))
        sonuc = forward_search(bagli_tex, TARGET_LINE, 1, bagli_pdf,
                               synctex_dir)
        assert sonuc is not None, "bagli yolda forward_search bos dondu"
        assert sonuc.page >= 1

    def test_BAGSIZ_yol_da_calismaya_devam_ediyor(self, compiled):
        """Karsi kol: cozme, calisan yolu bozmamali."""
        tex, pdf, synctex_dir = compiled
        sonuc = forward_search(tex, TARGET_LINE, 1, pdf, synctex_dir)
        assert sonuc is not None
        assert sonuc.page >= 1

    def test_COZME_ISLEVI_bagi_gercekten_aciyor(self, tmp_path):
        """Islevin kendisi: bag verilince hedefi donmeli.

        `synctex` cagirmiyor, yani TeX kurulu olmayan yerde de kosuyor.
        """
        from gui.synctex import _gercek_yol

        hedef = tmp_path / "hedef"
        hedef.mkdir()
        bag = tmp_path / "bag"
        try:
            os.symlink(hedef, bag)
        except (OSError, NotImplementedError):
            pytest.skip("sembolik bag kurulamiyor")
        assert _gercek_yol(str(bag)) == os.path.realpath(str(hedef))

    def test_COZULEMEYEN_yol_oldugu_gibi_donuyor(self):
        """Var olmayan yol istisna atmamali; synctex kendi hatasini versin."""
        from gui.synctex import _gercek_yol

        yok = os.path.join("olmayan_dizin_12345", "yok.tex")
        assert _gercek_yol(yok)
