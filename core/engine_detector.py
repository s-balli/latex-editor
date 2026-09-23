"""LaTeX derleme motoru algılama ve derlenebilirlik kontrolü."""

import os
import re
import logging

from core.input_parser import parse_inputs
from core.latex_utils import strip_comments

_logger = logging.getLogger("latex_editor.engine_detector")

# "% !TEX program = lualatex" / "% !TEX TS-program = pdflatex" — satır başında
_MAGIC_TEX_PROGRAM = re.compile(
    r"%\s*!\s*TEX\s+(?:TS-)?program\s*=\s*([A-Za-z]+)", re.IGNORECASE
)

# Magic comment'ler dosyanın üst kısmında olur; derin false-positive'leri önlemek için
_MAGIC_SCAN_LINES = 30

# Motor adlarının KANONİK karşılığı. TEK KAYNAK.
#
# Aynı bilgi ÜÇ yerde duruyordu ve hiçbir ikisi aynı değildi:
#
#   engine_detector._map        magic comment'teki ad  ->  `pdftex` YOK
#   log_parser._RE_ENGINE_REQ   hata metnindeki ad     ->  `pdfLaTeX` YOK
#   log_parser._engine_map      o adın karşılığı       ->  pdf* HİÇ YOK
#
# Son ikisi AYNI FONKSİYONUN iki ucunda ve birbirine ters: desen `pdfTeX`i
# yakalıyor, eşlem onu tanımıyor, `.get` varsayılanı da `lualatex`. ÖLÇÜLDÜ
# (2026-09-12), desenin KENDİ vaat ettiği beş adın tamamı denendi: dördü doğru,
# `pdfTeX` YANLIŞ. Kullanıcıya "Bu belge pdflatex gerektiriyor" yerine
# "lualatex gerektiriyor" deniyordu, yani gereksinimin tam TERSİ. Gerçek TeX
# Live'da `requires pdfTeX` dört, `requires pdfLaTeX` üç pakette geçiyor
# (asmeconf, asmejour, linegoal, autopdf, hypdestopt, tufte-latex).
#
# Anahtarlar KÜÇÜK harf; her iki tüketici de `.lower()` ile bakıyor.
MOTOR_TAKMA_ADLARI = {
    "pdftex": "pdflatex",
    "pdflatex": "pdflatex",
    "luatex": "lualatex",
    "lualatex": "lualatex",
    "xetex": "xelatex",
    "xelatex": "xelatex",
}


def _magic_engine_from_content(content: str) -> str | None:
    """
    İçeriğin üst satırlarındaki '% !TEX program = ...' yönergesinden motoru döndür.

    Dönüş: 'lualatex', 'pdflatex' veya 'xelatex'; tanınmazsa None.
    """
    for line in content.splitlines()[:_MAGIC_SCAN_LINES]:
        m = _MAGIC_TEX_PROGRAM.match(line.strip())
        if not m:
            continue
        mapped = MOTOR_TAKMA_ADLARI.get(m.group(1).lower())
        if mapped:
            return mapped
    return None


def detect_engine_from_magic_comment(tex_path: str) -> str | None:
    """
    Dosyanın üst satırlarındaki '% !TEX program = ...' yönergesini oku.

    Dönüş: 'lualatex', 'pdflatex', 'xelatex' veya None.
    """
    try:
        with open(tex_path, "r", encoding="utf-8", errors="replace") as f:
            head = "".join(line for _, line in zip(range(_MAGIC_SCAN_LINES), f))
    except OSError as e:
        _logger.warning("Magic comment okunamadı: %s (%s)", tex_path, e)
        return None
    return _magic_engine_from_content(head)


# "% !TEX root = main.tex" — TeXstudio/TeXShop/VS Code LaTeX Workshop uzlaşımı.
# Alt dosyalardan ana belgeyi gösterir; yol alt dosyanın dizinine göredir.
_MAGIC_TEX_ROOT = re.compile(r"%\s*!\s*TEX\s+root\s*=\s*(.+?)\s*$", re.IGNORECASE)


