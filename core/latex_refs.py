"""\\ref için \\label, \\cite için .bib anahtar toplama (doküman-farkında tamamlama).

Editörün \\ref{ / \\cite{ tamamlaması için kullanılır. Sadece okur/yazar dosya,
Qt bağımlılığı yok (tıpkı input_parser gibi).
"""

import logging
import os
import re
from dataclasses import dataclass, field

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


# --- \input / \include tamamlama: projedeki .tex dosyaları ---

def collect_input_paths(base_path: str) -> list[str]:
    """\\input{ / \\include{ tamamlaması için projedeki .tex dosyaları.

    Ana dosyanın dizinini ve alt dizinlerini tarar; kök dizine göre .tex
    uzantısı soyulmuş göreli yollar döndürür (\include uzantı kabul etmez,
    \input uzantısızı da bulur; ikisi için de uzantısız öneri derlenir).
    Gizli dizinlere inilmez; ana dosyanın kendisi listede olmaz (kendini
    \\input etmek döngü olur). Yol ayracı her platformda LaTeX'in beklediği
    '/'tir.
    """
    bdir = _base_dir(base_path)
    base_name = os.path.basename(os.path.abspath(base_path))
    rels: list[str] = []
    for root, dirs, files in os.walk(bdir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fn in files:
            if not fn.endswith('.tex'):
                continue
            rel = os.path.relpath(os.path.join(root, fn), bdir)
            if rel == base_name:
                continue
            rels.append(rel[:-4].replace(os.sep, '/'))
    return sorted(rels)


# Grafik uzantıları: derleyicinin/graphicx'in kabul ettiği yaygın biçimler
# (uygulamanın sürükle-bırak/yapıştır da desteklediği küme).
_IMG_EXTS = (".png", ".jpg", ".jpeg", ".pdf", ".eps")


def collect_image_paths(base_path: str) -> list[str]:
    """\\includegraphics{ tamamlaması için projedeki resim dosyaları.

    Ana dosyanın dizinini ve alt dizinlerini tarar (media/ vb. dahil); kök
    dizine göre, uzantısı KORUNMUŞ göreli yollar döndürür — görsel ekleme
    (sürükle-bırak/panodan yapıştır) da aynı kurala yazar. Ana dosyanın kendi
    derleme çıktısı (main.pdf) önerilmez; gizli dizinlere inilmez. Yol ayracı
    her platformda LaTeX'in beklediği '/'tir.
    """
    bdir = _base_dir(base_path)
    base_pdf = os.path.splitext(os.path.basename(os.path.abspath(base_path)))[0].lower() + ".pdf"
    rels: list[str] = []
    for root, dirs, files in os.walk(bdir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fn in files:
            if not fn.lower().endswith(_IMG_EXTS) or fn.lower() == base_pdf:
                continue
            rel = os.path.relpath(os.path.join(root, fn), bdir)
            rels.append(rel.replace(os.sep, '/'))
    return sorted(rels)


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


# --- Alt+tık ile tanıma git: anahtarın (dosya, satır) konumu ---

def _label_line_in(text: str, key: str) -> int | None:
    """\\label{key}'in 1-bazlı satır numarası (yorumlar strip edilmiş metinde).

    strip_comments satır sayısını korur (\\n'leri silmez), bu yüzden strip
    edilmiş metindeki satır no'su orijinalle aynıdır. Yorum içindeki \\label
    doğru şekilde yok sayılır.
    """
    pat = re.compile(r'\\label\s*\{\s*' + re.escape(key) + r'\s*\}')
    for i, ln in enumerate(strip_comments(text).split('\n'), start=1):
        if pat.search(ln):
            return i
    return None


def find_label_location(content: str, base_path: str, key: str) -> tuple[str, int] | None:
    """\\label{key}'in (dosya yolu, 1-bazlı satır) konumu.

    Önce mevcut ``content``'te, sonra \\input zincirindeki çocuk dosyalarda arar.
    Bulunamazsa None. Alt+tık ile \\ref tanıma git için kullanılır.
    """
    loc = _label_line_in(content, key)
    if loc is not None:
        return (base_path, loc)
    bdir = _base_dir(base_path)
    for path in _flatten_input_paths(content, bdir):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                t = f.read()
        except OSError:
            continue
        loc = _label_line_in(t, key)
        if loc is not None:
            return (path, loc)
    return None


def find_cite_location(content: str, base_path: str, key: str) -> tuple[str, int] | None:
    """\\cite{key} için .bib girişinin (dosya yolu, 1-bazlı satır) konumu.

    .bib bulunamaz veya anahtar yoksa None. Alt+tık ile \\cite tanıma git için.
    """
    bib_path = _find_bib_path(content, base_path)
    if not bib_path:
        return None
    pat = re.compile(r'@\w+\s*\{\s*' + re.escape(key) + r'\s*,')
    try:
        with open(bib_path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return None
    for i, ln in enumerate(text.split('\n'), start=1):
        if pat.search(ln):
            return (bib_path, i)
    return None


# --- \bibitem (thebibliography, el ile kaynakça): \cite için .bib yoksa fallback ---

def _bibitem_line_in(text: str, key: str) -> int | None:
    """\\bibitem{key}'in 1-bazlı satır numarası (yorumlar strip edilmiş metinde).

    \\bibitem[label]{key} opsiyonel etiketini de destekler.
    """
    pat = re.compile(r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{\s*' + re.escape(key) + r'\s*\}')
    for i, ln in enumerate(strip_comments(text).split('\n'), start=1):
        if pat.search(ln):
            return i
    return None


def find_bibitem_location(content: str, base_path: str, key: str) -> tuple[str, int] | None:
    """\\bibitem{key}'in (thebibliography) (dosya yolu, satır) konumu.

    El ile kaynakça kullanan (.bib'siz) belgelerde \\cite tanıma git için
    fallback. Önce mevcut content'te, sonra \\input zincirinde arar.
    """
    loc = _bibitem_line_in(content, key)
    if loc is not None:
        return (base_path, loc)
    bdir = _base_dir(base_path)
    for path in _flatten_input_paths(content, bdir):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                t = f.read()
        except OSError:
            continue
        loc = _bibitem_line_in(t, key)
        if loc is not None:
            return (path, loc)
    return None


# .bib girdisinden makalede \cite edildiği yere (ters yön) git
_RE_CITEUSE = re.compile(
    r'\\(?:cite|citep|citet|citeauthor|citeyear|citealp|parencite|textcite|nocite)'
    r'\s*(?:\[[^\]]*\]\s*)*\{([^}]*)\}'
)


def find_cite_usage(bib_path: str, key: str) -> tuple[str, int] | None:
    """\\bib girdisi ``key``'in makalede \\cite edildiği (tex yolu, satır) konumu.

    .bib ile aynı dizin ağacındaki .tex dosyalarını tarar; ilk eşleşmeyi döndürür.
    Alt+tık ile .bib'ten makaledeki atıfa gitmek için (ters yön).
    """
    bdir = os.path.dirname(os.path.abspath(bib_path)) if bib_path else ""
    if not bdir:
        return None
    for root, dirs, files in os.walk(bdir):
        dirs.sort()
        for fn in sorted(files):
            if not fn.endswith('.tex'):
                continue
            path = os.path.join(root, fn)
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    text = f.read()
            except OSError:
                continue
            for i, ln in enumerate(strip_comments(text).split('\n'), start=1):
                for m in _RE_CITEUSE.finditer(ln):
                    keys = [k.strip() for k in m.group(1).split(',')]
                    if key in keys:
                        return (path, i)
    return None


# --- Referans denetimi: tanımsız \ref / \cite, kullanılmayan .bib girdileri ---

_RE_REFUSE = re.compile(
    r'\\(?:ref|eqref|pageref|autoref|nameref|vref|cref|Cref)\s*\{([^}]*)\}'
)
_RE_BIBITEM = re.compile(r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}')
_RE_NOCITE_ALL = re.compile(r'\\nocite\s*\{\*\}')


@dataclass
class RefAudit:
    """Referans denetimi sonucu — tüm listeler sıralı ve tekil.

    undefined_refs:  kullanılan ama \\label'i (doküman + \\input zinciri) olmayan
                     \\ref ailesi anahtarları
    undefined_cites: kullanılan ama .bib girdisi de \\bibitem'i de olmayan
                     \\cite anahtarları
    unused_bib_keys: .bib'te olup hiç \\cite edilmemiş girdi anahtarları
                     (\\nocite{*} varsa boş — her şey kullanılmış sayılır)
    unused_labels:   tanımlı olup hiç \\ref ailesiyle kullanılmayan \\label
                     anahtarları (bilgi amaçlı; "ilerde lazım" label'ları da
                     yakalar, bu yüzden hata değil öneri olarak sunulur)
    """
    undefined_refs: list[str] = field(default_factory=list)
    undefined_cites: list[str] = field(default_factory=list)
    unused_bib_keys: list[str] = field(default_factory=list)
    unused_labels: list[str] = field(default_factory=list)


def _chain_texts(content: str, base_path: str) -> list[tuple[str, str]]:
    """\\input zincirindeki çocuk dosyaların (yol, yorumları soyulmuş metin) listesi."""
    bdir = _base_dir(base_path)
    out: list[tuple[str, str]] = []
    for path in _flatten_input_paths(content, bdir):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                out.append((path, strip_comments(f.read())))
        except OSError:
            continue
    return out


def _audit_texts(content: str, base_path: str) -> list[str]:
    """Denetim metinleri: mevcut içerik + \\input zinciri (yorumlar soyulmuş)."""
    return [strip_comments(content)] + [t for _p, t in _chain_texts(content, base_path)]


def audit_references(content: str, base_path: str) -> RefAudit:
    """Dokümanı (ve \\input zincirini) referans açısından denetle.

    Derlemeden bağımsız hızlı lokal analiz: kırık çapraz referanslar ve
    kullanılmayan kaynakça girdileri. ``content`` canlı editör içeriğidir;
    zincirdeki çocuk dosyalar diskten okunur.
    """
    texts = _audit_texts(content, base_path)
    used_refs: set[str] = set()
    used_cites: set[str] = set()
    nocite_all = False
    for t in texts:
        for m in _RE_REFUSE.finditer(t):
            used_refs.update(k.strip() for k in m.group(1).split(',') if k.strip())
        for m in _RE_CITEUSE.finditer(t):
            used_cites.update(k.strip() for k in m.group(1).split(',') if k.strip())
        if _RE_NOCITE_ALL.search(t):
            nocite_all = True

    defined_labels = set(collect_labels(content, base_path))
    bibitem_keys = {
        m.group(1).strip() for t in texts for m in _RE_BIBITEM.finditer(t)
    }
    bib_keys = set(collect_cite_keys(content, base_path))

    return RefAudit(
        undefined_refs=sorted(used_refs - defined_labels),
        undefined_cites=sorted(used_cites - bib_keys - bibitem_keys),
        unused_bib_keys=[] if nocite_all else sorted(bib_keys - used_cites),
        unused_labels=sorted(defined_labels - used_refs),
    )


def find_key_usage(content: str, base_path: str, key: str, family: str) -> tuple[str, int] | None:
    """``family`` ('ref' veya 'cite') komutlarında ``key``'in ilk kullanım konumu.

    Tanımsız \\ref/\\cite bulgusuna tıklayınca kullanıldığı yere atlamak için.
    Ana dosyanın canlı içeriği ve \\input zinciri taranır; yorumlar soyulur ama
    satır numaraları korunur (strip_comments satır sayısını bozmaz). Çok
    anahtarlı kullanımda (\\cref{a,b}) segment segment eşleşilir.
    Bulunamazsa None.
    """
    pat = _RE_REFUSE if family == "ref" else _RE_CITEUSE
    entries = [(base_path, strip_comments(content))] + _chain_texts(content, base_path)
    for path, t in entries:
        for i, ln in enumerate(t.split('\n'), start=1):
            for m in pat.finditer(ln):
                keys = [k.strip() for k in m.group(1).split(',')]
                if key in keys:
                    return (path, i)
    return None


# --- \label yeniden adlandırma (F2): doküman + \input zinciri ---

def input_chain_paths(content: str, base_path: str) -> list[str]:
    """\\input zincirindeki çocuk dosya yolları (flat, ana dosya hariç)."""
    return _flatten_input_paths(content, _base_dir(base_path))


def label_rename_spans(text: str, old: str) -> list[tuple[int, int]]:
    """``text`` içinde ``old``'a eşit \\label argümanı / \\ref segmentinin karakter
    aralıkları.

    Aralıklar tek satır içinde kalır (anahtarlar satır kırılmaz); GUI bu
    aralıkları seçip değiştirerek undo geçmişini korur. \\label{oldx},
    ``old='old'`` ile eşleşmez (segment birebir karşılaştırılır).
    """
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r'\\label\s*\{([^}]*)\}', text):
        a, b = m.span(1)
        if text[a:b].strip() == old:
            spans.append((a, b))
    for m in _RE_REFUSE.finditer(text):
        arg_a, _ = m.span(1)
        arg = m.group(1)
        off = 0
        for part in arg.split(','):
            if part.strip() == old:
                s = arg_a + off + (len(part) - len(part.lstrip()))
                spans.append((s, s + len(old)))
            off += len(part) + 1  # virgülü atla
    return spans


def rename_label_in_text(text: str, old: str, new: str) -> str:
    """``old`` anahtarının tüm \\label ve \\ref ailesi kullanımlarını ``new`` yap.

    Değişiklik yoksa aynı metni döndürür. Diskteki dosyalar için toplu metin
    dönüşümü; açık editör arabellekleri için GUI aralık bazlı değiştirme yapar
    (bkz. label_rename_spans).
    """
    out = text
    for s, e in sorted(label_rename_spans(text, old), reverse=True):
        out = out[:s] + new + out[e:]
    return out
