# -*- coding: utf-8 -*-
"""Yazım denetimi çekirdeği — LaTeX farkındalıklı, Qt'süz.

LaTeX'te yazım denetiminin bir numaralı katili YANLIŞ POZİTİFTİR. Düz bir
denetleyici `\\usepackage`, `\\alpha`, `sec:giris`, `ornek2024` hepsinin
altını çizer ve araç kullanılamaz olur. Bu modülün asıl işi sözlüğe bakmak
değil, NEYE bakılacağına karar vermek.

Ölçüldü (2026-09-03, hunspell-tr + spylls):
  - ek zincirleri 15/15 (kitaplarımızdan, yapabileceklerimizden...)
  - gerçek Türkçe şablonlarda %3.0 yanlış pozitif (4561 kelime)
  - gerçek İngilizce şablonlarda %2-3 (özel adlar ayrıldıktan sonra)

Üç tuzak ve çözümleri:

1. AKSAN MAKROLARI. Eski şablonlar Türkçe harfleri `M\\"{u}hendislik` diye
   yazıyor. Metni önden normalleştirmek KONUMLARI KAYDIRIR ve editör yanlış
   yeri gösterir; onun yerine tarayıcı bunları kelimenin İÇİNDE tek harf
   olarak yutuyor, kelimenin başlangıç konumu özgün metinde kalıyor.

2. `\\u` ve `\\c` GERÇEK KOMUTLARIN DA ÖNEKİ (`\\usepackage`, `\\cite`).
   Harf adlı aksanlar bu yüzden SÜSLÜ PARANTEZ şartı istiyor; yalnız
   noktalama adlı olanlar (`\\"o`, `\\.I`) parantezsiz kabul ediliyor.
   Ölçüldü: açgözlü desen `\\usepackage`'ı `spackage`'a çevirip yanlış
   pozitifi %9.9'dan %12.1'e ÇIKARIYORDU.

3. KOMUT ARGÜMANLARININ HEPSİ ATILAMAZ. `\\section{Giriş}` ve
   `\\caption{Şekil}` düz metindir, denetlenmeli; `\\label{sec:giris}` ve
   `\\cite{ornek2024}` denetlenmemeli. Bu yüzden ATILACAKLAR listelenmiş,
   tanınmayan komutun argümanı metin sayılıyor.

Dil SEÇİLİR, iki sözlüğe birden bakılmaz. Ölçüldü: ikili denetimin
"kurtardığı" kelimeler özel ad (Ballı, Muğla, Dergisi) ve Lorem Ipsum'un
Latincesi (elit, enim, erat) çıkıyor; özel adın çözümü ikinci sözlük değil,
`buyuk_atla` ve kullanıcı sözlüğü.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass

try:
    from spylls.hunspell import Dictionary
    SPYLLS_VAR = True
except ImportError:  # pragma: no cover — uygulama spylls'siz de AÇILMALI
    Dictionary = None
    SPYLLS_VAR = False


def _require():
    """spylls yoksa anlaşılır hata ver (uygulama başlarken değil, kullanırken)."""
    if not SPYLLS_VAR:
        raise RuntimeError(
            "Yazım denetimi için 'spylls' paketi gerekli (pip install spylls)")


# --------------------------------------------------------------------------
# Aksan makroları
# --------------------------------------------------------------------------

# Noktalama adlı aksanlar: parantezsiz de yazılabilir (\"o), çünkü hiçbir
# komut adının öneki değiller.
_AKSAN_NOKTALAMA = {
    ('"', "u"): "ü", ('"', "U"): "Ü", ('"', "o"): "ö", ('"', "O"): "Ö",
    ('"', "a"): "ä", ('"', "A"): "Ä", ('"', "i"): "ï", ('"', "e"): "ë",
    (".", "I"): "İ", (".", "i"): "İ", (".", "z"): "ż",
    ("'", "e"): "é", ("'", "a"): "á", ("'", "i"): "í", ("'", "o"): "ó",
    ("'", "u"): "ú", ("'", "c"): "ć", ("'", "s"): "ś",
    ("`", "e"): "è", ("`", "a"): "à", ("`", "i"): "ì", ("`", "o"): "ò",
    ("^", "e"): "ê", ("^", "a"): "â", ("^", "i"): "î", ("^", "o"): "ô",
    ("^", "u"): "û", ("~", "n"): "ñ", ("~", "a"): "ã", ("~", "o"): "õ",
}

# Harf adlı aksanlar: SÜSLÜ PARANTEZ ŞART. \u ve \c aksi hâlde
# \usepackage ve \cite ile karışıyor (ölçülmüş hata, bkz. modül başlığı).
_AKSAN_HARF = {
    ("c", "c"): "ç", ("c", "C"): "Ç", ("c", "s"): "ş", ("c", "S"): "Ş",
    ("u", "g"): "ğ", ("u", "G"): "Ğ", ("u", "a"): "ă", ("u", "e"): "ĕ",
    ("v", "s"): "š", ("v", "c"): "č", ("v", "z"): "ž", ("v", "r"): "ř",
    ("H", "o"): "ő", ("H", "u"): "ű", ("k", "a"): "ą", ("k", "e"): "ę",
}

# \i (noktasız ı) ve \j — argümansız, tek başına harf
_TEK_HARF_KOMUT = {"i": "ı", "j": "ȷ", "l": "ł", "o": "ø", "O": "Ø",
                   "aa": "å", "AA": "Å", "ss": "ß", "ae": "æ", "AE": "Æ"}


# --------------------------------------------------------------------------
# Denetlenmeyecek komut argümanları
# --------------------------------------------------------------------------

# Argümanı DÜZ METİN DEĞİL: etiket, anahtar, dosya adı, paket adı, URL.
_ARGUMANI_ATLA = frozenset("""
label ref eqref pageref autoref nameref cref Cref vref
cite citep citet citeauthor citeyear nocite bibliography bibliographystyle
input include includeonly includegraphics graphicspath
usepackage RequirePackage documentclass LoadClass
url href hyperref path lstinputlisting verbatiminput
newcommand renewcommand providecommand newenvironment renewenvironment
DeclareMathOperator newtheorem theoremstyle
setlength addtolength setcounter addtocounter usetikzlibrary
bibitem printbibliography addbibresource
lstset tikzset hypersetup geometry pagestyle thispagestyle
""".split())

# ÖNSÖZ (\begin{document} öncesi) yapılandırmadır, düz metin değildir:
# paket seçenekleri, renk adları, uzunluklar, stil tanımları. Denetlemek
# saf gürültü üretiyor. ÖLÇÜLDÜ (template36-ders, dokuz bölüm): önsöz dahil
# 2533 bulgu, önsöz hariç 1679 -> %34 azalma. Örnek gürültü, tcolorbox
# tanımlarından: colback, colframe, fonttitle, breakable, blue, white.
#
# Ama önsözdeki BAZI argümanlar gerçek metindir ve makalenin en görünür
# yeridir; onlar taranmaya devam ediyor.
_ONSOZ_METIN = frozenset("""
title subtitle author date institute affiliation keywords
shorttitle runningtitle thanks dedication
""".split())

# Bu ortamların İÇİ hiç denetlenmez.
_ATLANACAK_ORTAM = frozenset(
    "verbatim Verbatim lstlisting minted alltt tikzpicture "
    "equation equation* align align* gather gather* eqnarray eqnarray* "
    "displaymath math array matrix pmatrix bmatrix tabular* ".split())

_HARF = re.compile(r"[^\W\d_]", re.UNICODE)

# E-posta ve adresler kelime değildir. `\url{}` argümanı zaten atlanıyor ama
# yazar e-postası düz metinde geçiyor ve parçalanıyordu: eskinhasan@gmail.com
# -> "eskinhasan", "gmail", "com" diye üç yanlış işaret. ÖLÇÜLDÜ
# (template35-asyu): 434 bulgunun 30'u bu sınıftandı.
_RE_ADRES = re.compile(
    r"(?:[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    r"|https?://[^\s{}]+"
    r"|www\.[\w-]+(?:\.[\w-]+)+)", re.UNICODE)


def _harf_mi(ch: str) -> bool:
    return bool(ch) and bool(_HARF.match(ch))


# --------------------------------------------------------------------------
# Belgeden dil
# --------------------------------------------------------------------------

# TeXstudio/TeXworks geleneği; en açık niyet bildirimi, önce buna bakılır.
_RE_TEX_DIL = re.compile(
    r"^\s*%\s*!TEX\s+spellcheck\s*=\s*([A-Za-z]{2}(?:[_-][A-Za-z]{2})?)",
    re.M | re.I)
_RE_BABEL = re.compile(
    r"\\usepackage\s*\[([^\]]*)\]\s*\{(?:babel|polyglossia)\}")
_RE_ANA_DIL = re.compile(r"\\setmainlanguage\s*(?:\[[^\]]*\])?\s*\{(\w+)\}")

_DIL_ADI = {
    "turkish": "tr_TR", "turkce": "tr_TR", "tr": "tr_TR", "tr_tr": "tr_TR",
    "english": "en_US", "american": "en_US", "usenglish": "en_US",
    "en": "en_US", "en_us": "en_US", "en_gb": "en_GB", "british": "en_GB",
}


def belgeden_dil(metin: str) -> str | None:
    """Belgenin bildirdiği yazım dili ('tr_TR' / 'en_US'); yoksa None.

    Sıra önemli: `% !TEX spellcheck` kullanıcının AÇIK niyeti, babel ise
    dizgi dilidir (Türkçe tezde İngilizce özet için babel iki dil de
    listeler). Açık bildirim varsa o kazanır.
    """
    m = _RE_TEX_DIL.search(metin)
    if m:
        return _DIL_ADI.get(m.group(1).lower().replace("-", "_"),
                            m.group(1))
    m = _RE_ANA_DIL.search(metin)
    if m:
        return _DIL_ADI.get(m.group(1).lower())
    m = _RE_BABEL.search(metin)
    if m:
        # babel'de SON seçenek ana dildir: [english,turkish] -> turkish
        secenekler = [s.strip().lower() for s in m.group(1).split(",")
                      if s.strip()]
        for s in reversed(secenekler):
            if s in _DIL_ADI:
                return _DIL_ADI[s]
    return None


# --------------------------------------------------------------------------
# Metin çıkarımı
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Kelime:
    kelime: str      # aksan makroları çözülmüş hâli
    satir: int       # 1 tabanlı
    sutun: int       # 0 tabanlı, ÖZGÜN metindeki karakter konumu
    ofset: int       # metin başından karakter ofseti (özgün)


class _Tarayici:
    """LaTeX metnini tek geçişte tarar, yalnız DÜZ METİN kelimelerini verir."""

    def __init__(self, metin: str):
        self.s = metin
        self.n = len(metin)
        self.i = 0
        self.satir = 1
        self.satir_bas = 0

    # -- yardımcılar --
    def _ilerle(self, k: int = 1):
        for _ in range(k):
            if self.i < self.n:
                if self.s[self.i] == "\n":
                    self.satir += 1
                    self.satir_bas = self.i + 1
                self.i += 1

    def _bak(self, k: int = 0) -> str:
        j = self.i + k
        return self.s[j] if j < self.n else ""

    def _satir_sonuna(self):
        while self.i < self.n and self.s[self.i] != "\n":
            self._ilerle()

    def _grup_atla(self):
        """`{...}` dengeli atla; imleç `{` üzerindeyken çağrılır."""
        if self._bak() != "{":
            return
        derinlik = 0
        while self.i < self.n:
            c = self._bak()
            if c == "\\":
                self._ilerle(2)
                continue
            if c == "{":
                derinlik += 1
            elif c == "}":
                derinlik -= 1
                self._ilerle()
                if derinlik == 0:
                    return
                continue
            self._ilerle()

    def _grup_sonu(self, j: int) -> int:
        """`{` konumundan dengeli grubun BİTİŞ konumu; imleci oynatmaz."""
        if j >= self.n or self.s[j] != "{":
            return j
        derinlik = 0
        while j < self.n:
            c = self.s[j]
            if c == "\\":
                j += 2
                continue
            if c == "{":
                derinlik += 1
            elif c == "}":
                derinlik -= 1
                if derinlik == 0:
                    return j
            j += 1
        return self.n

    def _kose_atla(self):
        if self._bak() != "[":
            return
        while self.i < self.n and self._bak() != "]":
            self._ilerle()
        self._ilerle()

    def _bosluk_atla(self):
        while self.i < self.n and self.s[self.i] in " \t":
            self._ilerle()

    def _aksan_oku(self) -> tuple[str, int] | None:
        """İmleç `\\` üzerindeyken aksan makrosunu çöz.

        Döner: (harf, tüketilecek karakter sayısı) ya da None.
        """
        c1 = self._bak(1)
        if not c1:
            return None
        # noktalama adlı: \"o  ya da  \"{o}
        if (c1 in "\"'`^~.=") and c1 not in ("",):
            j = 2
            suslu = False
            if self._bak(j) == "{":
                suslu = True
                j += 1
            h = self._bak(j)
            if _harf_mi(h):
                sonuc = _AKSAN_NOKTALAMA.get((c1, h))
                if sonuc is None:
                    return None
                j += 1
                if suslu:
                    if self._bak(j) != "}":
                        return None
                    j += 1
                return sonuc, j
            return None
        # harf adlı: SÜSLÜ ŞART (\c{c}, \u{g}) — \usepackage karışmasın
        if _harf_mi(c1):
            j = 2
            ad = c1
            while _harf_mi(self._bak(j)):
                ad += self._bak(j)
                j += 1
            if self._bak(j) != "{":
                return None
            h = self._bak(j + 1)
            if not _harf_mi(h) or self._bak(j + 2) != "}":
                return None
            sonuc = _AKSAN_HARF.get((ad, h))
            if sonuc is None:
                return None
            return sonuc, j + 3
        return None

    def _tek_harf_komut(self) -> tuple[str, int] | None:
        """`\\i`, `\\ss` gibi argümansız harf komutları."""
        j = 1
        ad = ""
        while _harf_mi(self._bak(j)):
            ad += self._bak(j)
            j += 1
        if not ad or ad not in _TEK_HARF_KOMUT:
            return None
        # ardından `{}` gelebilir: \i{}
        if self._bak(j) == "{" and self._bak(j + 1) == "}":
            j += 2
        else:
            # TeX'te kontrol SÖZCÜĞÜNDEN sonraki boşluk sonlandırıcıdır ve
            # yutulur: `k\i sa` -> "kısa". Yutmazsak kelime ikiye bölünür.
            while self._bak(j) in (" ", "\t"):
                j += 1
        return _TEK_HARF_KOMUT[ad], j

    def _komut_oku(self) -> str:
        """İmleç `\\` üzerindeyken komut adını döndürür (imleç adın sonuna gider)."""
        self._ilerle()                       # \
        ad = ""
        while _harf_mi(self._bak()):
            ad += self._bak()
            self._ilerle()
        if not ad:                           # \{ \% \& gibi
            self._ilerle()
        return ad

    def _ortam_atla(self, ortam: str):
        """`\\end{ortam}`'a kadar atla."""
        hedef = "\\end{" + ortam + "}"
        j = self.s.find(hedef, self.i)
        if j < 0:
            self.i = self.n
            return
        while self.i < j + len(hedef):
            self._ilerle()

    # -- ana döngü --
    def kelimeler(self):
        kelime = []
        bas_ofset = bas_satir = bas_sutun = 0
        matematik = False
        # `\begin{document}` yoksa dosya bir bölüm parçasıdır; hepsi gövde.
        onsoz = self.s.find("\\begin{document}") >= 0
        # Önsözde YALNIZ beyaz listedeki komutun argümanı metin sayılır;
        # bu, o argümanın bittiği konum.
        onsoz_metin_sonu = -1

        def bosalt():
            nonlocal kelime
            if kelime:
                k = "".join(kelime)
                kelime = []
                # Türkçede kesme işareti özel ad + ek ayırır (Ankara'da).
                # Kökü denetle, eki bırak.
                kok = k.split("'")[0].split("\u2019")[0]
                if len(kok) >= 2 and any(_harf_mi(c) for c in kok):
                    return Kelime(kok, bas_satir, bas_sutun, bas_ofset)
            return None

        while self.i < self.n:
            c = self.s[self.i]

            if c == "%" and (self.i == 0 or self.s[self.i - 1] != "\\"):
                r = bosalt()
                if r:
                    yield r
                self._satir_sonuna()
                continue

            if c == "$":
                r = bosalt()
                if r:
                    yield r
                matematik = not matematik
                self._ilerle(2 if self._bak(1) == "$" else 1)
                continue

            if c == "\\":
                # \[ \] \( \) matematik sınırları
                if self._bak(1) in "[](" or (self._bak(1) == ")"):
                    r = bosalt()
                    if r:
                        yield r
                    matematik = self._bak(1) in "[("
                    self._ilerle(2)
                    continue

                aksan = self._aksan_oku()
                if aksan and not matematik:
                    harf, adim = aksan
                    if not kelime:
                        bas_ofset, bas_satir = self.i, self.satir
                        bas_sutun = self.i - self.satir_bas
                    kelime.append(harf)
                    self._ilerle(adim)
                    continue

                tek = self._tek_harf_komut()
                if tek and not matematik:
                    harf, adim = tek
                    if not kelime:
                        bas_ofset, bas_satir = self.i, self.satir
                        bas_sutun = self.i - self.satir_bas
                    kelime.append(harf)
                    self._ilerle(adim)
                    continue

                r = bosalt()
                if r:
                    yield r
                ad = self._komut_oku()

                if ad in ("begin", "end"):
                    self._bosluk_atla()
                    bas = self.i
                    self._grup_atla()
                    ortam = self.s[bas:self.i].strip("{} \t\n")
                    if ad == "begin" and ortam == "document":
                        onsoz = False
                    elif ad == "begin" and ortam in _ATLANACAK_ORTAM:
                        self._ortam_atla(ortam)
                    continue

                if onsoz:
                    # Önsöz yapılandırmadır. Beyaz listedeki komutun argümanı
                    # metin sayılır (başlık, yazar); gerisi tümüyle atlanır.
                    if ad in _ONSOZ_METIN:
                        self._bosluk_atla()
                        if self._bak() == "{":
                            onsoz_metin_sonu = self._grup_sonu(self.i)
                        continue
                    while True:
                        self._bosluk_atla()
                        if self._bak() == "[":
                            self._kose_atla()
                        elif self._bak() == "{":
                            self._grup_atla()
                        else:
                            break
                    continue

                if ad in _ARGUMANI_ATLA:
                    # köşeli ve süslü argümanların HEPSİNİ atla
                    while True:
                        self._bosluk_atla()
                        if self._bak() == "[":
                            self._kose_atla()
                        elif self._bak() == "{":
                            self._grup_atla()
                        else:
                            break
                    continue
                # tanınmayan komut: argümanı DÜZ METİN sayılır, taranmaya devam
                continue

            if matematik:
                self._ilerle()
                continue

            # \u00d6ns\u00f6zde d\u00fcz metin yok; yaln\u0131z beyaz liste arg\u00fcman\u0131n\u0131n i\u00e7i.
            if onsoz and self.i >= onsoz_metin_sonu:
                r = bosalt()
                if r:
                    yield r
                self._ilerle()
                continue

            # Rakam kelimenin \u0130\u00c7\u0130NDE olabilir ama ba\u015f\u0131nda olamaz: `sha256`,
            # `COVID19` tek token kalmal\u0131 ki rakam s\u00fczgeci onlar\u0131 eleyebilsin.
            # Aksi h\u00e2lde token "sha" diye kesiliyor ve s\u00fczge\u00e7 hi\u00e7 g\u00f6rm\u00fcyor.
            if _harf_mi(c) or (kelime and (c.isdigit() or c in "'\u2019")):
                if not kelime:
                    # Kelime BA\u015eINDA e-posta/URL mi: \u00f6yleyse tamam\u0131n\u0131 yut.
                    m = _RE_ADRES.match(self.s, self.i)
                    if m:
                        self._ilerle(m.end() - m.start())
                        continue
                    bas_ofset, bas_satir = self.i, self.satir
                    bas_sutun = self.i - self.satir_bas
                kelime.append(c)
                self._ilerle()
                continue

            r = bosalt()
            if r:
                yield r
            self._ilerle()

        r = bosalt()
        if r:
            yield r