def detect_root(tex_path: str) -> str:
    """'% !TEX root = ...' magic comment'ından kök belgenin mutlak yolunu çözümle.

    Yol bu dosyanın dizinine göredir ('../main.tex' gibi üst dizin çıkışları
    desteklenir). Magic comment yoksa veya kök dosya diskte yoksa boş string.
    Alt dosyadan (\\input ile bölünmüş bölüm dosyaları) ana belgeyi derlemek
    için kullanılır; TeXstudio'daki aynı uzlaşımın karşılığı.
    """
    try:
        with open(tex_path, "r", encoding="utf-8", errors="replace") as f:
            head = "".join(line for _, line in zip(range(_MAGIC_SCAN_LINES), f))
    except OSError:
        return ""
    return detect_root_from_head(head, tex_path)


def detect_root_from_head(head: str, tex_path: str) -> str:
    """detect_root'un içerik-alan varyantı (dosya zaten okunduysa ikinci
    okuma yapma; web backend'i de kullanabilir). ``head``: dosyanın en az
    ilk ``_MAGIC_SCAN_LINES`` satırı (tamamı da olur)."""
    for line in head.splitlines():
        m = _MAGIC_TEX_ROOT.match(line.strip())
        if not m:
            continue
        rel = m.group(1).strip().strip('"').strip("'")
        if not rel:
            continue
        root = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(tex_path)), rel))
        if os.path.isfile(root):
            return root
        _logger.debug("%% !TEX root hedefi bulunamadı: %s → %s", tex_path, rel)
        return ""
    return ""


# Kök belge üst dizinlerde en çok bu kadar kademe yukarıda aranıyor. Tez
# düzeninde bölümler bir (`Chapters/`), bazen iki kademe altta duruyor.
_KOK_ARAMA_KADEMESI = 3


def kok_belge(tex_path: str) -> str:
    r"""``tex_path`` hangi belgenin parçası: derlenen KÖK belgenin yolu.

    Sıra: dosya kendisi derlenebiliyorsa kendisi; `% !TEX root` varsa o;
    yoksa üst dizinlerdeki derlenebilir .tex dosyalarından `\input` /
    `\include` zinciri bu dosyayı içeren ilki. Hiçbiri tutmazsa dosyanın
    kendisi.

    NEDEN. LaTeX dosya yollarını KÖK belgenin dizinine göre çözüyor, alt
    dosyanınkine göre değil. ÖLÇÜLDÜ (2026-09-23, 39 şablon): alt klasörde
    görsel kullanan 6 bölüm dosyasındaki 14 yolun 14'ü yalnız köke göre
    var, bölüme göre hiçbiri; bu 6 dosyanın hiçbirinde `% !TEX root` yok.
    Görsel ekleme ve yol tamamlama bölümün dizinine göre yazıyordu; gerçek
    derlemede görsel de `\input` edilen dosya da bulunamıyordu.

    Dizge değil DOSYA karşılaştırılıyor (`samefile`): macOS'un öntanımlı
    birimi harf duyarsız ve `\input`taki yazım dosya adından farklı olabilir.
    """
    if can_compile(tex_path)[0]:
        return tex_path
    kok = detect_root(tex_path)
    if kok:
        return kok
    dizin = os.path.dirname(os.path.abspath(tex_path))
    for _ in range(_KOK_ARAMA_KADEMESI):
        ust = os.path.dirname(dizin)
        if ust == dizin:
            break
        dizin = ust
        try:
            adlar = sorted(os.listdir(dizin))
        except OSError:
            continue
        for ad in adlar:
            aday = os.path.join(dizin, ad)
            if ad.lower().endswith(".tex") and _zincirde_mi(aday, tex_path):
                return aday
    return tex_path


