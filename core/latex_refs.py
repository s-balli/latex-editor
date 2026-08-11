"""\\ref için \\label, \\cite için .bib anahtar toplama (doküman-farkında tamamlama).

Editörün \\ref{ / \\cite{ tamamlaması için kullanılır. Sadece okur/yazar dosya,
Qt bağımlılığı yok (tıpkı input_parser gibi).
"""

import logging
import os
import re

from core.input_parser import parse_inputs
from core.latex_utils import strip_comments

_logger = logging.getLogger("latex_editor.latex_refs")

_RE_LABEL = re.compile(r'\\label\s*\{([^}]+)\}')
_RE_BIBENTRY = re.compile(r'@\w+\s*\{\s*([^,\s}]+)\s*,')
_RE_ADDBIB = re.compile(r'\\addbibresource\s*\{([^}]+\.bib)\}')
_RE_BIBLIO = re.compile(r'\\bibliography\s*\{([^}]+)\}')

# Çocuk dosya (\\input zinciri) label önbelleği: path -> (mtime, [labels])
_label_file_cache: dict[str, tuple[float, list[str]]] = {}
# .bib anahtar önbelleği: bib_path -> (mtime, [keys])
_bib_cache: dict[str, tuple[float, list[str]]] = {}


def _base_dir(base_path: str) -> str:
    return os.path.dirname(os.path.abspath(base_path)) if base_path else os.getcwd()


def _extract_labels(text: str) -> list[str]:
    """Metinden (yorumları strip ederek) \\label anahtarlarını döndür."""
    return [m.group(1).strip() for m in _RE_LABEL.finditer(strip_comments(text))]


def _flatten_input_paths(content: str, base_dir: str) -> list[str]:
    """parse_inputs ağcını düz dosya-yolu listesine indir."""
    paths: list[str] = []

    def walk(nodes):
        for n in nodes:
            paths.append(n['path'])
            walk(n.get('children', []))

    try:
        walk(parse_inputs(content, base_dir))
    except Exception:
        _logger.warning("input zinciri çözülemedi (base: %s)", base_dir, exc_info=True)
    return paths


def collect_labels(content: str, base_path: str) -> list[str]:
    """Mevcut dosya (``content``) + \\input zincirindeki tüm \\label anahtarları.

    Canlı ``content`` her zaman taze değerlendirilir; zincirdeki çocuk dosyalar
    mtime'a göre önbelleklenir (değişmeyen dosya tekrar okunmaz). Sıralı + tekil.
    """
    labels = set(_extract_labels(content))
    bdir = _base_dir(base_path)
    for path in _flatten_input_paths(content, bdir):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        cached = _label_file_cache.get(path)
        if cached and cached[0] == mtime:
            file_labels = cached[1]
        else:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    file_labels = _extract_labels(f.read())
            except OSError:
                continue
            _label_file_cache[path] = (mtime, file_labels)
        labels.update(file_labels)
    return sorted(labels)


def _find_bib_path(content: str, base_path: str) -> str:
    """\\addbibresource{X.bib} / \\bibliography{X} ile referans verilen .bib yolu."""
    bdir = _base_dir(base_path)
    for pat in (_RE_ADDBIB, _RE_BIBLIO):
        m = pat.search(strip_comments(content))
        if not m:
            continue
        name = m.group(1).strip()
        if not name.endswith('.bib'):
            name += '.bib'
        cand = os.path.join(bdir, name)
        if os.path.isfile(cand):
            return cand
    return ""


def collect_cite_keys(content: str, base_path: str) -> list[str]:
    """Referans verilen .bib dosyasındaki tüm giriş anahtarları (mtime önbellekli).

    .bib bulunamazsa boş liste.
    """
    bib_path = _find_bib_path(content, base_path)
    if not bib_path:
        return []
    try:
        mtime = os.path.getmtime(bib_path)
    except OSError:
        return []
    cached = _bib_cache.get(bib_path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(bib_path, 'r', encoding='utf-8', errors='replace') as f:
            keys = sorted({m.group(1).strip() for m in _RE_BIBENTRY.finditer(f.read())})
    except OSError:
        return []
    _bib_cache[bib_path] = (mtime, keys)
    return keys
