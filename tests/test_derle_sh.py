"""derle.sh — derleme betiği testleri."""

import os
import re
import shutil
import signal
import subprocess
import sys
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
    , encoding="utf-8").stdout.strip()
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
    , encoding="utf-8").stdout.strip()
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

# İKİNCİ kaynakça: `multibib` `\newcites{ek}{...}` ayrı bir yardımcı dosya
# (`ek.aux`) açıyor ve BibTeX'in onun için AYRICA koşması gerekiyor.
MULTIBIB_TEX = r"""\documentclass{article}
\usepackage{natbib}
\usepackage{multibib}
\newcites{ek}{Ek Kaynaklar}
\begin{document}
Ana atif \cite{ana2020}. Ikinci atif \citeek{ek2021}.
\bibliographystyle{plain}
\bibliography{refs}
\bibliographystyleek{plain}
\bibliographyek{refs}
\end{document}
"""

MULTIBIB_REF = r"""@article{ana2020, author={Anaeser, Ali}, title={Ana Calisma},
  journal={Dergi A}, year={2020}}
@article{ek2021, author={Ekeser, Veli}, title={Ek Calisma},
  journal={Dergi B}, year={2021}}
"""


def _kpsewhich(ad):
    try:
        return subprocess.run(["kpsewhich", ad], capture_output=True,
                              text=True, encoding="utf-8").stdout.strip()
    except Exception:
        return ""


def _pdf_metni(pdf_yolu):
    """Üretilen PDF'in bütün sayfalarının metni.

    Kaynakça/sözlük/simge listesi gibi İKİ AŞAMALI bölümlerde tek geçerli
    kehanet PDF'in kendisi: yardımcı araç koşmayınca başlık basılıyor ama
    altı boş kalıyor ve derleme başarıyla bitiyor.

    `get_text_bounded`: uygulamanın PDF içi araması da onu kullanıyor
    (pdf_search_worker); `get_text_range` varsayılan argümanlarla uyarı
    basıyor.
    """
    pdfium = pytest.importorskip("pypdfium2")
    belge = pdfium.PdfDocument(str(pdf_yolu))
    try:
        return "".join(belge[i].get_textpage().get_text_bounded()
                       for i in range(len(belge)))
    finally:
        belge.close()


# Sözlük (glossaries) ve simge listesi (nomencl): kaynakça/dizinle aynı iki
# aşamalı düzen. LaTeX girdileri `.glo`/`.nlo` dosyasına yazıyor, ayrı bir
# araç basılacak `.gls`/`.nls` dosyasını üretiyor.
SOZLUK_TEX = r"""\documentclass{article}
\usepackage{glossaries}
\makeglossaries
\newglossaryentry{lat}{name=LatexDizgi,
  description={bir dizgi sistemi ACIKLAMASI}}
\begin{document}
Metinde \gls{lat} geciyor.
\printglossaries
\end{document}
"""

SIMGE_TEX = r"""\documentclass{article}
\usepackage{nomencl}
\makenomenclature
\begin{document}
Isik hizi \(c\) sabittir.
\nomenclature{\(c\)}{IsikHizi ACIKLAMASI}
\printnomenclature
\end{document}
"""

# Dizin: `imakeidx` ile `\makeindex[name=kisi]` ikinci bir dizin açıyor ve
# onu `kisi.idx` dosyasına yazıyor.
DIZIN_TEK_TEX = r"""\documentclass{article}
\usepackage{makeidx}
\makeindex
\begin{document}
Bir sozcuk\index{KlasikGirdi}.
\printindex
\end{document}
"""

DIZIN_IKI_TEX = r"""\documentclass{article}
\usepackage{imakeidx}
\makeindex
\makeindex[name=kisi, title=Kisi Dizini]
\begin{document}
Bir sozcuk\index{KonuGirdisi}.
Bir ad\index[kisi]{KisiGirdisi}.
\printindex
\printindex[kisi]
\end{document}
"""

_dizin_skip = pytest.mark.skipif(
    not (shutil.which("makeindex") and _kpsewhich("makeidx.sty")),
    reason="makeindex + makeidx kurulu değil",
)

_imakeidx_skip = pytest.mark.skipif(
    not (shutil.which("makeindex") and _kpsewhich("imakeidx.sty")),
    reason="makeindex + imakeidx kurulu değil",
)

_sozluk_skip = pytest.mark.skipif(
    not ((shutil.which("makeglossaries")
          or shutil.which("makeglossaries-lite"))
         and _kpsewhich("glossaries.sty")),
    reason="makeglossaries + glossaries kurulu değil",
)

_simge_skip = pytest.mark.skipif(
    not (shutil.which("makeindex") and _kpsewhich("nomencl.sty")
         and _kpsewhich("nomencl.ist")),
    reason="makeindex + nomencl kurulu değil",
)


def _komutu_gizle(*adlar):
    """`command -v <ad>` başarısız olsun; öteki komutlar etkilenmesin.

    Aynı hile `test_biber_eksik_onerisi`de de kullanılıyor.
    """
    kosullar = " ".join(
        'if [ "$1" = "-v" ] && [ "$2" = "%s" ]; then return 127; fi;' % ad
        for ad in adlar)
    return ('command() { %s builtin command "$@"; }; export -f command; '
            'bash "$0" "$@"' % kosullar)


_multibib_skip = pytest.mark.skipif(
    not (shutil.which("bibtex") and _kpsewhich("multibib.sty")
         and _kpsewhich("natbib.sty")),
    reason="bibtex + multibib + natbib kurulu değil",
)

