"""Platform path dönüşümleri — Windows/WSL köprüsü."""

import os
import re


def clean_child_env() -> dict:
    """AppImage gömülü kütüphane yollarından arındırılmış çocuk süreç ortamı.

    AppImage çalışma zamanı LD_LIBRARY_PATH/LD_PRELOAD ile kendi (eski)
    kütüphanelerini ortama yazar; bu ortamla başlayan sistem ikilileri
    (xelatex, pandoc, synctex) gömülü libstdc++'yi bulur ve
    "GLIBCXX_3.4.32 not found" ile düşer. Sistem aracı başlatan her
    subprocess'a env=clean_child_env() verilmeli.
    """
    return {k: v for k, v in os.environ.items()
            if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD")}


def windows_to_wsl(windows_path: str) -> str:
    """C:\\Users\\... -> /mnt/c/Users/..."""
    p = windows_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return f"/mnt/{p[0].lower()}{p[2:]}"
    return p


def wsl_to_windows(wsl_path: str) -> str:
    """/mnt/c/Users/... -> C:\\Users\\..."""
    m = re.match(r'^/mnt/([a-zA-Z])(/.*)$', wsl_path)
    if m:
        win_path = m.group(2).replace('/', '\\')
        return f"{m.group(1).upper()}:{win_path}"
    return wsl_path