def derleme_hedefi(tex_path: str) -> tuple[str, str]:
    r"""(derlenecek belge, hata mesajı): ``tex_path`` derlenmek istenince.

    Kendisi derlenebiliyorsa kendisi, değilse kök belgesi (`% !TEX root`
    ya da `\input` zinciri, bkz. kok_belge); ikisi de yoksa ("", sebep).
    TEK KURAL: F5, Ctrl+S ile otomatik derleme ve dosya ağacının "Derle"
    kararı buradan geçiyor.

    Eskiden yalnız `% !TEX root` aranıyordu. ÖLÇÜLDÜ (2026-09-23, tez
    düzeni; derlemdeki bölüm dosyalarının hiçbirinde bu yorum yok): bölümde
    F5 ve Ctrl+S "Bu dosya derlenemez" dedi. Ctrl+S kökten derlemenin hata
    listesini de siliyordu; kullanıcı hatayı düzeltmek için bölüme geçip
    kaydedince liste boşalıyor, düzelttiği dosya derlenmiyordu.
    """
    ok, msg = can_compile(tex_path)
    if ok:
        return tex_path, ""
    kok = kok_belge(tex_path)
    if kok != tex_path:
        return kok, ""
    return "", msg


def _zincirde_mi(kok: str, tex_path: str) -> bool:
    """``kok`` derlenebilir bir belge ve zinciri ``tex_path``i içeriyor mu."""
    try:
        with open(kok, "r", encoding="utf-8", errors="replace") as f:
            icerik = f.read()
    except OSError:
        return False
    if not _check_compilable_content(icerik)[0]:
        return False
    yigin = parse_inputs(icerik, os.path.dirname(os.path.abspath(kok)))
    while yigin:
        ref = yigin.pop()
        yigin.extend(ref.get("children") or [])
        try:
            if os.path.samefile(ref["path"], tex_path):
                return True
        except OSError:
            continue
    return False


# `\documentclass[...,pdftex,...]{...}`: yazar sürücüyü AÇIKÇA söylüyor ve
# sınıf onu grafik/renk paketlerine geçiriyor. ÖLÇÜLDÜ (2026-09-14):
# `template27` (mdpi sınıfı) lualatex'te HİÇ PDF üretmiyor, pdflatex'te
# üretiyor; günlükteki hata `\pdfcolorstack` (xcolor'un pdftex sürücüsü,
# LuaTeX'te o primitif yok). Ad tablosu `MOTOR_TAKMA_ADLARI`dan geliyor,
# ayrıca yazılmıyor. `dvips` gibi tanınmayan sürücüler yok sayılıyor.
_RE_SINIF_SECENEKLERI = re.compile(r'\\documentclass\s*\[([^\]]*)\]')

# pdfTeX'e ÖZGÜ primitifler: belge bunları kullanıyorsa lualatex/xelatex'te
# "Undefined control sequence" ile düşüyor.
#
# "Adı `\pdf` ile başlayan her şey" KURALI YANLIŞ olurdu: korpusta geçen
# `pdftitle`, `pdfauthor`, `pdfkeywords`, `pdfborder` hyperref SEÇENEĞİ,
# komut değil. Liste üç motorun kendisine sorularak çıkarıldı (2026-09-14,
# `\csname <ad>\endcsname` `\relax` mı): korpustaki üç `\pdf...` komutunun
# üçü de yalnız pdflatex'te tanımlı.
#
# `\pdfoutput` BİLEREK dışarıda: yaygın kullanımı `\ifdefined\pdfoutput
# \pdfoutput=1 \fi` biçiminde KORUNMUŞ ve o hâliyle lualatex'te de zararsız,
# yani motor gereksinimi anlamına gelmiyor. Korpustaki tek geçişi de yorum
# satırında. Kalan ikisi `template16/doc/elsdoc-cas.tex`te korumasız
# kullanılıyor ve belge lualatex'te derlenmiyor.
_PDFLATEX_PRIMITIFLERI = ("pdfgentounicode", "pdfglyphtounicode")
_RE_PDFLATEX_PRIMITIF = re.compile(
    r'\\(?:' + '|'.join(_PDFLATEX_PRIMITIFLERI) + r')(?![a-zA-Z])')

