"""derle.sh eksik_paket_goster — öneri üretim testleri (TeX gerektirmez).

Betikten renk tanımları + paket haritaları + fonksiyon ayıklanır ve sahte
derleme çıktısıyla çağrılır; gerçek derleme gerekmediğinden CI'da da koşar.
"""

import os
import subprocess
import sys
import tempfile

import pytest

# derle.sh POSIX bash betiği. Windows'ta PATH'teki `bash` Git Bash (MSYS)
# olabiliyor ve argüman/yol dönüşümü yüzünden "$1" boşalıyor; betiğin
# kendisiyle ilgisi olmayan bir kabuk farkı. Gerçek kapı, CI'ın Linux'ta
# koşan derle job'u; orada bu testler tam çalışıyor.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX bash gerekli; CI'da Linux'ta koşuyor",
)

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "core", "derle.sh")


def _eksik_paket_goster(cikti: str) -> str:
    # Ayıklanan parça GERÇEK BİR DOSYAYA yazılıp öyle source ediliyor.
    #
    # Eskiden `source <(sed ...)` yazıyordu. macOS'un /bin/bash'i 3.2.57 ve
    # orada `source <(...)` HİÇBİR ŞEY TANIMLAMIYOR: sessizce 0 dönüyor,
    # fonksiyon tanımlanmıyor, sonraki çağrı 127 veriyor. ÖLÇÜLDÜ
    # (2026-09-18, macos-15 ve Docker'da bash 3.2.57; `source <(echo
    # "f(){ :; }")` sonrası `type -t f` boş, aynı içerik DOSYADAN source
    # edilince tanımlanıyor).
    #
    # Betiğin kendisiyle ilgisi yok: derle.sh üretimde hiç source
    # edilmiyor, script olarak koşuyor. Kusur testin yöntemindeydi.
    with tempfile.TemporaryDirectory() as d:
        parca = os.path.join(d, "bas.sh")
        with open(SCRIPT, encoding="utf-8") as f:
            satirlar = []
            for satir in f:
                satirlar.append(satir)
                if satir.startswith("# Argüman kontrol"):
                    break
        with open(parca, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(satirlar)
        r = subprocess.run(
            ["bash", "-c", 'source "$1"; eksik_paket_goster "$2"',
             "bash", parca, cikti],
            capture_output=True, text=True, timeout=15, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout


# Beklenen paket adı PLATFORMA bağlı: macOS'ta apt yok, TeX Live
# paketleri CTAN adıyla ve Pygments pip ile geliyor. Debian adını orada
# beklemek, kullanıcıya yanlış ad göstermeyi test etmek olurdu.
_MAC = sys.platform == "darwin"


def test_missing_pygments_python3_pygments_onerir():
    """minted.sty kurulu ama pygmentize yok: 'Missing Pygments output'
    hatasına Pygments kurulum önerisi eşlik etmeli."""
    out = _eksik_paket_goster(
        "! Package minted Error: Missing Pygments output; "
        "\\input{_minted-ana/default.pyg} failed.\n"
    )
    if _MAC:
        assert "Eksik paket: Pygments" in out
        assert "pip3 install Pygments" in out
    else:
        assert "Eksik paket: python3-pygments" in out
        assert "sudo apt-get install python3-pygments" in out


def test_pygments_mesaji_yoksa_oneri_cikmaz():
    out = _eksik_paket_goster("[basarili] test.pdf guncellendi\n")
    assert "ygments" not in out


def test_minted_sty_eksikse_harita_onerisi_calisir():
    """Ayıklama zincirinin sağlamı: mevcut .sty eksikliği yolu örnek senaryo."""
    out = _eksik_paket_goster("! LaTeX Error: File `minted.sty' not found.\n")
    if _MAC:
        # macOS'ta CTAN adı `minted`. Pygments gereksinimi burada değil,
        # "Missing Pygments output" kolunda bildiriliyor (o kol gerçekten
        # ısırdığında); Debian haritası ikisini tek dizede topluyor.
        assert "Eksik paket: minted" in out
        assert "sudo tlmgr install minted" in out
    else:
        assert "Eksik paket: texlive-latex-extra" in out
        assert "python3-pygments" in out


class TestPaketYoneticisiPlatforma_Gore:
    r"""macOS'ta `sudo apt-get install` diyordu; orada apt YOK.

    TeX Live paketleri macOS'ta `tlmgr` ile geliyor ve adlari DEBIAN
    degil CTAN adlari: `texlive-latex-extra` tlmgr'de hic yok. Yani
    kullaniciya calistirilamaz bir komut ve bulunamayan bir paket adi
    veriliyordu.

    OLCULDU (2026-09-18, macos-15 + BasicTeX; TeX Live'in kendi
    veritabanina `tlmgr search --global --file` ile soruldu; Debian
    eslemesi de 2026-09-13'te `dpkg -S` ile boyle yapilmisti).

    WINDOWS BU DEGISIKLIKTEN ETKILENMIYOR: orada derle.sh WSL'in ICINDE
    kosuyor, `uname -s` Linux diyor ve apt kolu aynen gecerli kaliyor.
    Asagidaki apt kolu testleri o karsi kol.
    """

    GIRDILER = {
        "haritadaki .sty": "! LaTeX Error: File `cancel.sty' not found.\n",
        "haritadaki .cls": "! LaTeX Error: File `IEEEtran.cls' not found.\n",
        "haritada olmayan": "! LaTeX Error: File `aastex.cls' not found.\n",
        "babel dili": "! Package babel Error: Unknown option 'german'.\n",
    }

    @staticmethod
    def _kos(girdi, yonetici):
        """Betigi verilen paket yoneticisiyle kostur."""
        with tempfile.TemporaryDirectory() as d:
            parca = os.path.join(d, "bas.sh")
            with open(SCRIPT, encoding="utf-8") as f:
                satirlar = []
                for satir in f:
                    satirlar.append(satir)
                    if satir.startswith("# Argüman kontrol"):
                        break
            with open(parca, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(satirlar)
            r = subprocess.run(
                ["bash", "-c",
                 'source "$1"; PAKET_YONETICISI="$3"; eksik_paket_goster "$2"',
                 "bash", parca, girdi, yonetici],
                capture_output=True, text=True, timeout=30, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        return r.stdout.replace("\x1b", "")

    @pytest.mark.parametrize("ad", sorted(GIRDILER))
    def test_APT_kolunda_apt_get_komutu_var(self, ad):
        """Linux ve WSL: komut apt, baska paket yoneticisi gecmiyor."""
        out = self._kos(self.GIRDILER[ad], "apt")
        assert "sudo apt-get install" in out, out
        assert "tlmgr" not in out, out
        assert "brew" not in out, out

    @pytest.mark.parametrize("ad", sorted(GIRDILER))
    def test_TLMGR_kolunda_apt_get_HIC_gecmiyor(self, ad):
        """macOS: apt yok, o yuzden `apt-get` tek kelimeyle bile gecmemeli."""
        out = self._kos(self.GIRDILER[ad], "tlmgr")
        assert "apt-get" not in out, out
        assert "texlive-" not in out, out

    def test_TLMGR_CTAN_adini_veriyor(self):
        """Debian adi degil, tlmgr'nin tanidigi ad."""
        out = self._kos(self.GIRDILER["haritadaki .sty"], "tlmgr")
        assert "sudo tlmgr install cancel" in out, out

    def test_TLMGR_bilinmeyen_dosyada_ad_UYDURMUYOR(self):
        """CTAN adi olculemeyen dosyada arama komutu veriliyor.

        Uydurulmus bir paket adi, yanlis apt adiyla ayni kusur olurdu:
        kullanici komutu kosturur ve hicbir sey kurulmaz.
        """
        out = self._kos(self.GIRDILER["haritada olmayan"], "tlmgr")
        assert "tlmgr search --global --file" in out, out
        assert "tlmgr install" not in out, out

    @pytest.mark.parametrize("yonetici,beklenen",
                             [("apt", "texlive-lang-german"),
                              ("tlmgr", "babel-german")])
    def test_BASLIK_ve_KOMUT_ayni_paketi_soyluyor(self, yonetici, beklenen):
        """Baslikta bir ad, komutta baskasi olmamali.

        Once boyleydi: macOS kolunda baslik `texlive-lang-german` derken
        komut `tlmgr install babel-german` diyordu.
        """
        out = self._kos(self.GIRDILER["babel dili"], yonetici)
        baslik = [s for s in out.splitlines() if "==>" in s]
        komut = [s for s in out.splitlines() if "install" in s]
        assert baslik and komut, out
        assert beklenen in baslik[0], baslik
        assert beklenen in komut[0], komut

    @pytest.mark.parametrize("uname_ciktisi,beklenen",
                             [("Darwin", "tlmgr"), ("Linux", "apt")])
    def test_PAKET_YONETICISI_uname_den_seciliyor(self, uname_ciktisi,
                                                  beklenen):
        r"""Tespit satirinin KENDISI siniliyor.

        Digerleri `PAKET_YONETICISI`yi elle kurup kollari sinar; boylece
        tespit satiri kapisiz kalir. Mutasyon bunu gosterdi: satir
        `PAKET_YONETICISI=apt` ile degistirilince HICBIR test dusmuyordu,
        yani macOS sessizce apt koluna geri donerdi.

        Mac olmadan olculuyor: PATH'e "Darwin" diyen sahte bir `uname`
        konup betik source ediliyor.
        """
        with tempfile.TemporaryDirectory() as d:
            sahte = os.path.join(d, "uname")
            with open(sahte, "w", encoding="utf-8", newline="\n") as f:
                f.write("#!/bin/sh\necho %s\n" % uname_ciktisi)
            os.chmod(sahte, 0o755)
            parca = os.path.join(d, "bas.sh")
            with open(SCRIPT, encoding="utf-8") as f:
                satirlar = []
                for satir in f:
                    satirlar.append(satir)
                    if satir.startswith("# Argüman kontrol"):
                        break
            with open(parca, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(satirlar)
            r = subprocess.run(
                ["bash", "-c",
                 'PATH="$2:$PATH"; source "$1"; echo "$PAKET_YONETICISI"',
                 "bash", parca, d],
                capture_output=True, text=True, timeout=30, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == beklenen, (r.stdout, r.stderr)
