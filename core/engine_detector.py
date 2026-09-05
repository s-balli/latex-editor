"""LaTeX derleme motoru algılama ve derlenebilirlik kontrolü."""

import os
import re
import logging

from core.latex_utils import strip_comments

_logger = logging.getLogger("latex_editor.engine_detector")

# "% !TEX program = lualatex" / "% !TEX TS-program = pdflatex" — satır başında
_MAGIC_TEX_PROGRAM = re.compile(
    r"%\s*!\s*TEX\s+(?:TS-)?program\s*=\s*([A-Za-z]+)", re.IGNORECASE
)

# Magic comment'ler dosyanın üst kısmında olur; derin false-positive'leri önlemek için
_MAGIC_SCAN_LINES = 30


def _magic_engine_from_content(content: str) -> str | None:
    """
    İçeriğin üst satırlarındaki '% !TEX program = ...' yönergesinden motoru döndür.

    Dönüş: 'lualatex', 'pdflatex' veya 'xelatex'; tanınmazsa None.
    """
    _map = {
        "pdflatex": "pdflatex",
        "lualatex": "lualatex",
        "luatex": "lualatex",
        "xelatex": "xelatex",
        "xetex": "xelatex",
    }
    for line in content.splitlines()[:_MAGIC_SCAN_LINES]:
        m = _MAGIC_TEX_PROGRAM.match(line.strip())
        if not m:
            continue
        mapped = _map.get(m.group(1).lower())
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


_LUALATEX_PAKETLERI = ("fontspec", "unicode-math", "polyglossia")
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


def _engine_from_tex_signals(clean: str) -> str | None:
    """Yorumları temizlenmiş .tex içeriğindeki paket sinyallerinden motor döndür.

    magic comment ve .cls sinyalleri burada ele alınmaz.
    Dönüş: 'lualatex', 'pdflatex', 'xelatex' veya None.
    """
    paketler = _yuklenen_paketler(clean)
    for ad in _XELATEX_PAKETLERI:
        if ad in paketler:
            return "xelatex"
    for ad in _LUALATEX_PAKETLERI:
        if ad in paketler:
            return "lualatex"
    for ad in _PDFLATEX_PAKETLERI:
        if ad in paketler:
            return "pdflatex"
    return None


def detect_engine(tex_path: str) -> str | None:
    """
    .tex dosyasından ve referans verdiği .cls dosyasından
    uygun derleme motorunu algıla.

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

    # --- 1) .tex dosyasındaki sinyaller ---
    engine = _engine_from_tex_signals(clean)
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
