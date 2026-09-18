"""LaTeX yardımcı fonksiyonları: yorum temizleme, etiket anahtarı."""

import re

# Etiket anahtarında GÜVENLİ sayılan karakterler. Harf/rakamın yanında
# `_ - . :` duruyor; `fig:sonuc_grafik` LaTeX'te yaygın ve doğru bir anahtar.
#
# HARF Unicode harfidir, ASCII değil. Burada `A-Za-z` yazıyordu ve Türkçe
# harfler ELENİYORDU; bu uygulamanın birincil kitlesinde sıradan bir ad
# anlaşılmaz bir anahtara dönüyordu (ÖLÇÜLDÜ 2026-09-14):
#
#   "Ölçüm Değerleri" -> l-m-De-erleri
#   "Giriş"           -> Giri
#   "şekil çıktı"     -> ekil-kt
#
# Oysa Türkçe harfli etiket GERÇEKTEN derleniyor. Aynı ölçümde beş alfabe
# (Türkçe, Latin ek, Yunan, Kiril, CJK) üç motorda da (pdflatex, lualatex,
# xelatex) hem derlendi hem `\ref` çözüldü, yani `\w` güvenli sınır.
# Tablo sihirbazı zaten Türkçe harf bırakıyordu (`guvenli_label`), yani
# uygulama aynı soruya iki ayrı cevap veriyordu.
_ETIKET_GUVENSIZ = re.compile(r"[^\w\-.:]+")

# `\label` içine YAZILDIĞINDA derlemeyi kıran karakterler. TEK KAYNAK:
# `core.latex_tables.guvenli_label` (üretim) ve F2 yeniden adlandırmanın
# doğrulaması (gui/mixins/edit_ops) buradan besleniyor; ikisi ayrı
# yazılıyken F2, tablo sihirbazının KENDİ ÜRETTİĞİ Türkçe etiketi
# reddediyordu.
#
# ÖLÇÜLDÜ (2026-09-07, gerçek pdflatex): denenen altı karakterden BEŞİ
# belgeyi derlenemez yapıyor (`%`, `}`, `{`, `\`, `#`). Denetim
# karakterleri de eleniyor (`tab:a\x08b` derlenmiyor).
LABEL_YASAK = re.compile(r"[%\\{}#&$~^\x00-\x1f\x7f]")


def label_gecerli_mi(key: str) -> bool:
    r"""`key` doğrudan `\label{...}` içine yazılabilir mi.

    Boşluk da eleniyor: LaTeX kabul ediyor ama `\ref` yazmayı zorlaştırıyor
    ve uygulamanın ürettiği anahtarlarda hiç bulunmuyor.
    """
    return bool(key) and not LABEL_YASAK.search(key) and not re.search(
        r"\s", key)


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


# --------------------------------------------------------------------------
# Aksan makroları: TEK KAYNAK
# --------------------------------------------------------------------------
#
# Tablolar `core/yazim.py`de yazılıydı ve orada kalırsa ikinci bir kopya
# çıkardı: anahat paneli de aynı bilgiye muhtaç. Yazım denetimi kendi
# tarayıcısını kullanmayı sürdürüyor (o ofset korumak zorunda), buradan
# yalnız TABLOLARI alıyor; anahat ise aşağıdaki dizge çözücüyü kullanıyor.

