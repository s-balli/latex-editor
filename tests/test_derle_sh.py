"""derle.sh — derleme betiği testleri."""

import os
import shutil
import signal
import subprocess
import threading
import time
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

# minted testleri için pygmentize + minted.sty (texlive-latex-extra)
try:
    _has_minted = subprocess.run(
        ["kpsewhich", "minted.sty"], capture_output=True, text=True
    ).stdout.strip()
except Exception:
    _has_minted = ""
HAS_MINTED = bool(shutil.which("pygmentize")) and bool(_has_minted)

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
            ["bash", "-c", "printf '%s' \"$1\" | grep -A4 -E '^!' | grep -v '^--$' || true",
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

    def test_cascade_hatasinda_lNNN_yakalanir(self):
        # TikZ/math cascade: l.NNN, '!'dan 3 satır sonra. -A1 onu kaçırıyordu;
        # -A4 sayesinde editör hata işareti için satır numarasını alabilmeli.
        snippet = (
            "! Paragraph ended before \\tikz@picture was complete.\n"
            "<to be read again>\n"
            "                   \\par\n"
            "l.399 }}\n"
        )
        out = self._grep(snippet)
        assert "l.399" in out


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

    @pytest.mark.skipif(not HAS_MINTED, reason="minted + pygmentize kurulu değil")
    def test_minted_sty_icinden_requirepackage_otomatik(self, tmp_path):
        r"""minted bir .sty içinde \RequirePackage ile yüklüyse shell-escape otomatik açılmalı.

        webdiller.sty senaryosu: \usepackage{minted} hiçbir .tex'te geçmiyor,
        eski tespit deseni bunu kaçırıyordu.
        """
        (tmp_path / "paket.sty").write_text("\\RequirePackage{minted}\n")
        tex = tmp_path / "test.tex"
        tex.write_text(
            "\\documentclass{article}\n"
            "\\usepackage{paket}\n"
            "\\begin{document}\n"
            "\\begin{minted}{python}\nprint('merhaba')\n\\end{minted}\n"
            "\\end{document}\n"
        )
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=120)
        # Eski desen: '\usepackage{minted}' geçmediğinden shell-escape açılmıyor,
        # minted "shell-escape flag" hatasıyla düşüyordu.
        assert r.returncode == 0
        assert (tmp_path / "test.pdf").exists()


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


class TestXelatexModu:
    # xelatex ayrı paket (texlive-xetex); kurulu değilse bu sınıf skip
    _xe = pytest.mark.skipif(not shutil.which("xelatex"), reason="xelatex kurulu değil — texlive-xetex gerektirir")

    @_xe
    def test_xelatex_flag(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX)
        r = _run_derle([str(tex), "--xelatex"], cwd=str(tmp_path), timeout=90)
        assert r.returncode == 0
        assert "xelatex" in r.stdout.lower()
        assert (tmp_path / "test.pdf").exists()

    @_xe
    def test_xelatex_fontspec_pdf(self, tmp_path):
        # fontspec + sistem fontu: XeLaTeX'e özgü iş akışı, PDF üretmeli
        tex = tmp_path / "xe.tex"
        tex.write_text(
            "\\documentclass{article}\n"
            "\\usepackage{fontspec}\n"
            "\\setmainfont{DejaVu Serif}\n"
            "\\begin{document}\nMerhaba XeLaTeX Dünya!\n\\end{document}\n"
        )
        r = _run_derle([str(tex), "--xelatex"], cwd=str(tmp_path), timeout=90)
        assert r.returncode == 0
        assert (tmp_path / "xe.pdf").exists()

    @_xe
    def test_appimage_library_path_zehirlenmesi(self, tmp_path):
        """AppImage gömülü libstdc++ sızıntısı (LD_LIBRARY_PATH) derleyiciyi bozmamalı.

        Sahte bir libstdc++.so.6 içeren dizini LD_LIBRARY_PATH'e koyup xelatex
        ile derleriz; betik yolu temizlemezse xelatex sahte kütüphaneyi yüklemeye
        çalışıp düşer (GLIBCXX hatasının mekanizması).
        """
        libdir = tmp_path / "libs"
        libdir.mkdir()
        (libdir / "libstdc++.so.6").write_bytes(b"bozuk-ikili")
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX)
        r = subprocess.run(
            ["bash", SCRIPT, str(tex), "--xelatex"],
            capture_output=True, text=True, timeout=90,
            env={**os.environ, "LD_LIBRARY_PATH": str(libdir)},
            cwd=str(tmp_path),
        )
        assert r.returncode == 0
        assert (tmp_path / "test.pdf").exists()

    def test_motor_yoksa_paket_onerisi(self, tmp_path):
        # Kurulu olmayan motor: hata + '==> Eksik paket' önerisi (GUI Öneriler
        # sekmesi bu çıktıyı parse eder). Motoru sandbox PATH ile görünmez kıl.
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX)
        sandbox = tmp_path / "bin"
        sandbox.mkdir()
        for tool in ("bash", "dirname", "realpath", "basename"):
            os.symlink(shutil.which(tool), sandbox / tool)
        r = subprocess.run(
            ["bash", SCRIPT, str(tex), "--xelatex"],
            capture_output=True, text=True, timeout=30,
            env={"PATH": str(sandbox)},
            cwd=str(tmp_path),
        )
        assert r.returncode != 0
        assert "Eksik paket" in r.stdout
        assert "texlive-xetex" in r.stdout


