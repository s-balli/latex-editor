"""LaTeX yardımcı fonksiyonları: yorum temizleme, etiket anahtarı."""

import re

# Etiket anahtarında GÜVENLİ sayılan karakterler. Harf/rakamın yanında
# `_ - . :` duruyor; `fig:sonuc_grafik` LaTeX'te yaygın ve doğru bir anahtar.
_ETIKET_GUVENSIZ = re.compile(r"[^A-Za-z0-9_\-.:]+")


# Sözel ortamlar: içerikleri LaTeX kodu DEĞİL, gösterilen düz metin. TEK
# KAYNAK; lexer (desktop/syntax), anahat ve referans denetimi buradan alıyor.
# Liste bir kez kopyalanıp ayrışmıştı: `comment`, `BVerbatim`, `LVerbatim` ve
# `listing` anahatta eksikti (ölçüldü 2026-09-06, dördü de sızıyordu).
VERB_ENVS = ("verbatim", "verbatim*", "lstlisting", "minted", "alltt",
             "comment", "Verbatim", "BVerbatim", "LVerbatim", "listing")

_SOZEL_TABAN = tuple(sorted({e.rstrip("*") for e in VERB_ENVS}))
_RE_SOZEL_BLOK = re.compile(
    r"\\begin\{(" + "|".join(re.escape(e) for e in _SOZEL_TABAN) + r")\*?\}"
    r"(.*?)(?:\\end\{\1\*?\}|\Z)", re.S)
# Satır içi `\verb`: ayraç, harf olmayan herhangi bir karakter olabiliyor
# (`\verb|x|`, `\verb+x+`, `\verb'x'`). Satır sonunu GEÇMİYOR; LaTeX'te de
# geçmiyor, kapanmamış `\verb` satır sonunda biter.
_RE_VERB = re.compile(
    r"\\verb\*?(?P<d>[^A-Za-z0-9\s])(?:(?!(?P=d))[^\n])*(?P=d)?")


# ÇİZİM ortamları: içerik düz yazı değil, koordinat ve çizim komutu. Sözel
# ortamlardan AYRI durmaları gerekiyor, çünkü sözel olanların içeriği ekranda
# olduğu gibi BASILIYOR, bunlarınki basılmıyor.
#
# TEK KAYNAK. Yazım denetimi bu ortamları 2026-09-11'den beri atlıyordu ama
# adı kendi içinde yazılıydı; kelime sayımı o dersi hiç almamıştı. ÖLÇÜLDÜ
# (2026-09-12, 132 gerçek şablon): tikz içeriği 4 dosyada 717 sahte kelime
# sayılıyordu, bir soru kâğıdında tek başına 635 (gerçek sayının iki katı).
CIZIM_ENVS = ("tikzpicture", "pgfpicture")

_RE_CIZIM_BLOK = re.compile(
    r"\\begin\{(" + "|".join(re.escape(e) for e in CIZIM_ENVS) + r")\*?\}"
    r"(.*?)(?:\\end\{\1\*?\}|\Z)", re.S)


def cizim_soy(metin: str) -> str:
    r"""Çizim ortamlarını İÇERİĞİYLE BİRLİKTE sil."""
    return _RE_CIZIM_BLOK.sub(" ", metin)


def verb_sil(metin: str) -> str:
    r"""Satır içi ``\verb`` yapılarını KOMUTUYLA BİRLİKTE sil.

    ``sozel_soy`` gövdeyi boşaltıp komutu ve ayraçları BIRAKIYOR, çünkü
    çağıranlarının bir kısmı satır ve sütun hesaplıyor. Kelime sayımının
    ihtiyacı tersi: ayraçlar kalırsa ``\verb|x|`` gövdedeki kelimeler yerine
    iki ayrı ``|`` parçası sayılıyor, yani sayı düzelmiyor, bozuluyor.
    """
    return _RE_VERB.sub(" ", metin)


def _bosluga_cevir(metin: str) -> str:
    """Satır sonları DIŞINDA her karakteri boşluğa çevir."""
    return "".join("\n" if c == "\n" else " " for c in metin)


