# -*- coding: utf-8 -*-
"""Uretilen paketin ICINDE ne var, denetle.

NEDEN VAR: yazim denetiminin pakete girmesi UC ayri seyin bir arada
olmasina bagli ve ucu de ayri sekilde sessizce kaybolabiliyor:

  1. `spylls` modulu (PYZ icinde, saf Python)
  2. bizim `sozlukler/tr_TR.dic` + `.aff` (spec `.xz`den aciyor)
  3. spylls'in KENDI `en_US` sozlugu (ikinci dil ozelligi buna dayaniyor)

Ucuncusu ilk denemede GERCEKTEN EKSIK CIKTI: PyInstaller modul analizi
yalniz `.py` dosyalarini goruyor, paketin veri dosyalarini gormuyor. Exe
sorunsuz uretiliyordu ve ikinci dil calismiyordu. Testler bunu goremez,
cunku testler paketlenmemis kaynakta kosuyor.

Arayuz dili de ayni sinifta: uygulama IKI katalog kullaniyor, bizimki
(`translations/latexeditor_<dil>.qm`) ve Qt'nin kendisi
(`qtbase_<dil>.qm`). Ikincisinin adi bizde hicbir yerde gecmiyor,
PyInstaller Qt hook'u topluyor; dusarsa arayuz Turkce acilir ama Qt'nin
urettigi sag tik menuleri ve dugmeler Ingilizce kalir.

Ayrica pakete OLU AGIRLIK girmedigi de denetleniyor: `.xz` sozlukler
(1.6 MB), `.ts` ceviri kaynaklari (~300 KB) ve Qt'nin kullanilmayan dil
kataloglari (99 dosya, 6.9 MB; scripts/paket_suzgeci.py eliyor).

Kullanim:
    python scripts/paket_dogrula.py "desktop/dist/LaTeX Editor.exe"
    python scripts/paket_dogrula.py desktop/dist/LaTeXEditor      # onedir
"""
from __future__ import annotations

import os
import sys


_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tek_dosya_icerigi(yol):
    """Onefile exe: PyInstaller CArchive TOC'u. (ad, acilmis_boyut) verir."""
    from PyInstaller.archive.readers import CArchiveReader
    # toc: ad -> (offset, veri_uzunlugu, ACILMIS_uzunluk, sikistirma, tur)
    return [(ad, g[2]) for ad, g in CArchiveReader(yol).toc.items()]


def _dizin_icerigi(kok):
    """Onedir: dizin agacindaki (goreli yol, boyut) ciftleri."""
    adlar = []
    for r, _d, fs in os.walk(kok):
        for f in fs:
            tam = os.path.join(r, f)
            adlar.append((os.path.relpath(tam, kok), os.path.getsize(tam)))
    return adlar


def _beklenen_boyut(ad):
    """`sozlukler/<ad>.xz`in acilmis boyutu; kaynak yoksa None.

    Sabit bir esik yerine KAYNAKTAN hesaplaniyor: sozluk guncellenince
    denetim kendiliginden guncel kaliyor.
    """
    yol = os.path.join(_KOK, "sozlukler", ad + ".xz")
    if not os.path.exists(yol):
        return None
    import lzma
    toplam = 0
    with lzma.open(yol, "rb") as f:
        while True:
            parca = f.read(1 << 20)
            if not parca:
                return toplam
            toplam += len(parca)


