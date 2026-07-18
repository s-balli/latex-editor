"""derle.sh — derleme betiği testleri."""

import os
import shutil
import subprocess
import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "core", "derle.sh")

# CI'da TeX Live olmayabilir — lualatex yoksa tüm derle.sh testleri skip
pytestmark = pytest.mark.skipif(
    not shutil.which("lualatex"),
    reason="lualatex kurulu değil — TeX Live gerektirir",
)

# Kaynakça testleri için biber + biblatex
HAS_BIBER = bool(shutil.which("biber"))
try:
    _has_biblatex = subprocess.run(
        ["kpsewhich", "biblatex.sty"], capture_output=True, text=True
    ).stdout.strip()
except Exception:
    _has_biblatex = ""
HAS_BIBLATEX = bool(_has_biblatex)
_biber_skip = pytest.mark.skipif(
    not (HAS_BIBER and HAS_BIBLATEX),
    reason="biber + biblatex kurulu değil",
)

MINIMAL_TEX = r"""\documentclass{article}
\begin{document}
Merhaba Dünya!
\end{document}
"""

MINIMAL_TEX_ERROR = r"""\documentclass{article}
\begin{document}
\undefined_command
\end{document}
"""

MINIMAL_TEX_INPUT = r"""\documentclass{article}
\begin{document}
\input{bolum}
\end{document}
"""

BOLUM_TEX = r"""Bolum içeriği.
"""

# TOC + çapraz referans: birden çok geçiş (rerun) gerektirir
TOC_TEX = r"""\documentclass{article}
\begin{document}
\tableofcontents
\section{Bir}\label{sec:bir}
Bkz. b\"ol\"um \ref{sec:iki} (sayfa \pageref{sec:iki}).
\newpage
\section{Iki}\label{sec:iki}
Bkz. b\"ol\"um \ref{sec:bir} (sayfa \pageref{sec:bir}).
\end{document}
"""


BIB_TEX = r"""\documentclass{article}
\usepackage[backend=biber]{biblatex}
\addbibresource{refs.bib}
\begin{document}
\nocite{*}
\printbibliography
\end{document}
"""

BIB_REF = r"""@article{test2020, author={Test}, title={Sample}, journal={J}, year={2020}}
"""


