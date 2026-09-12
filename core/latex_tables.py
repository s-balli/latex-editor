"""LaTeX tablo üretimi ve hizalama — saf fonksiyonlar (Qt bağımlılığı yok).

Tablo sihirbazının (GUI) ve `Tabloyu Hizala` komutunun çekirdeği. Web
sürümünde de aynen kullanılabilir.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass

# --- Tablo ortamları ---

# Tablo ortamlarının BAŞLIK BİÇİMİ. TEK KAYNAK.
#
# LaTeX'te iki ortam ZORUNLU bir genişlik argümanı alıyor, diğer ikisi almıyor:
#
#     \begin{tabular}{spec}              \begin{longtable}{spec}
#     \begin{tabularx}{genişlik}{spec}   \begin{tabular*}{genişlik}{spec}
#
# Bu bilgi DÖRT ayrı yerde, dört farklı içerikle duruyordu: desen dört ortamı
# tanıyor, genişlik atlama yalnız `tabularx`i biliyor, `build_tabular`
# `\linewidth`i sabit yazıyor, sihirbazın kendi listesi ise üç ortam sayıyor.
# ÖLÇÜLDÜ (2026-09-12, 39 şablonda 194 gerçek tablo): var olan bir tabloyu
# sihirbazda açıp Tamam demek 8 `tabular*` bloğunun ortamını `tabular`a
# çeviriyor ve genişliğini düşürüyordu; 9 `tabularx` bloğunun genişliği de
# (`0.97\textwidth` gibi) `\linewidth`e eziliyordu.
#
# Sıra ARAYÜZ sırası: sihirbazın açılır kutusu da bu listeyi kullanıyor ve ilk
# öğe varsayılan seçim oluyor. Desen kurulurken uzundan kısaya sıralanıyor,
# yoksa `tabular` alternatifi `tabular*`ı önden yerdi.
TABLO_ORTAMLARI = ("tabular", "tabular*", "tabularx", "longtable")
GENISLIK_ISTEYEN = frozenset({"tabular*", "tabularx"})
VARSAYILAN_GENISLIK = "\\linewidth"

# --- Hücre kaçışı ---

# & satır ayracı, % yorum başlatır, _/# alt çizli/düz moduna sokar, $ math açar.
# Ters eğik çizgi KAÇIRILMAZ: hücreye \textbf{...} vb. bilinçli LaTeX yazma
# serbestliği korunur. (Bu serbestlik METİN KİPİ ile sınırlı: `\alpha` gibi
# matematik komutları hücrede derlenmez, ölçüldü.)
#
# `^` ve `~` SONRADAN eklendi:
#   ^ : metin kipinde üst simge açar ve "! Missing $ inserted." verir, yani
#       DERLEMEYİ KIRAR. `$` zaten kaçırıldığı için hücrede matematik kipi hiç
#       açılamıyor; dolayısıyla `^` bir hücrede hiçbir zaman meşru olamaz.
#   ~ : derleniyor ama bağlayıcı boşluğa dönüşüyor: '5~10' çıktıda '5 10'
#       oluyor (ölçüldü), yani metin yazıldığı gibi görünmüyor.
#
# İkisi de `\` + karakter ile kaçırılamaz: `R\^2` DERLENİR ama şapkayı bir
# SONRAKİ harfin üstüne koyar ('R2̂', ölçüldü). Doğru biçim `\^{}` / `\~{}`.
_ESCAPE_MAP = {"^": "\\^{}", "~": "\\~{}"}
_ESCAPE_RE = re.compile(r"([%&_#$^~])")


# Süslü parantez YALNIZ komut olmayan metinde kaçırılıyor. ÖLÇÜLDÜ
# (2026-09-07, gerçek pdflatex): hücrede ya da başlıkta tek bir `}` belgeyi
# DERLENEMEZ yapıyor ("Baslik}" ile blok düştü). Koşulsuz kaçırmak da olmaz:
# bu alanlarda komut yazmak bilerek destekleniyor (aşağıdaki docstring) ve
# `\textbf{x}` -> `\textbf\{x\}` olup o da düşerdi. Ters eğik çizgi YOKSA
# süslü parantezin gruplama işi de yoktur, yani kaçırmak güvenli.
_BRACE_RE = re.compile(r"([{}])")


def escape_cell(text: str) -> str:
    """Hücre metnindeki LaTeX özel karakterlerini kaçır (ters eğik çizgi hariç)."""
    ham = text.strip()
    # SIRA ÖNEMLİ: süslü parantez ÖNCE. Sonraki değişim `^` için `\^{}`
    # üretiyor ve sonra kaçırılırsa `\^\{\}` çıkıp derleme düşüyor (var olan
    # `TestSapkaVeTilde` testleri bunu yakaladı).
    out = _BRACE_RE.sub(lambda m: "\\" + m.group(1),
                        ham) if "\\" not in ham else ham
    return _ESCAPE_RE.sub(
        lambda m: _ESCAPE_MAP.get(m.group(1), "\\" + m.group(1)), out)


# `\label` argümanı dizgiye YAZILMIYOR ama kod olarak okunuyor: yorum işareti
# satırı kesiyor, süslü parantez dengeyi bozuyor, ters eğik çizgi komut
# başlatıyor. ÖLÇÜLDÜ (2026-09-07, gerçek pdflatex): denenen altı karakterden
# BEŞİ belgeyi derlenemez yapıyor (`%`, `}`, `{`, `\`, `#`); yalnız boşluk
# geçiyor.
# Denetim karakterleri de eleniyor: panodan ya da `extract_caption_label`
# ile gelen metinde bulunabiliyor ve LaTeX onlarda da düşüyor (ölçüldü:
# `tab:a\x08b` derlenmiyor). Türkçe harfler ELENMİYOR, `tab:sonuç` gerçek
# pdflatex'te derleniyor (aynı ölçüm).
_LABEL_YASAK = re.compile(r"[%\\{}#&$~^\x00-\x1f\x7f]")


def guvenli_label(text: str) -> str:
    """Etiketi `\\label` içinde güvenli hâle getir.

    KAÇIRMA değil ELEME: etiket bir ANAHTAR ve `\\ref` ile birebir eşleşmesi
    gerekiyor; `\\%` gibi bir kaçış anahtarın kendisini değiştirir ve
    kullanıcının `\\ref{...}` yazarken kaçışı da bilmesi gerekirdi.

    Boşluklar tireye iniyor: LaTeX kabul ediyor ama `\\ref` yazmayı
    zorlaştırıyor. `suggest_label` da tireli slug üretiyor, yani biçim aynı.
    """
    return re.sub(r"\s+", "-", _LABEL_YASAK.sub("", text.strip()))


_UNESCAPE_RE = re.compile(r"\\([%&_#${}])|\\([\^~])\{\}")


def unescape_cell(text: str) -> str:
    """escape_cell'in tersi: \\% → % vb. (grid'e yüklerken kullanılır).

    \\textbf gibi komutlar dokunulmaz; yalnız kaçırılmış özel karakterler açılır.
    """
    return _UNESCAPE_RE.sub(lambda m: m.group(1) or m.group(2), text.strip())


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
    environment: str = "tabular"      # bkz. TABLO_ORTAMLARI
    # Yalnız GENISLIK_ISTEYEN ortamlarda yazılır. Var olan bir tabloyu
    # düzenlerken sihirbaz onun KENDİ genişliğini buraya koyuyor; yoksa
    # kullanıcının `0.97\textwidth`i sessizce `\linewidth` oluyordu.
    width: str = VARSAYILAN_GENISLIK
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
    # Kolon sayısı EN UZUN satıra göre; satırlar da ona doldurulur. Eskiden
    # `len(rows[0])` alınıyor ve satırlar olduğu gibi yazılıyordu: CSV'den
    # gelen düzensiz bir tabloda (bir satırda fazladan virgül, Excel
    # çıktılarında olağan) üretilen blok DERLENMİYORDU
    # ("! Extra alignment tab has been changed to \\cr", ölçüldü). Kırpmak
    # yerine doldurmak seçildi: kullanıcının verisi sessizce düşmesin.
    ncols = max(len(r) for r in rows)
    aligns = (aligns + ["c"] * ncols)[:ncols]

    top = "\\toprule" if opts.booktabs else "\\hline"
    mid = "\\midrule" if opts.booktabs else "\\hline"
    bottom = "\\bottomrule" if opts.booktabs else "\\hline"

    col_spec = build_col_spec(aligns, opts.vertical_lines, opts.environment)
    if opts.environment in GENISLIK_ISTEYEN:
        genislik = opts.width or VARSAYILAN_GENISLIK
        begin = f"\\begin{{{opts.environment}}}{{{genislik}}}{{{col_spec}}}"
    else:
        begin = f"\\begin{{{opts.environment}}}{{{col_spec}}}"

    ind = opts.indent
    lines = [begin, f"{ind}{top}"]
    for i, row in enumerate(rows):
        cells = [escape_cell(c) for c in row]
        cells += [""] * (ncols - len(cells))     # kısa satırlar boş hücreyle
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
        head.append(f"{ind}\\label{{{guvenli_label(opts.label)}}}")
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


# Denenecek kodlamalar. Excel Turkce Windows'ta CSV'yi VARSAYILAN olarak
# cp1254 yaziyor; dosya yalnizca utf-8 denenince UnicodeDecodeError atiyordu ve
# bu hata tablo sihirbazinin `except OSError`inden kacip slot'tan disari
# cikiyordu: dugme sessizce hicbir sey yapmamis gibi oluyordu (olculdu
# 2026-09-02, dis guvenlik raporu 2. bulgu). latin-1 en sonda ve hic hata
# atmiyor, yani artik cozulemeyen dosya yok.
_CSV_KODLAMALARI = ("utf-8-sig", "cp1254", "latin-1")

# BOM'lu dosyalar once BOM'dan tanınıyor. UTF-32 UTF-16'DAN ONCE bakiliyor:
# FF FE 00 00 (UTF-32 LE) FF FE (UTF-16 LE) ile basliyor.
_CSV_BOM = (
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
)


def _ikili_mi(ham: bytes) -> bool:
    """Icerik metin degil ikili mi: NUL ya da cok fazla denetim karakteri."""
    bas = ham[:4096]
    if not bas:
        return False
    if b"\x00" in bas and not bas.startswith((b"\xff\xfe", b"\xfe\xff")):
        return True            # UTF-16/32 BOM'lularda NUL normal
    denetim = sum(1 for b in bas if b < 9 or 13 < b < 32)
    return denetim > len(bas) * 0.05


def _csv_metni(path: str) -> str:
    """CSV dosyasını metne çevir: kodlamayı BOM'dan ya da deneyerek bul."""
    with open(path, "rb") as f:
        ham = f.read()
    for bom, kod in _CSV_BOM:
        if ham.startswith(bom):
            try:
                return ham.decode(kod)
            except UnicodeDecodeError:
                break
    if _ikili_mi(ham):
        # latin-1 her seyi cozer, yani ikili bir dosya da "okunur" ve tablo
        # coplukle dolardi. Cagirana okunamadigini soylemek dogrusu.
        raise ValueError("CSV degil: ikili icerik")
    for kod in _CSV_KODLAMALARI:
        try:
            return ham.decode(kod)
        except UnicodeDecodeError:
            continue
    return ham.decode("latin-1", "replace")


