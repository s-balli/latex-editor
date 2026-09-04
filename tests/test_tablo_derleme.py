"""Tablo sihirbazının ÜRETTİĞİ LaTeX gerçekten derleniyor mu.

NEDEN AYRI DOSYA. Bu testler pdflatex gerektiriyor ve CI'da TeX Live yalnız
`derle` işinde kurulu. Matrix (`test`) işinde TeX yok; bu dosya oraya
konsaydı `skipif` yüzünden HER ZAMAN atlanır, kapı sessizce ölü kalırdı.
İş akışı bu tuzağı `test_derle_sh` / `test_synctex_live` için zaten
belgeliyor; bu dosya da aynı sebeple `derle` işinin listesinde.

NE SINANIYOR. `tests/test_latex_tables.py` üretimi DİZGE düzeyinde
sabitliyor (kaç hücre, hangi kaçış). Buradaki testler asıl soruyu soruyor:
kullanıcının belgesine giren blok LaTeX'i bozuyor mu. İki kusur da tam
buradan çıktı ve dizge testleri tek başına yakalayamazdı:

  düzensiz satır  -> "! Extra alignment tab has been changed to \\cr"
  hücrede `^`     -> "! Missing $ inserted."
"""

import os
import shutil
import subprocess
import tempfile

import pytest

from core.latex_tables import TableOptions, build_tabular

pdflatex = shutil.which("pdflatex")
pytestmark = pytest.mark.skipif(not pdflatex, reason="pdflatex gerekli")

_ONSOZ = ("\\documentclass{article}\n"
          "\\usepackage{booktabs}\n"
          "\\usepackage{tabularx}\n"
          "\\usepackage{longtable}\n"
          "\\begin{document}\n")


def _derle(govde: str) -> tuple[bool, str]:
    """Tablo bloğunu asgari bir belgeye koyup derle. (başarılı_mı, ilk_hata)."""
    d = tempfile.mkdtemp(prefix="tablo_derleme_")
    try:
        p = os.path.join(d, "t.tex")
        with open(p, "w", encoding="utf-8") as f:
            f.write(_ONSOZ + govde + "\n\\end{document}\n")
        r = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
             "-output-directory", d, p],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        if r.returncode == 0:
            return True, ""
        for satir in (r.stdout or "").split("\n"):
            if satir.startswith("!"):
                return False, satir.strip()
        return False, "bilinmeyen derleme hatası"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _derlenmeli(rows, aligns, opts=None):
    kod = build_tabular(rows, aligns, opts)
    ok, hata = _derle(kod)
    assert ok, "üretilen tablo derlenmedi: %s\n%s" % (hata, kod)


class TestDuzensizSatirlarDerleniyor:
    """CSV'den gelen satırlar farklı uzunlukta olabilir."""

    @pytest.mark.parametrize("rows", [
        [["Ad", "Yil", "Deger"], ["Ozturk", "2024", "12", "FAZLA"],
         ["Cagri", "2023", "9"]],
        [["a", "b", "c"], ["d"]],
        [["a"], ["b", "c", "d"]],
        [["a", ""], ["", "b"]],
    ])
    def test_duzensiz_tablo_derleniyor(self, rows):
        _derlenmeli(rows, ["l", "c", "r"])

    def test_duzenli_tablo_bozulmadi(self):
        _derlenmeli([["a", "b"], ["c", "d"]], ["l", "r"])


class TestOzelKarakterlerDerleniyor:
    """Hücre metni LaTeX'i bozmamalı."""

    @pytest.mark.parametrize("hucre", [
        "R^2", "a^b^c", "5~10", "a^b~c",
        "%50", "A&B", "x_1", "#5", "$5",
        "100% & x_1 #3 $5 R^2 5~10",
    ])
    def test_ozel_karakterli_hucre_derleniyor(self, hucre):
        _derlenmeli([["Olcut", "Deger"], [hucre, "1"]], ["l", "r"])

    def test_latex_komutu_hala_calisiyor(self):
        """Ters eğik çizgi bilinçli olarak kaçırılmıyor; bu serbestlik kalmalı."""
        _derlenmeli([["a", "b"], ["\\textbf{kalın}", "\\emph{eğik}"]],
                    ["l", "l"])


class TestOrtamlarDerleniyor:
    """Diğer üretim yolları da bozulmamalı."""

    @pytest.mark.parametrize("opts", [
        TableOptions(),
        TableOptions(environment="longtable"),
        TableOptions(environment="tabularx"),
        TableOptions(booktabs=False, vertical_lines=True),
        TableOptions(header_row=False),
        TableOptions(wrap_table=False),
        TableOptions(caption="Ba%lık & test", label="tab:x"),
    ])
    def test_ortam_derleniyor(self, opts):
        _derlenmeli([["Ad", "Değer"], ["R^2", "0,91"], ["%pay", "5~10"]],
                    ["l", "p"], opts)