def dogrula(yol: str) -> int:
    if os.path.isdir(yol):
        girdiler = _dizin_icerigi(yol)
    else:
        girdiler = _tek_dosya_icerigi(yol)
    boyut = {a.replace("\\", "/"): b for a, b in girdiler}
    duz = list(boyut)

    hata = []

    def var_mi(parca):
        return [a for a in duz if parca in a]

    tr = var_mi("sozlukler/tr_TR.dic")
    if not tr:
        hata.append("tr_TR.dic pakete GIRMEMIS (spec sozlugu acamamis olabilir)")
    if not var_mi("sozlukler/tr_TR.aff"):
        hata.append("tr_TR.aff pakete GIRMEMIS")

    # BOYUT DA DENETLENIYOR, yalniz varlik degil. Yarim acilmis bir sozluk
    # pakete girip bu kapidan "paket tam" diye geciyordu; OLCULDU
    # (2026-09-05): ucte birine kirpilmis .dic ile gunluk on Turkce
    # kelimenin sekizi yanlis sayiliyor, yani yazim denetimi calisiyor
    # gorunup neredeyse her kelimeyi ciziyor.
    for ad in ("tr_TR.dic", "tr_TR.aff"):
        # Tam eslesme: "sozlukler/tr_TR.dic.xz" de alt dize olarak icerir.
        pakettekiler = [b for a, b in boyut.items()
                        if a.endswith("sozlukler/" + ad)]
        beklenen = _beklenen_boyut(ad)
        if pakettekiler and beklenen is not None:
            if max(pakettekiler) != beklenen:
                hata.append("%s KIRPILMIS: pakette %d bayt, olmasi gereken %d"
                            % (ad, max(pakettekiler), beklenen))

    # Ikinci dil: spylls'in kendi en_US'u. ILK DENEMEDE EKSIKTI.
    if not var_mi("spylls/hunspell/data/en/en_US.dic"):
        hata.append("spylls en_US.dic pakete GIRMEMIS: ikinci dil calismaz")
    if not var_mi("spylls/hunspell/data/en/en_US.aff"):
        hata.append("spylls en_US.aff pakete GIRMEMIS: ikinci dil calismaz")

    # ARAYUZ DILI: iki ayri katalog, ikisi de ayri sekilde dusebilir.
    #
    #   1. Bizim `translations/latexeditor_<dil>.qm`imiz. Spec'in `datas`
    #      listesinden geliyor, yani adi bir yerde yazili.
    #   2. Qt'nin KENDI `qtbase_<dil>.qm`i. Bunun adi HICBIR YERDE gecmiyor:
    #      PyInstaller Qt hook'u `QtCore -> ['qt', 'qtbase']` eslemesinden
    #      topluyor. Hook degisirse ya da kurulumda katalog yoksa sessizce
    #      dusuyor; arayuz Turkce acilir ama Qt'nin urettigi sag tik
    #      menuleri ve diyalog dugmeleri Ingilizce kalir.
    #
    # Testler ikisini de goremez: testler paketlenmemis kaynakta kosuyor ve
    # orada `QLibraryInfo` dogrudan PyQt6 kurulumunu gosteriyor.
    for ad in ("latexeditor_tr.qm", "latexeditor_en.qm"):
        pakettekiler = [b for a, b in boyut.items()
                        if a.endswith("translations/" + ad)]
        if not pakettekiler:
            hata.append("%s pakete GIRMEMIS: arayuz o dilde acilmaz" % ad)
            continue
        kaynak = os.path.join(_KOK, "desktop", "translations", ad)
        if os.path.exists(kaynak):
            beklenen = os.path.getsize(kaynak)
            if max(pakettekiler) != beklenen:
                hata.append("%s KIRPILMIS: pakette %d bayt, olmasi gereken %d"
                            % (ad, max(pakettekiler), beklenen))

    if not [a for a in duz if a.endswith("/qtbase_tr.qm") or a == "qtbase_tr.qm"]:
        hata.append("Qt katalogu qtbase_tr.qm pakete GIRMEMIS: Turkce "
                    "arayuzde Qt'nin kendi menuleri Ingilizce kalir")

    # Olu agirlik denetimi
    xz = var_mi(".xz")
    if xz:
        hata.append("sikistirilmis sozluk de paketlenmis (olu agirlik): %s"
                    % xz[:3])
    # Ceviri KAYNAK dosyalari: yalniz derlenmis `.qm` okunuyor, `.ts`ler
    # ~300 KB olu agirlik. Alt dize DEGIL son ek denetimi; `.xz` kapisinda
    # alt dize kullanmak uydurma bir boyut hatasi dogurmustu.
    ts = [a for a in duz if a.endswith(".ts")]
    if ts:
        hata.append("ceviri kaynak dosyalari da paketlenmis (olu agirlik): %s"
                    % ts[:3])

    # Qt'nin KULLANILMAYAN dilleri. Hook `QtCore -> ['qt', 'qtbase']`,
    # `Qsci -> ['qscintilla']` ve `QtHelp -> ['qt_help']` eslemelerinden o
    # dizindeki butun dilleri topluyor. Yayinlanan v1.0.21 exe'sinde
    # olculdu: 101 katalog, acilmis 6.9 MB, kullanilan iki tanesi.
    # scripts/paket_suzgeci.py bunu yapim aninda eliyor; bu kapi suzgecin
    # sessizce dusmedigini soyluyor.
    istenen = {"qtbase_%s.qm" % a.rsplit("/", 1)[-1][len("latexeditor_"):-3]
               for a in duz if "translations/latexeditor_" in a}
    fazla = [a for a in duz
             if "PyQt6/" in a and "/translations/" in a
             and a.rsplit("/", 1)[-1] not in istenen]
    if fazla:
        hata.append("Qt'nin kullanilmayan %d dil katalogu paketlenmis "
                    "(olu agirlik): %s" % (len(fazla), sorted(fazla)[:3]))
    for istenmeyen in ("data/ru/", "data/sv/"):
        if var_mi(istenmeyen):
            hata.append("spylls'in kullanilmayan sozlugu paketlenmis: %s"
                        % istenmeyen)

    print("paket icerigi: %d girdi" % len(duz))
    # Yalniz DENETLENENLER listeleniyor. Qt'nin butun dilleri yazilsaydi
    # (gercek pakette 100'u askin katalog) CI kutugu okunmaz olurdu.
    for a in sorted(set(var_mi("sozlukler/") + var_mi("spylls/hunspell/data/")
                        + var_mi("translations/latexeditor")
                        + var_mi("qtbase_tr.qm"))):
        print("  bulundu: %s" % a)

    if hata:
        print()
        for h in hata:
            print("HATA: %s" % h)
        return 1
    print("paket tam: tr_TR sozlugu, spylls en_US ve ceviri kataloglari "
          "icinde, olu agirlik yok")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("kullanim: paket_dogrula.py <exe ya da dist dizini>")
    sys.exit(dogrula(sys.argv[1]))