def csv_to_rows(path: str) -> list[list[str]]:
    """CSV dosyasını hücre satırlarına oku (ayraç: , ; veya sekme, otomatik).

    Excel'in UTF-8 BOM'u temizlenir; tamamen boş satırlar atılır. Kodlama
    otomatik: BOM, sonra utf-8, sonra cp1254 (Excel'in Türkçe varsayılanı).
    """
    with io.StringIO(_csv_metni(path), newline="") as f:
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

_RE_BEGIN = re.compile(
    r"\\begin\{(" + "|".join(
        re.escape(e) for e in sorted(TABLO_ORTAMLARI, key=len, reverse=True)
    ) + r")\}")
_RE_RULE = re.compile(
    r"^\s*\\(toprule|midrule|bottomrule|hline|endhead|endfoot|endfirsthead)\b")
_RE_SPLIT_CELLS = re.compile(r"(?<!\\)&")


#  \\  ya da  \\[2mm]  — satır sonlandırıcı ve isteğe bağlı aralık argümanı
_RE_ROW_END = re.compile(r"\\\\(?:\[[^\]]*\])?\s*$")


def _is_passthrough(s: str) -> bool:
    r"""Satır veri satırı DEĞİL mi? (kural, \end, yorum, boş)"""
    return (not s or s.startswith("%") or bool(_RE_RULE.match(s))
            or s.startswith("\\end{"))