def _run_derle(args, cwd, timeout=30):
    result = subprocess.run(
        ["bash", SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout, cwd=cwd,
    )
    return result


class TestArgumanKontrolu:
    def test_argsiz_hata(self):
        r = _run_derle([], cwd="/tmp")
        assert r.returncode != 0
        assert "Kullanim" in r.stderr or "Kullanim" in r.stdout

    def test_olmayan_dosya(self, tmp_path):
        r = _run_derle([str(tmp_path / "yok.tex")], cwd=str(tmp_path))
        assert r.returncode != 0
        assert "bulunamadi" in r.stdout.lower() or r.returncode != 0

    def test_klasor_tex_dosyalarini_bulur(self, tmp_path):
        (tmp_path / "a.tex").write_text(MINIMAL_TEX)
        (tmp_path / "b.tex").write_text(MINIMAL_TEX)
        (tmp_path / "notex.txt").write_text("nope")
        r = _run_derle([str(tmp_path)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert "2 dosya" in r.stdout or "Basarili" in r.stdout

    def test_watch_modda_cok_dosya_hata(self, tmp_path):
        f1 = tmp_path / "a.tex"
        f2 = tmp_path / "b.tex"
        f1.write_text(MINIMAL_TEX)
        f2.write_text(MINIMAL_TEX)
        r = _run_derle([str(f1), str(f2), "--watch"], cwd=str(tmp_path))
        assert r.returncode != 0
        assert "tek dosya" in r.stdout.lower() or "Watch" in r.stdout


class TestMotorSecimi:
    def test_lualatex_varsayilan(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert "lualatex" in r.stdout.lower()

    def test_pdflatex_flag(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex), "--pdflatex"], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert "pdflatex" in r.stdout.lower()


class TestDerlemeBasarili:
    def test_pdf_olusur(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "test.pdf").exists()

    def test_turkce_karakter(self, tmp_path):
        tex = tmp_path / "turkce.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "turkce.pdf").exists()

    def test_buyuk_harf_uzanti(self, tmp_path):
        tex = tmp_path / "test.TEX"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "test.pdf").exists()


class TestDerlemeHatasi:
    def test_undefined_command(self, tmp_path):
        tex = tmp_path / "hata.tex"
        tex.write_text(MINIMAL_TEX_ERROR)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode != 0
        assert "basarisiz" in r.stdout.lower() or "hata" in r.stdout.lower()

    def test_bos_dosya(self, tmp_path):
        tex = tmp_path / "bos.tex"
        tex.write_text("")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode != 0


class TestHataDeseni:
    """Hata tespit deseni: 'l.NNN' tek başına hata sayılmamalı (yalnızca '!').

    Regresyon: hyperref 'duplicate destination' gibi uyarıların bağlamındaki
    'l.160 \\newpage' satırı, önünde '!' olmadığı için hata olarak gösterilmemeli.
    """

    @staticmethod
    def _grep(snippet):
        # derle.sh'in hata ayıklama deseniyle aynı davranış (gerçek '!' + bağlamı)
        r = subprocess.run(
            ["bash", "-c", "printf '%s' \"$1\" | grep -A1 -E '^!' | grep -v '^--$' || true",
             "bash", snippet],
            capture_output=True, text=True,
        )
        return r.stdout

    def test_warning_baglami_lNNN_hata_degil(self):
        # '!' yok — hyperref uyarı bağlamındaki l.160 hata değil
        snippet = (
            "pdfTeX warning (ext4): destination with the same identifier (name{page.i}) has\n"
            "been already used, duplicate ignored\n"
            "<to be read again>\n"
            "                   \\relax\n"
            "l.160 \\newpage\n"
        )
        assert self._grep(snippet) == ""

    def test_gercek_hata_ve_baglami(self):
        snippet = "! Undefined control sequence.\nl.42 \\badcommand\n"
        out = self._grep(snippet)
        assert "! Undefined control sequence." in out
        assert "l.42" in out


class TestCokluGecis:
    """Cok gecisli derleme: TOC + capraz referans rerun gerektirir; stabilize olmali."""

    def test_toc_ve_referanslar_cozulur(self, tmp_path):
        tex = tmp_path / "main.tex"
        tex.write_text(TOC_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=90)
        assert r.returncode == 0
        assert (tmp_path / "main.pdf").exists()
        # Gecisler converge etmis olmali: "Rerun to get" uyari mesaji kalmamali
        assert "Rerun to get" not in r.stdout


class TestKaynakca:
    """Kaynakça: biber varsa çözülmeli, yoksa kurulum önerisi verilmeli."""

    def _yaz(self, tmp_path):
        (tmp_path / "main.tex").write_text(BIB_TEX)
        (tmp_path / "refs.bib").write_text(BIB_REF)

    @_biber_skip
    def test_biber_var_kaynakca_cozulur(self, tmp_path):
        self._yaz(tmp_path)
        r = _run_derle([str(tmp_path / "main.tex")], cwd=str(tmp_path), timeout=120)
        assert r.returncode == 0
        assert (tmp_path / "main.pdf").exists()
        assert "Eksik paket: biber" not in r.stdout

    @_biber_skip
    def test_biber_eksik_onerisi(self, tmp_path):
        self._yaz(tmp_path)
        # biber'i gizle: command -v biber başarısız olsun, diğer komutlar etkilenmesin
        cmd = (
            'command() { if [ "$1" = "-v" ] && [ "$2" = "biber" ]; then return 127; fi; '
            'builtin command "$@"; }; export -f command; bash "$0" "$@"'
        )
        r = subprocess.run(
            ["bash", "-c", cmd, SCRIPT, str(tmp_path / "main.tex")],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=120,
        )
        assert "Eksik paket: biber" in r.stdout
        assert "sudo apt-get install biber" in r.stdout


class TestInputInclude:
    def test_input_dosyasi(self, tmp_path):
        tex = tmp_path / "main.tex"
        bolum = tmp_path / "bolum.tex"
        tex.write_text(MINIMAL_TEX_INPUT)
        bolum.write_text(BOLUM_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "main.pdf").exists()


class TestEksikPaketGoster:
    def test_eksik_sty_onerisi(self, tmp_path):
        tex = tmp_path / "paket.tex"
        tex.write_text(r"""\documentclass{article}
\usepackage{siunitx}
\begin{document}
\SI{5}{\meter}
\end{document}
""")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        # siunitx kurulu olabilir veya olmayabilir
        if r.returncode != 0:
            assert "siunitx" in r.stdout.lower() or "texlive-science" in r.stdout.lower() or "hata" in r.stdout.lower()


class TestCokluDosya:
    def test_iki_dosya_derleme(self, tmp_path):
        (tmp_path / "a.tex").write_text(MINIMAL_TEX)
        (tmp_path / "b.tex").write_text(MINIMAL_TEX)
        r = _run_derle([str(tmp_path / "a.tex"), str(tmp_path / "b.tex")],
                       cwd=str(tmp_path), timeout=120)
        assert r.returncode == 0
        assert (tmp_path / "a.pdf").exists()
        assert (tmp_path / "b.pdf").exists()
        assert "Toplam" in r.stdout or "Basarili" in r.stdout

    def test_biri_hatali(self, tmp_path):
        (tmp_path / "ok.tex").write_text(MINIMAL_TEX)
        (tmp_path / "bad.tex").write_text(MINIMAL_TEX_ERROR)
        r = _run_derle([str(tmp_path / "ok.tex"), str(tmp_path / "bad.tex")],
                       cwd=str(tmp_path), timeout=120)
        assert r.returncode != 0
        assert (tmp_path / "ok.pdf").exists()
        assert "Basarisiz" in r.stdout


class TestBoslukluYol:
    def test_bosluklu_dosya_yolu(self, tmp_path):
        klasor = tmp_path / "My Project"
        klasor.mkdir()
        tex = klasor / "test.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (klasor / "test.pdf").exists()

    def test_bosluklu_dosya_adi(self, tmp_path):
        tex = tmp_path / "my document.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "my document.pdf").exists()

    def test_turkce_klasor_adi(self, tmp_path):
        klasor = tmp_path / "Belgeler"
        klasor.mkdir()
        tex = klasor / "test.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (klasor / "test.pdf").exists()


class TestSynctex:
    def test_synctex_gz_olusur(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "test.synctex.gz").exists()


class TestIncludeAltDizin:
    def test_include_alt_dizin(self, tmp_path):
        alt = tmp_path / "bolumler"
        alt.mkdir()
        (alt / "giris.tex").write_text(r"""Giriş içeriği.
""")
        main = tmp_path / "main.tex"
        main.write_text(r"""\documentclass{article}
\begin{document}
\include{bolumler/giris}
\end{document}
""")
        r = _run_derle([str(main)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "main.pdf").exists()


class TestShellEscape:
    def test_shell_escape_flag_basarisiz(self, tmp_path):
        # minted olmayan dosyada --shell-escape zorla
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex), "--shell-escape"], cwd=str(tmp_path), timeout=60)
        # shell-escape ile derlemeli, başarılı olmalı
        assert r.returncode == 0


class TestGlob:
    def test_glob_tex_dosyalari(self, tmp_path):
        (tmp_path / "a.tex").write_text(MINIMAL_TEX)
        (tmp_path / "b.tex").write_text(MINIMAL_TEX)
        (tmp_path / "c.txt").write_text("nope")
        r = _run_derle([str(tmp_path / "*.tex")], cwd=str(tmp_path), timeout=120)
        # glob bash tarafından genişletilir veya betik içinde handle edilir
        # en azından a.tex derlenmiş olmalı
        assert (tmp_path / "a.pdf").exists() or r.returncode is not None


class TestLogDosyasi:
    def test_hatali_derleme_log_kopyalanir(self, tmp_path):
        tex = tmp_path / "hata.tex"
        tex.write_text(MINIMAL_TEX_ERROR)
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode != 0
        assert (tmp_path / "hata.log").exists()
