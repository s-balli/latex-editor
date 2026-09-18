# -*- coding: utf-8 -*-
"""TANI: macOS'ta harf duyarsizligi gercekten kusur uretiyor mu.

NEDEN. "Klasorde Ara"nin kok denetimi harf vakalarini `os.name != "nt"`
ile atliyordu; gerekce "POSIX'te farkli yazim farkli dosyadir" diyordu.
macOS POSIX ama ONTANIMLI APFS birimi harf DUYARSIZ: `.../TEZ/a.tex` ile
`.../tez/a.tex` AYNI dosya. Duzeltmenin dayandigi `os.path.normcase` ise
POSIX'te kimlik islevi, yani macOS'ta hicbir sey yapmiyordu.

UC KOL yazdiriliyor:
  KOL A  dosya sistemi harf duyarsiz mi (sonda dosyasiyla olculuyor)
  KOL B  duzeltme DEVRE DISI iken `_kok_disinda_mi` ne diyor
  KOL C  duzeltme ETKIN iken ne diyor

B'de uyari cikip C'de cikmazsa hem kusur hem duzeltme dogrulanmis olur.
A "duyarli" derse bu kosucuda kusur zaten olusmaz ve olcum bunu soyler.
"""
import os
import sys
import tempfile
from types import SimpleNamespace

KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KOK)
sys.path.insert(0, os.path.join(KOK, "desktop"))

import gui.mixins.project_search_ops as pso                      # noqa: E402

print("platform:", sys.platform, "| os.name:", os.name)
print("normcase('/A/B') ->", os.path.normcase("/A/B"))


class _Sahte(pso.ProjectSearchMixin):
    """`_kok_disinda_mi` icin gereken en kucuk yuzey."""

    def __init__(self, dosya_yolu):
        self._dosya = dosya_yolu

    def _current_editor(self):
        return SimpleNamespace(file_path=self._dosya,
                               hasSelectedText=lambda: False)


def kol(etiket, duzeltme_acik):
    gercek = pso._ayni_agacta
    if not duzeltme_acik:
        pso._ayni_agacta = lambda yol, kok: False
    try:
        with tempfile.TemporaryDirectory() as d:
            kok = os.path.join(d, "Tez")
            os.makedirs(os.path.join(kok, "bolumler"))
            dosya = os.path.join(kok, "bolumler", "a.tex")
            with open(dosya, "w", encoding="utf-8") as f:
                f.write("x\n")
            s = _Sahte(dosya)
            sonuc = {
                "ayni yazim": s._kok_disinda_mi(kok),
                "kok BUYUK": s._kok_disinda_mi(kok.upper()),
                "kok kucuk": s._kok_disinda_mi(kok.lower()),
            }
    finally:
        pso._ayni_agacta = gercek
    print("=== " + etiket + " ===")
    for ad, u in sonuc.items():
        print("    %-12s -> %s" % (ad, u if u else "(uyari yok)"))
    return sonuc


with tempfile.TemporaryDirectory() as d:
    with open(os.path.join(d, "SondaDosyasi"), "w", encoding="utf-8") as f:
        f.write("x")
    duyarsiz = os.path.exists(os.path.join(d, "sondadosyasi"))
print("KOL A: dosya sistemi harf DUYARSIZ mi :", duyarsiz)
print()

b = kol("KOL B: duzeltme DEVRE DISI", False)
print()
c = kol("KOL C: duzeltme ETKIN", True)
print()

normcase_etkisiz = os.path.normcase("/A/B") == "/A/B"
if not duyarsiz:
    print("SONUC: bu kosucuda dosya sistemi DUYARLI, kusur burada olusmaz")
elif not normcase_etkisiz:
    # Windows: `normcase` kucuk harfe indiriyor ve kusuru O gizliyor.
    # Kosul eksik oldugu icin B kolu da temiz cikar; beklenen budur.
    print("SONUC: `normcase` bu platformda harfi indiriyor, kusurun ikinci "
          "kosulu yok (macOS'ta kimlik islevi)")
else:
    kusur = bool(b["kok BUYUK"]) and bool(b["kok kucuk"])
    temiz = not (c["kok BUYUK"] or c["kok kucuk"] or c["ayni yazim"])
    print("kusur uretildi mi (B):", kusur)
    print("duzeltme tuttu mu (C):", temiz)
    print("SONUC:", "KUSUR DOGRULANDI VE DUZELTME TUTUYOR"
          if (kusur and temiz) else "BEKLENMEYEN DURUM")
