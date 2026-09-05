"""LaTeX derleme çıktısını parse etme — hatalar ve uyarıları ayıklama."""

import os
import re
from dataclasses import dataclass, field


@dataclass
class LatexError:
    line_number: int = 0
    message: str = ""
    context: str = ""
    file_path: str = ""


@dataclass
class LatexWarning:
    line_number: int = 0
    message: str = ""
    warning_type: str = ""
    file_path: str = ""


@dataclass
class LatexSuggestion:
    message: str = ""
    install_command: str = ""


@dataclass
class CompileResult:
    success: bool = False
    pdf_path: str = ""
    errors: list[LatexError] = field(default_factory=list)
    warnings: list[LatexWarning] = field(default_factory=list)
    suggestions: list[LatexSuggestion] = field(default_factory=list)
    raw_output: str = ""
    duration: float = 0.0


# Hata satırı: "! Undefined control sequence." vb.
_RE_ERROR = re.compile(r'^\s*! (.+)')
# Paket hatası: "! Package babel Error: ..."
_RE_PKG_ERROR = re.compile(r'^\s*! Package (\S+) Error: (.+)')
# Satır numarası bağlamı: "l.42 \badcommand"
_RE_LINE_CTX = re.compile(r'^\s*l\.(\d+)')
# Uyarı satır numarası: "on input line 42" veya "on lines 5--10"
_RE_WARN_LINE = re.compile(r'(?:on|at) (?:input )?lines? (\d+)')
# LaTeX uyarısı
_RE_LATEX_WARN = re.compile(r'^\s*LaTeX Warning: (.+)')
# Paket uyarısı
_RE_PKG_WARN = re.compile(r'^\s*Package (\S+) Warning: (.+)')
# Motor uyarısı: "pdfTeX warning (ext4): destination ... duplicate ignored" vb.
# Çift \label tespiti (error_hints duplicate_label ipucu) bu satırdan gelir.
_RE_ENGINE_WARN = re.compile(r'^\s*(pdfTeX|LuaTeX|XeTeX) warning[^:]*: (.+)', re.IGNORECASE)
# Overfull/Underfull
_RE_BOX_WARN = re.compile(r'^\s*(Overfull|Underfull) \\\w+ .+')
# Font uyarısı
_RE_FONT_WARN = re.compile(r'^\s*Font .+ not loadable')
# "Missing character: There is no ş (U+015F) in font ec-lmr10!"
#
# XeLaTeX/LuaLaTeX + [T1]{fontenc} birleşiminde Türkçeye özgü harfler PDF'e
# yazılmadan atlanıyor ve derleme BAŞARILI bitiyor. Kullanıcı okuyana kadar
# fark etmiyor, o yüzden panele çıkması gerek (ipucu error_hints'te).
#
# TEK TEK EKLENMEZ: belge başına yüzlerce, binlerce satır geliyor. Ölçüldü:
# demo belgemizde 149, template36-ders'te 8226. Hepsini listelemek Uyarılar
# sekmesini kullanılmaz yapardı. Yazı tipi başına TEK uyarı üretilip kaç kez
# geçtiği yazılıyor; mesaj ilk gerçek satırı koruyor ki error_hints'teki
# desen yazı tipi adını çıkarabilsin.
_RE_MISSING_GLYPH = re.compile(
    r'^\s*Missing character: There is no .+? in font ([^\s!]+)')
# Öneri: ==> Eksik paketi: ... veya ==> Eksik dil paketi: ...
_RE_SUGGESTION = re.compile(r'^==>\s*(Eksik (?:dil )?paket[ie]?): (.+)')
# Kurulum komutu: "    sudo apt-get install ..."
_RE_INSTALL = re.compile(r'^\s+sudo apt-get install (.+)')
# Motor gereksinimi: hata mesajında "requires LuaLaTeX" vb.
_RE_ENGINE_REQ = re.compile(r'requires\s+(LuaLaTeX|LuaTeX|XeLaTeX|XeTeX|pdfTeX)', re.IGNORECASE)
# derle.sh'nin KENDİ hataları: "[hata] lualatex kurulu değil — derlenemedi".
# Bunlar LaTeX log'u değil betik çıktısı, o yüzden yukarıdaki '! ' desenleri
# hiçbirini görmüyordu: motor kurulu değilken, dosya bulunamazken veya PDF hiç
# oluşmazken panel "Başarısız — 0 hata" diyor, ayrıştırıcı success=True
# döndürüyordu — kullanıcıya sebebi söyleyen tek satır kayıptı.
_RE_SCRIPT_ERROR = re.compile(r'^\s*\[hata\]\s*(.+?)\s*$')

