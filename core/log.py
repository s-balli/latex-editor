"""Merkezi logging modülü — platform-aware dosya + console çıktısı."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from PyQt6.QtCore import QStandardPaths

# normpath ŞART: QStandardPaths EĞİK bölü döndürüyor (Windows'ta bile:
# "C:/Users/.../AppData/Local"), os.path.join ise platform ayracını ekliyor →
# "C:/Users/secho/AppData/Local\LatexEditor" gibi karışık ayraçlı bir yol
# çıkıyordu. İşlevsel olarak zararsız (Windows API ikisini de kabul eder) ama
# log satırlarında ve hata mesajlarında görünüyor, üstelik bu yol tek başına
# kalmadı: çökme kurtarma dizini de buradan türüyor
# (gui/mixins/recovery_ops.py:_recovery_dizini). Aynı klasör, düzgün yazım.
LOG_DIR = os.path.normpath(os.path.join(
    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation),
    "LatexEditor",
))
LOG_FILE = os.path.join(LOG_DIR, "latex-editor.log")

_initialized = False


def get_logger(name: str) -> logging.Logger:
    """Modül bazlı logger döndür."""
    _init_once()
    return logging.getLogger(f"latex_editor.{name}")


def _init_once():
    global _initialized
    if _initialized:
        return
    _initialized = True

    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger("latex_editor")
    root.setLevel(logging.DEBUG)

    # Dosya handler — INFO ve üstü, rotating
    fh = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,   # 1 MB
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    # Console handler — DEBUG ve üstü (sadece geliştirme).
    # Paketlenmiş sürüm windowed (console=False): sys.stdout/stderr None olur ve
    # StreamHandler(None) stream'i sys.stderr'e (yine None) düşürür; her log
    # kaydı emit()'te AttributeError atıp handleError() içinde sessizce yutulur.
    # Konsol yoksa handler hiç eklenmez.
    if sys.stdout is not None:
        # Konsol varsa da kodlaması dar olabilir: Türkçe Windows'ta cp1254.
        # Log metinlerinde geçen '→' (10 çağrı: exporter, synctex_ops, file_ops...)
        # cp1254'te yok; emit() UnicodeEncodeError atar, handleError() yutar ve
        # satır konsola HİÇ yazılmaz. errors="replace" ile kayıp yerine '?' basılır.
        # Dosya handler'ı zaten UTF-8, tam metin oraya gidiyor.
        # Not: reconfigure sys.stdout'u global etkiler — bu uygulamada stdout
        # yalnız log için kullanılıyor, print() ile çakışan bir kullanım yok.
        try:
            sys.stdout.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # reconfigure yok/desteklenmiyor: eski davranış sürsün
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(logging.Formatter(
            "%(levelname)-8s | %(name)s | %(message)s",
        ))
        root.addHandler(ch)

    root.info("LaTeX Editor başlatıldı, log dizini: %s", LOG_DIR)


def log_path() -> str:
    """Log dosyasının yolunu döndür (ayarlar/hakkında için)."""
    return LOG_FILE
