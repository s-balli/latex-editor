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


# `\\wsl.localhost\<dağıtım>` kökü. `windows_to_wsl` bu öneki ATIYOR
# (dağıtımın kendi kökü `/`), yani geri çevrim onu tek başına üretemiyor;
# `ornek` bu yüzden gerekiyor.
_RE_WSL_KOK = re.compile(
    r'^(\\\\wsl(?:\$|\.localhost)\\[^\\]+)(?=\\|$)', re.IGNORECASE)


def wsl_to_windows(wsl_path: str, *, ornek: str = "") -> str:
    """/mnt/c/Users/... -> C:\\Users\\...

    ``ornek``: AYNI derlemeden bilinen bir Windows yolu (uygulamada PDF'in
    yolu). Verilirse `/mnt/` DIŞINDAKİ biçimler de geri çevrilebiliyor.

    Neden gerekli: proje WSL'in KENDİ dosya sisteminde durabiliyor
    (`\\\\wsl.localhost\\Ubuntu\\home\\x`) ve WSL belgeleri bunu zaten
    öneriyor, çapraz dosya sistemi erişimi yavaş olduğu için. İleri çevrim
    o biçimi biliyor, geri çevrim BİLMİYORDU: SyncTeX ters araması
    synctex'ten `/home/x/tez.tex` alıp Windows'a öyle veriyordu ve
    `main_window._goto_line` o yolu açamayıp sessizce vazgeçiyordu.
    ÜRETİLDİ (2026-09-12, WSL'in kendi dosya sisteminde derlenmiş gerçek
    bir belgeyle): ileri arama çalışıyor, satır numarası da doğru geliyor,
    ama kullanıcı PDF'te tıklayınca editörde hiçbir şey olmuyordu.

    Dağıtım adı ileri çevrimde atıldığı için burada ÖRNEKTEN alınıyor;
    uydurmak yanlış olurdu (kullanıcının birden çok dağıtımı olabilir).
    """
    m = re.match(r'^/mnt/([a-zA-Z])(/.*)$', wsl_path)
    if m:
        win_path = m.group(2).replace('/', '\\')
        return f"{m.group(1).upper()}:{win_path}"
    if ornek and wsl_path.startswith("/"):
        kok = _RE_WSL_KOK.match(ornek)
        if kok:
            return kok.group(1) + wsl_path.replace("/", "\\")
    return wsl_path
