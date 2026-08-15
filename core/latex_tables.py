"""LaTeX tablo üretimi ve hizalama — saf fonksiyonlar (Qt bağımlılığı yok).

Tablo sihirbazının (GUI) ve `Tabloyu Hizala` komutunun çekirdeği. Web
sürümünde de aynen kullanılabilir.
"""

import csv
import re
import unicodedata
from dataclasses import dataclass

# --- Hücre kaçışı ---

# & satır ayracı, % yorum başlatır, _/# alt çizli/düz moduna sokar, $ math açar.
# Ters eğik çizgi KAÇIRILMAZ: hücreye \alpha, \textbf vb. bilinçli LaTeX yazma
# serbestliği korunur.
_ESCAPE_RE = re.compile(r"([%&_#$])")


def escape_cell(text: str) -> str:
    """Hücre metnindeki LaTeX özel karakterlerini kaçır (ters eğik çizgi hariç)."""
    return _ESCAPE_RE.sub(r"\\\1", text.strip())


_UNESCAPE_RE = re.compile(r"\\([%&_#$])")


def unescape_cell(text: str) -> str:
    """escape_cell'in tersi: \\% → % vb. (grid'e yüklerken kullanılır).

    \\alpha gibi komutlar dokunulmaz; yalnız kaçırılmış özel karakterler açılır.
    """
    return _UNESCAPE_RE.sub(r"\1", text.strip())


# --- Kolon belirtimi ---


def build_col_spec(aligns: list[str], vertical_lines: bool,
                   environment: str = "tabular") -> str:
    """Hizalama listesinden kolon belirtimi üret.

    aligns öğeleri 'l' | 'c' | 'r' | 'p' (p = p{3cm}; tabularx ortamında X'e
    dönüşür). vertical_lines True ise kolonlar arası/kenarlarda |.
    """
    tokens = []
    for a in aligns:
        if a == "p":
            tokens.append("X" if environment == "tabularx" else "p{3cm}")
        else:
            tokens.append(a)
    if vertical_lines:
        return "|" + "|".join(tokens) + "|"
    return "".join(tokens)


@dataclass
class TableOptions:
    """Tablo üretimi seçenekleri (GUI dialog değerleri)."""
    environment: str = "tabular"      # tabular | tabularx | longtable
    booktabs: bool = True             # toprule/midrule/bottomrule (yoksa \hline)
    header_row: bool = True           # ilk satır başlık (kural ile ayrılır)
    vertical_lines: bool = False      # kolon çizgileri (|)
    wrap_table: bool = True           # \begin{table} + caption + label kılıfı
    caption: str = ""
    label: str = ""
    indent: str = "    "
    extra_args: str = "[htbp]"        # table kılıfı konum parametresi


def build_tabular(rows: list[list[str]], aligns: list[str],
                  opts: TableOptions | None = None) -> str:
    """Hücre satırlarından tam LaTeX tablo bloğu üret.

    Hücreler escape_cell ile kaçırılır (kullanıcı \alpha gibi komutlar
    yazabilir; bunlar korunur). Satır sayısı 0 ise boş string.
    """
    if not rows:
        return ""
    opts = opts or TableOptions()
    ncols = len(rows[0])
    aligns = (aligns + ["c"] * ncols)[:ncols]

    top = "\\toprule" if opts.booktabs else "\\hline"
    mid = "\\midrule" if opts.booktabs else "\\hline"
    bottom = "\\bottomrule" if opts.booktabs else "\\hline"

    col_spec = build_col_spec(aligns, opts.vertical_lines, opts.environment)
    if opts.environment == "tabularx":
        begin = f"\\begin{{tabularx}}{{\\linewidth}}{{{col_spec}}}"
    else:
        begin = f"\\begin{{{opts.environment}}}{{{col_spec}}}"

    ind = opts.indent
    lines = [begin, f"{ind}{top}"]
    for i, row in enumerate(rows):
        cells = [escape_cell(c) for c in row]
        lines.append(f"{ind}{' & '.join(cells)} \\\\")
        if opts.header_row and i == 0 and len(rows) > 1:
            lines.append(f"{ind}{mid}")
    lines.append(f"{ind}{bottom}")
    lines.append(f"\\end{{{opts.environment}}}")
    body = "\n".join(lines)

    # longtable yüzen ortam İÇİNDE olamaz; kılıf yalnız tabular/tabularx'te
    if not opts.wrap_table or opts.environment == "longtable":
        return body

    head = [f"\\begin{{table}}{opts.extra_args}", f"{ind}\\centering"]
    if opts.caption:
        head.append(f"{ind}\\caption{{{escape_cell(opts.caption)}}}")
    if opts.label:
        head.append(f"{ind}\\label{{{opts.label}}}")
    return "\n".join(head) + "\n" + body + "\n\\end{table}"


# --- Etiket önerisi ---

_TR_UPPER = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def slugify(text: str) -> str:
    """Metni label için güvenli slug'a indir (ASCII, tire ayraçlı)."""
    t = unicodedata.normalize("NFKD", text.translate(_TR_UPPER))
    t = t.encode("ascii", "ignore").decode("ascii")
    return "-".join(p for p in re.split(r"[^A-Za-z0-9]+", t) if p).lower()


def suggest_label(existing: list[str], caption: str = "",
                  prefix: str = "tab:") -> str:
    """Çakışmayan label öner: 'tab:caption-slugu', gerekirse -2, -3..."""
    base = prefix + (slugify(caption) or "tablo")
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


