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
        _qt_cevirmenini_yukle(app, locale, _logger)
    else:
        mevcut = ([f for f in os.listdir(_trans_dir) if f.endswith(".qm")]
                  if os.path.isdir(_trans_dir) else "(dizin yok)")
        _logger.warning(
            "Çeviri dosyası yüklenemedi: %s, dizindeki .qm dosyaları: %s",
            qm_path, mevcut)


_qt_translator = None       # Qt'nin kendi kataloğu; referans TUTULMALI


def _qt_cevirmenini_yukle(app, locale, logger):
    """Qt'nin KENDİ metinlerini de çevir (qtbase_<dil>.qm).

    Uygulama yalnız `latexeditor_<dil>.qm`i yüklüyordu. Qt'nin kendi ürettiği
    arayüz parçaları o katalogda yok: `QLineEdit`/`QTextEdit` sağ tık menüsü
    (Undo/Redo/Cut/Copy/Paste/Delete/Select All), dosya ve renk diyaloglarının
    düğmeleri, standart buton metinleri. Türkçe arayüzde bunlar İngilizce
    kalıyordu (kullanıcı bildirdi 2026-09-06: kaynakça süzme kutusunun sağ tık
    menüsü). `qtbase_tr.qm` PyQt6 ile birlikte GELİYOR, yüklenmiyordu.

    Referans MODÜL DÜZEYİNDE tutuluyor: `installTranslator` sahiplik almıyor,
    yerel değişken kalsa çeviri fixture biter bitmez düşerdi.

    PAKETLENMİŞ SÜRÜMDE DE ÇALIŞIR, iki uçtan da bakıldı (PyInstaller 6.x):
    - Qt hook'u `QtCore -> ['qt', 'qtbase']` eşlemesinden `qtbase_*.qm`i
      toplayıp `PyQt6/Qt6/translations` altına koyuyor.
    - `pyi_rth_pyqt6` çalışma anı hook'u Qt önekini `_MEIPASS/PyQt6/Qt6`
      yapıyor; `TranslationsPath` de önekin altındaki `translations`.
    Yani aşağıdaki `QLibraryInfo.path` donmuş uygulamada da dosyaları bulur.
    Hook toplayamazsa uyarı basıp geçiyoruz; menüler İngilizce kalır, çökmez.
    """
    global _qt_translator
    from PyQt6.QtCore import QLibraryInfo, QTranslator

    dizin = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    ceviren = QTranslator()
    if ceviren.load("qtbase_" + locale, dizin):
        app.installTranslator(ceviren)
        _qt_translator = ceviren
        logger.info("Qt çevirisi yüklendi: qtbase_%s", locale)
    else:
        # İngilizce Qt'nin KAYNAK dili: katalog olmaması normal, uyarı değil.
        (logger.debug if locale.startswith("en") else logger.warning)(
            "Qt çevirisi yüklenemedi: qtbase_%s (dizin: %s)", locale, dizin)


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
