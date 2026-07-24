"""Uluslararasılaştırma — desktop ve web ortak arayüz."""

import os
import sys

_backend = None
_trans_dir = None


def init(app=None):
    """Çeviri backend'ini başlat.

    Desktop (app verilirse): Qt QTranslator yükler.
    Web veya app=None: pas geçer (gelecekte gettext eklenebilir).
    """
    global _backend, _trans_dir

    if app is None:
        return

    from core.log import get_logger
    _logger = get_logger("i18n")

    from PyQt6.QtCore import QSettings, QTranslator

    _trans_dir = os.path.normpath(_find_trans_dir())
    _logger.info("Çeviri dizini: %s (var: %s)", _trans_dir, os.path.isdir(_trans_dir))

    # Ayarlardan dil al, yoksa kaynak dil (Türkçe)
    settings = QSettings("LatexEditor", "LatexEditor")
    lang = settings.value("language", "")
    _logger.info("Ayardaki dil: [%s]", lang)
    locale = lang if lang else "tr"
    _logger.info("Kullanılacak locale: [%s]", locale)

    # Tam dosya yolunu oluştur
    qm_path = os.path.join(_trans_dir, f"latexeditor_{locale}.qm")
    qm_path = os.path.normpath(qm_path)
    _logger.info("Yüklenecek dosya: %s (var: %s, boyut: %s)",
                 qm_path, os.path.isfile(qm_path),
                 os.path.getsize(qm_path) if os.path.isfile(qm_path) else "N/A")

    translator = QTranslator()
    loaded = translator.load(qm_path)
    _logger.info("translator.load sonucu: %s", loaded)

    if loaded:
        app.installTranslator(translator)
        _backend = _QtBackend(translator)
        _logger.info("Çeviri backend'i yüklendi: %s", locale)
    else:
        _logger.warning("Çeviri dosyası yüklenemedi: %s", qm_path)
        if os.path.isdir(_trans_dir):
            _logger.info("Mevcut .qm dosyaları: %s",
                         [f for f in os.listdir(_trans_dir) if f.endswith('.qm')])


def translator(ctx: str):
    """Modül seviyesi çeviri fonksiyonu üretir.

    Kullanım:
        from core.i18n import translator
        _ = translator("MainWindow")
        menu.addMenu(_("&Dosya"))
    """
    return lambda text: _translate(ctx, text)


def available_languages():
    """Mevcut dilleri listele.

    Dönüş: [("tr", "Türkçe"), ("en", "English"), ...]
    """
    langs = [("tr", "Türkçe")]
    if _trans_dir is None:
        _find = _find_trans_dir()
    else:
        _find = _trans_dir

    if not os.path.isdir(_find):
        return langs

    seen = {"tr"}
    for f in os.listdir(_find):
        if f.startswith("latexeditor_") and f.endswith(".qm"):
            code = f[len("latexeditor_"):-3]
            if code not in seen:
                langs.append((code, _lang_name(code)))
                seen.add(code)
    return langs


def set_language(lang_code: str):
    """Dil tercihi ayarlara kaydedilir. Sonraki başlatmada etkili olur."""
    from core.log import get_logger
    _logger = get_logger("i18n")
    from PyQt6.QtCore import QSettings
    settings = QSettings("LatexEditor", "LatexEditor")
    settings.setValue("language", lang_code)
    _logger.info("Dil tercihi kaydedildi: %s", lang_code)


def _translate(ctx: str, text: str) -> str:
    if _backend is not None:
        return _backend.translate(ctx, text)
    return text


def _find_trans_dir() -> str:
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'desktop')
    return os.path.join(base, 'translations')


def _lang_name(code: str) -> str:
    names = {
        "en": "English", "de": "Deutsch", "fr": "Français",
        "es": "Español", "it": "Italiano", "pt": "Português",
        "ru": "Русский", "zh": "中文", "ja": "日本語",
        "ko": "한국어", "ar": "العربية",
    }
    return names.get(code, code)


class _QtBackend:
    """PyQt6 QTranslator backend."""

    def __init__(self, translator):
        self._translator = translator

    def translate(self, ctx: str, text: str) -> str:
        from PyQt6.QtCore import QCoreApplication
        result = QCoreApplication.translate(ctx, text)
        return result if result != text else text