# TeX log'u SABİT GENİŞLİKTE sarıyor (`max_print_line`, ölçüldü: 59 gerçek
# şablon logunda 70426 satırın 4147'si tam 79 sütun). Uyarılar da sarıyor ve
# devam satırı hiçbir desene uymadığı için düşüyordu:
#
#   Package natbib Warning: Citation `Abramowitz_1972' on page 7 undefined on input
#    line 241.
#
# Sonuç: mesaj cümle ortasında kesiliyor, "on input line 241" kaybolduğu için
# satır numarası 0 kalıyor (Uyarılar sekmesinde tıklanamıyor) ve error_hints
# deseni eksik metinde eşleşmediği için ipucu da gitmiş oluyor. ÖLÇÜLDÜ:
# 1084 uyarının 344'ü (%31.7) sarıyor, 135'i satır numarasını kaybediyor.
_SARMA = 79
_RE_UYARI_BAS = re.compile(
    r'^\s*(?:LaTeX|Package \S+) Warning: ')
# Birleştirme YALNIZ uyarılar için. Her 79 sütunluk satırı körlemesine
# birleştirmek GÜVENSİZ: ölçüldü, 4147 tam-79 satırın 395'inin (%9.5)
# ardından gerçek bir yapı satırı geliyor (çoğu `l.NN` hata bağlamı) ve onları
# yutardık.
_RE_YAPI_BAS = re.compile(
    r'^\s*(?:!|l\.\d+|LaTeX Warning:|Package \S+ Warning:|'
    r'(?:pdfTeX|LuaTeX|XeTeX) warning|Overfull|Underfull|==>|'
    r'Missing character:)', re.IGNORECASE)


def _mantiksal_satirlar(ham: list[str]) -> list[str]:
    """79 sütunda sarmış UYARI satırlarını devamlarıyla birleştir."""
    out: list[str] = []
    i, n = 0, len(ham)
    while i < n:
        s = ham[i]
        if _RE_UYARI_BAS.match(s):
            son = s
            while (len(son) == _SARMA and i + 1 < n
                   and ham[i + 1].strip()
                   and not _RE_YAPI_BAS.match(ham[i + 1])):
                son = ham[i + 1]
                s += son
                i += 1
        out.append(s)
        i += 1
    return out


# Dosya açılışı `(ad.uzanti`, kapanışı `)`. Her açılış yığına giriyor
# (kapanışlar dengelensin diye), ama rapor edilen yalnız kullanıcının
# .tex kaynağı: `.cls`/`.sty` yüklemeleri ebeveynin adını taşıyor.
_RE_PAREN = re.compile(r'\((?:\./)?([^\s()]*\.[A-Za-z0-9]+)|(\))')


