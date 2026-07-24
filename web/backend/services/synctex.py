"""SyncTeX bridge (web) — ileri/geri arama via synctex CLI.

desktop/gui/synctex.py'nin Linux-native mantığı, PyQt6 bağımlılığı olmadan.
Web sunucusu Linux üzerinde çalışır; synctex binary'si TeX Live ile birlikte
gelir. Koordinatlar PDF point (1/72") cinsindendir (desktop ile aynı).
"""

import logging
import subprocess
from dataclasses import dataclass

_logger = logging.getLogger("latex_editor.web.synctex")


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
    # Birden fazla sonuç var — ilkini al (en yakın eşleşme).
    # desktop/gui/synctex.py ile birebir aynı parse mantığı.
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


def forward_search(tex_path: str, line: int, col: int, pdf_path: str) -> ForwardResult | None:
    """synctex view — (tex, satır, sütun) → (sayfa, x, y).

    .synctex.gz PDF ile aynı dizinde aranır (derle.sh oraya üretir).
    """
    cmd = ["synctex", "view", "-i", f"{line}:{col}:{tex_path}", "-o", pdf_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            return None
        return _parse_forward(r.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX forward başarısız: %s:%d — %s", tex_path, line, e)
        return None


def reverse_search(page: int, x: float, y: float, pdf_path: str) -> ReverseResult | None:
    """synctex edit — (sayfa, x, y) → (dosya, satır)."""
    cmd = ["synctex", "edit", "-o", f"{page}:{int(x)}:{int(y)}:{pdf_path}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            return None
        return _parse_reverse(r.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        _logger.warning("SyncTeX reverse başarısız: sayfa %d — %s", page, e)
        return None
