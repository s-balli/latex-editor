# -*- coding: utf-8 -*-
"""TANI: macOS'ta dosya sistemi harf duyarsiz mi, ve bu bir kusur mu.

NEDEN. `tests/test_project_search.py` icindeki iki harf vakasi
`os.name != "nt"` ile atlaniyor ve gerekce "POSIX'te farkli yazim farkli
dosyadir" diyor. macOS POSIX ama ONTANIMLI APFS birimi harf DUYARSIZ:
`.../TEZ/a.tex` ile `.../tez/a.tex` AYNI dosya. Duzeltme ise
`os.path.normcase`e dayaniyor ve normcase POSIX'te kimlik islevi, yani
macOS'ta hicbir sey yapmiyor.

Eger dosya sistemi gercekten duyarsizsa, Windows'ta duzeltilen kusur
macOS'ta HALA yasiyor demektir: kullanici klasorun ICINDEki bir dosyada
arama yaparken "acik dosya bu klasorun disinda" uyarisi aliyor.

Iki kol yazdiriliyor:
  KOL A  dosya sistemi duyarsiz mi (sonda dosyasiyla olculuyor)
  KOL B  `_kok_disinda_mi` yalnizca yazim degisince ne diyor
Ikisi de "duyarsiz" ve "uyari var" derse kusur dogrulanmis olur.
"""
import os
import sys
import tempfile
from types import SimpleNamespace

KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KOK)
sys.path.insert(0, os.path.join(KOK, "desktop"))

from gui.mixins.project_search_ops import ProjectSearchMixin      # noqa: E402

print("platform:", sys.platform, "| os.name:", os.name)

with tempfile.TemporaryDirectory() as d:
    sonda = os.path.join(d, "SondaDosyasi")
    with open(sonda, "w", encoding="utf-8") as f:
        f.write("x")
    duyarsiz = os.path.exists(os.path.join(d, "sondadosyasi"))
    print("KOL A: dosya sistemi harf DUYARSIZ mi :", duyarsiz)
    print("       normcase('/A/B') ->", os.path.normcase("/A/B"))


class _Sahte(ProjectSearchMixin):
    """Yalniz `_kok_disinda_mi` icin gereken en kucuk yuzey."""

    def __init__(self, dosya_yolu):
        self._dosya = dosya_yolu

    def _current_editor(self):
        return SimpleNamespace(file_path=self._dosya,
                               hasSelectedText=lambda: False)


with tempfile.TemporaryDirectory() as d:
    kok = os.path.join(d, "Tez")
    os.makedirs(os.path.join(kok, "bolumler"))
    dosya = os.path.join(kok, "bolumler", "a.tex")
    with open(dosya, "w", encoding="utf-8") as f:
        f.write("x\n")

    s = _Sahte(dosya)
    print("KOL B: ayni yazim      ->", repr(s._kok_disinda_mi(kok)) or "(bos)")
    for etiket, bicim in (("kok BUYUK", str.upper), ("kok kucuk", str.lower)):
        uyari = s._kok_disinda_mi(bicim(kok))
        print("       %-14s -> %s" % (etiket, repr(uyari)))
        # DUYARLI bir dosya sisteminde farkli yazim GERCEKTEN baska bir yol,
        # yani uyari dogru; kusur yalniz DUYARSIZ dosya sisteminde kusur.
        if uyari and duyarsiz:
            print("         ^ KUSUR: dosya kokun ICINDE ama disinda deniyor")
        elif uyari:
            print("         (duyarli dosya sistemi: uyari DOGRU)")