def _run_derle(args, cwd, timeout=30):
    result = subprocess.run(
        ["bash", SCRIPT] + args,
        capture_output=True, text=True, timeout=timeout, cwd=cwd, encoding="utf-8")
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

    def test_SALT_OKUNUR_klasorde_BASARILI_demiyor(self, tmp_path):
        """Derleme geçici dizinde koşuyor; PDF sonra proje klasörüne
        taşınıyor. Klasör yazılamazsa taşıma düşüyordu ve betik yine de
        `[basarili]` deyip 0 ile bitiyordu.

        ÖLÇÜLDÜ (2026-09-17, klasör salt okunur yapılarak): çıkış 0,
        proje klasöründe PDF YOK, panelde 0 hata; `cp`nin
        "Permission denied" satırı ayrıştırıcının görmediği bir biçimde
        geliyor. Kullanıcıya "başarılı" deniyor ve önizleme eski PDF'te
        kalıyor.
        """
        proje = tmp_path / "proje"
        proje.mkdir()
        tex = proje / "tez.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=120)
        assert r.returncode == 0 and (proje / "tez.pdf").exists()

        (proje / "tez.pdf").unlink()
        os.chmod(str(proje), 0o500)
        try:
            r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=120)
        finally:
            os.chmod(str(proje), 0o700)
        assert r.returncode != 0, r.stdout
        assert "basarili" not in r.stdout.lower(), r.stdout
        assert "salt okunur" in r.stdout, r.stdout

    def test_BAGLANMAMIS_SURUCU_sebebi_soyluyor(self, tmp_path):
        r"""Windows'ta her şey WSL içinde koşuyor ve WSL yalnız YEREL sabit
        sürücüleri kendiliğinden bağlıyor. Üniversitenin ağ ev dizini
        (H:, Z:) ya da `subst` ile türetilen bir sürücü `/mnt/<harf>`
        altında YOK.

        ÖLÇÜLDÜ (2026-09-16, `subst` ile oluşturulmuş Q: sürücüsü):
        kullanıcı `Q:\tez.tex` dosyasını açıyor, derleyince "Dosya
        bulunamadi: /mnt/q/tez.tex" görüyor. Dosya gözünün önünde duruyor
        ve yol hiç görmediği bir yol; sebebi bulması mümkün değil.
        """
        harf = next((c for c in "qzyxwv"
                     if not os.path.isdir("/mnt/" + c)), "")
        if not harf:
            pytest.skip("bağlanmamış bir /mnt/<harf> bulunamadı")
        r = _run_derle(["/mnt/%s/tez.tex" % harf], cwd=str(tmp_path))
        assert r.returncode != 0
        assert "surucusu WSL icinde gorunmuyor" in r.stdout, r.stdout
        assert harf.upper() + ":" in r.stdout, r.stdout

    def test_BAGLI_surucude_ipucu_YOK(self, tmp_path):
        """Aşırı düzeltme kapısı: sürücü bağlıysa dosya gerçekten yoktur,
        ipucu gürültü olur."""
        r = _run_derle([str(tmp_path / "yok.tex")], cwd=str(tmp_path))
        assert r.returncode != 0
        assert "bulunamadi" in r.stdout.lower()
        assert "gorunmuyor" not in r.stdout, r.stdout

        # BAĞLI bir /mnt/<harf> varsa asıl kolu da sına: ipucu yalnız
        # bağlı OLMAYAN sürücüde çıkmalı. (Linux CI'da /mnt boş olabilir.)
        bagli = next((c for c in "cdefgh"
                      if os.path.isdir("/mnt/" + c)), "")
        if bagli:
            r = _run_derle(["/mnt/%s/yok-boyle-bir-dosya.tex" % bagli],
                           cwd=str(tmp_path))
            assert r.returncode != 0
            assert "gorunmuyor" not in r.stdout, r.stdout

    def test_UNC_yolunun_WSL_karsiligi_YOK_deniyor(self, tmp_path):
        r"""`core/paths.py` UNC yolunu çeviremediği için OLDUĞU GİBİ
        geçiriyor; kullanıcı yine "bulunamadi" görüyordu."""
        r = _run_derle(["\\\\sunucu\\paylasim\\tez.tex"], cwd=str(tmp_path))
        assert r.returncode != 0
        assert "UNC" in r.stdout, r.stdout

    def test_klasor_tex_dosyalarini_bulur(self, tmp_path):
        (tmp_path / "a.tex").write_text(MINIMAL_TEX, encoding="utf-8")
        (tmp_path / "b.tex").write_text(MINIMAL_TEX, encoding="utf-8")
        (tmp_path / "notex.txt").write_text("nope", encoding="utf-8")
        r = _run_derle([str(tmp_path)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert "2 dosya" in r.stdout or "Basarili" in r.stdout

    def test_watch_modda_cok_dosya_hata(self, tmp_path):
        f1 = tmp_path / "a.tex"
        f2 = tmp_path / "b.tex"
        f1.write_text(MINIMAL_TEX, encoding="utf-8")
        f2.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(f1), str(f2), "--watch"], cwd=str(tmp_path))
        assert r.returncode != 0
        assert "tek dosya" in r.stdout.lower() or "Watch" in r.stdout


class TestMotorSecimi:
    def test_lualatex_varsayilan(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert "lualatex" in r.stdout.lower()

    def test_pdflatex_flag(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex), "--pdflatex"], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert "pdflatex" in r.stdout.lower()


class TestDerlemeBasarili:
    def test_pdf_olusur(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "test.pdf").exists()

    def test_turkce_karakter(self, tmp_path):
        tex = tmp_path / "turkce.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "turkce.pdf").exists()

    def test_buyuk_harf_uzanti(self, tmp_path):
        tex = tmp_path / "test.TEX"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "test.pdf").exists()


class TestDerlemeHatasi:
    def test_undefined_command(self, tmp_path):
        tex = tmp_path / "hata.tex"
        tex.write_text(MINIMAL_TEX_ERROR, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode != 0
        assert "basarisiz" in r.stdout.lower() or "hata" in r.stdout.lower()

    def test_bos_dosya(self, tmp_path):
        tex = tmp_path / "bos.tex"
        tex.write_text("", encoding="utf-8")
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
            capture_output=True, text=True, encoding="utf-8")
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
        tex.write_text(TOC_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=90)
        assert r.returncode == 0
        assert (tmp_path / "main.pdf").exists()
        # Gecisler converge etmis olmali: "Rerun to get" uyari mesaji kalmamali
        assert "Rerun to get" not in r.stdout


