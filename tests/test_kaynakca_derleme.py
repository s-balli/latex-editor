r"""DOI ile eklenen kaynak GERÇEKTEN derleniyor ve doğru basılıyor mu.

NEDEN AYRI DOSYA. TeX Live CI'da yalnız `derle` işinde kurulu (bkz.
`test_ipucu_derleme`); matrix işinde bu dosya hep atlanır.

NE SINANIYOR. Üç GERÇEK Crossref kaydı, uygulamanın aldığı ham BibTeX'le
(2026-09-27): `NF-κB` (Yunan harfi), `TiO₂` (Unicode alt simge) ve Wiley'nin
girintili `TiO<sub>2</sub>`i. `normallestir`den geçip bibtex + motorla
derleniyor; basılan kaynakça pdfium ile okunuyor. ÖLÇÜLDÜ, düzeltmeden önce:

  pdflatex  "Unicode character κ (U+03BA) not set up", derleme DÜŞÜYOR
  lualatex  derleniyor ama κ ve ₂ SESSİZCE yok ("NF-B", "tio for")
  ikisi     `<sub>2</sub>` olduğu gibi basılıyor

`test_bibtex` dönüşümü DİZGE olarak sabitliyor; burası üretilen LaTeX'in iki
motorda da gerçekten derlendiğini soruyor (tanımsız bir makro, eksik paket
ya da plain.bst'nin küçük harfe çevirmesi dizge testinden kaçar).
"""

import os
import re
import shutil
import subprocess
import tempfile

import pytest

from core.bibtex import normallestir

pytestmark = pytest.mark.skipif(
    not (shutil.which("pdflatex") and shutil.which("bibtex")),
    reason="pdflatex ve bibtex gerekli")

_KAYITLAR = [
    " @article{Madge_2010, title={Classical NF-κB Activation Negatively "
    "Regulates Noncanonical NF-κB-dependent CXCL12 Expression}, volume={285}, "
    "journal={Journal of Biological Chemistry}, author={Madge, Lisa A. and "
    "May, Michael J.}, year={2010}, month=Dec, pages={38069\N{EN DASH}38077} }\n",
    " @article{Li_2014, title={Influence of electronic structures of doped TiO\n"
    "                    <sub>2</sub>\n                    on their photocatalysis},"
    " volume={9}, journal={physica status solidi (RRL) - Rapid Research Letters},"
    " author={Li, Wenxian}, year={2014}, month=Nov, pages={10\N{EN DASH}27} }\n",
    " @article{Jadhav_2026, title={Phase-Selective Engineering of Mixed-Phase "
    "TiO₂ for Efficient Solar Photocatalysis}, publisher={Cassyni}, "
    "author={Jadhav, Amol}, year={2026}, month=Sept }\n",
]
_ONSOZ = {
    "pdflatex": "\\documentclass{article}\n\\usepackage[T1]{fontenc}\n"
                "\\usepackage[utf8]{inputenc}\n",
    "lualatex": "\\documentclass{article}\n\\usepackage{fontspec}\n",
}


@pytest.mark.parametrize("motor", ["pdflatex", "lualatex"])
def test_DOI_kaynagi_iki_motorda_HATASIZ_ve_EKSIKSIZ_basiliyor(motor):
    if not shutil.which(motor):
        pytest.skip(motor + " yok")
    import pypdfium2
    from gui.pdfium_lock import pdfium_lock

    d = tempfile.mkdtemp(prefix="kaynakca_derleme_")
    try:
        with open(os.path.join(d, "refs.bib"), "w", encoding="utf-8") as f:
            for ham in _KAYITLAR:
                f.write(normallestir(ham)[0] + "\n\n")
        with open(os.path.join(d, "a.tex"), "w", encoding="utf-8") as f:
            f.write(_ONSOZ[motor] + "\\begin{document}\n\\nocite{*}\n"
                    "\\bibliographystyle{plain}\n\\bibliography{refs}\n"
                    "\\end{document}\n")
        for komut in ([motor], ["bibtex"], [motor], [motor]):
            arg = (["-interaction=nonstopmode", "a.tex"] if komut[0] == motor
                   else ["a"])
            subprocess.run(komut + arg, cwd=d, capture_output=True, timeout=180)
        with open(os.path.join(d, "a.log"), encoding="utf-8",
                  errors="replace") as f:
            gunluk = f.read()
        with pdfium_lock:
            belge = pypdfium2.PdfDocument(os.path.join(d, "a.pdf"))
            try:
                metin = "".join(s.get_textpage().get_text_bounded()
                                for s in belge)
            finally:
                belge.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)

    hatalar = [s for s in gunluk.splitlines() if s.startswith("!")]
    assert not hatalar, hatalar
    assert "Missing character" not in gunluk, re.findall(
        r"Missing character: There is no \S+", gunluk)
    # pdfium satır sonu tiresini U+0002 veriyor; bitişik harf (fi, ffi) bazı
    # dağıtımların yazı tipinde metne hiç dönmüyor (MiKTeX: "e cient"), o
    # yüzden denetlenen parçalarda bitişik harf yok.
    metin = re.sub(r"\s+", " ", metin.replace("\x02", "")).lower()
    # ÖNKOŞUL: kaynakça basıldı; yoksa aşağıdakiler boşa geçer
    assert "madge" in metin and "jadhav" in metin, metin[:300]
    assert "nf-κb" in metin, metin[:600]
    assert "mixed-phase tio2 for" in metin and "doped tio2 on their" in metin, \
        metin[:600]
    assert "sub>" not in metin
