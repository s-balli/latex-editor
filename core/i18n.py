"""Uluslararasılaştırma — desktop ve web ortak arayüz."""

import os
import sys

# Hiç tercih kaydedilmemişken açılacak dil. TEK KAYNAK: arayüzdeki dil
# seçici de bunu okuyor. İkisi ayrı ayrı yazılıydı ve ayrışabilirlerdi;
# ayrışsalardı arayüz bir dilde açılır, seçicide başka dil yazardı.
VARSAYILAN_DIL = "en"

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

    # Ayarlardan dil al, yoksa VARSAYILAN_DIL. Eskiden kaynak dil (Türkçe)
    # açılıyordu ve sistem dili hiç sorulmuyordu, yani uygulama dünyanın her
    # yerinde Türkçe başlıyordu. AppImageHub'ın CI'ı uygulamayı İngilizce bir
    # makinede çalıştırıp ekran görüntüsü alınca görüldü. Türkçe araç
    # çubuğundaki seçiciden tek tıkla geri geliyor ve tercih kaydediliyor.
    settings = QSettings("LatexEditor", "LatexEditor")
    lang = settings.value("language", "")
    locale = lang if lang else VARSAYILAN_DIL
    qm_path = os.path.normpath(
        os.path.join(_trans_dir, f"latexeditor_{locale}.qm"))

    # Adım adım teşhis DEBUG'da: dosya handler'ı INFO ve üstünü yazıyor, bu
    # satırlar her açılışta rotating log'un yerini yiyordu. Sorun çıktığında
    # gereken bilgi aşağıdaki tek WARNING satırında zaten toplu duruyor.
    _logger.debug("Çeviri aranıyor: %s (dizin var: %s, dosya var: %s, ayar: [%s])",
                  qm_path, os.path.isdir(_trans_dir), os.path.isfile(qm_path), lang)

    translator = QTranslator()
    if translator.load(qm_path):
        app.installTranslator(translator)
        _backend = _QtBackend(translator)
        _logger.info("Çeviri yüklendi: %s", locale)
    else:
        mevcut = ([f for f in os.listdir(_trans_dir) if f.endswith(".qm")]
                  if os.path.isdir(_trans_dir) else "(dizin yok)")
        _logger.warning(
            "Çeviri dosyası yüklenemedi: %s, dizindeki .qm dosyaları: %s",
            qm_path, mevcut)


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
        # QCoreApplication.translate karşılık bulamazsa kaynak metni aynen
        # döndürür — istenen davranış bu (Türkçe kaynak dil). Buradaki eski
        # 'result != text' üçlüsü iki dalda da aynı değeri veriyordu; bir yedek
        # düşünülüp yazılmamış, ölü koda dönüşmüştü.
        from PyQt6.QtCore import QCoreApplication
        return QCoreApplication.translate(ctx, text)