def _row_cells(line: str) -> list[str] | None:
    r"""Satır tablo veri satırıysa hücrelerini, değilse None döndür.

    Kural satırları (\toprule vb.), \end satırı, yorum ve boş satırlar None.
    Tek satırlık kullanım içindir; sarılmış satırlar için _logical_rows.
    """
    s = line.strip()
    if _is_passthrough(s):
        return None
    cells = [c.strip() for c in _RE_SPLIT_CELLS.split(s.rstrip("\\").strip())]
    return None if cells == [""] else cells


def _logical_rows(lines):
    r"""Kaynak satırlarını MANTIKSAL tablo satırlarına grupla.

    Bir tablo satırı kaynakta birden fazla satıra sarılmış olabilir; mantıksal
    satır ``\\`` ile biter. SON veri satırında sonlandırıcı bulunmaması
    LaTeX'te geçerlidir — o da tek başına bir mantıksal satırdır. İkisini
    ayırmadan her kaynak satırına ``\\`` eklemek, sarılmış bir satırı ikiye
    bölüp olmayan bir satır sonlandırıcı uyduruyordu ("Extra alignment tab").

    Üretir:
      ("gec", ham_satır)                      — olduğu gibi korunacak satır
      ("satir", hücreler, sonek, ham_satırlar) — sonek: "" | "\\" | "\\[2mm]"
    """
    tampon: list[str] = []

    def bosalt():
        if not tampon:
            return None
        s = " ".join(x.strip() for x in tampon)
        m = _RE_ROW_END.search(s)
        sonek = m.group(0).strip() if m else ""
        if m:
            s = s[:m.start()]
        cells = [c.strip() for c in _RE_SPLIT_CELLS.split(s.strip())]
        grup = ("satir", cells, sonek, list(tampon))
        tampon.clear()
        return grup

    for ln in lines:
        s = ln.strip()
        if _is_passthrough(s):
            bekleyen = bosalt()
            if bekleyen:
                yield bekleyen
            yield ("gec", ln)
            continue
        tampon.append(ln)
        if _RE_ROW_END.search(s):
            yield bosalt()
    son = bosalt()
    if son:
        yield son


