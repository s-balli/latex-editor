"""Test bootstrap — QT offscreen platform + import yolları + Qt nesne temizliği.

Daha önce her test dosyasında tekrarlanan sys.path bloğu burada toplandı;
conftest, test modülleri toplanmadan önce yüklendiği için herkese yeter.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DESKTOP = os.path.join(_REPO, "desktop")
for _p in (_REPO, _DESKTOP):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _qt():
    """(QApplication örneği, QsciScintilla sınıfı) — yoksa (None, None).

    Tembel import: conftest Qt'siz ortamda da yüklenir (saf core testleri).
    """
    try:
        from PyQt6.QtCore import QCoreApplication, QEvent
        from PyQt6.QtWidgets import QApplication
        from PyQt6.Qsci import QsciScintilla
    except ImportError:
        return None, None, None, None
    return QApplication.instance(), QsciScintilla, QCoreApplication, QEvent


@pytest.fixture(autouse=True)
def _sahipsiz_qsci_temizle():
    """Her testten sonra SAHİPSİZ QsciScintilla'ları deterministik yok et.

    NEDEN. Suite ~100 tane `EditorWidget()` kuruyor (28 dosyada) ve
    neredeyse hiçbiri açıkça yok edilmiyor; Python GC onları rastgele
    anlarda topluyor. Toplama, bir `processEvents()` çağrısının ORTASINDA
    denk gelirse Qt zamanlayıcı listesini yinelerken alıcı nesne ölüyor ve
    sonraki zamanlayıcı serbest bırakılmış belleğe düşüyor.

    CI'da gdb ile YAKALANDI (2026-08-31, Python 3.10, tam suite koşusunun
    ~%25'i):

        #0  0x0000000000000000 in ?? ()          <- NULL üzerinden çağrı
        #1  Scintilla::Editor::WrapLines(WrapScope)
        #2  Scintilla::Editor::Idle()
        #3  QsciScintillaQt::onIdle()
        #4  QTimer::timeout                      <- Scintilla'nın idle timer'ı
        #10 QTimerInfoList::activateTimers
        (ana thread: test_version_ops.py:72 _snap → processEvents döngüsü)

    `test_version_ops` yalnızca BİLDİRİM YERİ: suite'teki tek uzun
    `processEvents` döngüsü orası. Sebep, ondan önce çalışan testlerin
    bıraktığı sahipsiz editörler. (Deneyle de doğrulandı: yalnız
    test_version_ops 20 kez koşturulduğunda çökme 0/20; tam suite ile 3/10.)

    ÇÖZÜM. Sahipsiz olanlar `deleteLater` + DeferredDelete boşaltmasıyla,
    OLAY DÖNGÜSÜ DÖNMEZKEN kesin olarak yok edilir. `QApplication.allWidgets()`
    Python sarmalayıcısı çoktan referanssız kalmış ama henüz toplanmamış
    widget'ları da görüyor; onları da burada yakalıyoruz. Bu yüzden ayrıca
    `gc.collect()` ÇAĞIRMIYORUZ — denendi, tam suite'i 57 sn'den 96 sn'ye
    çıkarıyor ve hiçbir şey eklemiyor (kapılar onsuz da yakalıyor).

    Ebeveyni OLAN widget'lara dokunulmaz: onlar ebeveynleriyle birlikte
    Qt'nin kendi zincirinden ölüyor, sorun onlarda değil.
    """
    yield

    app, QsciScintilla, QCoreApplication, QEvent = _qt()
    if app is None or QsciScintilla is None:
        return

    silinen = 0
    for w in list(app.allWidgets()):
        try:
            if isinstance(w, QsciScintilla) and w.parent() is None:
                w.deleteLater()
                silinen += 1
        except RuntimeError:
            continue            # C++ tarafı zaten gitmiş
    if silinen:
        # deleteLater yalnız DeferredDelete olayını KUYRUĞA alır; processEvents
        # onu kendiliğinden işlemez, açıkça boşaltmak gerekiyor.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


@pytest.fixture
def ana_pencere(monkeypatch, tmp_path):
    """GERÇEK MainWindow üreten fabrika (tek kaynak).

    Bazı davranışlar ancak gerçek pencerede sınanabiliyor: closeEvent ile
    _save_state'in etkileşimi, sürükle-bırak ile "Birlikte Aç" yollarının
    aynı kümeye bakması gibi. Vekil bir nesne bu etkileşimleri taşımıyor.

    DİKKAT, QSettings: MainWindow kapanışta oturum durumu YAZIYOR (geometri,
    açık sekmeler, dosya ağacı kökü) ve Windows'ta varsayılan arka uç KAYIT
    DEFTERİ. Önlem alınmazsa testler kullanıcının gerçek oturumunu bozar.
    Burada geçici bir .ini dosyasına hapsediliyor ve hapis tutmazsa fixture
    SERT DÜŞÜYOR: sessizce gerçek ayara yazmaktansa test patlasın.

    TEK KAYNAK olması bilinçli: bu kurulumun ikinci bir kopyası çıkarsa
    biri güncellenip öbürü unutulduğunda kaybeden kullanıcının ayarları olur.
    """
    pytest.importorskip("PyQt6")
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    import gui.main_window as mw
    from gui.mixins.recovery_ops import RecoveryOpsMixin

    app = QApplication.instance() or QApplication([])

    kum = str(tmp_path / "ayarlar")
    os.makedirs(kum, exist_ok=True)

    def _ayar(*a, **k):
        return QSettings(os.path.join(kum, "ayar.ini"), QSettings.Format.IniFormat)

    monkeypatch.setattr(mw, "QSettings", _ayar)
    beklenen = os.path.normcase(os.path.normpath(kum))
    gercek = os.path.normcase(os.path.normpath(_ayar().fileName()))
    assert beklenen in gercek, (
        "QSettings hapsedilemedi, gerçek kullanıcı ayarlarına yazılırdı: "
        + _ayar().fileName())

    # Açılışta ağa çıkma ve modal kurtarma sorusu açma
    monkeypatch.setattr(mw.UpdateCheckThread, "start", lambda self: None)
    monkeypatch.setattr(RecoveryOpsMixin, "_recovery_prompt", lambda self: None)

    pencereler = []

    def _kur(karar="discard"):
        w = mw.MainWindow()
        w._save_dialog = lambda ad: karar      # kirli sekme sorusu
        pencereler.append(w)
        return w

    _kur.ayar = _ayar
    _kur.app = app
    yield _kur

    for w in pencereler:
        try:
            w._save_dialog = lambda ad: "discard"
            w.close()
            w.deleteLater()
        except RuntimeError:                   # zaten yok edilmiş
            pass
    app.processEvents()
