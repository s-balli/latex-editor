"""BibTeX girdi ayrıştırma ve denetim: Qt'süz saf katman.

`core/latex_refs.py` .bib dosyasından yalnız ANAHTARLARI çıkarıyor
(`collect_cite_keys`) ve bunu tek satırlık bir regex ile yapıyor. Bu, tanıma
git ve otomatik tamamlama için yeterli ama denetim için değil: girdinin türünü
ve alanlarını bilmek gerekiyor.

NEDEN REGEX DEĞİL DE AYRAÇ SAYIMI: alan değerleri iç içe süslü parantez
taşıyor ve bu istisna değil kural. `title={The {BERT} Model}` gibi bir değerde
regex ilk `}` ile durur, başlık yarım kalır. Ayrıca `@string`, `@comment`,
`@preamble` girdi DEĞİL ve atlanmalı; `%` BibTeX'te yorum değil (girdi dışında
kalan metin zaten yok sayılıyor).

`collect_cite_keys` anahtarları KÜME olarak topluyor, yani mükerrer anahtarlar
orada sessizce tekilleşiyor. Mükerrer anahtar sinsi bir hata: BibTeX uyarmıyor,
ilk tanımı alıyor ve belgede YANLIŞ kaynak basılıyor. Bu modül girdileri sırayla
ve satır numarasıyla döndürdüğü için ikisi de görülebiliyor.
"""

import os
from dataclasses import dataclass, field

# Girdi olmayan @ blokları: makro tanımı, yorum, önsöz.
_GIRDI_DISI = frozenset(["string", "comment", "preamble"])

# Klasik BibTeX'in (plain.bst) zorunlu alanları. Her öğe bir SEÇENEK demeti:
# ("author", "editor") "author ya da editor" demek.
#
# biblatex/biber bunlardan daha hoşgörülü, o yüzden liste bilinçli olarak DAR
# tutuldu: yalnız klasik BibTeX'in gerçekten şikâyet ettiği alanlar var.
# Fazla katı bir liste her denetimi gürültüye boğar ve kullanıcı hepsini
# görmezden gelmeye başlar. `misc` ve tanımadığımız türler hiç denetlenmiyor.
_ZORUNLU: dict[str, tuple[tuple[str, ...], ...]] = {
    "article": (("author",), ("title",), ("journal",), ("year",)),
    "book": (("author", "editor"), ("title",), ("publisher",), ("year",)),
    "inproceedings": (("author",), ("title",), ("booktitle",), ("year",)),
    "conference": (("author",), ("title",), ("booktitle",), ("year",)),
    "incollection": (("author",), ("title",), ("booktitle",), ("publisher",), ("year",)),
    "inbook": (("author", "editor"), ("title",), ("chapter", "pages"),
               ("publisher",), ("year",)),
    "phdthesis": (("author",), ("title",), ("school",), ("year",)),
    "mastersthesis": (("author",), ("title",), ("school",), ("year",)),
    "techreport": (("author",), ("title",), ("institution",), ("year",)),
    "unpublished": (("author",), ("title",), ("note",)),
    "proceedings": (("title",), ("year",)),
    "manual": (("title",),),
    "booklet": (("title",),),
}


@dataclass(frozen=True)
class BibGirdi:
    """Tek bir .bib girdisi.

    tur/anahtar/alan adları küçük harfe indirgenmiş (BibTeX bunlarda harf
    duyarsız); alan DEĞERLERİ ham bırakılıyor.
    satir: `@tur{` satırının 1 tabanlı numarası.
    """
    tur: str
    anahtar: str
    satir: int
    alanlar: dict = field(default_factory=dict)


def _kapanis(text: str, bas: int, kapali: str) -> int:
    """`text[bas]` açık ayraç; eşleşen kapanışın indisi. Dengelenmemişse -1."""
    derinlik = 0
    i, n = bas, len(text)
    while i < n:
        c = text[i]
        if c == "\\":          # \{ ve \} kaçışları ayraç sayılmaz
            i += 2
            continue
        if c == "{":
            derinlik += 1
        elif c == "}":
            derinlik -= 1
            if kapali == "}" and derinlik == 0:
                return i
        elif c == kapali and kapali == ")" and derinlik == 0 and i > bas:
            return i
        i += 1
    return -1