# `lua` ile başlayan aile: adı sinyal gibi görünüyor ama liste TAHMİNLE
# değil DERLEMEYLE kesildi. ÖLÇÜLDÜ (2026-09-17, her paket üç motorda da
# denendi; ölçüt PDF'in varlığı değil, günlükte `!` hatası bulunmaması):
# yedisi de YALNIZ lualatex'te derleniyor.
#
# Seçici bunlarda SESSİZ kalıyordu; sessizlik "kullanıcının açılır
# kutudaki seçimi" demek ve o seçim pdflatex'teyse belge hiç derlenmiyor.
# Varsayılan lualatex olduğu için olağan kullanıcı bunu görmüyor, başka
# bir proje için motoru değiştirmiş olan görüyor.
#
# 39 şablonda bu paketlerin hiçbiri geçmiyor; gerekçe korpus değil
# paketin kendisi. Dış işaret olarak TeX Live'da `luacode`u 41,
# `luatexbase`i 37 paket yüklüyor (listede zaten duran `xeCJK` 9,
# `xltxtra` 12).
#
# SINIR: belge paketi `\ifluatex` kolunda yüklüyorsa seçici yine
# lualatex diyor. Aynı açıklık `fontspec` için de var ve zararsız:
# seçilen motor belgenin ZATEN desteklediği motor.
_LUALATEX_PAKETLERI = (
    "fontspec", "unicode-math", "polyglossia",
    "luacode", "luamplib", "lua-ul", "luatextra", "luacolor",
    "luaotfload", "luatexbase",
)
# XeLaTeX'e özgü paketler: mathspec/xeCJK LuaLaTeX'te çalışmaz. fontspec/
# polyglossia her ikisinde de çalıştığından lualatex tarafında kalır.
_XELATEX_PAKETLERI = ("mathspec", "xeCJK", "xltxtra")
_PDFLATEX_PAKETLERI = ("inputenc", "fontenc")