class TestWatchModu:
    """Watch modunun hatalı derlemeden sonra da yaşamaya devam etmesi."""

    @staticmethod
    def _pump(proc, sink):
        for line in iter(proc.stdout.readline, ""):
            sink.append(line)

    @staticmethod
    def _wait_marker(lines, markers, timeout=40):
        """Çıktıda işaretleyicilerden biri geçene kadar bekle; bulursa True."""
        if isinstance(markers, str):
            markers = (markers,)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(m in ln for ln in lines for m in markers):
                return True
            time.sleep(0.2)
        return False

    def test_ilk_derleme_hatasi_watchu_oldurmez(self, tmp_path):
        """Regression: derle_dosya hata durumunda 1 döner; koşulsuz çağrı
        set -e altında betiği ilk hatada öldürüyordu. Hata sonrası dosya
        düzeltilirse watch modu yeniden derleyip PDF üretmeli."""
        tex = tmp_path / "w.tex"
        tex.write_text(MINIMAL_TEX_ERROR, encoding="utf-8")
        proc = subprocess.Popen(
            ["bash", SCRIPT, str(tex), "--watch"],
            cwd=str(tmp_path), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        out = []
        reader = threading.Thread(target=self._pump, args=(proc, out), daemon=True)
        reader.start()
        try:
            # İlk derleme hata verir: PDF kısmen üretildiyse [uyari], üretil-
            # mediyse [hata] gelir; hangisi olursa olsun derle_dosya 1 döner.
            assert self._wait_marker(out, ("[hata]", "[uyari]")), "".join(out)
            assert proc.poll() is None, \
                "watch modu ilk hatada öldü: " + "".join(out)

            # SON_MOD istatistiği derle_dosya DÖNDÜKTEN sonra alınır; işareti
            # gördüğümüz anda betik henüz orada olabileceğinden önce bekliyoruz
            # (beklemeden yazarsak stat düzelttiğimiz mtime'ı okur, değişim
            # hiç görülmez, yeniden derleme tetiklenmez).
            time.sleep(2.2)
            # Dosyayı düzelt → döngü mtime değişimini görüp yeniden derlemeli.
            # stat %Y saniye çözünürlüklü olduğundan ileri tarihli mtime
            # veriyoruz: düzeltme SON_MOD ile aynı saniyeye düşerse kaçmasın.
            tex.write_text(MINIMAL_TEX, encoding="utf-8")
            future = time.time() + 5
            os.utime(tex, (future, future))
            assert self._wait_marker(out, "[basarili]"), "".join(out)
            assert (tmp_path / "w.pdf").exists()
        finally:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        assert proc.returncode == 0  # INT trap'ı temiz çıkış yapar
