"""LaTeX derleme çıktısını parse etme — hatalar ve uyarıları ayıklama."""

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
# Dosya referansı: "(./dosya.tex" veya "/full/path/dosya.cls" vb.
_RE_FILE_REF = re.compile(r'\((\./)?(\S+\.(tex|cls|sty|bib))')
# Uyarı satır numarası: "on input line 42" veya "on lines 5--10"
_RE_WARN_LINE = re.compile(r'(?:on|at) (?:input )?lines? (\d+)')
# LaTeX uyarısı
_RE_LATEX_WARN = re.compile(r'^\s*LaTeX Warning: (.+)')
# Paket uyarısı
_RE_PKG_WARN = re.compile(r'^\s*Package (\S+) Warning: (.+)')
# Overfull/Underfull
_RE_BOX_WARN = re.compile(r'^\s*(Overfull|Underfull) \\\w+ .+')
# Font uyarısı
_RE_FONT_WARN = re.compile(r'^\s*Font .+ not loadable')
# Öneri: ==> Eksik paketi: ... veya ==> Eksik dil paketi: ...
_RE_SUGGESTION = re.compile(r'^==>\s*(Eksik (?:dil )?paket[ie]?): (.+)')
# Kurulum komutu: "    sudo apt-get install ..."
_RE_INSTALL = re.compile(r'^\s+sudo apt-get install (.+)')
# Motor gereksinimi: hata mesajında "requires LuaLaTeX" vb.
_RE_ENGINE_REQ = re.compile(r'requires\s+(LuaLaTeX|LuaTeX|XeLaTeX|pdfTeX)', re.IGNORECASE)

def parse_output(raw: str, source_file: str = "") -> CompileResult:
    """derle.sh çıktısını parse eder."""
    result = CompileResult()
    result.raw_output = raw
    current_file = source_file

    lines = raw.split('\n')
    current_error: LatexError | None = None

    for line in lines:
        # Dosya referansı takibi
        m = _RE_FILE_REF.search(line)
        if m:
            current_file = m.group(2) if m.group(2) else current_file

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

    # Hata mesajlarında motor gereksinimi tespiti
    _engine_map = {
        "lualatex": "lualatex",
        "luatex": "lualatex",
        "xelatex": "lualatex",
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
