"""İlk açılış pencere boyutu ekrana sığdırılıyor mu.

Boyut sabit 1400x900 idi ve ekrana hiç bakılmıyordu; 1366x768 gibi hâlâ
yaygın dizüstü ekranlarında pencere ilk açılışta taşıyordu. Kaydedilmiş
boyutu olan hiç kimse görmediği için gözden kaçmıştı; AppImageHub'ın
800x600'lük Xvfb ekranında aldığı ekran görüntüsünde ortaya çıktı.
"""

import inspect
import re
from unittest.mock import MagicMock, patch

import pytest

try:
    from PyQt6.QtCore import QRect
    from gui.main_window import MainWindow, ekrana_sigan_boyut
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


# --- Sığdırma ---


def test_kucuk_ekranda_kuculuyor():
    """1366x768 dizüstü: istenen 1400x900 ikisinde de taşıyor."""
    assert ekrana_sigan_boyut(1400, 900, QRect(0, 0, 1366, 768)) == (1366, 768)


def test_yalnizca_TASAN_boyut_kisiliyor():
    """Bir eksen sığıyorsa o eksene dokunulmamalı.

    Yükseklikte de kısmak, geniş ama alçak ekranlarda pencereyi gereksiz
    yere küçültürdü.
    """
    assert ekrana_sigan_boyut(1400, 900, QRect(0, 0, 1280, 1024)) == (1280, 900)
    assert ekrana_sigan_boyut(1400, 900, QRect(0, 0, 1920, 800)) == (1400, 800)


def test_buyuk_ekranda_BUYUMUYOR():
    """4K ekranda pencere ekranı kaplamamalı, istenen boyutta kalmalı."""
    assert ekrana_sigan_boyut(1400, 900, QRect(0, 0, 3840, 2160)) == (1400, 900)


def test_ekran_yoksa_istenen_boyut_donuyor():
    """primaryScreen None dönebiliyor (ekransız ortam); çökmemeli."""
    with patch("gui.main_window.QApplication.primaryScreen", return_value=None):
        assert ekrana_sigan_boyut(1400, 900) == (1400, 900)


def test_gercek_ekran_sorguya_giriyor():
    """`alan` verilmezse availableGeometry OKUNMALI.

    `alan` yalnızca test kolaylığı; üretimde ekrana gerçekten bakıldığı
    denetlenmezse işlev sahada hiçbir şey yapmadan geçer.
    """
    sahte = MagicMock()
    sahte.availableGeometry.return_value = QRect(0, 0, 1024, 768)
    with patch("gui.main_window.QApplication.primaryScreen", return_value=sahte):
        assert ekrana_sigan_boyut(1400, 900) == (1024, 768)
    sahte.availableGeometry.assert_called_once()


# --- Kaydedilmiş boyutla çakışmıyor ---


def test_KAYITLI_boyut_varsayilani_EZIYOR():
    """Sığdırma yalnızca İLK açılışı ilgilendiriyor.

    `resize` __init__'in başında, `_restore_state` sonunda çağrılıyor;
    kaydedilmiş geometri sonradan gelip üstüne yazıyor. Sıra tersine
    dönerse mevcut kullanıcıların pencere boyutu sessizce sıfırlanır ve
    bunu ancak kullanıcılar fark eder.
    """
    kaynak = inspect.getsource(MainWindow.__init__)
    i_resize = kaynak.index("ekrana_sigan_boyut(")
    i_restore = kaynak.index("_restore_state()")
    assert i_resize < i_restore, "restore önce koşuyor, kayıtlı boyut eziliyor"


def test_restore_kayitli_geometriyi_uyguluyor():
    """Kayıt varsa restoreGeometry o baytlarla çağrılmalı."""
    sahte = MagicMock()
    # *args: _restore_state bazı anahtarları varsayılanla da okuyor
    sahte._settings.value.side_effect = lambda anahtar, *_: (
        b"GEOMETRI" if anahtar == "geometry" else None)

    MainWindow._restore_state(sahte)

    sahte.restoreGeometry.assert_called_once_with(b"GEOMETRI")