def _ust_duzey_bol(s: str) -> list[str]:
    """Ayraç derinliği 0 olan virgüllerden böl (alan değerlerindekiler hariç)."""
    parcalar: list[str] = []
    derinlik, tirnakta, bas, i = 0, False, 0, 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == '"' and derinlik == 0:
            tirnakta = not tirnakta
        elif not tirnakta:
            if c == "{":
                derinlik += 1
            elif c == "}":
                derinlik -= 1
            elif c == "," and derinlik == 0:
                parcalar.append(s[bas:i])
                bas = i + 1
        i += 1
    parcalar.append(s[bas:])
    return parcalar


def _deger_soy(v: str) -> str:
    """Değerin dış sarmalını at. Sarmalsız değer makro/sayıdır, aynen kalır."""
    v = v.strip()
    if len(v) >= 2 and v[0] == "{" and v[-1] == "}":
        return v[1:-1].strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1].strip()
    return v


def parse_entries(text: str) -> list[BibGirdi]:
    """.bib içeriğindeki girdileri DOSYA SIRASIYLA döndür (mükerrerler dahil)."""
    girdiler: list[BibGirdi] = []
    i, n = 0, len(text)
    while True:
        i = text.find("@", i)
        if i < 0:
            return girdiler
        j = i + 1
        while j < n and text[j].isalpha():
            j += 1
        tur = text[i + 1:j].lower()
        k = j
        while k < n and text[k] in " \t\r\n":
            k += 1
        if not tur or k >= n or text[k] not in "{(":
            # Alan değerinin içindeki bir '@' (e-posta, DOI) — girdi değil.
            i = max(j, i + 1)
            continue
        kapali = "}" if text[k] == "{" else ")"
        son = _kapanis(text, k, kapali)
        if son < 0:
            # Dengelenmemiş ayraç: dosyanın kalanı güvenle ayrıştırılamaz.
            # Bulunanları döndürüyoruz; kısmi sonuç, sessiz yanlıştan iyidir.
            return girdiler
        if tur not in _GIRDI_DISI:
            parcalar = _ust_duzey_bol(text[k + 1:son])
            anahtar = parcalar[0].strip()
            if anahtar:
                alanlar = {}
                for p in parcalar[1:]:
                    ad, ayrac, deger = p.partition("=")
                    if not ayrac:
                        continue
                    ad = ad.strip().lower()
                    if ad:
                        alanlar[ad] = _deger_soy(deger)
                girdiler.append(BibGirdi(tur, anahtar,
                                         text.count("\n", 0, i) + 1, alanlar))
        i = son + 1


def mukerrer_anahtarlar(girdiler) -> list[tuple[str, list[int]]]:
    """Birden çok kez tanımlanmış anahtarlar: (anahtar, satırlar), sıralı.

    BibTeX mükerrerde UYARMIYOR, ilk tanımı alıyor. Kullanıcı ikinci girdiyi
    düzeltip belgenin değişmemesine anlam veremiyor.
    """
    yerler: dict[str, list[int]] = {}
    for g in girdiler:
        yerler.setdefault(g.anahtar, []).append(g.satir)
    return sorted((a, s) for a, s in yerler.items() if len(s) > 1)


def eksik_alanlar(girdi: BibGirdi) -> list[str]:
    """Girdinin türü için eksik zorunlu alanlar.

    Seçenekli alanlar "author/editor" biçiminde tek öğe olarak döner.
    Tanınmayan tür (ör. `misc`, biblatex'e özgü türler) hiç denetlenmez:
    kural listesi klasik BibTeX'e ait, uydurma zorunluluk üretilmemeli.
    """
    kurallar = _ZORUNLU.get(girdi.tur)
    if not kurallar:
        return []
    eksik = []
    for secenekler in kurallar:
        if not any(girdi.alanlar.get(a, "").strip() for a in secenekler):
            eksik.append("/".join(secenekler))
    return eksik


