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
    (re.compile(r"destination with the same identifier"), "duplicate_label"),
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
