"""derle.sh eksik_paket_goster — öneri üretim testleri (TeX gerektirmez).

Betikten renk tanımları + paket haritaları + fonksiyon ayıklanır ve sahte
derleme çıktısıyla çağrılır; gerçek derleme gerekmediğinden CI'da da koşar.
"""

import os
import subprocess

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "core", "derle.sh")


def _eksik_paket_goster(cikti: str) -> str:
    r = subprocess.run(
        ["bash", "-c",
         'source <(sed -n "1,/^# Argüman kontrol/p" "$1"); eksik_paket_goster "$2"',
         "bash", SCRIPT, cikti],
        capture_output=True, text=True, timeout=15,
    )
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
