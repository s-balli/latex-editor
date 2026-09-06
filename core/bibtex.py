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
import re
import urllib.error
import urllib.parse
import urllib.request
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
    # Satır numarası ARTIMLI sayılıyor. Her girdi için `text.count("\n", 0, i)`
    # demek dosyanın başından yeniden saymaktı ve ayrıştırmayı KARESEL yapıyordu
    # (ölçüldü 2026-09-02: 5000 kayıt 0.5 sn, 20000 kayıt 5.5 sn, 40000 kayıt
    # 21 sn; kayıt başına maliyet 0.027 ms'den 0.523 ms'ye tırmanıyordu).
    # `i` her turda yalnızca ileri gittiği için son sayılan yerden devam etmek
    # aynı sonucu veriyor.
    sayilan_yer, satir_no = 0, 1
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
            # Alan değerinin içindeki bir '@' (e-posta, DOI) girdi DEĞİLDİR.
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
                satir_no += text.count("\n", sayilan_yer, i)
                sayilan_yer = i
                girdiler.append(BibGirdi(tur, anahtar, satir_no, alanlar))
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


# --- DOI ile girdi getirme ---------------------------------------------
#
# İki uç, sırayla denenir:
#   1. api.crossref.org/works/{doi}/transform/application/x-bibtex
#      Ölçüldü: ~0.5 sn, geçersiz DOI'de temiz 404. Yalnız Crossref kayıtları.
#   2. doi.org/{doi} + Accept: application/x-bibtex
#      DataCite kayıtlarını da veriyor (arXiv gibi), biraz daha yavaş.
#
# Gelen BibTeX HAM HÂLİYLE kullanılamıyor; gerçek derlemeyle ölçülen üç kusur
# `normallestir` içinde düzeltiliyor (gerekçeler orada).

_UA = "latex-editor (https://github.com/s-balli/latex-editor)"
_CROSSREF = "https://api.crossref.org/works/%s/transform/application/x-bibtex"
_DOI_ORG = "https://doi.org/%s"
GETIRME_ZAMAN_ASIMI = 8
# Yanıt üst sınırı. Gerçek BibTeX kayıtları 341-504 bayt ölçüldü.
_MAX_YANIT = 256 * 1024

# Ayın üç harfli BibTeX makroları. Crossref bazen "June", bazen "Apr"
# döndürüyor; "June" STANDART DEĞİL ve bibtex "Warning--string name 'june' is
# undefined" deyip ayı SESSİZCE düşürüyor (gerçek derlemeyle ölçüldü).
_AYLAR = {}
for _i, _uzun in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"]):
    _kisa = _uzun[:3]
    _AYLAR[_uzun] = _kisa
    _AYLAR[_kisa] = _kisa

# BibTeX anahtarında güvenle kullanılabilecek karakterler. Crossref doi.org
# yolunda anahtar olarak URL döndürebiliyor
# (`@misc{https://doi.org/10.48550/arxiv...`), o geçerli bir anahtar değil.
_ANAHTAR_GECERLI = re.compile(r"^[A-Za-z0-9_.+:-]+$")
_RE_ALAN = re.compile(r"(\w+)\s*=\s*", re.I)


class DoiHatasi(Exception):
    """Getirme başarısız: ağ hatası ya da DOI bulunamadı."""


def doi_temizle(girdi: str) -> str:
    """Kullanıcının yapıştırdığından çıplak DOI'yi çıkar.

    Yapıştırılan şey çoğu zaman tam URL oluyor; `10.` ile başlamasını
    beklemek kullanıcıyı elle kırpmaya zorlardı.
    """
    s = (girdi or "").strip()
    for onek in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                 "http://dx.doi.org/", "doi:", "DOI:"):
        if s.lower().startswith(onek.lower()):
            s = s[len(onek):]
            break
    return s.strip().strip("/")


def _iste(url: str, kabul: str = "") -> str:
    basliklar = {"User-Agent": _UA}
    if kabul:
        basliklar["Accept"] = kabul
    istek = urllib.request.Request(url, headers=basliklar)
    with urllib.request.urlopen(istek, timeout=GETIRME_ZAMAN_ASIMI) as r:
        # SINIRLI okuma: `read()` sınırsızdır ve karşı taraf (ele geçirilmiş
        # ya da yalnızca bozuk bir uç, araya giren bir vekil) gigabaytlarca
        # veri gönderip belleği tüketebilir. Ölçülen gerçek yanıtlar 341-504
        # bayt; 256 KB fazlasıyla geniş bir tavan.
        return r.read(_MAX_YANIT + 1)[:_MAX_YANIT].decode("utf-8", "replace")


