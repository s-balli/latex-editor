r"""Hata ipuçları GERÇEK derleyici çıktısıyla doğru komutu gösteriyor mu.

NEDEN AYRI DOSYA. Bu testler pdflatex gerektiriyor ve CI'da TeX Live yalnız
`derle` işinde kurulu. Matrix (`test`) işine konsaydı `skipif` yüzünden HER
ZAMAN atlanır, kapı sessizce ölü kalırdı; iş akışı bu tuzağı `test_derle_sh`,
`test_synctex_live` ve `test_tablo_derleme` için zaten belgeliyor.

NE SINANIYOR. `tests/test_error_hints.py` bağlam satırını DİZGE olarak
sabitliyor ve o dizgeler buradan, yani gerçek pdflatex çıktısından alındı.
Buradaki testler asıl soruyu soruyor: pdflatex bağlam satırını gerçekten
iddia ettiğimiz yerde mi kesiyor. Kusur tam bu varsayımdan çıktı.

  kod ilk komudu alıyordu    ->  "Tanımsız komut (\textbf)" (suçsuz komut)
  TeX satırı suçludan sonra kesiyor -> aranan komut satırın SONUNCUSU

Zincir uçtan uca koşuyor: pdflatex -> core.log_parser -> core.error_hints.
Aradaki üç halkadan biri bozulursa (log biçimi değişir, log_parser bağlamı
başka satırdan alır, ipucu çıkarımı bozulur) bu dosya düşer.
"""

import os
import re
import shutil
import subprocess
import tempfile

import pytest

from core.error_hints import get_hint
from core.log_parser import parse_output

pdflatex = shutil.which("pdflatex")
pytestmark = pytest.mark.skipif(not pdflatex, reason="pdflatex gerekli")

_BELGE = ("\\documentclass{article}\n"
          "\\begin{document}\n"
          "%s\n"
          "\\end{document}\n")


def _derle_ve_ipucu(govde: str):
    """Gövdeyi derle, logu ayrıştır, ilk 'Undefined control sequence' ipucunu ver.

    Dönüş: (ipucu_kimliği, parametreler, bağlam_satırı)
    """
    d = tempfile.mkdtemp(prefix="ipucu_derleme_")
    try:
        p = os.path.join(d, "a.tex")
        with open(p, "w", encoding="utf-8") as f:
            f.write(_BELGE % govde)
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
             "-output-directory", d, p],
            capture_output=True, timeout=120)
        log = os.path.join(d, "a.log")
        assert os.path.isfile(log), "pdflatex log üretmedi"
        with open(log, encoding="utf-8", errors="replace") as f:
            r = parse_output(f.read())
    finally:
        shutil.rmtree(d, ignore_errors=True)

    err = next((e for e in r.errors
                if "Undefined control sequence" in e.message), None)
    # ÖNKOŞUL: hata gerçekten ayrıştırılmalı, yoksa kapı boşalır.
    assert err is not None, \
        "log'da 'Undefined control sequence' ayrıştırılamadı: %r" % \
        [e.message for e in r.errors]
    assert err.context, "log_parser bağlam satırını yakalamadı"
    h = get_hint(err.message, err.context)
    assert h is not None and h[0] == "undefined_control"
    return h[0], h[1], err.context


class TestSucluKomutDogruBulunuyor:
    @pytest.mark.parametrize("govde,suclu", [
        # satırda TEK komut: ilk = son, ayrım yok ama geri dönük kontrol
        (r"\bilinmeyenkomut", r"\bilinmeyenkomut"),
        # önce düz metin: eskiden komut adı hiç yazılmıyordu
        (r"Merhaba \bilinmeyenkomut", r"\bilinmeyenkomut"),
        ("\\section{Giris}\n\nBu bolumde \\ozelKomut kullanilir.",
         r"\ozelKomut"),
        # önce GEÇERLİ komut(lar): eskiden onlardan biri suçlanıyordu
        (r"\textbf{Kalin} \bilinmeyenkomut", r"\bilinmeyenkomut"),
        (r"\emph{a} \textit{b} \textbf{c} \sonuncu", r"\sonuncu"),
        (r"\textbf{\icerdekiKomut}", r"\icerdekiKomut"),
        (r"$x = \alpha + \tanimsizFonksiyon$", r"\tanimsizFonksiyon"),
    ])
    def test_ipucu_gercekten_tanimsiz_olan_komutu_gosteriyor(self, govde, suclu):
        _kimlik, params, ctx = _derle_ve_ipucu(govde)
        assert params.get("cmd") == suclu, \
            "bağlam %r -> %r beklenirken %r" % (ctx, suclu, params.get("cmd"))


class TestBaglamSatiriVarsayimi:
    r"""Düzeltmenin dayandığı varsayım: TeX satırı SUÇLUDAN SONRA kesiyor.

    Varsayım yanlışsa "son komutu al" kuralı da yanlış olur. Bu yüzden
    ipucunun kendisinden bağımsız olarak, ham bağlam satırının biçimi de
    sınanıyor.
    """

    def test_suclu_komut_baglam_satirinin_SONUNDA(self):
        _kimlik, _params, ctx = _derle_ve_ipucu(
            r"\textbf{Kalin} \emph{Egik} \bilinmeyenkomut")
        komutlar = re.findall(r"\\[A-Za-z]+", ctx)
        # önkoşul: vaka gerçekten birden fazla komut içermeli
        assert len(komutlar) > 1, ctx
        assert komutlar[-1] == "\\bilinmeyenkomut", ctx
        # ve eski davranışın alacağı komut BAŞKA biri olmalı
        assert komutlar[0] != "\\bilinmeyenkomut", ctx

    def test_ilk_komut_suclu_DEGIL(self):
        """Eski kodun verdiği yanıt gerçek çıktıda da yanlış çıkıyor."""
        _kimlik, params, ctx = _derle_ve_ipucu(
            r"\textbf{Kalin} \bilinmeyenkomut")
        ilk = re.findall(r"\\[A-Za-z]+", ctx)[0]
        assert ilk == "\\textbf", ctx
        assert params["cmd"] != ilk