# Noktalama adlı aksanlar: parantezsiz de yazılabilir (\"o), çünkü hiçbir
# komut adının öneki değiller.
AKSAN_NOKTALAMA = {
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
# \usepackage ve \cite ile karışıyor (ölçülmüş hata, bkz. core/yazim.py).
AKSAN_HARF = {
    ("c", "c"): "ç", ("c", "C"): "Ç", ("c", "s"): "ş", ("c", "S"): "Ş",
    ("u", "g"): "ğ", ("u", "G"): "Ğ", ("u", "a"): "ă", ("u", "e"): "ĕ",
    ("v", "s"): "š", ("v", "c"): "č", ("v", "z"): "ž", ("v", "r"): "ř",
    ("H", "o"): "ő", ("H", "u"): "ű", ("k", "a"): "ą", ("k", "e"): "ę",
}

# \i (noktasız ı) ve \j: argümansız, tek başına harf
TEK_HARF_KOMUT = {"i": "ı", "j": "ȷ", "l": "ł", "o": "ø", "O": "Ø",
                  "aa": "å", "AA": "Å", "ss": "ß", "ae": "æ", "AE": "Æ"}

_RE_AKSAN_NOKTALAMA = re.compile(
    r'\\(["\'`^~.=])\s*(?:\{([A-Za-z])\}|([A-Za-z]))')
_RE_AKSAN_HARF = re.compile(r'\\([A-Za-z]+)\s*\{([A-Za-z])\}')
# Harf adlı komuttan SONRAKİ tek boşluk komuta aittir (TeX kuralı):
# `Bilg\i sayar` "Bilgısayar" basıyor, "Bilgı sayar" değil (ölçüldü).
_RE_TEK_HARF = re.compile(r'\\([A-Za-z]+)[ \t]?')


def aksanlari_coz(metin: str) -> str:
    r"""Aksan makrolarını BASILAN harfe çevir (gösterim için).

    ÖLÇÜLDÜ (2026-09-15, lualatex ile derlenip PDF metni okunarak):

        \"Olcum          -> Ölcum
        \c{C}alisma      -> Çalisma
        \u{g}ercek       -> ğercek
        Bilg\i sayar     -> Bilgısayar

    Anahat paneli bunları çözmüyordu; `\c{C}` "C", `\i` ise "i" oluyordu,
    yani panelde belgede YAZMAYAN bir kelime görünüyordu.

    Tanınmayan komut OLDUĞU GİBİ kalıyor (`\alpha`, `\usepackage`): bu
    işlev yalnız tablodaki makroları çözer, komut ayıklamaz.
    """
    def _noktalama(m):
        harf = m.group(2) or m.group(3)
        return AKSAN_NOKTALAMA.get((m.group(1), harf), m.group(0))

    def _harf(m):
        return AKSAN_HARF.get((m.group(1), m.group(2)), m.group(0))

    def _tek(m):
        return TEK_HARF_KOMUT.get(m.group(1), m.group(0))

    metin = _RE_AKSAN_NOKTALAMA.sub(_noktalama, metin)
    metin = _RE_AKSAN_HARF.sub(_harf, metin)
    return _RE_TEK_HARF.sub(_tek, metin)


# --------------------------------------------------------------------------
# Kağıt boyu: belgenin İSTEDİĞİ ile PDF'te ÇIKAN
#
# Standart sınıfların kağıt seçeneği metin bloğunu kuruyor ama FİZİKSEL
# sayfayı belirlemiyor; onu TeX dağıtımının öntanımı veriyor. Debian/Ubuntu
# TeX Live A4'e, MacTeX/BasicTeX US Letter'a ayarlı. ÖLÇÜLDÜ (2026-09-19,
# aynı kaynak, aynı motor, iki platform):
#
#   \documentclass{article}              Linux A4   | macOS US Letter
#   \documentclass[a4paper]{article}     Linux A4   | macOS US Letter  <-- (*)
#   [a4paper] + \usepackage{geometry}    Linux A4   | macOS A4
#   [letterpaper] + geometry             Linux Letter | macOS Letter
#
# (*) işaretli satır kusurun kendisi: belge A4 İSTEMİŞ, macOS'ta Letter
# almış ve kimse bunu söylememiş. `geometry` yüklendiğinde belge sözünü
# geçiriyor, yüklenmediğinde geçmiyor.
#
# Buradaki iki işlev saf: dosya açmıyor, pdfium'a dokunmuyor. Karşılaştırma
# GUI tarafında yapılıyor (compile_ops), çünkü asıl sayfa boyutu üretilen
# PDF'ten okunuyor.

# Genişlik x yükseklik, NOKTA (1/72 inç). Adlar `\documentclass`
# seçeneklerinde geçtiği gibi.
KAGIT_SECENEKLERI = {
    "a4paper": (595.276, 841.890),
    "a5paper": (419.528, 595.276),
    "b5paper": (498.898, 708.661),
    "letterpaper": (612.0, 792.0),
    "legalpaper": (612.0, 1008.0),
    "executivepaper": (540.0, 720.0),
}

# İnsan okuru için kısa adlar.
KAGIT_ADLARI = {
    "a4paper": "A4",
    "a5paper": "A5",
    "b5paper": "B5",
    "letterpaper": "US Letter",
    "legalpaper": "US Legal",
    "executivepaper": "US Executive",
}

_RE_SINIF_SECENEK = re.compile(r'\\documentclass\s*\[([^\]]*)\]')
_KAGIT_TOLERANS = 2.0           # nokta; yuvarlama payı


def bildirilen_kagit(metin: str) -> str | None:
    """Belgenin `\\documentclass` seçeneklerinde bildirdiği kağıt adı.

    Dönüş `KAGIT_SECENEKLERI` anahtarı ya da None (bildirmemiş).
    Yorum satırları önce ayıklanıyor: yorumdaki eski bir `\\documentclass`
    satırı gerçek olanın yerine geçmemeli.
    """
    m = _RE_SINIF_SECENEK.search(strip_comments(metin))
    if not m:
        return None
    for ham in m.group(1).split(","):
        ad = ham.strip().lower()
        if ad in KAGIT_SECENEKLERI:
            return ad
    return None


def kagit_eslesiyor_mu(secenek: str, genislik: float, yukseklik: float) -> bool:
    """Ölçülen sayfa boyu bildirilen kağıda uyuyor mu.

    Yatay (landscape) belgede kenarlar yer değiştirdiği için iki yön de
    kabul ediliyor; yoksa `\\documentclass[a4paper,landscape]` yanlışlıkla
    uyumsuz sayılırdı.
    """
    beklenen = KAGIT_SECENEKLERI.get(secenek)
    if beklenen is None:
        return True
    bg, by = beklenen
    duz = abs(genislik - bg) <= _KAGIT_TOLERANS and \
        abs(yukseklik - by) <= _KAGIT_TOLERANS
    yatay = abs(genislik - by) <= _KAGIT_TOLERANS and \
        abs(yukseklik - bg) <= _KAGIT_TOLERANS
    return duz or yatay


def kagit_adi(genislik: float, yukseklik: float) -> str:
    """Ölçülen boyutun bilinen kağıt adı; tanınmazsa milimetre olarak."""
    for anahtar, (g, y) in KAGIT_SECENEKLERI.items():
        for a, b in ((g, y), (y, g)):
            if abs(genislik - a) <= _KAGIT_TOLERANS and \
                    abs(yukseklik - b) <= _KAGIT_TOLERANS:
                return KAGIT_ADLARI[anahtar]
    return "%.0f x %.0f mm" % (genislik * 25.4 / 72, yukseklik * 25.4 / 72)
