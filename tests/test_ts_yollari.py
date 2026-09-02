"""`.ts` içindeki `location` yolları kararlı ve gerçek kaynağı göstermeli.

`pylupdate6` kaynakları `mktemp -d` ile açılan geçici bir dizinden okuyor
(gerekçe: scripts/extract_tr.py) ve `location` satırlarına OKUDUĞU yolu
yazıyor. O dizinin adı her koşuda değiştiği için her çeviri güncellemesi
~1800 satırlık anlamsız diff üretiyordu; ölçüldü (2026-09-02): e1796f6 1811
satır, 90a3b66 1820, 7c2bea5 1801, hepsi neredeyse tamamen yol değişimi.

Gerçek değişikliğin o gürültünün içinde kaybolması, çeviri commit'lerini
gözden geçirilemez yapıyordu.
"""

import importlib.util
import os

import pytest

_BETIK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "ts_yollarini_duzelt.py")


def _yukle():
    spec = importlib.util.spec_from_file_location("ts_yollari", _BETIK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    if not os.path.exists(_BETIK):
        pytest.skip("scripts/ts_yollarini_duzelt.py yok")
    return _yukle()


def _konum(yol):
    return '        <location filename="%s" line="12" />' % yol


def test_gecici_dizin_yolu_gercek_kaynaga_ceviriliyor(mod):
    ham = _konum("../../../../../../../../tmp/tmp.UyYLWT2AAZ/desktop/gui/editor.py")

    yeni, sayac = mod.duzelt(ham)

    assert sayac == 1
    assert yeni == _konum("../gui/editor.py")


def test_ic_ice_dizin_korunuyor(mod):
    ham = _konum("/tmp/tmp.X/desktop/gui/mixins/compile_ops.py")

    yeni, _n = mod.duzelt(ham)

    assert yeni == _konum("../gui/mixins/compile_ops.py")


def test_desktop_kokundeki_dosya(mod):
    ham = _konum("/tmp/tmp.X/desktop/main.py")

    yeni, _n = mod.duzelt(ham)

    assert yeni == _konum("../main.py")


def test_farkli_gecici_dizinler_AYNI_sonucu_veriyor(mod):
    """Asıl mesele bu: iki koşunun çıktısı birbirinin aynısı olmalı."""
    a = _konum("/tmp/tmp.UyYLWT2AAZ/desktop/gui/editor.py")
    b = _konum("/tmp/tmp.pVVrxTAZ6h/desktop/gui/editor.py")

    assert mod.duzelt(a)[0] == mod.duzelt(b)[0]


def test_ikinci_kez_calistirmak_degistirmiyor(mod):
    """Betik kendi çıktısı üzerinde de güvenli olmalı (idempotent)."""
    ham = _konum("/tmp/tmp.X/desktop/gui/editor.py")

    bir = mod.duzelt(ham)[0]
    iki = mod.duzelt(bir)[0]

    assert bir == iki


def test_location_disindaki_satirlara_dokunmuyor(mod):
    """`/desktop/` geçen bir KAYNAK metni yanlışlıkla yeniden yazılmamalı.

    Yol BAŞ EĞİK ÇİZGİLİ: ilk halinde `desktop/gui` yazmıştım ve deseni
    gevşetip `<location` koşulunu kaldırınca test yine geçiyordu, çünkü
    eşleşme zaten olmuyordu. Kırılma denemesinde yakalandı.
    """
    ham = "        <source>/home/ali/desktop/gui klasörünü aç</source>"

    yeni, sayac = mod.duzelt(ham)

    assert sayac == 0
    assert yeni == ham


def test_uretilen_yol_gercekten_var():
    """Yol `desktop/translations/` dizinine göre çözülmeli, yoksa Linguist
    kaynağa atlayamaz."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ts_dizin = os.path.join(kok, "desktop", "translations")
    if not os.path.isdir(ts_dizin):
        pytest.skip("çeviri dizini yok")

    hedef = os.path.normpath(os.path.join(ts_dizin, "../gui/editor.py"))

    assert os.path.isfile(hedef), hedef