def yazar_kisalt(deger: str) -> str:
    """`author` alanını listede gösterilecek kısa biçime indir.

    Ham alan tabloya sığmıyor: ölçülen bir örnek
    `{Kaya, Aydın and Keçeli, Ali Seydi and Can, Ahmet Burak}`.

    BibTeX iki yazar biçimini de kabul ediyor ve ikisi de sahada var:
        "Kaya, Aydın"   -> soyadı virgülden ÖNCE
        "Aydın Kaya"    -> soyadı SON kelime
    Süslü parantezle sarılı ad kurum demektir (`{Dünya Sağlık Örgütü}`) ve
    bölünmemeli; oradaki virgül yazar ayracı değil.
    """
    deger = deger.strip()
    if not deger:
        return ""
    if deger.startswith("{") and deger.endswith("}"):
        return deger[1:-1].strip()
    yazarlar = [y.strip() for y in deger.split(" and ") if y.strip()]
    if not yazarlar:
        return ""
    ilk = yazarlar[0]
    soyad = ilk.split(",")[0].strip() if "," in ilk else ilk.split()[-1]
    return soyad + (" vd." if len(yazarlar) > 1 else "")


def ozet(girdi: BibGirdi) -> tuple[str, str, str, str, str]:
    """Listeleme için (anahtar, tür, yazar, yıl, başlık).

    Değerler ham; yalnız gösterim için kısaltılıyor. Başlıktaki koruma
    parantezleri (`{BERT}`) atılıyor: kullanıcı okuyacak, dizgi motoru değil.
    """
    baslik = girdi.alanlar.get("title", "").replace("{", "").replace("}", "")
    return (girdi.anahtar, girdi.tur,
            yazar_kisalt(girdi.alanlar.get("author")
                         or girdi.alanlar.get("editor", "")),
            girdi.alanlar.get("year", ""), " ".join(baslik.split()))


@dataclass
class BibDenetim:
    """.bib dosyasının KENDİ tutarlılığı (referans denetiminden ayrı).

    mukerrer: (anahtar, tanımlandığı satırlar) — birden çok tanım
    eksik:    (anahtar, satır, eksik alan adları)
    """
    mukerrer: list = field(default_factory=list)
    eksik: list = field(default_factory=list)


def denetle(text: str) -> BibDenetim:
    """.bib içeriğini denetle. Dosya okuma yok; çağıran metni verir."""
    girdiler = parse_entries(text)
    eksik = []
    for g in girdiler:
        e = eksik_alanlar(g)
        if e:
            eksik.append((g.anahtar, g.satir, e))
    return BibDenetim(mukerrer_anahtarlar(girdiler), eksik)


# Ayrıştırma sonucu (mtime, denetim) olarak önbellekleniyor. Denetim derleme
# sonrası da koşuyor; .bib değişmediyse aynı dosyayı her derlemede yeniden
# ayrıştırmanın anlamı yok. Aynı desen latex_refs._bib_cache'te de var.
_cache: dict = {}
_CACHE_SINIR = 8


def dosyayi_denetle(yol: str) -> BibDenetim:
    """Yoldaki .bib'i oku ve denetle. Okunamıyorsa boş denetim.

    Kodlama: utf-8 dışındaki .bib'ler de var (cp1254 ile kaydedilmiş Türkçe
    dosyalar). `project_search.coz` bu depodaki tek çözücü, aynısı kullanılıyor.
    """
    if not yol:
        return BibDenetim()
    try:
        mtime = os.path.getmtime(yol)
    except OSError:
        return BibDenetim()
    onbellek = _cache.get(yol)
    if onbellek and onbellek[0] == mtime:
        return onbellek[1]
    try:
        with open(yol, "rb") as f:
            ham = f.read()
    except OSError:
        return BibDenetim()
    from core.project_search import coz
    sonuc = denetle(coz(ham))
    if len(_cache) >= _CACHE_SINIR:
        _cache.clear()
    _cache[yol] = (mtime, sonuc)
    return sonuc