def doi_getir(doi: str, *, ac=None) -> str:
    """DOI'nin ham BibTeX'ini getir. Bulunamazsa/erişilemezse DoiHatasi.

    `ac`: test için URL açıcı (url, kabul) -> metin.
    """
    temiz = doi_temizle(doi)
    if not temiz or not temiz.startswith("10."):
        raise DoiHatasi("gecersiz")
    # DOI kullanıcıdan geliyor ve URL'in YOL bileşenine giriyor. Denetimsiz
    # bırakılınca istek istenen uca gitmiyor (ölçüldü):
    #   "10.1/x?callback=evil" -> .../works/10.1/x?callback=evil/transform/...
    #   "10.1/x#frag"          -> parçadan sonrası hiç gönderilmiyor
    #   "10.1/../../../admin"  -> yol geziniyor
    #   "10.1/x y"             -> boşluk geçersiz URL
    # Uzunluk sınırı: gerçek DOI'ler 255 karakterin çok altında.
    if len(temiz) > 255 or any(c.isspace() or ord(c) < 0x20 for c in temiz):
        raise DoiHatasi("gecersiz")
    if ".." in temiz.split("/"):
        raise DoiHatasi("gecersiz")
    # `/` DOI'nin parçası, korunuyor; `?`, `#`, `%` ve gerisi kaçırılıyor.
    kodlu = urllib.parse.quote(temiz, safe="/")
    ac = ac or _iste
    son_hata = None
    for url, kabul in ((_CROSSREF % kodlu, ""),
                       (_DOI_ORG % kodlu, "application/x-bibtex")):
        try:
            govde = ac(url, kabul)
        except urllib.error.HTTPError as e:
            son_hata = "bulunamadi" if e.code == 404 else "ag"
            continue
        except Exception:
            son_hata = "ag"
            continue
        if govde and govde.lstrip().startswith("@"):
            return govde
        son_hata = "bulunamadi"
    raise DoiHatasi(son_hata or "ag")


def _anahtar_uret(alanlar: dict, eski: str) -> str:
    """Geçersiz anahtar yerine `Soyad2020` biçiminde bir tane üret."""
    soyad = yazar_kisalt(alanlar.get("author") or alanlar.get("editor", ""))
    soyad = soyad.replace(" vd.", "")
    soyad = re.sub(r"[^A-Za-zÀ-ÿ0-9]", "", soyad) or "kaynak"
    yil = re.sub(r"[^0-9]", "", alanlar.get("year", ""))[:4]
    uretilen = soyad + yil
    return uretilen if uretilen.strip("0123456789") else (eski or uretilen)


def benzersiz_anahtar(istenen: str, mevcut) -> str:
    """Çakışıyorsa sonuna a, b, c ekle.

    Mükerrer anahtar BibTeX'te sessiz bir hata: uyarı çıkmadan ilk tanım
    alınıyor ve belgede yanlış kaynak basılıyor (bkz. mukerrer_anahtarlar).
    """
    mevcut = set(mevcut or ())
    if istenen not in mevcut:
        return istenen
    for kod in range(ord("a"), ord("z") + 1):
        aday = istenen + chr(kod)
        if aday not in mevcut:
            return aday
    ek = 2
    while (istenen + str(ek)) in mevcut:
        ek += 1
    return istenen + str(ek)


def _deger_duzelt(ad: str, deger: str) -> str:
    """Alan değerinin ölçülen kusurlarını gider."""
    if ad == "pages":
        # Crossref sayfa aralığını ORTA TİRE (U+2013) ile veriyor.
        # plain.bst aralığı `--` ile tanıyor; tire kalınca çıktıya
        # "page 770<U+2013>778" yazıyor (tekil!), "pages 770--778" değil.
        # Gerçek derlemeyle ölçüldü.
        deger = deger.replace("–", "--").replace("—", "--")
    # LaTeX'te `&` kaçışsız kullanılamaz; kaçışlı olanlara dokunma.
    deger = re.sub(r"(?<!\\)&", r"\\&", deger)
    return deger


def normallestir(ham: str, *, mevcut_anahtarlar=()) -> tuple[str, str]:
    """Getirilen BibTeX'i .bib'e eklenebilir hâle getir: (metin, anahtar).

    Üç düzeltme de GERÇEK DERLEMEYLE ölçülmüş kusurlara karşılık geliyor:
    ay makrosu, orta tireli sayfa aralığı, geçersiz anahtar. Ayrıca gelen
    girdi TEK SATIR oluyor; .bib'e öyle eklemek dosyayı okunmaz yapardı.
    """
    girdiler = parse_entries(ham)
    if not girdiler:
        raise DoiHatasi("ayristirilamadi")
    g = girdiler[0]

    alanlar = {}
    for ad, deger in g.alanlar.items():
        if ad == "month":
            kisa = _AYLAR.get(deger.strip().strip("{}").lower())
            # Tanınmayan ay değerini AYNEN bırakmak yerine atıyoruz: makro
            # olarak çözülmezse bibtex zaten uyarıp düşürüyor.
            if kisa:
                alanlar[ad] = kisa
            continue
        alanlar[ad] = _deger_duzelt(ad, deger)

    anahtar = g.anahtar
    if not _ANAHTAR_GECERLI.match(anahtar):
        anahtar = _anahtar_uret(alanlar, "")
    anahtar = benzersiz_anahtar(anahtar, mevcut_anahtarlar)

    satirlar = ["@%s{%s," % (g.tur, anahtar)]
    for ad, deger in alanlar.items():
        # `month` makro; süslü parantez içine alınırsa metin olur ve
        # bibtex ayı "jun" diye basar, "June" diye değil.
        if ad == "month":
            satirlar.append("  month = %s," % deger)
        else:
            satirlar.append("  %s = {%s}," % (ad, deger))
    satirlar.append("}")
    return "\n".join(satirlar), anahtar


