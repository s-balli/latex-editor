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
