"""LaTeX derleme motoru algılama ve derlenebilirlik kontrolü."""

import os
import re
import logging

from core.latex_utils import strip_comments

_logger = logging.getLogger("latex_editor.engine_detector")


def detect_engine(tex_path: str) -> str | None:
    """
    .tex dosyasından ve referans verdiği .cls dosyasından
    uygun derleme motorunu algıla.

    Dönüş: 'lualatex', 'pdflatex' veya None (belirsiz — pdflatex varsayılmalı)
    """
    try:
        with open(tex_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        _logger.warning("Motor algılama — dosya okunamadı: %s — %s", tex_path, e)
        return None

    clean = strip_comments(content)

    # --- 1) .tex dosyasındaki sinyaller ---

    # Güçlü LuaLaTeX sinyalleri
    if "\\usepackage{fontspec}" in clean:
        return "lualatex"
    if "\\usepackage{unicode-math}" in clean:
        return "lualatex"
    if "\\usepackage{polyglossia}" in clean:
        return "lualatex"

    # Güçlü pdfLaTeX sinyalleri
    if "{inputenc}" in clean:
        return "pdflatex"
    if "{fontenc}" in clean:
        return "pdflatex"

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
    clean = strip_comments(content)

    # LuaLaTeX sinyalleri (.tex)
    if "\\usepackage{fontspec}" in clean:
        return "lualatex"
    if "\\usepackage{unicode-math}" in clean:
        return "lualatex"
    if "\\usepackage{polyglossia}" in clean:
        return "lualatex"

    # pdfLaTeX sinyalleri (.tex)
    if "{inputenc}" in clean:
        return "pdflatex"
    if "{fontenc}" in clean:
        return "pdflatex"

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
        _logger.warning("Derlenebilirlik kontrolü — dosya okunamadı: %s — %s", path, e)
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
        return False, "Bu dosya derlenemez — \\begin{document} içermiyor (başka bir dosyadan çağrılan alt dosya olabilir)."
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
        _logger.debug(".cls okunamadı (normal): %s — %s", cls_path, e)
        return None
    return _detect_from_cls_content(content)


def _detect_from_cls_content(content: str) -> str | None:
    """Yorumları temizlenmiş .cls içeriğinden motor algıla."""
    clean = strip_comments(content)

    # LuaLaTeX sinyalleri
    lualatex_signals = [
        "requires LuaLaTeX",
        "requires LuaTeX",
        "requires XeLaTeX",
        "\\RequireLuaTeX",
        "\\RequireXeTeX",
    ]
    for signal in lualatex_signals:
        if signal in clean:
            return "lualatex"

    # fontspec koşulsuz yüklemesi → LuaLaTeX
    if "\\RequirePackage{fontspec}" in clean:
        return "lualatex"

    # pdfLaTeX sinyalleri
    if "\\pdfmapfile" in clean:
        return "pdflatex"

    return None