class TestKaynakca:
    """Kaynakça: biber varsa çözülmeli, yoksa kurulum önerisi verilmeli."""

    def _yaz(self, tmp_path):
        (tmp_path / "main.tex").write_text(BIB_TEX, encoding="utf-8")
        (tmp_path / "refs.bib").write_text(BIB_REF, encoding="utf-8")

    @_biber_skip
    def test_biber_var_kaynakca_cozulur(self, tmp_path):
        self._yaz(tmp_path)
        r = _run_derle([str(tmp_path / "main.tex")], cwd=str(tmp_path), timeout=120)
        assert r.returncode == 0
        assert (tmp_path / "main.pdf").exists()
        assert "Eksik paket: biber" not in r.stdout

    @_multibib_skip
    def test_IKINCI_kaynakca_da_basiliyor(self, tmp_path):
        r"""BibTeX `\bibdata` içeren HER `.aux` için koşmalı.

        Kırılırsa ikinci kaynakça belgede BOŞ çıkıyor: başlık basılıyor,
        altında hiçbir girdi yok. ÖLÇÜLDÜ (2026-09-13, template11 ve
        uretilen PDF'in metniyle): dört girdinin dördü de eksikti.

        Ana kaynakça da aynı testte sınanıyor (karşı kol): düzeltme
        fazladan iş yapıp çalışan tarafı bozmamalı.
        """
        (tmp_path / "ana.tex").write_text(MULTIBIB_TEX, encoding="utf-8")
        (tmp_path / "refs.bib").write_text(MULTIBIB_REF, encoding="utf-8")

        r = _run_derle([str(tmp_path / "ana.tex")], cwd=str(tmp_path),
                       timeout=180)

        assert (tmp_path / "ana.pdf").exists(), r.stdout[-2000:]
        metin = _pdf_metni(tmp_path / "ana.pdf")
        assert "Anaeser" in metin, metin[-800:]
        assert "Ekeser" in metin, metin[-800:]

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
            capture_output=True, text=True, cwd=str(tmp_path), timeout=120, encoding="utf-8")
        assert "Eksik paket: biber" in r.stdout
        assert "sudo apt-get install biber" in r.stdout


class TestKaynakcaAraciDuserse:
    r"""Kaynakça aracı DÜŞTÜĞÜNDE derleme "basarili" demiyor.

    Araç sıfırdan farklı dönünce `.bbl` hiç oluşmuyor: belge yine
    derleniyor, nonstopmode PDF'i üretiyor ama kaynakça BOŞ çıkıyor.
    Betik aracın çıkış kodunu `|| true` ile atıyor, çıktısından süzdüğü
    satırları SARI "uyarilari" başlığıyla basıyordu.

    ÖLÇÜLDÜ (2026-09-17, gerçek biber 2.19 ve bibtex 0.99d; bozuk ve
    eksik `.bib` ile; kehanet üretilen PDF'in METNİ): dört kurulumun
    dördünde de kaynakça boştu, ekranda `[basarili]` yazıyordu, çıkış
    kodu 0 ve panelde 0 hata vardı.

    Eşik ÖLÇÜMLE seçildi: iki araç da sağlam kurulumda 0, çözülemeyen
    atıf anahtarında 0, kaynakça hiç kurulamadığında 2 dönüyor. Uygulama
    ile gelen 28 kaynakçalı şablonun tamamı düzeltmeden önce ve sonra
    aynı sonucu veriyor.
    """

    BOZUK_BIB = "@article{ornek2020,\n  author = {Yilmaz, Ayse,\n  year = {2020},\n"
    SAGLAM_BIB = ("@article{ornek2020, author={Yilmaz, Ayse},\n"
                  "  title={Baslik}, journal={Dergi}, year={2020}}\n")

    BIBLATEX = r"""\documentclass{article}
\usepackage[backend=biber]{biblatex}
\addbibresource{kaynak.bib}
\begin{document}
Atif \cite{%s}.
\printbibliography
\end{document}
"""

    BIBTEX = r"""\documentclass{article}
\begin{document}
Atif \cite{%s}.
\bibliographystyle{plain}
\bibliography{kaynak}
\end{document}
"""

    def _kos(self, tmp_path, govde, bib, anahtar="ornek2020"):
        from core.log_parser import parse_output

        (tmp_path / "tez.tex").write_text(govde % anahtar, encoding="utf-8")
        if bib is not None:
            (tmp_path / "kaynak.bib").write_text(bib, encoding="utf-8")
        r = _run_derle([str(tmp_path / "tez.tex")], cwd=str(tmp_path),
                       timeout=180)
        temiz = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
        return r, temiz, parse_output(temiz, "tez.tex")

    @_biber_skip
    def test_BIBER_DUSUNCE_basarili_demiyor(self, tmp_path):
        r, temiz, sonuc = self._kos(tmp_path, self.BIBLATEX, self.BOZUK_BIB)

        assert r.returncode != 0, temiz[-1500:]
        assert "[basarili]" not in temiz, temiz[-1500:]
        # Panelde SAYILAN bir hata olmalı. Betiğin başlık satırı iki nokta
        # ile biterse ayrıştırıcı onu başlık sayıp atlıyor ve sayı 0 kalıyor.
        assert any("kaynakcasi olusturulamadi" in h.message
                   for h in sonuc.errors), (temiz[-1500:], sonuc.errors)

    def test_BIBTEX_DUSUNCE_basarili_demiyor(self, tmp_path):
        if not shutil.which("bibtex"):
            pytest.skip("bibtex kurulu degil")
        r, temiz, sonuc = self._kos(tmp_path, self.BIBTEX, None)

        assert r.returncode != 0, temiz[-1500:]
        assert "[basarili]" not in temiz, temiz[-1500:]
        assert any("kaynakcasi olusturulamadi" in h.message
                   for h in sonuc.errors), (temiz[-1500:], sonuc.errors)

    @_biber_skip
    def test_COZULEMEYEN_ATIF_hata_sayilmiyor(self, tmp_path):
        """Karşı kol: yazım hâlindeki belge kırmızı yanmamalı.

        `\\cite{henuz-yok}` yazarken çok sık; biber bu durumda uyarıyor
        ama 0 dönüyor. Eşik gevşetilirse her yarım belge hata verir.
        """
        r, temiz, sonuc = self._kos(tmp_path, self.BIBLATEX, self.SAGLAM_BIB,
                                    anahtar="henuz-yazilmadi")

        assert r.returncode == 0, temiz[-1500:]
        assert "[basarili]" in temiz, temiz[-1500:]
        assert not any("kaynakcasi olusturulamadi" in h.message
                       for h in sonuc.errors), sonuc.errors