def sozel_soy(text: str) -> str:
    r"""Sözel ortamların ve satır içi ``\verb``in İÇERİĞİNİ boşluğa çevir.

    Neden: o içerik kod ÖRNEĞİ, çalışan LaTeX değil. Referans denetimi
    örnekteki ``\cite{key}``i gerçek atıf sanıp kullanıcının
    düzeltemeyeceği bulgu üretiyordu. ÖLÇÜLDÜ (2026-09-09, 39 gerçek
    şablonda): "Tanımsız \cite/\ref" bulgularının çoğu ``\verb`` içindeki
    örneklerden geliyordu (``\verb'\citet{key}'``, ``\verb+\ref{tiger}+``,
    ``\verb|\eqref{Eq}|``).

    Uzunluk ve satır yapısı KORUNUYOR (``strip_comments`` ile aynı
    sözleşme): çağıranların bir kısmı satır numarası hesaplıyor.
    """
    # Hız yolu ölçütü ters bölü: soyduğumuz her şey bir komutla başlıyor.
    # Burada bir kez `"verb" not in text` yazılmıştı ve YANLIŞTI: `comment`,
    # `minted`, `alltt`, `listing` adlarında "verb" geçmiyor, yani o
    # ortamların içi hiç soyulmuyordu. Deponun mevcut anahat kapıları bunu
    # yakaladı (test_file_watch_outline, sekiz ortamın sekizi).
    if "\\" not in text:
        return text
    text = _RE_SOZEL_BLOK.sub(
        lambda m: (m.group(0)[:m.start(2) - m.start(0)]
                   + _bosluga_cevir(m.group(2))
                   + m.group(0)[m.end(2) - m.start(0):]), text)
    return _RE_VERB.sub(_verb_bosalt, text)


def _verb_bosalt(m) -> str:
    r"""``\verb|...|`` içeriğini boşalt; komutu ve ayraçları BIRAK.

    Ayraçlar bırakılıyor ki uzunluk aynı kalsın ve komut hâlâ bir komut
    gibi görünsün (bir başkası onu ayrıştırıyorsa bozulmasın).
    """
    ham = m.group(0)
    bas = ham.index(m.group("d")) + 1
    son = len(ham) - 1 if (len(ham) > bas and ham[-1] == m.group("d")) \
        else len(ham)
    return ham[:bas] + " " * (son - bas) + ham[son:]


def strip_comments(text: str) -> str:
    """Yorum satırlarını ve satır içi yorumları kaldır.

    \\% kaçırılmış yüzde işaretlerini korur.
    Satır yapısını (girintiler dahil) korur, sadece yorum kısmını kaldırır.
    """
    result = []
    for line in text.split('\n'):
        # Hız yolu: '%' içermeyen satır değişmez (aşağıdaki döngü bu satırı
        # birebir kopyalayarak aynı sonucu verir). C-hızlı 'in' denetimi,
        # karakter-karakter Python döngüsünü yorumlu azınlık satırlara indirger.
        if '%' not in line:
            result.append(line)
            continue
        clean = []
        i = 0
        while i < len(line):
            if line[i] == '\\' and i + 1 < len(line):
                clean.append(line[i:i + 2])
                i += 2
            elif line[i] == '%':
                break
            else:
                clean.append(line[i])
                i += 1
        result.append(''.join(clean))
    return '\n'.join(result)


def label_key(text: str) -> str:
    r"""Serbest metinden kullanılabilir bir `\label` anahtarı üret.

    Dosya adından etiket türetilirken gerekiyor. İki ayrı sorun var ve
    ikisi de ÖLÇÜLDÜ (2026-09-06, pdflatex, `\label{...}` tek başına):

      %   -> "! File ended while scanning use of \label."  DERLEME KIRILIR
      #   -> "! Illegal parameter number in definition of \reserved@a."

    `_ & $ ^` ise etiket içinde sorunsuz derleniyor; anahtar TİPOGRAFİK
    metin değil, `\label` argümanını dizmiyor. O yüzden burada kaçış
    (`\_`) YANLIŞ olurdu: anahtarı değiştirir, kullanıcının `\ref` ile
    yazacağı ad tutmaz ve deponun `\label{...}` tarayıcıları (anahat,
    F2 yeniden adlandırma, referans denetimi) başka bir dize görür.

    Bu yüzden kaçırmak yerine SADELEŞTİRİLİYOR: güvenli olmayan her öbek
    tek bir `-` oluyor. `&` ve `$` derlense de elle yazılması zor bir
    anahtar üretiyorlar, onlar da sadeleşiyor.
    """
    return _ETIKET_GUVENSIZ.sub("-", text).strip("-") or "etiket"
