"""Yaygın LaTeX hataları için insan dili ipuçları — kalıp eşleme (Qt'süz).

Derleyici mesajları yeni kullanıcı için korsan argodur; araştırmada en çok
oylu somut istek "helpful error messages"dı. Bu modül yaygın ~14 kalıbı tanır
ve (ipucu_kimliği, parametreler) döndürür. İpucu METİNLERİ sunum katmanında
durur (GUI'de çevrilir; web'de de aynı kimlikler kullanılabilir).

Eksik paket tespiti ayrıca yapılır (derle.sh önerisi + install komutu);
burada tekrarlanmaz.
"""

import re

# Bağlam satırı "l.42 ... \komut": tanımsız komudu buradan çıkarıyoruz.
#
# SON komut alınıyor, ilki değil. TeX bağlam satırını hatanın olduğu YERDE
# kesiyor ve "Undefined control sequence" komut okunur okunmaz atılıyor; yani
# suçlu komut o satırın SON belirteci oluyor. Eskiden ilki alınıyordu.
# GERÇEK pdflatex çıktısıyla ölçüldü (2026-09-05):
#
#   l.3 \bilinmeyenkomut                 ilk = son  -> doğru
#   l.3 Merhaba \bilinmeyenkomut         ilk YOK    -> komut adı hiç yazılmıyor
#   l.3 \textbf{Kalin} \bilinmeyenkomut  ilk \textbf -> SAĞLAM komut suçlanıyor
#
# Depodaki 59 şablonun 135330 komut geçişinde: %49.8 doğru, %10.8 boş, %39.4
# yanlış. Yanlış olan en kötüsü: ipucu kullanıcıyı "\textbf tanımsız, paketini
# yükle" diye gayet çalışan bir komudun peşine yolluyordu.
_RE_CTX_SATIRI = re.compile(r"l\.\d+\s+(.*)")
# TeX kontrol sözcüğü yalnızca HARFtir: `\foo_bar`, TeX'te `\foo` + `_bar`.
_RE_KOMUT = re.compile(r"\\[A-Za-z]+")

# (mesaj deseni, ipucu kimliği). Sıra önemli: özgül olan önce.
# Parametreli ipuçlar (ortam adı, komut adı) aşağıda ayrıca işlenir.
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Undefined control sequence"), "undefined_control"),
    (re.compile(r"Missing \$ inserted"), "missing_math"),
    (re.compile(r"Display math should end with"), "missing_math"),
    (re.compile(r"Text line contains an invalid character"), "invalid_character"),
    # pdflatex + inputenc'te akıllı tırnak/tire bu mesajla gelir:
    # "[inputenc] Unicode character ... (U+201C) not set up for use with LaTeX."
    (re.compile(r"Unicode character .+ not set up"), "invalid_character"),
    (re.compile(r"Missing \} inserted|Too many \}'s|Extra \}"), "brace_mismatch"),
    (re.compile(r"Double subscripts?|Double superscripts?"), "double_subscript"),
    (re.compile(r"File ended while scanning"), "file_ended_scanning"),
    (re.compile(r"Emergency stop"), "emergency_stop"),
    (re.compile(r"Counter too large"), "counter_too_large"),
    (re.compile(r"Misplaced \\noalign|Misplaced \\omit"), "misplaced_noalign"),
    (re.compile(r"Citation `[^']*' undefined|Citation .* undefined"), "citation_undefined"),
    (re.compile(r"Reference `[^']*' .*undefined|Reference .* undefined"), "reference_undefined"),
    (re.compile(r"There were undefined references|Rerun to get cross"), "rerun_needed"),
    # İki motor AYNI kusuru başka kelimelerle bildiriyor; ipucu ikisini de
    # tanımak zorunda. pdfTeX: "destination with the same identifier
    # (name{figure.1}) has been already used, duplicate ignored".
    # LuaTeX: "ignoring duplicate destination with the name 'figure.1'".
    # LuaTeX biçimi tanınmıyordu, yani ipucu uygulamanın VARSAYILAN
    # motorunda hiç çıkamıyordu (ölçüldü 2026-09-14, 55 gerçek belgenin
    # 17'sinde 358 satır).
    (re.compile(r"destination with the same identifier"
                r"|ignoring duplicate destination"), "duplicate_label"),
    # LaTeX'in kendi çift-etiket uyarısı (ikinci derleme geçesinde):
    # "Label `x' multiply defined." / "There were multiply-defined labels."
    (re.compile(r"multiply.defined labels?|Label `[^']*' multiply defined"),
     "duplicate_label"),
    # listings + Türkçe babel çakışması: turkish.ldf tek harflik dil adlarının
    # (C) lehçe çözümlemesini bozuyor → "language ansi of c undefined".
    # Dil adı gerçekten yanlış da yazılmış olabilir; ipucu ikisini kapsar.
    (re.compile(r"Listings Error: Couldn't load requested language"
                r"|language \S+ of \S+ undefined"), "listings_language"),
]

_RE_ENV_UNDEFINED = re.compile(r"Environment (\S+) undefined")