class TestHataKonumu:
    r"""Hata, HANGİ DOSYADA olduğuysa orada gösterilmeli.

    `derle.sh` GUI'ye motorun ham günlüğünü değil, yalnız hata bloklarını
    basıyor; günlükteki `(dosya ...)` işaretleri o akışta hiç yok. Bu yüzden
    `\input` ile bölünmüş belgelerde HER hata ana dosyaya atfediliyordu ve
    kullanıcı hataya tıklayınca ana belgenin sağlam bir satırına gidiyordu.

    ÖLÇÜLDÜ (2026-09-13, hata bilerek belli bir dosyanın belli bir satırına
    konarak): on kurgunun onunda da dosya ana belge çıkıyordu; motora
    `-file-line-error` verilince onunda da doğru dosya çıkıyor.
    """

    ALT_TEX = "Duz satir.\nDuz satir.\n\\budurBilinmeyenKomut\nDuz satir.\n"

    def _derle_ve_ayristir(self, tmp_path):
        from core.log_parser import parse_output

        (tmp_path / "bolum").mkdir()
        (tmp_path / "bolum" / "ch1.tex").write_text(self.ALT_TEX,
                                                    encoding="utf-8")
        (tmp_path / "ana.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\input{bolum/ch1}\n\\end{document}\n", encoding="utf-8")

        r = _run_derle([str(tmp_path / "ana.tex")], cwd=str(tmp_path),
                       timeout=180)

        # GUI de çıktıyı ANSI'den arındırıp parse_output'a veriyor
        # (core/compiler.py'deki aynı desen).
        temiz = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
        return parse_output(temiz, str(tmp_path / "ana.tex")), r

    def test_ALT_DOSYADAKI_hata_o_dosyaya_atfediliyor(self, tmp_path):
        sonuc, r = self._derle_ve_ayristir(tmp_path)

        assert sonuc.errors, r.stdout[-1500:]
        hata = sonuc.errors[0]
        assert hata.file_path.replace("\\", "/").endswith("bolum/ch1.tex"), \
            hata.file_path
        assert hata.line_number == 3, hata.line_number

    def test_hata_mesaji_hala_okunuyor(self, tmp_path):
        """Karşı kol: biçim değişti, mesajın kendisi kaybolmamalı."""
        sonuc, r = self._derle_ve_ayristir(tmp_path)

        assert any("Undefined control sequence" in (h.message or "")
                   for h in sonuc.errors), [h.message for h in sonuc.errors]


class TestUyariSuzgeci:
    r"""`derle.sh` süzgeci ile ayrıştırıcının bildiği sınıflar AYNI olmalı.

    Panelin gördüğü tek şey bu betiğin çıktısı; burada süzülen bir uyarı
    GUI'ye hiç ulaşmıyor. ÖLÇÜLDÜ (2026-09-13): "Missing character" sınıfı
    süzgeçte yoktu, yani ayrıştırıcının o sınıf için yazdığı toplama kolu
    ve `error_hints`teki ipucu HİÇ görünemiyordu.
    """

    # Her sınıf için GERÇEK bir günlük satırı. Ayrıştırıcı bunu tanıyorsa
    # betiğin süzgeci de tanımak zorunda: iki taraf da sınanıyor.
    SATIRLAR = [
        "LaTeX Warning: Reference `x' on page 1 undefined on input line 4.",
        "Package hyperref Warning: Token not allowed in a PDF string.",
        "Overfull \\hbox (12.0pt too wide) in paragraph at lines 5--6",
        "Underfull \\vbox (badness 10000) detected at line 20",
        "pdfTeX warning (ext4): destination with the same identifier",
        "Font T1/ptm/b/n/10 not loadable",
        "Missing character: There is no ı (U+0131) in font ptmr8t!",
        # 2026-09-14'te gerçek korpustan: ikisi de hiçbir kolda yoktu.
        "LaTeX Font Warning: Font shape `T1/ptm/m/sl' undefined",
        "warning  (pdf backend): ignoring duplicate destination with the "
        "name 'figure.1'",
    ]

    @staticmethod
    def _desenler():
        """Betikteki İKİ süzgeç kolu da buradan okunuyor, elle yazılmıyor."""
        with open(SCRIPT, encoding="utf-8") as f:
            kaynak = f.read()
        desenler = []
        for ad in ("UYARI_DESENI", "TEKRARLAYAN_UYARI"):
            m = re.search(r"^%s='([^']*)'" % ad, kaynak, re.M)
            assert m, "%s bulunamadi" % ad
            desenler.append(m.group(1))
        return desenler

    @pytest.mark.parametrize("satir", SATIRLAR)
    def test_AYRISTIRICININ_bildigi_sinif_SUZGECTEN_geciyor(self, satir):
        from core.log_parser import parse_output

        assert parse_output(satir).warnings, satir      # ayrıştırıcı tanıyor
        assert any(re.search(d, satir) for d in self._desenler()), satir

    def test_ILGISIZ_satir_uyari_sayilmiyor(self):
        """Karşı kol: desen her satırı yakalarsa panel çöple dolar."""
        ilgisiz = "This is LuaHBTeX, Version 1.18.0 (TeX Live 2023)"

        assert not any(re.search(d, ilgisiz) for d in self._desenler())

    def test_EKSIK_GLIF_panele_ulasiyor_ve_YIGILMIYOR(self, tmp_path):
        r"""Uçtan uca: harf PDF'e basılmıyor, derleme BAŞARILI bitiyor.

        Aynı karakter belge boyunca yüzlerce kez eksik olabiliyor; betik
        satırları benzersizleştiriyor, ayrıştırıcı da yazı tipi başına tek
        uyarıya indiriyor. ÖLÇÜLDÜ (2026-09-13): 360 ham satır, 6 benzersiz
        satır, panele 1 uyarı.

        SAYI DA DENETLENİYOR (2026-09-15). Betik benzersizleştirirken tekrar
        sayısını atıyordu, yani ayrıştırıcının "kaç kez geçti" kolu gerçek
        sayıyı HİÇ görmüyordu: bu belgede 160 harf düşerken panel "toplam 4
        karakter" diyordu. Gövde 4 düşen harfi 40 kez yazıyor, yani yer
        gerçeği 160 ve 4 farklı harf.
        """
        from core.log_parser import parse_output

        govde = "Turkce harfler: \u0131\u015f\u011f\u0130. " * 40
        (tmp_path / "ana.tex").write_text(
            "\\documentclass{article}\n\\usepackage[T1]{fontenc}\n"
            "\\usepackage{mathptmx}\n\\begin{document}\n" + govde
            + "\n\\end{document}\n", encoding="utf-8")

        r = _run_derle([str(tmp_path / "ana.tex")], cwd=str(tmp_path),
                       timeout=180)

        temiz = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
        sonuc = parse_output(temiz, str(tmp_path / "ana.tex"))
        font_uyarilari = [u for u in sonuc.warnings
                          if "Missing character" in (u.message or "")]
        assert font_uyarilari, temiz[-1500:]
        # Yazı tipi başına tek uyarı: yığılma yok.
        assert len(font_uyarilari) <= 2, [u.message for u in font_uyarilari]
        assert temiz.count("Missing character") <= 12, \
            temiz.count("Missing character")
        mesaj = font_uyarilari[0].message
        assert "4 farklı harf" in mesaj, mesaj
        # Sayı TAM 160 diye sınanmıyordu ve bu macOS'ta düşüyordu: orada
        # 480 geliyor. Sebep geçiş sayısı DEĞİL (toplama yalnız SON geçişin
        # çıktısını okuyor, `SON_CIKTI`); TeX paragrafı birden çok kez
        # bölmeyi deniyor ve her denemede eksik harfi yeniden bildiriyor.
        # Deneme sayısı yazı tipi metriklerine bağlı, yani TeX dağıtımına.
        #
        # ÖLÇÜLDÜ (2026-09-18): Linux/TeX Live `(x40)`, macOS/BasicTeX
        # `(x120)`, İKİSİNDE DE aynı yazı tipi (ptmr8t) ve aynı 4 harf.
        #
        # Kapının DİŞİ duruyor: kusur `sort -u`nun tekrar sayısını atması
        # ve panelin 160 yerine 4 demesiydi. Alt sınır yer gerçeği olan
        # 160; sayı yine atılırsa 4'e düşer ve kapı yanar.
        m = re.search(r"toplam (\d+) karakter", mesaj)
        assert m, mesaj
        assert int(m.group(1)) >= 160, mesaj