# --- Sabit boyut geri gelmesin ---


def test_ham_resize_cagrisi_kalmadi():
    """`self.resize(1400, 900)` doğrudan geri yazılırsa kapı düşsün."""
    kaynak = inspect.getsource(MainWindow.__init__)
    assert not re.search(r"resize\(\s*\d+\s*,", kaynak), \
        "ilk boyut yine ekrana bakmadan veriliyor"


# --- Yardım pencereleri ekrana sığıyor ---
#
# Klavye Kısayolları bir QMessageBox'tı ve QMessageBox boyunu içeriğe
# sabitliyor: 1080p ekranda %150 ölçekte çalışma alanını aşıyor, %175'te son
# satır yarım ve Tamam düğmesi ekranın dışında kalıyordu (ölçüldü 2026-09-29,
# v1.1.2 exe'si 1.75 ölçekte: 147 px). Özellikler'in sabit 950x600'ü de
# %175'te taşıyordu.

# Windows 10 başlık çubuğu ve alt kenar, mantıksal piksel. Kod kendi payını
# ayırıyor; bu sayı ondan bağımsız, taşmayı gerçek çerçeveyle ölçmek için.
CERCEVE = 31


class _Ekran:
    """Kullanılabilir alanı verilen sahte QScreen."""

    def __init__(self, alan):
        self._alan = alan

    def availableGeometry(self):
        return self._alan


@pytest.fixture
def yardim_ac(monkeypatch):
    """`cagri(ebeveyn)`i gerçekten çalıştırıp açılan pencereyi döndürür.

    Ebeveyn iskelet bir QWidget (MainWindow'u kurmak ağır), ekranı sahte.
    Pencere gizli gösteriliyor ki yerleşim gerçekten yapılsın.
    """
    import types
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget
    from gui.theme import THEMES

    app = QApplication.instance() or QApplication([])  # noqa: F841
    acilan, ebeveynler = [], []
    # Eski yola dönülürse test modal döngüde kilitlenmesin, düşsün
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: acilan.append("QMessageBox")))
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: acilan.append("QMessageBox") or 0)

    def goster(dlg):
        dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        dlg.show()
        QApplication.processEvents()
        acilan.append(dlg)
        return 0

    monkeypatch.setattr(QDialog, "exec", goster)

    def ac(cagri, alan):
        ebeveyn = QWidget()
        ebeveyn._theme_mgr = types.SimpleNamespace(theme=THEMES["dark"])
        ebeveyn._status = types.SimpleNamespace(showMessage=lambda *a: None)
        ebeveyn.screen = lambda: _Ekran(alan)
        ebeveynler.append(ebeveyn)   # diyalog onun çocuğu, silinmesin
        cagri(ebeveyn)
        assert acilan, "pencere açılmadı"
        assert acilan[-1] != "QMessageBox", (
            "boyu içeriğe sabit QMessageBox'a dönülmüş, küçük ekranda taşar")
        return acilan[-1]

    yield ac
    for e in ebeveynler:
        e.close()


BUYUK = QRect(0, 0, 2560, 1400)


def _kaydirma_payi(dlg):
    from PyQt6.QtWidgets import QTextBrowser
    return dlg.findChild(QTextBrowser).verticalScrollBar().maximum()


def test_kisayollar_KUCUK_ekrana_sigiyor(yardim_ac):
    """1920x1080 %175, Windows 11: kullanılabilir alan 1097x569."""
    alan = QRect(0, 0, 1097, 569)
    dlg = yardim_ac(MainWindow._show_shortcuts, alan)
    assert dlg.height() + CERCEVE <= alan.height(), dlg.size()
    assert dlg.width() <= alan.width(), dlg.size()