# Paket yüklemesi: SEÇENEKLİ ve VİRGÜLLÜ biçimleri de görüyor.
#
# Eskiden tam dize aranıyordu ("\\usepackage{fontspec}") ve fontspec el
# kitabının kendi örneği olan `\usepackage[no-math]{fontspec}` görülmüyordu.
# pdflatex sinyalleri ise yalnız "{fontenc}" arıyordu, yani seçeneğe
# dayanıklıydı; asimetri pdflatex yönüne çalışıyor ve fontspec pdflatex'te
# DERLENMİYOR. ÖLÇÜLDÜ (2026-09-05, gerçek derlemeyle): altı vakanın beşinde
# yanlış motor seçiliyor ve beşinde de PDF hiç üretilmiyor.
#
#   \usepackage[no-math]{fontspec}          -> None     -> pdflatex -> PDF yok
#   \usepackage{amsmath,fontspec}           -> None     -> pdflatex -> PDF yok
#   \usepackage[T1]{fontenc} + yukarıdaki   -> pdflatex            -> PDF yok
_RE_PAKET_YUKLEME = re.compile(
    r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")


def _yuklenen_paketler(clean: str) -> set[str]:
    """Yorumları temizlenmiş içerikte yüklenen paket adları."""
    adlar: set[str] = set()
    for m in _RE_PAKET_YUKLEME.finditer(clean):
        for ad in m.group(1).split(","):
            ad = ad.strip()
            if ad:
                adlar.add(ad)
    return adlar


def _surucu_secenegi(clean: str) -> str | None:
    r"""``\documentclass`` seçenekleri arasındaki sürücü adından motor."""
    for m in _RE_SINIF_SECENEKLERI.finditer(clean):
        for secenek in m.group(1).split(","):
            motor = MOTOR_TAKMA_ADLARI.get(secenek.strip().lower())
            if motor:
                return motor
    return None


def _engine_from_tex_signals(clean: str) -> str | None:
    r"""Yorumları temizlenmiş .tex içeriğindeki sinyallerden motor döndür.

    magic comment ve .cls sinyalleri burada ele alınmaz.
    Dönüş: 'lualatex', 'pdflatex', 'xelatex' veya None.

    SIRA ÖLÇÜLDÜ (2026-09-14, gerçek derlemeyle). Sürücü seçeneği ve
    pdfTeX primitifi ilk başta en öne konmuştu ("yazar açıkça söylüyor")
    ama çeliştikleri tek durumda YANILIYORLAR:

        \documentclass[pdftex]{article} + \usepackage{fontspec}
            -> lualatex ve xelatex PDF üretiyor, pdflatex ÜRETMİYOR
        \pdfgentounicode=1 + \usepackage{fontspec}
            -> aynı sonuç

    Yani fontspec/mathspec gibi paketler DAHA GÜÇLÜ kısıt: onlar
    olmayanı yapamaz, sürücü seçeneği ise çoğu zaman eski bir alışkanlık.
    İkisi de pdflatex katmanında, ama onun paket listesinden önce.
    """
    paketler = _yuklenen_paketler(clean)
    for ad in _XELATEX_PAKETLERI:
        if ad in paketler:
            return "xelatex"
    for ad in _LUALATEX_PAKETLERI:
        if ad in paketler:
            return "lualatex"
    motor = _surucu_secenegi(clean)
    if motor:
        return motor
    if _RE_PDFLATEX_PRIMITIF.search(clean):
        return "pdflatex"
    for ad in _PDFLATEX_PAKETLERI:
        if ad in paketler:
            return "pdflatex"
    return None


def _zincir_onsozu(content: str, tex_path: str) -> list[str]:
    r"""``\input``/``\include`` zincirindeki dosyaların yorumsuz içeriği.

    Önsözünü ayrı bir dosyaya bölen belge yaygın: `\input{paketler}`.
    Sinyal paketi orada durunca ana dosyada GÖRÜNMÜYOR ve motor yanlış
    seçiliyordu. Zinciri çözen `parse_inputs` uygulamada zaten vardı
    (dosya ağacı ve Referans Denetimi onu kullanıyor); motor algılama ondan
    hiç beslenmiyordu.

    ÖLÇÜLDÜ (2026-09-13, tasarlanmış yer gerçeği, uygulamanın kendi boru
    hattından yani `core/derle.sh` ile). Aynı önsöz iki biçimde yazıldı,
    tek fark `\usepackage` satırının hangi dosyada durduğu:

        \usepackage{mathspec} ALT DOSYADA  -> algı None -> lualatex -> PDF YOK
        \usepackage{mathspec} ANA DOSYADA  -> algı xelatex         -> PDF VAR

    Zincir ana dosyayla BİRLEŞTİRİLİYOR, ayrı bir aşama olarak
    sorulmuyor: `\usepackage[T1]{fontenc}` ana dosyada, `fontspec` alt
    dosyadayken "önce ana dosya" sırası pdflatex'te kalır ve o belge
    pdflatex'te derlenmez (aynı çakışma kaynakta 2026-09-05'te ölçülmüş).
    Önsöz kaç dosyaya bölünürse bölünsün TEK önsözdür.

    Gerçek korpusta (39 şablonun 57 ana belgesi) bu birleşim tek bir
    belgenin cevabını değiştiriyor (template32, önsözü `packages.tex`e
    bölünmüş: None -> pdflatex) ve o belge yeni motorla derleniyor.
    """
    parcalar = []
    yigin = parse_inputs(content, os.path.dirname(os.path.abspath(tex_path)))
    while yigin:
        ref = yigin.pop()
        yigin.extend(ref.get("children") or [])
        try:
            with open(ref["path"], "r", encoding="utf-8",
                      errors="replace") as f:
                parcalar.append(strip_comments(f.read()))
        except OSError as e:
            _logger.warning("Motor algılama, alt dosya okunamadı: %s (%s)",
                            ref["path"], e)
    return parcalar


def detect_engine(tex_path: str) -> str | None:
    """
    .tex dosyasından, ``\\input`` zincirinden ve referans verdiği .cls
    dosyasından uygun derleme motorunu algıla.

    Dönüş: 'lualatex', 'pdflatex', 'xelatex' veya None (belirsiz — pdflatex varsayılmalı)
    """
    try:
        with open(tex_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        _logger.warning("Motor algılama, dosya okunamadı: %s (%s)", tex_path, e)
        return None

    # --- 0) % !TEX program magic comment (en yüksek öncelik) ---
    magic = _magic_engine_from_content(content)
    if magic:
        return magic

    clean = strip_comments(content)

    # --- 1) .tex dosyasındaki VE \input zincirindeki sinyaller ---
    engine = _engine_from_tex_signals(
        "\n".join([clean] + _zincir_onsozu(content, tex_path)))
    if engine:
        return engine

    # --- 2) .cls dosyası kontrolü ---
    docclass = _extract_documentclass(clean)
    if docclass:
        cls_dir = os.path.dirname(os.path.abspath(tex_path))
        cls_path = os.path.join(cls_dir, docclass + ".cls")
        if os.path.isfile(cls_path):
            return _detect_from_cls(cls_path)

    return None


def detect_engine_from_content(content: str, cls_content: str | None = None) -> str | None:
    """
    Dosya içeriğinden motor algıla (dosya yolu olmadan).
    Web backend endpoint'i için.
    """
    # --- 0) % !TEX program magic comment (en yüksek öncelik) ---
    magic = _magic_engine_from_content(content)
    if magic:
        return magic

    clean = strip_comments(content)

    # .tex sinyalleri
    engine = _engine_from_tex_signals(clean)
    if engine:
        return engine

    # .cls içeriği verildiyse kontrol et
    if cls_content:
        engine = _detect_from_cls_content(cls_content)
        if engine:
            return engine

    return None


def can_compile(path: str) -> tuple[bool, str]:
    """
    Dosyanın doğrudan derlenip derlenemeyeceğini kontrol et.

    Dönüş: (True, "") veya (False, "sebep mesajı")
    """
    _, ext = os.path.splitext(path.lower())
    if ext not in (".tex",):
        return False, f"Bu dosya derlenemez (.{ext.lstrip('.')} dosyaları bağımsız derlenemez)."

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        _logger.warning("Derlenebilirlik kontrolü, dosya okunamadı: %s (%s)", path, e)
        return False, "Dosya okunamadı."

    return _check_compilable_content(content)


def can_compile_from_content(content: str, filename: str = "") -> tuple[bool, str]:
    """
    Dosya içeriğinden derlenebilirlik kontrolü (dosya yolu olmadan).
    Web backend endpoint'i için.
    """
    if filename:
        _, ext = os.path.splitext(filename.lower())
        if ext not in (".tex", ""):
            return False, f"Bu dosya derlenemez (.{ext.lstrip('.')} dosyaları bağımsız derlenemez)."

    return _check_compilable_content(content)


def _check_compilable_content(content: str) -> tuple[bool, str]:
    """Yorumları temizlenmiş içerikte \\begin{document} ara."""
    clean = strip_comments(content)
    if "\\begin{document}" not in clean:
        return False, "Bu dosya derlenemez, \\begin{document} içermiyor (başka bir dosyadan çağrılan alt dosya olabilir)."
    return True, ""


def _extract_documentclass(content: str) -> str | None:
    """\\documentclass[...]{ClassName} -> ClassName"""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("%"):
            continue
        m = re.search(r"\\documentclass(?:\[.*?\])?\{(\w[\w-]*)\}", stripped)
        if m:
            return m.group(1)
    return None


def _detect_from_cls(cls_path: str) -> str | None:
    """ .cls dosyasından motor gereksinimini algıla."""
    try:
        with open(cls_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        _logger.debug(".cls okunamadı (normal): %s (%s)", cls_path, e)
        return None
    return _detect_from_cls_content(content)


def _detect_from_cls_content(content: str) -> str | None:
    """Yorumları temizlenmiş .cls içeriğinden motor algıla."""
    clean = strip_comments(content)

    # XeLaTeX sinyalleri
    xelatex_signals = [
        "requires XeLaTeX",
        "\\RequireXeTeX",
    ]
    for signal in xelatex_signals:
        if signal in clean:
            return "xelatex"

    # LuaLaTeX sinyalleri
    lualatex_signals = [
        "requires LuaLaTeX",
        "requires LuaTeX",
        "\\RequireLuaTeX",
    ]
    for signal in lualatex_signals:
        if signal in clean:
            return "lualatex"

    # fontspec koşulsuz yüklemesi → LuaLaTeX. Seçenekli biçim de sayılıyor:
    # `.cls` dosyalarında `\RequirePackage[no-math]{fontspec}` yaygın.
    if "fontspec" in _yuklenen_paketler(clean):
        return "lualatex"

    # pdfLaTeX sinyalleri
    if "\\pdfmapfile" in clean:
        return "pdflatex"

    return None