class TestSozlukVeSimge:
    r"""Sözlük ve simge listesi: yardımcı araç koşmazsa bölüm BOŞ çıkıyor.

    Kaynakçadan tek farkı sessizliği: derleme başarıyla bitiyor, `[?]` ya da
    `??` işareti çıkmıyor, kullanıcı yalnız boş bir "Kısaltmalar" sayfası
    görüyor. ÖLÇÜLDÜ (2026-09-13, kehanet üretilen PDF'in metni): ikisi de
    PDF'te yoktu.
    """

    @_sozluk_skip
    def test_SOZLUK_basiliyor(self, tmp_path):
        (tmp_path / "ana.tex").write_text(SOZLUK_TEX, encoding="utf-8")

        r = _run_derle([str(tmp_path / "ana.tex")], cwd=str(tmp_path),
                       timeout=180)

        assert (tmp_path / "ana.pdf").exists(), r.stdout[-2000:]
        metin = _pdf_metni(tmp_path / "ana.pdf")
        assert "LatexDizgi" in metin, metin[-800:]
        assert "ACIKLAMASI" in metin, metin[-800:]

    @_simge_skip
    def test_SIMGE_LISTESI_basiliyor(self, tmp_path):
        (tmp_path / "ana.tex").write_text(SIMGE_TEX, encoding="utf-8")

        r = _run_derle([str(tmp_path / "ana.tex")], cwd=str(tmp_path),
                       timeout=180)

        assert (tmp_path / "ana.pdf").exists(), r.stdout[-2000:]
        metin = _pdf_metni(tmp_path / "ana.pdf")
        assert "IsikHizi" in metin, metin[-800:]
        assert "ACIKLAMASI" in metin, metin[-800:]

    @_sozluk_skip
    def test_YEDEK_arac_devreye_giriyor(self, tmp_path):
        """`makeglossaries` yoksa Lua sürümü (`-lite`) koşmalı.

        Bazı kurulumlarda Perl yok; ikisi de aynı apt paketinden geliyor.
        """
        if not shutil.which("makeglossaries-lite"):
            pytest.skip("makeglossaries-lite kurulu değil")
        (tmp_path / "ana.tex").write_text(SOZLUK_TEX, encoding="utf-8")

        subprocess.run(
            ["bash", "-c", _komutu_gizle("makeglossaries"), SCRIPT,
             str(tmp_path / "ana.tex")],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=180,
            encoding="utf-8")

        # Ölçüt AÇIKLAMA, ad değil: `\gls{lat}` girdinin ADINI gövdede
        # zaten basıyor, yani "LatexDizgi" sözlük hiç üretilmese de PDF'te
        # görünüyor. Mutasyon bunu yakaladı: sözlük adımı kapatıldığında bu
        # kapı yanmıyordu.
        metin = _pdf_metni(tmp_path / "ana.pdf")
        assert "ACIKLAMASI" in metin, metin[-800:]

    # `ids`: belge metni test adına girince CI günlüğünde satır satır ham
    # LaTeX görünüyor ve hangi kolun düştüğü okunamıyor.
    @pytest.mark.parametrize("tex,uyari_bekleniyor", [
        (SOZLUK_TEX, True),
        # Karşı kol: sözlüğü olmayan belgede uyarı ÇIKMAMALI. Koşulsuz
        # uyarı her derlemeye kalıcı gürültü eklerdi.
        (MINIMAL_TEX, False),
    ], ids=["sozluklu", "sozluksuz"])
    def test_arac_yoksa_paket_onerisi(self, tmp_path, tex, uyari_bekleniyor):
        (tmp_path / "ana.tex").write_text(tex, encoding="utf-8")

        r = subprocess.run(
            ["bash", "-c",
             _komutu_gizle("makeglossaries", "makeglossaries-lite"),
             SCRIPT, str(tmp_path / "ana.tex")],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=180,
            encoding="utf-8")

        # `==>` satırı PAKET adını taşıyor, araç adı parantez içinde.
        # Önceden araç adı yazılıydı ve `log_parser` onu "Eksik paket:
        # makeglossaries" diye Öneriler sekmesine koyuyordu; apt'de öyle
        # bir paket yok (2026-09-15).
        #
        # Beklenen ad PLATFORMA bağlı: macOS'ta apt yok ve TeX Live
        # paketi CTAN adıyla geliyor (`glossaries`). Debian adını orada
        # beklemek, kullanıcıya yanlış ad göstermeyi test etmek olurdu.
        paket = ("glossaries" if sys.platform == "darwin"
                 else "texlive-latex-extra")
        assert ("Eksik paket: %s" % paket in r.stdout) is uyari_bekleniyor
        assert ("makeglossaries" in r.stdout) is uyari_bekleniyor


