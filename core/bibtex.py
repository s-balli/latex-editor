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
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# Girdi olmayan @ blokları: makro tanımı, yorum, önsöz.
GIRDI_DISI = frozenset(["string", "comment", "preamble"])

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
        if tur not in GIRDI_DISI:
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


# Girdi ANAHTARININ kendisini bulan desen: `@article{kaya2020,` içindeki
# `kaya2020`. Ayrıştırıcı (parse_entries) girdinin tamamını istiyor,
# tüketicilerin bir bölümü ise yalnız anahtarın metindeki YERİNİ istiyor:
# imleç altındaki anahtar (Alt+tık, F2), satır numarası, yeniden adlandırma
# aralığı. Onlar için ayrıştırıcı çalıştırmak gerekmiyor; ama desen
# ayrıştırıcıyla AYNI kuralları taşımak zorunda, yoksa aynı dosya hakkında
# iki farklı cevap çıkıyor.
#
# ÖLÇÜLDÜ (2026-09-09): desenin iki kopyası (latex_refs, editor) `@tur(...)`
# parantezli biçimi tanımıyor, `@comment{eski,` bloğunu ise girdi sanıyordu.
# Parantezli tek bir girdi uygulamayı kendisiyle çelişkiye düşürüyordu:
# Kaynakça sekmesi girdiyi listeliyor, referans denetimi aynı anahtara
# "Tanımsız atıf" diyor, Alt+tık gitmiyor, F2 .bib girdisini atlayıp
# belgede sarkan atıf bırakıyordu.
#
# SINIR (bilerek): virgülsüz `@book{anahtar}` biçimi bu desenle eşleşmiyor,
# ayrıştırıcıyla ise eşleşiyor. 22 gerçek .bib dosyasının 306 girdisinde
# örneği yok; alanı olmayan girdi kaynakçada da bir şey basmıyor.
RE_GIRDI_ANAHTARI = re.compile(
    r'@(?!(?:' + '|'.join(sorted(GIRDI_DISI)) + r')[\s{(])'
    r'\w+\s*[{(]\s*([^,\s{}()]+)\s*,', re.I)


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


def _tek_grup(deger: str) -> bool:
    """Değer baştan sona TEK bir `{...}` grubu mu?"""
    derinlik = 0
    for i, c in enumerate(deger):
        derinlik += (c == "{") - (c == "}")
        if derinlik == 0:
            return c == "}" and i == len(deger) - 1
    return False


def yazar_kisalt(deger: str) -> str:
    """`author` alanını listede gösterilecek kısa biçime indir.

    Ham alan tabloya sığmıyor: ölçülen bir örnek
    `{Kaya, Aydın and Keçeli, Ali Seydi and Can, Ahmet Burak}`.

    BibTeX iki yazar biçimini de kabul ediyor ve ikisi de sahada var:
        "Kaya, Aydın"   -> soyadı virgülden ÖNCE
        "Aydın Kaya"    -> soyadı SON kelime
    Süslü parantezle sarılı ad kurum demektir (`{Dünya Sağlık Örgütü}`) ve
    bölünmemeli; oradaki virgül yazar ayracı değil. Sarılı olan değerin
    TAMAMI olmalı: `{\\"O}mer Kaya and Serkan Ball{\\i}` de `{` ile başlayıp
    `}` ile bitiyor ama iki yazar.
    """
    deger = deger.strip()
    if not deger:
        return ""
    if _tek_grup(deger):
        return deger[1:-1].strip()
    yazarlar = [y.strip() for y in deger.split(" and ") if y.strip()]
    if not yazarlar:
        return ""
    ilk = yazarlar[0]
    soyad = ilk.split(",")[0].strip() if "," in ilk else ilk.split()[-1]
    return soyad + (" vd." if len(yazarlar) > 1 else "")