def _grup_oku(text: str, i: int, limit: int) -> tuple[str, int]:
    """``i``den başlayarak dengeli bir ``{...}`` grubu oku.

    Döner: (içerik, kapanıştan sonraki konum). Grup yoksa ("", i).

    Düzenli ifadeyle YAZILAMIYOR: kolon belirtimi keyfi derinlikte iç grup
    taşıyabiliyor. Eski desen tek düzey iç gruba izin veriyordu ve gerçek bir
    şablondaki `|c|>{\\columncolor{layer7!30}}c|c|` belirtimini hiç
    okuyamıyordu (ölçüldü); belirtim boş kalınca metni GÖVDE sanıp tablonun
    ilk satırına hücre olarak yazıyordu.
    """
    while i < limit and text[i] in " \t\r\n":
        i += 1
    if i >= limit or text[i] != "{":
        return "", i
    derinlik, bas = 0, i
    while i < limit:
        if text[i] == "{":
            derinlik += 1
        elif text[i] == "}":
            derinlik -= 1
            if derinlik == 0:
                return text[bas + 1:i], i + 1
        i += 1
    return "", bas


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
    i = m.end()
    width = ""
    if env in GENISLIK_ISTEYEN:
        # İlk küme parantezi GENİŞLİK argümanıdır, kolon belirtimi ikincisidir.
        width, i = _grup_oku(text, i, end)
    col_spec, i = _grup_oku(text, i, end)

    rows = [g[1] for g in _logical_rows(text[i:end].split("\n"))
            if g[0] == "satir" and g[1] != [""]]
    return {"start": start, "end": end, "env": env, "col_spec": col_spec,
            "width": width, "rows": rows}


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
    gruplar = list(_logical_rows(src_lines[1:]))
    rows = [g[1] for g in gruplar if g[0] == "satir" and g[1] != [""]]
    if not rows:
        return None
    ncols = max(len(r) for r in rows)
    widths = [0] * ncols
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))

    out = [src_lines[0]]  # \begin{...}{spec} satırı olduğu gibi
    for g in gruplar:
        if g[0] == "gec":
            out.append(g[1])
            continue
        _, cells, sonek, ham = g
        if cells == [""]:
            out.extend(ham)
            continue
        padded = [c.ljust(widths[i]) for i, c in enumerate(cells)]
        # Sonlandırıcı YENİDEN ÜRETİLMEZ: kaynakta yoksa eklenmez (son satırda
        # `\\` bulunmaması geçerlidir), varsa aynen korunur (`\\[2mm]` dahil).
        out.append(indent + " & ".join(padded).rstrip() + (" " + sonek if sonek else ""))
    return text[:block["start"]] + "\n".join(out) + text[block["end"]:]