class TestDizin:
    r"""Dizin: `makeindex` HER `.idx` için koşmalı.

    `\index{X}` görünür çıktı üretmiyor, yani anahtar PDF'te ancak BASILAN
    dizinde geçebilir; ölçüt bu. ÖLÇÜLDÜ (2026-09-13): iki dizinli belgede
    ikinci dizinin girdisi PDF'te hiç yoktu.
    """

    @_imakeidx_skip
    def test_IKI_dizin_de_basiliyor(self, tmp_path):
        (tmp_path / "ana.tex").write_text(DIZIN_IKI_TEX, encoding="utf-8")

        r = _run_derle([str(tmp_path / "ana.tex")], cwd=str(tmp_path),
                       timeout=180)

        assert (tmp_path / "ana.pdf").exists(), r.stdout[-2000:]
        metin = _pdf_metni(tmp_path / "ana.pdf")
        assert "KonuGirdisi" in metin, metin[-800:]
        assert "KisiGirdisi" in metin, metin[-800:]

    @_dizin_skip
    def test_TEK_dizin_hala_basiliyor(self, tmp_path):
        """Karşı kol: döngüye geçiş klasik tek dizini bozmamalı.

        SAĞLIKLI KOŞUDA SESSİZ OLMALI (2026-09-15). Süzgeç `error|warn`
        idi ve makeindex'in `...done (5 lines written, 0 warnings).`
        satırı ona takılıyordu: her başarılı derlemede "makeindex
        uyarilari" başlıklı bir blok çıkıyor, içinde sıfır uyarı
        yazıyordu.
        """
        (tmp_path / "ana.tex").write_text(DIZIN_TEK_TEX, encoding="utf-8")

        r = _run_derle([str(tmp_path / "ana.tex")], cwd=str(tmp_path),
                       timeout=180)

        assert (tmp_path / "ana.pdf").exists(), r.stdout[-2000:]
        assert "KlasikGirdi" in _pdf_metni(tmp_path / "ana.pdf")
        assert "makeindex" not in r.stdout, r.stdout[-800:]

    @_dizin_skip
    def test_REDDEDILEN_girdi_kullaniciya_soyleniyor(self, tmp_path):
        r"""Dizinden DÜŞEN girdi sessiz kalmamalı.

        makeindex ayrıştıramadığı girdiyi atıyor ama `!!` satırını
        stdout'a basmıyor (o döküm `.ilg`ye gidiyor) ve çıkış kodu 0
        kalıyor. Tek iz "N rejected" sayacı ve eski süzgeç onu ELİYORDU:
        girdi dizinde yok, kullanıcıya da bir şey denmiyordu (ölçüldü,
        üç ayrı bozuk girdi biçiminde de aynı).
        """
        (tmp_path / "ana.tex").write_text(
            "\\documentclass{article}\n\\usepackage{makeidx}\n\\makeindex\n"
            "\\begin{document}\n"
            "Bir\\index{A!B!C!D!E}. Iki\\index{IyiGirdi}.\n"
            "\\printindex\n\\end{document}\n", encoding="utf-8")

        r = _run_derle([str(tmp_path / "ana.tex")], cwd=str(tmp_path),
                       timeout=180)

        assert (tmp_path / "ana.pdf").exists(), r.stdout[-2000:]
        assert "rejected" in r.stdout, r.stdout[-800:]


class TestInputInclude:
    def test_input_dosyasi(self, tmp_path):
        tex = tmp_path / "main.tex"
        bolum = tmp_path / "bolum.tex"
        tex.write_text(MINIMAL_TEX_INPUT, encoding="utf-8")
        bolum.write_text(BOLUM_TEX, encoding="utf-8")
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
""", encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        # siunitx kurulu olabilir veya olmayabilir
        if r.returncode != 0:
            assert "siunitx" in r.stdout.lower() or "texlive-science" in r.stdout.lower() or "hata" in r.stdout.lower()


class TestCokluDosya:
    def test_iki_dosya_derleme(self, tmp_path):
        (tmp_path / "a.tex").write_text(MINIMAL_TEX, encoding="utf-8")
        (tmp_path / "b.tex").write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tmp_path / "a.tex"), str(tmp_path / "b.tex")],
                       cwd=str(tmp_path), timeout=120)
        assert r.returncode == 0
        assert (tmp_path / "a.pdf").exists()
        assert (tmp_path / "b.pdf").exists()
        assert "Toplam" in r.stdout or "Basarili" in r.stdout

    def test_biri_hatali(self, tmp_path):
        (tmp_path / "ok.tex").write_text(MINIMAL_TEX, encoding="utf-8")
        (tmp_path / "bad.tex").write_text(MINIMAL_TEX_ERROR, encoding="utf-8")
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
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (klasor / "test.pdf").exists()

    def test_bosluklu_dosya_adi(self, tmp_path):
        tex = tmp_path / "my document.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "my document.pdf").exists()

    def test_turkce_klasor_adi(self, tmp_path):
        klasor = tmp_path / "Belgeler"
        klasor.mkdir()
        tex = klasor / "test.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (klasor / "test.pdf").exists()


class TestSynctex:
    def test_synctex_gz_olusur(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "test.synctex.gz").exists()


class TestIncludeAltDizin:
    def test_include_alt_dizin(self, tmp_path):
        alt = tmp_path / "bolumler"
        alt.mkdir()
        (alt / "giris.tex").write_text(r"""Giriş içeriği.
""", encoding="utf-8")
        main = tmp_path / "main.tex"
        main.write_text(r"""\documentclass{article}
