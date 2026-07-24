"""SyncTeX bridge — ileri/geri arama via synctex CLI."""

import subprocess
import sys
from dataclasses import dataclass

from core.log import get_logger
from core.paths import windows_to_wsl, wsl_to_windows

_logger = get_logger("synctex")

_PLATFORM = sys.platform

# Windows'ta konsol penceresi açılmasını engelle
_SUBPROCESS_FLAGS = 0
_SI = None
if _PLATFORM == "win32":
    _SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW
    _SI = subprocess.STARTUPINFO()
    _SI.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _SI.wShowWindow = 0  # SW_HIDE


@dataclass
class ForwardResult:
    page: int
    x: float
    y: float
    left: float = 0.0   # h alanı — satır sol kenarı
    width: float = 0.0   # W alanı — satır genişliği
    height: float = 0.0  # H alanı — metin yüksekliği


@dataclass
class ReverseResult:
    file_path: str
    line: int
    col: int = 0


def _parse_forward(output: str) -> ForwardResult | None:
    # Birden fazla sonuç var — ilkini al (en yakın eşleşme)
    page = x = y = left = width = height = None
    for ln in output.split('\n'):
        ln = ln.strip()
        if ln.startswith("Page:"):
            if page is not None and x is not None and y is not None:
                break  # İlk sonuç tamam, döngüden çık
            page = int(ln.split(":")[1].strip())
        elif ln.startswith("x:"):
            x = float(ln.split(":")[1].strip())
        elif ln.startswith("y:"):
            y = float(ln.split(":")[1].strip())
        elif ln.startswith("h:"):
            left = float(ln.split(":")[1].strip())
        elif ln.startswith("W:"):
            width = float(ln.split(":")[1].strip())
        elif ln.startswith("H:"):
            height = float(ln.split(":")[1].strip())
    if page is not None and x is not None and y is not None:
        return ForwardResult(page=page, x=x, y=y,
                             left=left or 0.0, width=width or 0.0, height=height or 0.0)
    return None


def _parse_reverse(output: str) -> ReverseResult | None:
    input_file = line = col = None
    for ln in output.split('\n'):
        ln = ln.strip()
        if ln.startswith("Input:"):
            input_file = ln.split(":", 1)[1].strip()
        elif ln.startswith("Line:"):
            line = int(ln.split(":")[1].strip())
        elif ln.startswith("Column:"):
            c = ln.split(":")[1].strip()
            col = int(c) if c != "-1" else 0
    if input_file and line is not None:
        return ReverseResult(file_path=input_file, line=line, col=col or 0)
    return None


def forward_search(tex_path: str, line: int, col: int, pdf_path: str,
                   synctex_dir: str = "") -> ForwardResult | None:
    if _PLATFORM == "win32":
        return _forward_wsl(tex_path, line, col, pdf_path, synctex_dir)
    return _forward_native(tex_path, line, col, pdf_path, synctex_dir)


def reverse_search(page: int, x: float, y: float, pdf_path: str,
                   synctex_dir: str = "") -> ReverseResult | None:
    if _PLATFORM == "win32":
        return _reverse_wsl(page, x, y, pdf_path, synctex_dir)
    return _reverse_native(page, x, y, pdf_path, synctex_dir)


def _forward_wsl(tex_path: str, line: int, col: int, pdf_path: str,
                synctex_dir: str = "") -> ForwardResult | None:
    cmd = ["wsl", "-e", "synctex", "view",
           "-i", f"{line}:{col}:{windows_to_wsl(tex_path)}",
           "-o", windows_to_wsl(pdf_path)]
    if synctex_dir:
        cmd += ["-d", windows_to_wsl(synctex_dir)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3,
                           startupinfo=_SI, creationflags=_SUBPROCESS_FLAGS)
        if r.returncode != 0:
            return None
        return _parse_forward(r.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX forward (WSL) başarısız: %s:%d — %s", tex_path, line, e)
        return None


def _forward_native(tex_path: str, line: int, col: int, pdf_path: str,
                    synctex_dir: str = "") -> ForwardResult | None:
    cmd = ["synctex", "view",
           "-i", f"{line}:{col}:{tex_path}",
           "-o", pdf_path]
    if synctex_dir:
        cmd += ["-d", synctex_dir]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            return None
        return _parse_forward(r.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX forward (native) başarısız: %s:%d — %s", tex_path, line, e)
        return None


def _reverse_wsl(page: int, x: float, y: float, pdf_path: str,
                synctex_dir: str = "") -> ReverseResult | None:
    wsl_pdf = windows_to_wsl(pdf_path)
    cmd = ["wsl", "-e", "synctex", "edit",
           "-o", f"{page}:{int(x)}:{int(y)}:{wsl_pdf}"]
    if synctex_dir:
        cmd += ["-d", windows_to_wsl(synctex_dir)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3,
                           startupinfo=_SI, creationflags=_SUBPROCESS_FLAGS)
        if r.returncode != 0:
            return None
        parsed = _parse_reverse(r.stdout)
        if parsed:
            parsed.file_path = wsl_to_windows(parsed.file_path)
        return parsed
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX reverse (WSL) başarısız: sayfa %d — %s", page, e)
        return None


def _reverse_native(page: int, x: float, y: float, pdf_path: str,
                    synctex_dir: str = "") -> ReverseResult | None:
    cmd = ["synctex", "edit",
           "-o", f"{page}:{int(x)}:{int(y)}:{pdf_path}"]
    if synctex_dir:
        cmd += ["-d", synctex_dir]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            return None
        return _parse_reverse(r.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX reverse (native) başarısız: sayfa %d — %s", page, e)
        return None