# Ortamı TANIMLAYAN paket.
#
# NEDEN BURADA: uygulama bu ortamları KENDİSİ öneriyor ya da KENDİSİ yazıyor.
# `\begin{` tamamlaması 62 ortam adı sayıyor, tablo sihirbazı `tabularx` ve
# `longtable` yazabiliyor, yazım denetimi ile anahat `tikzpicture`,
# `algorithm`, `Verbatim` gibi adları zaten tanıyor. Uygulamanın "Yeni
# Dosya" belgesi ise sade `\documentclass{article}`: hiç paket yüklemiyor.
#
# ÖLÇÜLDÜ (2026-09-14, gerçek derleme, core/derle.sh ile): uygulamanın
# bildiği 79 ortam adının 43'ü o belgede TANIMSIZ. Kullanıcı tamamlamadan
# `align` seçiyor, derliyor ve "Environment align undefined" alıyordu;
# ipucu ise yalnız "paketi yüklenmemiş" diyor, HANGİ paket olduğunu
# söylemiyordu.
#
# Her satır İKİ YÖNLÜ doğrulandı: paketsiz hâli "Environment X undefined"
# ile düşüyor, `\usepackage{...}` eklenince GEÇİYOR. Yanlış ad kullanıcıyı
# boşuna uğraştırır; nitekim ölçüm iki iddiayı ELEDİ: `amsthm` yedi teorem
# ortamını TANIMLAMIYOR (doğru cevap `\newtheorem`) ve `subfig`
# `subfigure` ORTAMINI vermiyor (doğru cevap `subcaption`).
ORTAM_PAKETI = {
    "align": "amsmath", "align*": "amsmath",
    "gather": "amsmath", "gather*": "amsmath",
    "multline": "amsmath", "multline*": "amsmath",
    "equation*": "amsmath", "split": "amsmath",
    "bmatrix": "amsmath", "vmatrix": "amsmath", "Vmatrix": "amsmath",
    "proof": "amsthm",
    "alltt": "alltt",
    "comment": "comment",
    "lstlisting": "listings",
    "minted": "minted", "listing": "minted",
    "wrapfigure": "wrapfig", "wraptable": "wrapfig",
    "subfigure": "subcaption", "subtable": "subcaption",
    "tabularx": "tabularx",
    "longtable": "longtable",
    "tikzpicture": "tikz",
    "pgfpicture": "pgf",
    "Verbatim": "fancyvrb", "BVerbatim": "fancyvrb", "LVerbatim": "fancyvrb",
    "algorithm": "algorithm",
    "algorithmic": "algorithmic",
    "multicols": "multicol",
    "threeparttable": "threeparttable",
    "sidewaystable": "rotating", "sideways": "rotating",
    "adjustbox": "adjustbox",
}

# "Missing character: There is no ş (U+015F) in font ec-lmr10!"
#
# Bu SESSIZ bir kayıp: derleme başarılı biter, PDF açılır, harf yoktur.
# En sık sebebi XeLaTeX/LuaLaTeX ile `\usepackage[T1]{fontenc}` kullanmak;
# o birleşim 8 bitlik EC yazı tiplerini yüklüyor ve Türkçeye özgü dört harfin
# (ş, ı, İ, ğ) orada karşılığı yok. Almanca/Fransızcayla ortak olanlar (ü, ö,
# ç) T1 yuvası olduğu için sağ kalıyor, bu yüzden kusur gözden kaçıyor.
#
# 2026-09-03'te ölçüldü, aynı belge üç kez derlendi:
#   pdflatex + fontenc       -> 92 Türkçe harf
#   XeTeX    + fontenc       -> 37   (ş 0, ı 0, İ 0, ğ 0)
#   XeTeX    fontenc olmadan -> 92   (birebir aynı, sıfır uyarı)
_RE_EKSIK_GLIF = re.compile(
    r"Missing character: There is no .+? in font ([^\s!]+)")


def get_hint(message: str, context: str = "") -> tuple[str, dict[str, str]] | None:
    """Hata/uyarı mesajı için (ipucu_kimliği, parametreler); tanınmazsa None.

    ``context``: log_parser'ın yakaladığı "l.42 ..." satırı (tanımsız komutun
    kaynağını çıkarmada kullanılır).
    """
    if not message:
        return None
    m = _RE_ENV_UNDEFINED.search(message)
    if m:
        paket = ORTAM_PAKETI.get(m.group(1))
        if paket:
            return "env_needs_package", {"env": m.group(1), "paket": paket}
        return "env_undefined", {"env": m.group(1)}
    m = _RE_EKSIK_GLIF.search(message)
    if m:
        return "missing_glyph", {"font": m.group(1)}
    for pat, hint_id in _PATTERNS:
        if pat.search(message):
            params: dict[str, str] = {}
            if hint_id == "undefined_control" and context:
                sm = _RE_CTX_SATIRI.search(context)
                if sm:
                    komutlar = _RE_KOMUT.findall(sm.group(1))
                    if komutlar:
                        params["cmd"] = komutlar[-1]
            return hint_id, params
    return None