def test_kisayollar_BUYUK_ekranda_kaydirmasiz(yardim_ac):
    """Sığan ekranda liste eskisi gibi tümüyle görünmeli, kaydırma yok."""
    from PyQt6.QtWidgets import QTextBrowser

    dlg = yardim_ac(MainWindow._show_shortcuts, BUYUK)
    assert "Ctrl+Shift+Y" in dlg.findChild(QTextBrowser).toPlainText()
    assert _kaydirma_payi(dlg) == 0, (
        "büyük ekranda kaydırma çubuğu çıkıyor, içerik boyu eksik isteniyor")


def test_icerik_boyu_PENCERENIN_genisliginde_olculuyor(yardim_ac):
    """Boy, satırların pencerede gerçekten kırıldığı genişlikte ölçülmeli.

    QTextBrowser kendi belgesinin genişliğini yönetiyor: gösterilmemiş
    pencerede verilen genişlik hemen varsayılana (624) dönüyordu, boy o
    genişlikte ölçülüyor ve kaydırma çubuğu kalıyordu (ölçüldü, Windows
    Fusion: 10 px). Kısayol listesinde fark yazı tipine bağlı, Linux'ta
    görünmüyor; dar pencerede uzun satırlar her yerde kırılıyor.
    """
    # Burada: modül başındaki içe aktarma korumalı, yoksa düzeltmesiz kodda
    # bütün dosya atlanırdı.
    from gui.main_window import yardim_penceresi
    from gui.theme import THEMES

    html = "<br>".join("Ctrl+Shift+%d · " % i + "uzunca bir açıklama " * 4
                       for i in range(12))
    dlg = yardim_ac(lambda e: yardim_penceresi(
        e, THEMES["dark"], "Dar", html, 300), BUYUK)
    assert _kaydirma_payi(dlg) == 0, (
        "boy yanlış genişlikte ölçülmüş, dar pencerede kaydırma çubuğu kaldı")


def test_ozellikler_DAR_ekrana_sigiyor(yardim_ac):
    """1366x768 %150, Windows 10: kullanılabilir alan 911x472."""
    alan = QRect(0, 0, 911, 472)
    dlg = yardim_ac(MainWindow._show_features, alan)
    assert dlg.height() + CERCEVE <= alan.height(), dlg.size()
    assert dlg.width() <= alan.width(), dlg.size()


# Gerçek v1.1.2 yanıtı kadar not (1417 karakter, kırpılmış). QMessageBox bu
# notlarla 414x724 çıkıyordu: 1366x768 ekranda %100'de bile çerçeveyle 27 px
# taşıyor, düğmeler görev çubuğunun altında kalıyordu (ölçüldü 2026-09-29,
# gerçek GitHub yanıtı, gerçek Windows platformu).
GUNCELLEME = {"tag": "v9.9.9", "url": "https://example.org/r", "kirpildi": True,
              "notes": "\n\n".join("- " + "uzunca bir sürüm notu maddesi " * 4
                                   for _ in range(12))}


def test_guncelleme_bildirimi_KUCUK_ekrana_sigiyor(yardim_ac):
    """1920x1080 %175, Windows 11: kullanılabilir alan 1097x569."""
    alan = QRect(0, 0, 1097, 569)
    dlg = yardim_ac(lambda e: MainWindow._on_update_found(e, GUNCELLEME), alan)
    assert dlg.height() + CERCEVE <= alan.height(), dlg.size()


def test_guncelleme_bildirimi_BUYUK_ekranda_kaydirmasiz(yardim_ac):
    """Soru satırı düğmelerin üstünde, boya o da girmeli."""
    dlg = yardim_ac(lambda e: MainWindow._on_update_found(e, GUNCELLEME),
                    BUYUK)
    assert _kaydirma_payi(dlg) == 0, (
        "soru satırı boya katılmamış, sığan notlar kaydırmaya düşüyor")
