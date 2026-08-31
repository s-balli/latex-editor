"""Tema stilleri tek kaynaktan gelmeli — kurulum kendi kopyasını kurmasın.

`FileTree` ve `OutputPanel` stil bloklarını HEM kurulumda HEM `apply_theme`'de
kuruyordu. İki kopya zamanla ayrıştı: `OutputPanel._history_list` yalnız
kurulumda stilleniyordu, yani tema değiştirilince Sürüm Geçmişi sekmesi eski
temanın renklerinde kalıyordu (2026-08-31, teknik borç 1).

Buradaki testler iki şeyi koruyor:
- kurulumdan gelen stil ile apply_theme'in ürettiği stil AYNI olmalı
  (ayrışma yeniden başlarsa burası kırılır)
- tema değiştirilince İSTİSNASIZ her widget yeni temaya geçmeli
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.file_tree import FileTree
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# Stil taşıyan widget alanları — apply_theme hepsini güncellemeli
_ALANLAR = {
    "FileTree": ["_bar_widget", "_title_label", "_btn_refresh", "_root_label",
                 "_tree", "_input_tree", "_input_header"],
    "OutputPanel": ["_tabs", "_error_list", "_warn_list", "_suggest_list",
                    "_log_text", "_history_list"],
}


def _kur(ad, tema):
    return (FileTree if ad == "FileTree" else OutputPanel)(theme=THEMES[tema])


@pytest.mark.parametrize("sinif", sorted(_ALANLAR))
def test_kurulum_stili_apply_theme_ile_ayni(qapp, sinif):
    """Kurulumdan çıkan stil, aynı temayla apply_theme'in ürettiğiyle aynı olmalı.

    Kurulum kendi kopyasını kurarsa iki blok zamanla ayrışır; bu test ayrışmayı
    kopyanın geri gelmesiyle AYNI anda yakalar.
    """
    w = _kur(sinif, "dark")
    try:
        kurulum = {a: getattr(w, a).styleSheet() for a in _ALANLAR[sinif]}
        w.apply_theme(THEMES["dark"])
        sonra = {a: getattr(w, a).styleSheet() for a in _ALANLAR[sinif]}
        farkli = [a for a in kurulum if kurulum[a] != sonra[a]]
        assert not farkli, f"kurulum ile apply_theme ayrışmış: {farkli}"
        assert all(kurulum.values()), "stilsiz kalan widget var"
    finally:
        w.deleteLater()


@pytest.mark.parametrize("sinif", sorted(_ALANLAR))
def test_tema_degisince_her_widget_guncelleniyor(qapp, sinif):
    """apply_theme HİÇBİR widget'ı atlamamalı.

    _history_list tam olarak burada kaçıyordu: kurulumda stilleniyor,
    apply_theme'de unutuluyordu. Koyu temadan açık temaya geçince eski koyu
    arka planla kalıyordu.
    """
    w = _kur(sinif, "dark")
    try:
        koyu = {a: getattr(w, a).styleSheet() for a in _ALANLAR[sinif]}
        w.apply_theme(THEMES["light"])
        acik = {a: getattr(w, a).styleSheet() for a in _ALANLAR[sinif]}
        degismeyen = [a for a in koyu if koyu[a] == acik[a]]
        assert not degismeyen, (
            f"tema değişti ama şu widget'lar eski renklerde kaldı: {degismeyen}")
    finally:
        w.deleteLater()


def test_tum_temalar_uygulanabiliyor(qapp):
    """Yedi temanın hepsi istisnasız uygulanmalı (eksik anahtar KeyError verir)."""
    for sinif in sorted(_ALANLAR):
        w = _kur(sinif, "dark")
        try:
            for tema in THEMES:
                w.apply_theme(THEMES[tema])
                for a in _ALANLAR[sinif]:
                    assert getattr(w, a).styleSheet(), f"{sinif}.{a} boş ({tema})"
        finally:
            w.deleteLater()