def kelimeleri_cikar(metin: str) -> list[Kelime]:
    """Belgedeki DÜZ METİN kelimeleri, özgün konumlarıyla."""
    return list(_Tarayici(metin).kelimeler())


# --------------------------------------------------------------------------
# Denetleyici
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Bulgu:
    kelime: str
    satir: int
    sutun: int
    ofset: int


class Denetleyici:
    """Sözlük sarmalayıcı + kullanıcı sözlüğü. Qt yok.

    Sözlük yüklemesi YAVAŞ (ölçüldü: tr_TR 3.8 sn). Bu yüzden `yukle()` ayrı
    bir çağrı; arayüz katmanı onu arka planda çalıştırmalı.
    """

    def __init__(self, dil: str = "tr_TR", sozluk_dizini: str = "",
                 kullanici_sozlugu: str = ""):
        self.dil = dil
        self.sozluk_dizini = sozluk_dizini
        self.kullanici_sozlugu = kullanici_sozlugu
        self._sozluk = None
        self._kullanici: set[str] = set()
        self._kullanici_yuklendi = False
        # ÖRNEK BAŞINA önbellek. functools.lru_cache bir METODA konursa
        # önbellek sınıf düzeyinde olur: bütün örnekler paylaşır (dil
        # değişince eski sonuçlar kalır) ve `self` sonsuza dek canlı tutulur.
        self._onbellek: dict[str, bool] = {}

    # -- kullanıcı sözlüğü --
    def _kullanici_yukle(self):
        if self._kullanici_yuklendi:
            return
        self._kullanici_yuklendi = True
        yol = self.kullanici_sozlugu
        if not yol or not os.path.exists(yol):
            return
        try:
            with io.open(yol, encoding="utf-8") as f:
                self._kullanici = {s.strip() for s in f if s.strip()}
        except OSError:                          # pragma: no cover
            pass

    def kullaniciya_ekle(self, kelime: str) -> bool:
        """Kelimeyi kullanıcı sözlüğüne ekler ve diske yazar."""
        self._kullanici_yukle()
        if not kelime or kelime in self._kullanici:
            return False
        self._kullanici.add(kelime)
        self._onbellek.clear()
        if not self.kullanici_sozlugu:
            return True
        try:
            os.makedirs(os.path.dirname(self.kullanici_sozlugu), exist_ok=True)
            with io.open(self.kullanici_sozlugu, "w", encoding="utf-8",
                         newline="\n") as f:
                f.write("\n".join(sorted(self._kullanici)) + "\n")
        except OSError:                          # pragma: no cover
            return False
        return True

    # -- sözlük --
    def yukle(self):
        """Sözlüğü belleğe al. YAVAŞ; arka planda çağrılmalı."""
        _require()
        if self._sozluk is not None:
            return
        self._kullanici_yukle()
        yol = os.path.join(self.sozluk_dizini, self.dil) \
            if self.sozluk_dizini else self.dil
        self._sozluk = Dictionary.from_files(yol)

    @property
    def hazir(self) -> bool:
        return self._sozluk is not None

    def dogru_mu(self, kelime: str) -> bool:
        # Kullanıcı sözlüğü BURADA yükleniyor, yukle() içinde değil: denetle()
        # sözlük yüklenmeden de çağrılabiliyor ve o hâlde kullanıcının
        # eklediği kelimeler görülmüyordu.
        self._kullanici_yukle()
        sonuc = self._onbellek.get(kelime)
        if sonuc is not None:
            return sonuc
        if kelime in self._kullanici:
            sonuc = True
        elif self._sozluk is None:
            sonuc = True                         # sözlük yokken kimseyi suçlama
        else:
            sonuc = bool(self._sozluk.lookup(kelime))
        self._onbellek[kelime] = sonuc
        return sonuc

    def oneriler(self, kelime: str, tavan: int = 7) -> list[str]:
        if self._sozluk is None:
            return []
        try:
            return list(self._sozluk.suggest(kelime))[:tavan]
        except Exception:                        # pragma: no cover — spylls
            return []

    # -- ana giriş --
    def denetle(self, metin: str, *, buyuk_atla: bool = False,
                en_az: int = 3) -> list[Bulgu]:
        """Metindeki yanlış yazılmış kelimeler, konumlarıyla.

        ``buyuk_atla``: büyük harfle başlayanları geç. Ölçüldü, gürültünün
        yarısı özel ad: İngilizce şablonlarda %10.0'ın 4.5 puanı, Türkçe
        template36'da 125 işaretin 34'ü.
        """
        bulgular = []
        for k in kelimeleri_cikar(metin):
            if len(k.kelime) < en_az:
                continue
            if buyuk_atla and k.kelime[:1].isupper():
                continue
            if any(ch.isdigit() for ch in k.kelime):
                continue
            if not self.dogru_mu(k.kelime):
                bulgular.append(Bulgu(k.kelime, k.satir, k.sutun, k.ofset))
        return bulgular