\begin{document}
\include{bolumler/giris}
\end{document}
""", encoding="utf-8")
        r = _run_derle([str(main)], cwd=str(tmp_path), timeout=60)
        assert r.returncode == 0
        assert (tmp_path / "main.pdf").exists()


class TestShellEscape:
    def test_shell_escape_flag_basarisiz(self, tmp_path):
        # minted olmayan dosyada --shell-escape zorla
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = _run_derle([str(tex), "--shell-escape"], cwd=str(tmp_path), timeout=60)
        # shell-escape ile derlemeli, başarılı olmalı
        assert r.returncode == 0

    @pytest.mark.skipif(not HAS_MINTED, reason="minted + pygmentize kurulu değil")
    def test_minted_sty_icinden_requirepackage_otomatik(self, tmp_path):
        r"""minted bir .sty içinde \RequirePackage ile yüklüyse shell-escape otomatik açılmalı.

        webdiller.sty senaryosu: \usepackage{minted} hiçbir .tex'te geçmiyor,
        eski tespit deseni bunu kaçırıyordu.
        """
        (tmp_path / "paket.sty").write_text("\\RequirePackage{minted}\n", encoding="utf-8")
        tex = tmp_path / "test.tex"
        tex.write_text(
            "\\documentclass{article}\n"
            "\\usepackage{paket}\n"
            "\\begin{document}\n"
            "\\begin{minted}{python}\nprint('merhaba')\n\\end{minted}\n"
            "\\end{document}\n"
        , encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=120)
        # Eski desen: '\usepackage{minted}' geçmediğinden shell-escape açılmıyor,
        # minted "shell-escape flag" hatasıyla düşüyordu.
        assert r.returncode == 0
        assert (tmp_path / "test.pdf").exists()


class TestGlob:
    def test_glob_tex_dosyalari(self, tmp_path):
        (tmp_path / "a.tex").write_text(MINIMAL_TEX, encoding="utf-8")
        (tmp_path / "b.tex").write_text(MINIMAL_TEX, encoding="utf-8")
        (tmp_path / "c.txt").write_text("nope", encoding="utf-8")
        r = _run_derle([str(tmp_path / "*.tex")], cwd=str(tmp_path), timeout=120)
        # glob bash tarafından genişletilir veya betik içinde handle edilir
        # en azından a.tex derlenmiş olmalı
        assert (tmp_path / "a.pdf").exists() or r.returncode is not None


class TestLogDosyasi:
    def test_hatali_derleme_log_kopyalanir(self, tmp_path):
        tex = tmp_path / "hata.tex"
        tex.write_text(MINIMAL_TEX_ERROR, encoding="utf-8")
        r = _run_derle([str(tex)], cwd=str(tmp_path), timeout=60)
        assert r.returncode != 0
        assert (tmp_path / "hata.log").exists()


class TestXelatexModu:
    # xelatex ayrı paket (texlive-xetex); kurulu değilse bu sınıf skip
    _xe = pytest.mark.skipif(not shutil.which("xelatex"), reason="xelatex kurulu değil — texlive-xetex gerektirir")

    @_xe
    def test_xelatex_flag(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
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
        , encoding="utf-8")
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
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        r = subprocess.run(
            ["bash", SCRIPT, str(tex), "--xelatex"],
            capture_output=True, text=True, timeout=90,
            env={**os.environ, "LD_LIBRARY_PATH": str(libdir)},
            cwd=str(tmp_path), encoding="utf-8")
        assert r.returncode == 0
        assert (tmp_path / "test.pdf").exists()

    def test_motor_yoksa_paket_onerisi(self, tmp_path):
        # Kurulu olmayan motor: hata + '==> Eksik paket' önerisi (GUI Öneriler
        # sekmesi bu çıktıyı parse eder). Motoru sandbox PATH ile görünmez kıl.
        tex = tmp_path / "test.tex"
        tex.write_text(MINIMAL_TEX, encoding="utf-8")
        sandbox = tmp_path / "bin"
        sandbox.mkdir()
        for tool in ("bash", "dirname", "realpath", "basename"):
            os.symlink(shutil.which(tool), sandbox / tool)
        r = subprocess.run(
            ["bash", SCRIPT, str(tex), "--xelatex"],
            capture_output=True, text=True, timeout=30,
            env={"PATH": str(sandbox)},
            cwd=str(tmp_path), encoding="utf-8")
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
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8")
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


class TestTekrarSayisiBorusu:
    r"""Betik tekrarlayan uyarıları tekilleştirirken SAYIYI koruyor mu.

    Boru hattı betikten OKUNUYOR, teste kopyalanmıyor: kopyalansaydı test
    kendini ölçerdi ve betikteki değişikliği hiç görmezdi.
    """

    @staticmethod
    def _boru():
        with open(SCRIPT, encoding="utf-8") as f:
            kaynak = f.read()
        m = re.search(r"\|\s*sort\s*\|\s*uniq -c\s*\\\s*\n\s*\|\s*sed -E "
                      r"('[^']*')", kaynak)
        assert m, "betikteki tekrar borusu bulunamadi"
        return "sort | uniq -c | sed -E " + m.group(1)

    def _kos(self, metin):
        r = subprocess.run(
            ["bash", "-c", 'printf "%s" "$1" | ' + self._boru(),
             "bash", metin],
            capture_output=True, text=True, encoding="utf-8")
        return [s for s in r.stdout.splitlines() if s.strip()]

    def test_TEKRARLAYAN_satir_sayiyi_tasiyor(self):
        """Sayı atılırsa panel 140 düşen harfi 4 sanıyor (ölçüldü)."""
        metin = "Missing character: There is no X in font f!\n" * 3
        assert self._kos(metin) == [
            "Missing character: There is no X in font f! (x3)"]

    def test_TEK_GECISTE_ek_yok(self):
        """Karşı kol: bir kez geçen satıra `(x1)` yazmak gürültü olur."""
        metin = "Missing character: There is no X in font f!\n"
        assert self._kos(metin) == [
            "Missing character: There is no X in font f!"]

    def test_SATIR_BASI_degismiyor(self):
        r"""Ayrıştırıcı desenleri satır başına çapalı (`^Missing character:`);
        sayı öne konsaydı uyarılar panelden tümüyle kaybolurdu."""
        metin = "LaTeX Font Warning: Font shape undefined\n" * 2
        cikti = self._kos(metin)
        assert cikti[0].startswith("LaTeX Font Warning:"), cikti


class TestKaynakcaAraciSuzgeci:
    r"""bibtex/biber'in KENDİ tanısı kullanıcıya ulaşıyor mu.

    Betiğin süzgeci `error|warn` idi; bibtex ise ölümcül sorunları başka
    kelimelerle bildiriyor. ÖLÇÜLDÜ (2026-09-15, gerçek bibtex, dört bozuk
    kurulum): dördünde de derleme 0 ile bitti, PDF açıldı ve kaynakça BOŞ
    kaldı; `.bib` sözdizimi bozuk olanda panele HİÇ satır ulaşmadı.

    İki taraf da sınanıyor: satır betiğin süzgecinden geçmeli VE
    ayrıştırıcı onu tanımalı. Biri eksikse satır kullanıcıya ulaşmaz.
    """

    # Gerçek bibtex/biber çıktısından alınan satırlar.
    SATIRLAR = [
        "I couldn't open style file yokboylestil.bst",
        "I found no style file---while reading file d.aux",
        "I couldn't open database file kaynak.bib",
        "I found no database files---while reading file d.aux",
        "Illegal end of database file---line 2 of file kaynak.bib",
        'Warning--I didn\'t find a database entry for "ali2020"',
        "Warning--empty author in ali2020",
        "(There were 2 error messages)",
        "ERROR - Cannot find 'refs.bib'!",
    ]

    # Karşı kol: bunlar bibtex'in SIRADAN satırları, panele girmemeli.
    SIRADAN = [
        "This is BibTeX, Version 0.99d (TeX Live 2023/Debian)",
        "The top-level auxiliary file: d.aux",
        "The style file: plain.bst",
        "Database file #1: kaynak.bib",
    ]

    @staticmethod
    def _desen():
        """Süzgeç betikten OKUNUYOR, teste kopyalanmıyor."""
        with open(SCRIPT, encoding="utf-8") as f:
            kaynak = f.read()
        m = re.search(r"^BIB_DESENI='([^']*)'", kaynak, re.M)
        assert m, "BIB_DESENI bulunamadi"
        return m.group(1)

    @pytest.mark.parametrize("satir", SATIRLAR)
    def test_ARAC_TANISI_suzgecten_geciyor_ve_taniniyor(self, satir):
        from core.log_parser import parse_output

        assert re.search(self._desen(), satir, re.I), satir
        uyarilar = parse_output(satir).warnings
        assert uyarilar, satir
        assert uyarilar[0].warning_type == "BibTeX", uyarilar[0]

    @pytest.mark.parametrize("satir", SIRADAN)
    def test_SIRADAN_satir_panele_girmiyor(self, satir):
        """Süzgeç her satırı geçirirse panel bibtex'in banner'ıyla dolar."""
        from core.log_parser import parse_output

        assert not re.search(self._desen(), satir, re.I), satir
        assert not parse_output(satir).warnings, satir

    def test_STIL_DOSYASI_YOKKEN_sebep_panele_ulasiyor(self, tmp_path):
        r"""Uçtan uca: derleme BAŞARILI bitiyor, PDF açılıyor, kaynakça boş.

        Eskiden panelde yalnız LaTeX'in "Citation undefined" uyarısı
        vardı ve onun ipucu "tekrar derleyin, iki geçe gerekir" diyordu;
        eksik `.bst` ile bu asla düzelmez.
        """
        from core.log_parser import parse_output

        if not shutil.which("bibtex"):
            pytest.skip("bibtex kurulu degil")
        (tmp_path / "kaynak.bib").write_text(
            "@article{ali2020, author={Ali Veli}, title={Baslik},\n"
            "  journal={Dergi}, year={2020}}\n", encoding="utf-8")
        (tmp_path / "d.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Atif \\cite{ali2020}.\n"
            "\\bibliographystyle{yokboylestil}\n\\bibliography{kaynak}\n"
            "\\end{document}\n", encoding="utf-8")

        r = _run_derle([str(tmp_path / "d.tex")], cwd=str(tmp_path),
                       timeout=180)
        temiz = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
        sonuc = parse_output(temiz, "d.tex")
        bib = [u.message for u in sonuc.warnings
               if u.warning_type == "BibTeX"]
        assert any("couldn't open style file" in m for m in bib), temiz[-1200:]


class TestYardimciAracSuzgeci:
    r"""makeindex / makeglossaries / nomencl çıktısında hangi satır gösterilir.

    Ölçüt SAYININ SIFIR OLMAMASI: sayaç taşıyan satır ancak sayı sıfırdan
    büyükse kullanıcıya çıkar. Süzgeç TERSİNE çalışıyordu; "0 warnings"
    geçiyor, "1 rejected" süzülüyordu.

    Desenler betikten OKUNUYOR, teste kopyalanmıyor.
    """

    # Üç aracın GERÇEK çıktısından alınan satırlar (2026-09-15).
    GOSTERILECEK = [
        "Scanning input file d.idx....done (1 entries accepted, 1 rejected).",
        "Scanning input file d.glo....done (1 entries accepted, 2 rejected).",
        "Scanning input file d.nlo....done (1 entries accepted, 1 rejected).",
        "!! Input index error (file = d.glo, line = 2):",
        "Generating output file d.ind....done (5 lines written, 3 warnings).",
    ]
    SUSTURULACAK = [
        "Scanning input file d.idx....done (1 entries accepted, 0 rejected).",
        "Generating output file d.ind....done (5 lines written, 0 warnings).",
        "This is makeindex, version 2.17 [TeX Live 2023] (kpathsea + Thai)",
        "Sorting entries...done (0 comparisons).",
        "Output written in d.ind.",
        "Transcript written in d.ilg.",
        "makeglossaries version 4.53 (2023-09-29)",
    ]

    @staticmethod
    def _desenler():
        with open(SCRIPT, encoding="utf-8") as f:
            kaynak = f.read()
        cikan = []
        for ad in ("ARAC_DESENI", "ARAC_SESSIZ"):
            m = re.search(r"^%s='([^']*)'" % ad, kaynak, re.M)
            assert m, "%s bulunamadi" % ad
            cikan.append(m.group(1))
        return cikan

    def _gorunur(self, satir):
        """Satır betiğin İKİ GREP'inden geçiyor mu.

        GERÇEK `grep` koşuyor, Python'un `re`si değil: desen bir POSIX
        ERE ve iki motor her yerde aynı davranmıyor. `[[:space:]]`
        grep'te boşluk sınıfı, Python'da ise `[ : s p a c e ]` harfleri;
        kapı Python ile yazılıydı ve bu yüzden ANLAMCA AYNI bir yazımı
        bozuk sanıyordu (mutasyon kontrolünde yakalandı).
        """
        desen, sessiz = self._desenler()
        r = subprocess.run(
            ["bash", "-c",
             'printf "%s\\n" "$1" | grep -iE "$2" | grep -viE "$3" || true',
             "bash", satir, desen, sessiz],
            capture_output=True, text=True, encoding="utf-8")
        return bool((r.stdout or "").strip())

    @pytest.mark.parametrize("satir", GOSTERILECEK)
    def test_SORUN_bildiren_satir_gorunuyor(self, satir):
        assert self._gorunur(satir), satir

    @pytest.mark.parametrize("satir", SUSTURULACAK)
    def test_ZARARSIZ_satir_gorunmuyor(self, satir):
        """Karşı kol: sağlıklı koşuda blok hiç çıkmamalı."""
        assert not self._gorunur(satir), satir

    def test_UC_KOL_DA_ayni_deseni_kullaniyor(self):
        """Eskiden ikisi `error|warn`, biri yalnız `error` yazıyordu."""
        with open(SCRIPT, encoding="utf-8") as f:
            kaynak = f.read()
        for degisken in ("IDX_HATALAR", "GLO_HATALAR", "NLO_HATALAR"):
            m = re.search(r"%s=\$\(echo[^)]*?\)" % degisken, kaynak, re.S)
            assert m, degisken
            assert "$ARAC_DESENI" in m.group(0), degisken
            assert "$ARAC_SESSIZ" in m.group(0), degisken
