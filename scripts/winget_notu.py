# -*- coding: utf-8 -*-
"""winget manifestindeki `ReleaseNotes` alanini etiket notuyla degistirir.

komac notu GitHub yayin sayfasinin TAMAMINDAN aliyor (yayin sayfasinin HTML'i)
ve metni degistiren bir secenegi yok: 1.2.5'te nota iki dilin kurulum
bolumleriyle 86 satir girdi, `winget show` hepsini gosteriyor. release.yml'in
winget isi PR'i acildiktan sonra dalindaki locale manifestini cekiyor, bu
betik notu yayin sayfasindaki degisiklik listesinin kaynagiyla (etiket notu)
degistiriyor, is ayni dala ikinci commit olarak yaziyor.

    python3 scripts/winget_notu.py <manifest_klasoru> <not_dosyasi>
"""
import glob
import os
import sys


def notu_degistir(metin: str, not_metni: str) -> str:
    """`metin` (locale manifesti) icindeki ReleaseNotes'u `not_metni` yap.

    Alan bir blok skaler (`|-`) olarak yaziliyor; eski deger ust duzeydeki
    bir sonraki anahtara kadar (girintili ya da bos satirlar) atiliyor. Alan
    yoksa ReleaseNotesUrl'den, o da yoksa ManifestType'tan once ekleniyor.
    """
    blok = ["ReleaseNotes: |-"] + [
        ("  " + s) if s.strip() else ""
        for s in not_metni.strip("\n").split("\n")]
    satirlar = metin.split("\n")
    cikti, i, yazildi = [], 0, False
    while i < len(satirlar):
        s = satirlar[i]
        if s.startswith("ReleaseNotes:"):
            if not yazildi:         # ikinci kez yazilirsa anahtar yinelenir
                cikti.extend(blok)
                yazildi = True
            i += 1
            while i < len(satirlar) and (satirlar[i].startswith(" ")
                                         or not satirlar[i].strip()):
                i += 1
            continue
        if not yazildi and s.startswith(("ReleaseNotesUrl:", "ManifestType:")):
            cikti.extend(blok)
            yazildi = True
        cikti.append(s)
        i += 1
    return "\n".join(cikti)


def main(argv) -> int:
    klasor, not_dosyasi = argv[1], argv[2]
    with open(not_dosyasi, encoding="utf-8") as f:
        not_metni = f.read()
    if not not_metni.strip():
        print("HATA: etiket notu bos", file=sys.stderr)
        return 1
    dosyalar = glob.glob(os.path.join(klasor, "**", "*.locale.*.yaml"),
                         recursive=True)
    if not dosyalar:
        print("HATA: %s altinda locale manifesti yok" % klasor, file=sys.stderr)
        return 1
    for yol in dosyalar:
        with open(yol, encoding="utf-8", newline="") as f:
            metin = f.read()
        with open(yol, "w", encoding="utf-8", newline="") as f:
            f.write(notu_degistir(metin, not_metni))
        print("ReleaseNotes degisti:", yol)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