# Dosyanın kendi kodlaması. `core.project_search.coz` ve
# `gui.editor._decode_bytes` ile AYNI sıra; buradaki fark, yazabilmek için
# kodlamanın ADININ da gerekmesi.
_KODLAMALAR = ("utf-8", "cp1254", "iso-8859-9")


def _coz_adiyla(ham: bytes) -> tuple[str, str]:
    """(metin, kodlama adı). Hiçbiri tutmazsa utf-8 + replace."""
    for enc in _KODLAMALAR:
        try:
            return ham.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return ham.decode("utf-8", errors="replace"), "utf-8"


def ekleme_metni(var_olan: str, girdi_metni: str) -> str:
    """`bibe_ekle`nin sona ekleyeceği metin (ayraç dahil).

    AYRI FONKSİYON, çünkü .bib DOSYAYA yazılan tek yol değil: hedef .bib bir
    sekmede AÇIKSA girdi diske değil o sekmenin arabelleğine ekleniyor
    (bkz. `edit_ops._on_doi_fetched`). İki yol aynı ayracı kullanmak
    zorunda; kural burada tek yerde duruyor.
    """
    ayrac = "" if (not var_olan or var_olan.endswith("\n\n")) else (
        "\n" if var_olan.endswith("\n") else "\n\n")
    return ayrac + girdi_metni + "\n"


def bibe_ekle(yol: str, girdi_metni: str) -> None:
    """Girdiyi .bib dosyasının SONUNA ekle.

    Dosya yeniden yazılmıyor, yalnız ekleniyor: mevcut yorumlar, `@string`
    makroları ve girdi sırası olduğu gibi kalıyor.

    EKLEME DOSYANIN KENDİ KODLAMASIYLA yapılıyor. Eskiden okuma `coz()` ile
    kodlamayı ALGILIYOR ama yazma koşulsuz utf-8'di; cp1254 ile yazılmış bir
    .bib'e utf-8 baytlar eklenince dosya KARMA KODLAMALI oluyordu. Ölçüldü:
    dosya sonrasında ne utf-8 ne cp1254 olarak çözülüyor, `coz()`
    iso-8859-9'a düşüyor ve YENİ eklenen girdi mojibake okunuyor
    (`Yılmaz, Şule` -> `YÄ±lmaz, Å\x9eule`) — hem Kaynakça sekmesinde hem
    derlenen kaynakçada.

    Bu depo eski Türkçe kodlamaları üç ayrı yerde ciddiye alıyor
    (`project_search.coz`, `editor._decode_bytes`, `editor.save_file_as`);
    `bibe_ekle` o zincirin dışında kalmıştı.
    """
    var_olan, kodlama = "", "utf-8"
    if os.path.isfile(yol):
        with open(yol, "rb") as f:
            var_olan, kodlama = _coz_adiyla(f.read())
    eklenecek = ekleme_metni(var_olan, girdi_metni)

    try:
        veri = eklenecek.encode(kodlama)
    except UnicodeEncodeError:
        # Yeni girdi eski kodlamaya SIĞMIYOR (ör. cp1254'te karşılığı olmayan
        # bir harf; DOI ile gelen kayıtlarda olağan). Karma kodlamalı dosya
        # üretmektense dosyanın TAMAMI utf-8'e çevriliyor: metin birebir
        # korunuyor, yalnız baytlar değişiyor ve dosya tek kodlamada kalıyor.
        with open(yol, "wb") as f:
            f.write((var_olan + eklenecek).encode("utf-8"))
        return

    # İkili ekleme: satır sonu çevirisi yok (eski `newline=""` ile aynı).
    with open(yol, "ab") as f:
        f.write(veri)


@dataclass
class BibDenetim:
    """.bib dosyasının KENDİ tutarlılığı (referans denetiminden ayrı).

    mukerrer: (anahtar, tanımlandığı satırlar): birden çok tanım
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
