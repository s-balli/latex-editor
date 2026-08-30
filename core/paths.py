"""Platform path dönüşümleri — Windows/WSL köprüsü."""

import logging
import os
import re

# Bu modül bilerek Qt'süz: core.log PyQt6'ya bağımlı, paths ise saf kalmalı.
_logger = logging.getLogger("latex_editor.paths")


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


# \\wsl.localhost\Ubuntu\... veya \\wsl$\Ubuntu\...  (dağıtım adı yutulur)
_RE_WSL_UNC = re.compile(r'^\\\\wsl(?:\$|\.localhost)\\[^\\]+(\\.*)?$', re.IGNORECASE)


def windows_to_wsl(windows_path: str) -> str:
    """Windows yolunu WSL yoluna çevir.

    C:\\Users\\...              -> /mnt/c/Users/...
    \\\\wsl.localhost\\Ubuntu\\ev -> /ev        (dağıtımın kendi dosya sistemi)
    \\\\sunucu\\paylasim\\...     -> DEĞİŞTİRİLMEDEN döner + uyarı loglanır

    Eskiden yalnız "X:" biçimi tanınıyordu; her UNC yolu ters eğik çizgiler
    düz çizgiye çevrilip olduğu gibi geçiyordu (\\\\sunucu\\paylasim\\tez.tex
    -> /sunucu/paylasim/tez.tex). Bu WSL'de var olmayan bir yol; hata da
    verilmediği için derleme "dosya bulunamadı" ile sessizce düşüyordu.
    Ağ paylaşımının WSL'de doğru bir karşılığı YOK (mount edilmedikçe), o
    yüzden uydurmak yerine yol korunuyor ve teşhis için log'a yazılıyor.
    """
    m = _RE_WSL_UNC.match(windows_path)
    if m:
        # WSL'in kendi dosya sistemi: \\wsl.localhost\Ubuntu\home\s -> /home/s
        return (m.group(1) or "\\").replace("\\", "/")

    if windows_path.startswith("\\\\") or windows_path.startswith("//"):
        _logger.warning(
            "Ağ (UNC) yolunun WSL karşılığı yok, olduğu gibi geçiliyor: %s",
            windows_path)
        return windows_path

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
