"""`template/` agacindaki DOSYA ADLARINI test verisine yazar.

NEDEN. `tests/test_quick_open.py` hizli acma siralamasini GERCEK sablon
dosya adlari uzerinde siniyordu, ama `template/` 207 MB ve .gitignore'da:
kapi hicbir CI isinde kosmuyordu. Testin kullandigi tek sey ADLAR, icerik
degil; adlar 6 KB tutuyor ve depoda durabilir.

Kullanim (sablonlarin durdugu makinede):

    python scripts/sablon_adlari_uret.py

Cikti: tests/veri/sablon_dosya_adlari.json
Sablonlar degisince yeniden calistirilir; `tests/test_quick_open.py`
icindeki tazelik kapisi, calistirmayi unutursan soyler.
"""

import json
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)                                     # core.*
sys.path.insert(0, os.path.join(KOK, "desktop"))            # gui.*

from gui.quick_open import collect_project_files            # noqa: E402

SABLON = os.path.join(KOK, "template")
HEDEF = os.path.join(KOK, "tests", "veri", "sablon_dosya_adlari.json")

# Testin kendi esigi: ucten az dosyali projede siralama sorusu anlamsiz.
ASGARI_DOSYA = 3


def topla(sablon_kok: str) -> dict:
    agac = {}
    for ad in sorted(os.listdir(sablon_kok)):
        proje = os.path.join(sablon_kok, ad)
        if not os.path.isdir(proje):
            continue
        dosyalar = collect_project_files(proje)
        if len(dosyalar) >= ASGARI_DOSYA:
            agac[ad] = dosyalar
    return agac


def main() -> int:
    if not os.path.isdir(SABLON):
        print("template/ yok, uretilecek bir sey de yok:", SABLON)
        return 1
    agac = topla(SABLON)
    os.makedirs(os.path.dirname(HEDEF), exist_ok=True)
    with open(HEDEF, "w", encoding="utf-8", newline="\n") as f:
        json.dump(agac, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print("%d proje, %d dosya adi -> %s"
          % (len(agac), sum(len(v) for v in agac.values()), HEDEF))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
