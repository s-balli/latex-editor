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


def test_missing_pygments_python3_pygments_onerir():
    """minted.sty kurulu ama pygmentize yok: 'Missing Pygments output'
    hatasına python3-pygments kurulum önerisi eşlik etmeli."""
    out = _eksik_paket_goster(
        "! Package minted Error: Missing Pygments output; "
        "\\input{_minted-ana/default.pyg} failed.\n"
    )
    assert "Eksik paket: python3-pygments" in out
    assert "sudo apt-get install python3-pygments" in out


def test_pygments_mesaji_yoksa_oneri_cikmaz():
    out = _eksik_paket_goster("[basarili] test.pdf guncellendi\n")
    assert "python3-pygments" not in out


def test_minted_sty_eksikse_harita_onerisi_calisir():
    """Ayıklama zincirinin sağlamı: mevcut .sty eksikliği yolu örnek senaryo."""
    out = _eksik_paket_goster("! LaTeX Error: File `minted.sty' not found.\n")
    assert "Eksik paket: texlive-latex-extra" in out
    assert "python3-pygments" in out