def ozet(girdi: BibGirdi) -> tuple[str, str, str, str, str]:
    """Listeleme için (anahtar, tür, yazar, yıl, başlık).

    Değerler ham; yalnız gösterim için kısaltılıyor. Koruma parantezleri
    (`{BERT}`, `Ball{\\i}`) atılıyor: kullanıcı okuyacak, dizgi motoru değil.
    LaTeX de okunur metne dönüyor (`_latex_okunur`); yazarda kısaltmadan
    SONRA, çünkü BibTeX de adları ham metinde ayırıyor: `Ball\\i and Kaya`da
    `\\i`nin yuttuğu boşluk önce çevrilince " and " ayracını siliyordu. Aynı
    sebeple " vd." eki (bizim, TeX'in değil) çeviriden sonra ekleniyor.
    """
    baslik = _latex_okunur(girdi.alanlar.get("title", ""))
    baslik = baslik.replace("{", "").replace("}", "")
    yazar = yazar_kisalt(girdi.alanlar.get("author")
                         or girdi.alanlar.get("editor", ""))
    ek = " vd." if yazar.endswith(" vd.") else ""
    yazar = _latex_okunur(yazar.removesuffix(ek)) + ek
    return (girdi.anahtar, girdi.tur,
            yazar.replace("{", "").replace("}", ""),
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
# Crossref dört harfli "Sept" de döndürüyor (ölçüldü, 10.52843/cassyni.qb211x);
# tabloda yokken ay sessizce atılıyordu.
_AYLAR["sept"] = "sep"

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


# DOI'den gelen alan değerinde LaTeX'in özel karakterleri. ÖLÇÜLDÜ
# (2026-09-14), her karakter için küçük bir belge + `.bib` üretilip
# uygulamanın KENDİ boru hattından (bibtex dahil) geçirilerek ve basılan
# kaynakça `pdftotext` ile okunarak:
#
#   95% guven araligi     -> PDF'te yalnız "95"; SESSİZ, derleme hatası YOK
#   spam_filtresi uzerine -> derleme hatası, "spamf iltresiuzerine"
#   C# ile gelistirme     -> derleme hatası, "#" kayıp
#   x^2 buyumesi          -> derleme hatası, "x2"
#   Bilim & Teknoloji     -> DOĞRU (`&` zaten kaçırılıyordu)
#
# `%`in sessiz olması en kötüsü: kullanıcı DOI yapıştırıyor, kaynak
# eklendi sanıyor ve kaynakçasının yarısı yok.
#
# MATEMATİĞE DOKUNULMUYOR: Crossref başlıklarda TeX döndürüyor ve
# `$x_1$ degiskeni` bugün DOĞRU basılıyor (ölçüldü); `_`i körlemesine
# kaçırmak onu bozardı. `%` istisna, matematik içinde de yorum başlatıyor.
#
# `$`, `~` ve `\` BİLEREK dışarıda: `$` matematik açıyor, `~` bağlayıcı
# boşluk basıyor (yanlış ama derleme durmuyor), `\` zaten kaçış.
_RE_MATEMATIK = re.compile(r"(\$[^$]*\$)")
_RE_METIN_OZEL = re.compile(r"(?<!\\)([#_^])")
_METIN_KACIS = {"#": r"\#", "_": r"\_", "^": r"\^{}"}

# UNICODE VE JATS. Crossref başlığı olduğu gibi veriyor: `NF-κB`, `TiO₂`,
# `TiO<sub>2</sub>`, `<i>via</i>`. ÖLÇÜLDÜ (2026-09-27), 19 gerçek kayıt
# (uygulamanın aldığı ham BibTeX) uygulamanın boru hattıyla (derle.sh,
# bibtex) iki motorda derlenip basılan kaynakça pdfium ile okunarak:
#   Yunan harfi, alt simge -> pdflatex: "Unicode character κ (U+03BA) not set
#                             up", derleme DÜŞÜYOR (19 girdinin 10'u);
#                             lualatex: derleniyor ama karakter SESSİZCE
#                             yok ("NF-B", "tio for"; yine 10)
#   <sub>2</sub>           -> iki motorda da etiket OLDUĞU GİBİ basılıyor (9)
# Liste tahmin değil: 112 aday karakter tek tek derlendi; pdflatex (T1 +
# utf8) 81'ini, lualatex (Latin Modern) 66'sını basamıyor. Aşağıdakiler o
# iki kümenin birleşimi. İkisinin de bastıkları (orta ve uzun tire, ‐ → ±
# × ° µ, tırnak) DOKUNULMADAN kalıyor.
#
# Üretilen matematik `{...}` içinde: plain.bst başlığı küçük harfe çeviriyor
# ve korumasız `$\Delta$` `$\delta$` olurdu (ham `Δ`ya dokunmuyordu).
_YUNAN = dict(zip(
    "αβγδεζηθικλμνξπρςστυφχψωϑϕϖϰϱϵΓΔΘΛΞΠΣΥΦΨΩ∆",
    r"alpha beta gamma delta varepsilon zeta eta theta iota kappa lambda mu nu"
    r" xi pi rho varsigma sigma tau upsilon varphi chi psi omega vartheta phi"
    r" varpi kappa varrho epsilon Gamma Delta Theta Lambda Xi Pi Sigma Upsilon"
    r" Phi Psi Omega Delta".split()))
# Latin harfiyle AYNI görünen büyük Yunan harflerinin makrosu yok (`\Alpha`
# tanımsız); küçük omikron da öyle.
_YUNAN_LATIN = dict(zip("ΑΒΕΖΗΙΚΜΝΟΡΤΧο", "ABEZHIKMNOPTXo"))
_SIMGE_MAT = {"′": "'", "″": "''", "↔": r"\leftrightarrow", "⇒": r"\Rightarrow",
              "−": "-", "∓": r"\mp", "∞": r"\infty", "∼": r"\sim",
              "≈": r"\approx", "≠": r"\neq", "≤": r"\leq", "≥": r"\geq"}
_SIMGE_METIN = {" ": r"\,", " ": r"\,", "‒": "--"}
_ALT = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋", "0123456789+-"))
_UST = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-"))
_RE_ALT = re.compile("[%s]+" % "".join(_ALT))
_RE_UST = re.compile("[%s]+" % "".join(_UST))
_RE_MAT_SIMGE = re.compile("[%s]" % re.escape(
    "".join(_YUNAN) + "".join(_SIMGE_MAT)))
# Crossref'in başlıkta izin verdiği biçim etiketleri. Karşılığı olmayanlar
# (`ovl`, `font`, MathML) atılıp içerikleri kalıyor. Liste BİLİNEN adlarla
# sınırlı: başlıktaki düz bir karşılaştırma ("x<y and y>z") etiket değil.
_JATS = {"sub": r"\textsubscript{%s}", "sup": r"\textsuperscript{%s}",
         "i": r"\textit{%s}", "b": r"\textbf{%s}", "scp": r"\textsc{%s}",
         "tt": r"\texttt{%s}", "u": r"\underline{%s}"}
_RE_JATS = re.compile(r"<(%s)>(.*?)</\1>" % "|".join(_JATS), re.S)
_RE_ETIKET = re.compile(
    r"</?(?:%s|ovl|font|mml:[\w.-]+|inline-formula|alternatives)"
    r"(?:\s[^<>]*)?/?>" % "|".join(_JATS))
# Wiley ve RSC kayıtları JATS'ı GİRİNTİLİ veriyor ("TiO\n      <sub>2</sub>\n
# on their"). Alt/üst simgeden önceki girinti yapışık (TiO₂); kapanıştan
# sonraki, ardından noktalama (orta tire dahil) gelirse yapışık, yoksa boşluk.
_RE_GIRINTI_ONCE = re.compile(r"\s*\n\s*(?=<su[bp]>)")
_RE_GIRINTI_SONRA = re.compile(
    r"(?<=</sub>|</sup>)\s*\n\s*(?=[\N{EN DASH}\N{EM DASH}\-),.;:/])")
_RE_GIRINTI = re.compile(r"\s*\n\s*")
# Adres ve kimlik alanları metin değil; LaTeX'e çevrilmiyor.
_KIMLIK_ALANI = frozenset(["url", "doi", "isbn", "issn", "eprint"])

# BÜYÜK HARF KORUMASI. plain, abbrv, unsrt, plainnat gibi stiller makale
# başlığını küçültüyor (`change.case$ "t"`) ve Crossref başlığında koruma
# parantezi yok. ÖLÇÜLDÜ (2026-09-27, 21 gerçek kayıt plain.bst ile derlenip
# basılan metin ELLE yazılmış cümle düzeniyle karşılaştırılarak): 45 kelimenin
# harfi bozuluyordu ("nf-κb", "tio2", "cd28", "Malt lymphoma").
#
# Kelime tire ve eğik çizgiden parçalanıyor; parça şu üç durumda `{}` içine
# alınıyor: ilk harfinden SONRA büyük harf var (NF, TiO, κB, CXCL12,
# ChemInform); büyük harfle birlikte rakam ya da yük işareti var (Ca2+, Na+,
# Dishevelled1); başlığın ilk kelimesi değilken tek büyük harf (filamin A,
# K-ATPase). Yalnız baş harfi büyük parça (Phase-Selective, Wnt) korunmuyor:
# başlık düzeni ile özel ad ayırt edilemiyor, onu stil küçültüyor.
_RE_KORUMA_AYIRAC = re.compile(
    r"([-/\N{HYPHEN}\N{NON-BREAKING HYPHEN}\N{EN DASH}\N{EM DASH}](?![^<]*>))")
_RE_HAM_ETIKET = re.compile(r"</?[a-z]+>")
_KORUMA_ON = "([\"'\N{LEFT DOUBLE QUOTATION MARK}"
_KORUMA_SON = ")]\"'.,;:!?\N{RIGHT DOUBLE QUOTATION MARK}"
_YUK = "+\N{MINUS SIGN}\N{SUPERSCRIPT PLUS SIGN}\N{SUPERSCRIPT MINUS}" \
       "\N{SUBSCRIPT PLUS SIGN}\N{SUBSCRIPT MINUS}"


def _parca_koru(parca: str, ilk: bool) -> str:
    """Tek parçayı (tiresiz) gerekiyorsa `{}` içine al; noktalama dışarıda."""
    i, j = 0, len(parca)
    while i < j and parca[i] in _KORUMA_ON:
        i += 1
    while j > i and parca[j - 1] in _KORUMA_SON:
        j -= 1
    cekirdek = parca[i:j]
    gorunen = _RE_HAM_ETIKET.sub("", cekirdek)
    if any(c in gorunen for c in "${}\\"):
        return parca                        # zaten LaTeX ya da korumalı
    buyuk = [k for k, c in enumerate(gorunen) if c.isupper()]
    if not buyuk:
        return parca
    ilk_harf = next(k for k, c in enumerate(gorunen) if c.isalpha())
    if (any(k > ilk_harf for k in buyuk)
            or any(c.isdigit() or c in _YUK for c in gorunen)
            or (len(gorunen) == 1 and not ilk)):
        return parca[:i] + "{" + cekirdek + "}" + parca[j:]
    return parca


def _buyuk_harf_koru(baslik: str) -> str:
    """Başlıktaki kısaltma, formül ve simgeleri stilin küçültmesinden koru."""
    sayac = [0]

    def kelime(m):
        ilk = sayac[0] == 0
        sayac[0] += 1
        return "".join(p if _RE_KORUMA_AYIRAC.fullmatch(p) else _parca_koru(p, ilk)
                       for p in _RE_KORUMA_AYIRAC.split(m.group(0)))

    return re.sub(r"\S+", kelime, baslik)


def _unicode_latex(deger: str) -> str:
    """Motorların basamadığı ölçülen karakterleri LaTeX'e çevir.

    Matematik bölgesinde (`$...$`) `$` açılmıyor, komut doğrudan yazılıyor.
    """
    parcalar = []
    for p in _RE_MATEMATIK.split(deger):
        mat = p.startswith("$")
        for eski, yeni in _YUNAN_LATIN.items():
            p = p.replace(eski, yeni)
        for eski, yeni in _SIMGE_METIN.items():
            p = p.replace(eski, yeni)
        if mat:
            p = _RE_MAT_SIMGE.sub(lambda m: "\\" + _YUNAN[m.group(0)] + " "
                                  if m.group(0) in _YUNAN
                                  else _SIMGE_MAT[m.group(0)] + " ", p)
            p = _RE_ALT.sub(lambda m: "_{%s}" % "".join(_ALT[c] for c in m.group(0)), p)
            p = _RE_UST.sub(lambda m: "^{%s}" % "".join(_UST[c] for c in m.group(0)), p)
        else:
            p = _RE_MAT_SIMGE.sub(lambda m: "{$%s$}" % (
                "\\" + _YUNAN[m.group(0)] if m.group(0) in _YUNAN
                else _SIMGE_MAT[m.group(0)]), p)
            p = _RE_ALT.sub(lambda m: r"\textsubscript{%s}" % "".join(
                _ALT[c] for c in m.group(0)), p)
            p = _RE_UST.sub(lambda m: r"\textsuperscript{%s}" % "".join(
                _UST[c] for c in m.group(0)), p)
        parcalar.append(p)
    return "".join(parcalar)


# Kaynakça SEKMESİ için ters yön: `normallestir`in ürettiği LaTeX okunur
# metne dönüyor. ÖLÇÜLDÜ (2026-09-27, gerçek pencere): Unicode çevirisinden
# sonra sekmede "NF-$\kappa$B" ve "TiO\textsubscript2" görünüyordu, öncesinde
# "NF-κB" ve "TiO₂". Tablolar yukarıdakilerle aynı (tek kaynak).
_YUNAN_TERS = {}
for _harf, _ad in _YUNAN.items():
    _YUNAN_TERS.setdefault(_ad, _harf)      # \Delta: Δ (∆ değil)
_MAT_TERS = {v.lstrip("\\"): k for k, v in _SIMGE_MAT.items()}
_ALT_TERS = {v: k for k, v in _ALT.items()}
_UST_TERS = {v: k for k, v in _UST.items()}
_RE_MAT_TEK = re.compile(r"\$\\?([A-Za-z]+|'{1,2}|-) ?\$")
_RE_ALT_UST = re.compile(r"\\text(sub|super)script\{([^{}]*)\}")
_RE_BICIM = re.compile(r"\\(?:textit|textbf|textsc|texttt|underline|emph)\{([^{}]*)\}")

# Elle yazılmış .bib'in LaTeX'i de okunur metne dönüyor: aksan (`\"o`,
# `\c{s}`, `\c c`, `\'{\i}`), özel harf (`\i`, `\ss`), logo (`\TeX`),
# kaçış (`\&`) ve bağ (`~`). ÖLÇÜLDÜ (2026-09-28): template/ altındaki 306
# girdi pdflatex ile basılıp sekmeyle karşılaştırıldı; başlıkta 11, yazarda
# 29 fark vardı ("Ball{\i} vd.", "veri madencili\ugi"). Bilerek dışarıda
# kalanlar: `--` ve tırnak yazı tipinin bitişik harfi, `@preamble`
# makrosunun (`\VAN`) ne bastığı buradan bilinemiyor.
_AKSAN = {
    '"': "\N{COMBINING DIAERESIS}", "'": "\N{COMBINING ACUTE ACCENT}",
    "`": "\N{COMBINING GRAVE ACCENT}", "^": "\N{COMBINING CIRCUMFLEX ACCENT}",
    "~": "\N{COMBINING TILDE}", "=": "\N{COMBINING MACRON}",
    ".": "\N{COMBINING DOT ABOVE}", "u": "\N{COMBINING BREVE}",
    "v": "\N{COMBINING CARON}", "H": "\N{COMBINING DOUBLE ACUTE ACCENT}",
    "c": "\N{COMBINING CEDILLA}", "k": "\N{COMBINING OGONEK}",
    "r": "\N{COMBINING RING ABOVE}", "d": "\N{COMBINING DOT BELOW}",
    "b": "\N{COMBINING MACRON BELOW}"}
_OZEL_HARF = {"i": "ı", "j": "ȷ", "o": "ø", "O": "Ø", "l": "ł", "L": "Ł",
              "ss": "ß", "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ",
              "aa": "å", "AA": "Å",
              "LaTeXe": "LaTeX2\N{GREEK SMALL LETTER EPSILON}"}
_LOGO = "TeX LaTeX BibTeX XeTeX XeLaTeX LuaTeX LuaLaTeX pdfTeX pdfLaTeX ConTeXt"
# Komut adından sonraki boşluğu TeX yutuyor: "The \TeX book" -> "The TeXbook".
_RE_OZEL_HARF = re.compile(r"\\(%s)(?![A-Za-z]) *" % "|".join(
    list(_OZEL_HARF) + _LOGO.split()))
_RE_AKSAN = re.compile(
    r"\\([\"'`^~=.]|[uvHckrdb](?![A-Za-z])) *(\{[A-Za-zıȷ]?\}|[A-Za-zıȷ])")
_RE_DERECE = re.compile(r"\$\^\{?\\circ\}?\$")


def _aksan(m) -> str:
    """`\\c{s}` -> ş. Aksanın altındaki `\\i` noktalı harfe dönüyor (í)."""
    taban = m.group(2).strip("{}")
    taban = {"ı": "i", "ȷ": "j"}.get(taban, taban)
    if not taban:                           # `\^{}`: işaretin kendisi
        return "" if m.group(1).isalpha() else m.group(1)
    return unicodedata.normalize("NFC", taban + _AKSAN[m.group(1)])


def _latex_okunur(metin: str) -> str:
    """`{$\\kappa$}`, `\\textsubscript{2}`, `\\textit{via}` -> κ, ₂, via."""
    metin = _RE_MAT_TEK.sub(
        lambda m: _YUNAN_TERS.get(m.group(1)) or _MAT_TERS.get(m.group(1))
        or m.group(0), metin)
    metin = _RE_DERECE.sub("°", metin)
    metin = _RE_ALT_UST.sub(lambda m: "".join(
        (_ALT_TERS if m.group(1) == "sub" else _UST_TERS).get(c, c)
        for c in m.group(2)), metin)
    metin = re.sub(r"(?<!\\)~", " ", metin)
    metin = _RE_OZEL_HARF.sub(lambda m: _OZEL_HARF.get(m.group(1), m.group(1)), metin)
    metin = _RE_AKSAN.sub(_aksan, metin)
    metin = re.sub(r"\\([&%$#_])", r"\1", metin)
    return _RE_BICIM.sub(r"\1", metin).replace(r"\,", " ")


def _jats_latex(deger: str) -> str:
    """Biçim etiketlerini LaTeX'e çevir; girintiyi etiketlerle birlikte çöz."""
    if "<" not in deger:
        return deger
    deger = _RE_GIRINTI_ONCE.sub("", deger)
    deger = _RE_GIRINTI_SONRA.sub("", deger)
    deger = _RE_GIRINTI.sub(" ", deger)
    for _ in range(3):                      # iç içe etiket (`<i><sub>`)
        yeni = _RE_JATS.sub(lambda m: _JATS[m.group(1)] % m.group(2), deger)
        if yeni == deger:
            break
        deger = yeni
    return _RE_ETIKET.sub("", deger)


def _deger_duzelt(ad: str, deger: str) -> str:
    """Alan değerinin ölçülen kusurlarını gider."""
    if ad == "title":
        # İlk adım: yalnız `{}` ekliyor, sonraki kaçış ve çeviriler
        # parantezin İÇİNDE çalışıyor (`{NF}-{κB}` -> `{NF}-{{$\kappa$}B}`).
        deger = _buyuk_harf_koru(deger)
    if ad == "pages":
        # Crossref sayfa aralığını ORTA TİRE (U+2013) ile veriyor.
        # plain.bst aralığı `--` ile tanıyor; tire kalınca çıktıya
        # "page 770<U+2013>778" yazıyor (tekil!), "pages 770--778" değil.
        # Gerçek derlemeyle ölçüldü.
        deger = deger.replace("–", "--").replace("—", "--")
    # LaTeX'te `&` kaçışsız kullanılamaz; kaçışlı olanlara dokunma.
    deger = re.sub(r"(?<!\\)&", r"\\&", deger)
    # `%` HER YERDE kaçırılıyor, matematik içinde bile: yorum başlatıyor.
    deger = re.sub(r"(?<!\\)%", r"\\%", deger)
    # `# _ ^` yalnız MATEMATİK DIŞINDA kaçırılıyor; `$...$` bölgesi
    # dokunulmadan geçiyor (gerekçe aşağıda).
    deger = "".join(p if p.startswith("$") else _RE_METIN_OZEL.sub(
        lambda m: _METIN_KACIS[m.group(1)], p)
        for p in _RE_MATEMATIK.split(deger))
    if ad in _KIMLIK_ALANI:
        return deger
    return _unicode_latex(_jats_latex(deger))


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


# Dosyanın kendi kodlaması: yazabilmek için kodlamanın ADI da gerekiyor.
# Çözücü zincir TEK KAYNAK core.fs_ops (bkz. oradaki not); burada kendi
# gövdesi vardı ve `gui/editor._decode_bytes` ile birebir aynıydı.
from core.fs_ops import coz_adiyla as _coz_adiyla  # noqa: E402
from core.fs_ops import yaz_atomik  # noqa: E402


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

    # UTF-16'da SONA EKLEME olmaz: `encode("utf-16")` her çağrıda başa bir
    # BOM koyuyor, yani ekleme dosyanın ORTASINA ikinci bir BOM yerleştirirdi.
    # Dosyanın tamamı yeniden yazılıyor, kodlaması korunarak (bkz.
    # `fs_ops.coz_adiyla`: PowerShell'in `>` yönlendirmesi bu kodlamayı yazıyor).
    if kodlama == "utf-16":
        yaz_atomik(yol, (var_olan + eklenecek).encode("utf-16"))
        return

    try:
        veri = eklenecek.encode(kodlama)
    except UnicodeEncodeError:
        # Yeni girdi eski kodlamaya SIĞMIYOR (ör. cp1254'te karşılığı olmayan
        # bir harf; DOI ile gelen kayıtlarda olağan). Karma kodlamalı dosya
        # üretmektense dosyanın TAMAMI utf-8'e çevriliyor: metin birebir
        # korunuyor, yalnız baytlar değişiyor ve dosya tek kodlamada kalıyor.
        #
        # ATOMİK: burası kullanıcının var olan kaynakçasının ÜSTÜNE yazıyor.
        # `open(yol, "wb")` ile yazılıyordu ve o dosyayı açar açmaz
        # boşaltıyor; ÖLÇÜLDÜ (2026-09-12, hata enjeksiyonu): yazma tek bir
        # noktada düşürülünce `.bib` 0 BAYTA indi ve var olan girdi gitti.
        yaz_atomik(yol, (var_olan + eklenecek).encode("utf-8"))
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
    from core.fs_ops import coz
    sonuc = denetle(coz(ham))
    if len(_cache) >= _CACHE_SINIR:
        _cache.clear()
    _cache[yol] = (mtime, sonuc)
    return sonuc