def parse_output(raw: str, source_file: str = "") -> CompileResult:
    """derle.sh çıktısını parse eder."""
    result = CompileResult()
    result.raw_output = raw
    current_file = source_file
    # Dosya yığını: '(' ile GİR, ')' ile ÇIK. Eskiden yalnız giriş vardı ve
    # çocuk dosya kapandıktan sonraki hatalar hâlâ ona atfediliyordu; F4 ile
    # hata satırına gitmek kullanıcıyı YANLIŞ DOSYAYA götürüyordu (ölçüldü:
    # main.tex:5'teki hata, 3 satırlık bolumler/b1.tex'in 5. satırı diye
    # gösteriliyordu). pdflatex'in `-file-line-error` çıktısına karşı
    # doğrulandı: 59 şablonun 230 hatasında doğruluk %97.4'ten %98.7'ye
    # çıkıyor, gerileme yok.
    dosya_yigini: list[str] = [source_file]

    lines = _mantiksal_satirlar(raw.split('\n'))
    current_error: LatexError | None = None
    # yazı tipi -> [ilk ham satır, kaç kez]. Döngü sonunda tek uyarıya iner.
    eksik_glif: dict[str, list] = {}

    for line in lines:
        # Dosya takibi: yalnız kullanıcının .tex kaynağı raporlanır.
        # .cls/.sty/.bib yüklemeleri de yığına girer ki `)` sayısı tutsun, ama
        # ebeveynin adını taşırlar; yoksa hatalar epstopdf-base.sty gibi
        # paketlere atfedilip editörde işaretlenmezdi.
        for pm in _RE_PAREN.finditer(line):
            if pm.group(1):
                ad = pm.group(1)
                kullanilabilir = (ad.endswith(".tex")
                                  and not os.path.isabs(ad))
                dosya_yigini.append(ad if kullanilabilir else dosya_yigini[-1])
            elif len(dosya_yigini) > 1:
                dosya_yigini.pop()
        current_file = dosya_yigini[-1]

        # derle.sh'nin kendi hata satırı
        m = _RE_SCRIPT_ERROR.match(line)
        if m:
            mesaj = m.group(1)
            # İki nokta ile biten satırlar BAŞLIK ("— derleme hatalari:"),
            # ardından gerçek ayrıntılar geliyor; onları hata saymak listeyi
            # ikizlerdi.
            if not mesaj.endswith(":"):
                if current_error:
                    result.errors.append(current_error)
                    current_error = None
                result.errors.append(LatexError(message=mesaj, file_path=current_file))
            continue

        # Paket hatası (daha spesifik, önce kontrol edilmeli)
        m = _RE_PKG_ERROR.match(line)
        if m:
            if current_error:
                result.errors.append(current_error)
            current_error = LatexError(
                message=f"[{m.group(1)}] {m.group(2)}",
                file_path=current_file,
            )
            continue

        # Genel hata
        m = _RE_ERROR.match(line)
        if m:
            if current_error:
                result.errors.append(current_error)
            current_error = LatexError(message=m.group(1), file_path=current_file)
            continue

        # Hata satır numarası
        if current_error and current_error.line_number == 0:
            m = _RE_LINE_CTX.match(line)
            if m:
                current_error.line_number = int(m.group(1))
                current_error.context = line
                continue

        # LaTeX uyarısı
        m = _RE_LATEX_WARN.match(line)
        if m:
            warn_line = 0
            lm = _RE_WARN_LINE.search(m.group(1))
            if lm:
                warn_line = int(lm.group(1))
            result.warnings.append(LatexWarning(
                message=m.group(1),
                warning_type="LaTeX",
                file_path=current_file,
                line_number=warn_line,
            ))
            continue

        # Motor uyarısı (pdfTeX/LuaTeX): çift \label buradan gelir
        m = _RE_ENGINE_WARN.match(line)
        if m:
            result.warnings.append(LatexWarning(
                message=m.group(2),
                warning_type=m.group(1),
                file_path=current_file,
            ))
            continue

        # Paket uyarısı
        m = _RE_PKG_WARN.match(line)
        if m:
            warn_line = 0
            lm = _RE_WARN_LINE.search(m.group(2))
            if lm:
                warn_line = int(lm.group(1))
            result.warnings.append(LatexWarning(
                message=m.group(2),
                warning_type=m.group(1),
                file_path=current_file,
                line_number=warn_line,
            ))
            continue

        # Box uyarısı
        m = _RE_BOX_WARN.match(line)
        if m:
            warn_line = 0
            lm = _RE_WARN_LINE.search(line)
            if lm:
                warn_line = int(lm.group(1))
            result.warnings.append(LatexWarning(
                message=line.strip(),
                warning_type=m.group(1),
                file_path=current_file,
                line_number=warn_line,
            ))
            continue

        # Font uyarısı
        m = _RE_FONT_WARN.match(line)
        if m:
            result.warnings.append(LatexWarning(
                message=line.strip(),
                warning_type="Font",
                file_path=current_file,
            ))
            continue

        # Eksik glif: biriktir, döngü sonunda yazı tipi başına tek uyarı
        m = _RE_MISSING_GLYPH.match(line)
        if m:
            kayit = eksik_glif.setdefault(m.group(1), [line.strip(), 0])
            kayit[1] += 1
            continue

        # Öneri: eksik paketi / dil paketi
        m = _RE_SUGGESTION.match(line)
        if m:
            result.suggestions.append(LatexSuggestion(
                message=f"{m.group(1)}: {m.group(2)}",
            ))
            continue

        # Kurulum komutu (öneriye eşlik eden)
        m = _RE_INSTALL.match(line)
        if m and result.suggestions:
            result.suggestions[-1].install_command = f"sudo apt-get install {m.group(1)}"
            continue

    if current_error:
        result.errors.append(current_error)

    # Eksik glifler: yazı tipi başına tek uyarı. Mesaj ilk GERÇEK log satırını
    # koruyor (error_hints deseni yazı tipi adını oradan çıkarıyor); tekrar
    # sayısı sonuna ekleniyor.
    for _font, (ilk_satir, adet) in eksik_glif.items():
        mesaj = ilk_satir if adet == 1 else f"{ilk_satir} (toplam {adet} karakter)"
        result.warnings.append(LatexWarning(
            message=mesaj,
            warning_type="Font",
            file_path=source_file,
        ))

    # Hata mesajlarında motor gereksinimi tespiti
    _engine_map = {
        "lualatex": "lualatex",
        "luatex": "lualatex",
        "xelatex": "xelatex",
        "xetex": "xelatex",
    }
    for err in result.errors:
        m = _RE_ENGINE_REQ.search(err.message)
        if m:
            required = _engine_map.get(m.group(1).lower(), "lualatex")
            result.suggestions.append(LatexSuggestion(
                message=f"Bu belge {required} gerektiriyor. Derleme motorunu {required} olarak değiştirin.",
            ))
            break

    result.success = len(result.errors) == 0
    return result


def resolve_error_path(file_path: str, base_dir: str) -> str:
    """Hata kaynağı olan dosya yolunu ana dosya dizinine göre çözümle.

    Parser çok dosyalı belgelerde çocuk dosyalar (\\input) için bare filename
    (örn. 'bolum1.tex'), ana dosya için tam yol döndürür. UI katmanı bunu
    base_dir (ana dosyanın dizini) ile birleştirip gerçek yola çevirir; böylece
    F4 ile hata satırına ve gutter işaretine doğru dosyada ulaşılabilir.

    Çözümlenen dosya diskte yoksa (parser yanlış yakalamış olabilir) yolu
    olduğu gibi geri döndürür — çağıran yine de deneyebilir.
    """
    if not file_path:
        return file_path
    if os.path.isabs(file_path) and os.path.isfile(file_path):
        return file_path
    cand = os.path.normpath(os.path.join(base_dir, file_path))
    return cand if os.path.isfile(cand) else file_path