# --- CSV içe aktarma ---


def csv_to_rows(path: str) -> list[list[str]]:
    """CSV dosyasını hücre satırlarına oku (ayraç: , ; veya sekme, otomatik).

    Excel'in UTF-8 BOM'u temizlenir; tamamen boş satırlar atılır.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = None
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error:
            counts = {c: sample.count(c) for c in ",;\t"}
            delim = max(counts, key=counts.get)
        return [row for row in csv.reader(f, delimiter=delim)
                if any(c.strip() for c in row)]


# --- Mevcut tabloyu bulma / hizalama ---

_RE_BEGIN = re.compile(r"\\begin\{(tabular\*?|tabularx|longtable)\}")
_RE_RULE = re.compile(
    r"^\s*\\(toprule|midrule|bottomrule|hline|endhead|endfoot|endfirsthead)\b")
_RE_SPLIT_CELLS = re.compile(r"(?<!\\)&")


def _row_cells(line: str) -> list[str] | None:
    r"""Satır tablo veri satırıysa hücrelerini, değilse None döndür.

    Kural satırları (\toprule vb.), \end satırı, yorum ve boş satırlar None.
    """
    s = line.strip()
    if not s or s.startswith("%") or _RE_RULE.match(s) or s.startswith("\\end{"):
        return None
    cells = [c.strip() for c in _RE_SPLIT_CELLS.split(s.rstrip("\\").strip())]
    return None if cells == [""] else cells


def parse_tabular_at(text: str, pos: int) -> dict | None:
    """``pos`` (karakter offset) bir tabular ortamı içindeyse blok bilgisi döndür.

    Dönüş: {start, end, env, col_spec, rows} — rows hücre listeleri (kaçışlar
    OLDUĞU GİBİ, ham); kural, boş ve yorum satırları atılır. İç içe ortamlarda
    pos'u içeren en geç başlayan (en içteki) blok seçilir.
    """
    best = None
    for m in _RE_BEGIN.finditer(text):
        end_m = re.search(r"\\end\{" + re.escape(m.group(1)) + r"\}", text[m.end():])
        if not end_m:
            continue
        start, end = m.start(), m.end() + end_m.end()
        if start <= pos <= end and (best is None or start > best[1]):
            best = (m, start, end)
    if best is None:
        return None
    m, start, end = best
    env = m.group(1)
    spec_at = m.end()
    if env == "tabularx":
        # \begin{tabularx}{\linewidth}{spec} — ilk küme parantezi genişlik
        # argümanıdır; kolon belirtimi ikincisidir.
        width_m = re.match(r"\s*\{[^{}]*\}", text[spec_at:end])
        if width_m:
            spec_at += width_m.end()
    spec_m = re.match(r"\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", text[spec_at:end])
    col_spec = spec_m.group(1)[1:-1] if spec_m else ""

    rows = []
    body_start = spec_at + (spec_m.end() if spec_m else 0)
    for raw in text[body_start:end].split("\n"):
        cells = _row_cells(raw)
        if cells is not None:
            rows.append(cells)
    return {"start": start, "end": end, "env": env, "col_spec": col_spec,
            "rows": rows}


def parse_first_tabular(text: str) -> dict | None:
    """Metindeki (yapıştırılan koddaki) ilk tabular bloğunu bul.

    Sihirbazın 'Koddan Yükle' akışı için: parse_tabular_at pozisyon ister;
    burada ilk \\begin{tabular...} konumu kullanılır.
    """
    m = _RE_BEGIN.search(text)
    if not m:
        return None
    return parse_tabular_at(text, m.start() + 1)


def extract_caption_label(text: str) -> tuple[str, str]:
    """Metindeki \\caption{...} ve \\label{tab:...} değerlerini döndür (yoksa boş).

    Kaption kaçışları açılır (unescape_cell); label oldugu gibi alınır.
    """
    cap = re.search(r"\\caption\{([^{}]*)\}", text)
    lab = re.search(r"\\label\{(tab:[^{}]*)\}", text)
    return (unescape_cell(cap.group(1)) if cap else "",
            lab.group(1) if lab else "")


def format_tabular(text: str, pos: int) -> str | None:
    """``pos`` içindeki tabular bloğunun hücrelerini hizala; yeni tam metin döndür.

    Her kolon en geniş hücreye göre boşlukla doldurulur; kolon belirtimi,
    kural satırları (\toprule vb.) ve boş/yorum satırlar yerinde korunur.
    Blok yoksa veya hizalanacak satır yoksa None.
    """
    block = parse_tabular_at(text, pos)
    if block is None:
        return None

    begin_line_start = text.rfind("\n", 0, block["start"]) + 1
    indent = re.match(r"[ \t]*", text[begin_line_start:block["start"]]).group(0) or "    "

    src_lines = text[block["start"]:block["end"]].split("\n")
    rows = [c for c in (_row_cells(ln) for ln in src_lines[1:]) if c]
    if not rows:
        return None
    ncols = max(len(r) for r in rows)
    widths = [0] * ncols
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))

    out = [src_lines[0]]  # \begin{...}{spec} satırı olduğu gibi
    for ln in src_lines[1:]:
        cells = _row_cells(ln)
        if cells is None:
            out.append(ln)
            continue
        padded = [c.ljust(widths[i]) for i, c in enumerate(cells)]
        out.append(indent + " & ".join(padded).rstrip() + " \\\\")
    return text[:block["start"]] + "\n".join(out) + text[block["end"]:]
