"""Menü/eylem doğruluğu — Alt kısayolları, Ctrl+S bağlantısı, kalıcı tercihler.

2026-08-30 denetimi (C1/C2/C3):
- Aynı menüde iki öğe aynı Alt harfini kullanınca Qt düğmeyi TETİKLEMEZ,
  yalnız odağı gezdirir. Menü çubuğunda Alt+D hem Dosya'yı hem Derle'yi
  gösteriyordu; Dosya menüsünde dört öğe Alt+K'daydı.
- Menü/araç çubuğu "Kaydet" yalnız kaydediyor, Ctrl+S ise kaydedip
  derliyordu — üstelik menüde kısayol hiç yazmıyordu.
- Otomatik Derle tercihi hatırlanmıyordu.

Kaynak ayrıştırma yaklaşımı test_tr_extraction.py ile aynı: MainWindow'u
gerçekten kurmak ağır ve kırılgan, menü tanımı ise düz metinde okunabilir.
"""

import collections
import io
import os
import re
import xml.etree.ElementTree as ET

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAIN = os.path.join(_ROOT, "desktop", "gui", "main_window.py")
_EN_TS = os.path.join(_ROOT, "desktop", "translations", "latexeditor_en.ts")


def _menu_tablosu() -> dict[str, list[str]]:
    """main_window._setup_menu'den {menü_değişkeni: [etiketler]} çıkar."""
    satirlar = io.open(_MAIN, encoding="utf-8").read().splitlines()
    menus: dict[str, list[str]] = collections.OrderedDict()
    menus["menubar"] = []
    for line in satirlar:
        m = re.search(r'(\w+)\s*=\s*(?:self\.)?(\w+)\.addMenu\(_\("([^"]+)"\)', line)
        if m:
            var, parent, label = m.groups()
            if parent == "menubar":
                menus["menubar"].append(label)
            else:
                menus.setdefault(parent, []).append(label)
            menus.setdefault(var, [])
            continue
        m = re.search(r'_add_action\((\w+),\s*_\("([^"]+)"\)', line)
        if m:
            menus.setdefault(m.group(1), []).append(m.group(2))
    return {k: v for k, v in menus.items() if v}


def _mnemonic(label: str) -> str | None:
    m = re.search(r"&(.)", label)
    return m.group(1).lower() if m else None


def _cakismalar(labels: list[str]) -> dict[str, list[str]]:
    sayac = collections.Counter(x for x in map(_mnemonic, labels) if x)
    return {h: [l for l in labels if _mnemonic(l) == h]
            for h, n in sayac.items() if n > 1}


def _en_katalog() -> dict[str, str]:
    kok = ET.parse(_EN_TS).getroot()
    out: dict[str, str] = {}
    for ctx in kok.findall("context"):
        for msg in ctx.findall("message"):
            tr = msg.find("translation")
            if tr is None or tr.get("type") in ("vanished", "obsolete"):
                continue
            kaynak, hedef = msg.findtext("source"), (tr.text or "")
            if kaynak and hedef:
                out.setdefault(kaynak, hedef)
    return out


def test_menu_tablosu_okunabiliyor():
    """Ayrıştırma bozulursa aşağıdaki kapılar sessizce boşa düşmesin."""
    menus = _menu_tablosu()
    assert "menubar" in menus and len(menus["menubar"]) >= 5
    assert "file_menu" in menus and len(menus["file_menu"]) >= 6


def test_turkce_alt_kisayollari_cakismiyor():
    hatalar = []
    for menu, labels in _menu_tablosu().items():
        for harf, grup in _cakismalar(labels).items():
            hatalar.append(f"{menu}: Alt+{harf.upper()} -> {' | '.join(grup)}")
    assert not hatalar, "Türkçe menüde Alt kısayolu çakışması:\n" + "\n".join(hatalar)


def test_ingilizce_alt_kisayollari_cakismiyor():
    en = _en_katalog()
    hatalar, cevirisiz = [], []
    for menu, labels in _menu_tablosu().items():
        ceviriler = []
        for t in labels:
            if t in en:
                ceviriler.append(en[t])
            else:
                cevirisiz.append(f"{menu}: {t}")
        for harf, grup in _cakismalar(ceviriler).items():
            hatalar.append(f"{menu}: Alt+{harf.upper()} -> {' | '.join(grup)}")
    assert not cevirisiz, "menü etiketi EN kataloğunda yok:\n" + "\n".join(cevirisiz)
    assert not hatalar, "İngilizce menüde Alt kısayolu çakışması:\n" + "\n".join(hatalar)


def test_kaydet_menu_toolbar_ve_ctrl_s_ayni_isi_yapiyor():
    """Üç giriş noktası da _on_save_and_compile'a gitmeli ve menüde kısayol görünmeli."""
    kaynak = io.open(_MAIN, encoding="utf-8").read()

    m = re.search(r'_add_action\(file_menu,\s*_\("Ka&ydet"\),\s*self\.(\w+),\s*"([^"]+)"',
                  kaynak)
    assert m, "Dosya menüsündeki Kaydet öğesi bulunamadı"
    assert m.group(1) == "_on_save_and_compile", \
        "menüdeki Kaydet, Ctrl+S'ten farklı bir işleyiciye gidiyor"
    assert m.group(2) == "Ctrl+S", "menüde kısayol görünmüyor"

    assert re.search(r'toolbar\.addAction\(_\("💾 Kaydet"\),\s*self\._on_save_and_compile\)',
                     kaynak), "araç çubuğundaki Kaydet farklı iş yapıyor"

    # Ayrı QShortcut kalmamalı: menü QAction'ı app_shortcut ile aynı işi görüyor
    assert 'QShortcut(QKeySequence("Ctrl+S")' not in kaynak, \
        "Ctrl+S hem QAction hem QShortcut olarak tanımlı — çift bağlantı"


def test_otomatik_derle_kalici_ve_menude():
    kaynak = io.open(_MAIN, encoding="utf-8").read()
    assert 'settings.value("compile/auto_compile"' in kaynak, \
        "Otomatik Derle tercihi açılışta okunmuyor"
    assert '_add_action(build_menu, _("&Otomatik Derle")' in kaynak, \
        "Otomatik Derle Derle menüsünde yok (yalnız fareyle erişilebilir kalır)"

    ops = io.open(os.path.join(_ROOT, "desktop", "gui", "mixins", "compile_ops.py"),
                  encoding="utf-8").read()
    assert 'setValue("compile/auto_compile"' in ops, \
        "Otomatik Derle tercihi kaydedilmiyor"


@pytest.mark.parametrize("dizge", [
    "kurulu değil",
    "çalışıyor",
    "wsl bulunamadı",
    "minted belgeleri için gerekli",
])
def test_ortam_denetimi_metinleri_katalogda(dizge):
    """core/env_check.py'nin ham Türkçe metinleri EN arayüzde çevrilmeli."""
    en = _en_katalog()
    assert dizge in en, f"Ortam Denetimi metni EN kataloğunda yok: {dizge!r}"
    assert en[dizge] != dizge, f"EN çevirisi Türkçe kalmış: {dizge!r}"


@pytest.fixture(scope="session")
def qapp():
    """QApplication REFERANSI TUTULMALI: `QApplication([])` sonucu bir yere
    bağlanmazsa hemen toplanıyor ve sonraki widget kurulumu süreci
    'Fatal Python error: Aborted' ile düşürüyor."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_satira_git_dialogu_gercekten_aciliyor(qapp, monkeypatch):
    """Ctrl+G / Düzenle→Satıra Git ÇAĞRILDIĞINDA patlamamalı.

    Gerçekten patlıyordu (2026-08-31): `line, _ = editor.getCursorPosition()`
    modüldeki `_` çeviri fonksiyonunu yerel bir int'le gölgeliyor, hemen
    ardından gelen `_("Satıra Git")` "TypeError: 'int' object is not callable"
    veriyordu. Statik kapı tests/test_i18n.py'de; bu test davranışı tutuyor:
    imza değişip gölgeleme başka biçimde geri gelirse burası düşer.
    """
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QWidget
    from gui.editor import EditorWidget
    from gui.mixins.edit_ops import EditOpsMixin
    import gui.mixins.edit_ops as eo

    class _Stub(EditOpsMixin, QWidget):
        def __init__(self, ed):
            super().__init__()
            self._ed = ed

        def _current_editor(self):
            return self._ed

    ed = EditorWidget()
    ed.setText("bir\niki\nuc\ndort\n")
    ed.setCursorPosition(2, 1)

    yakalanan = {}

    def _sahte_getInt(parent, baslik, etiket, deger, alt, ust):
        yakalanan.update(baslik=baslik, etiket=etiket, deger=deger,
                         alt=alt, ust=ust)
        return (4, True)

    monkeypatch.setattr(eo.QInputDialog, "getInt", staticmethod(_sahte_getInt))

    stub = _Stub(ed)
    stub._goto_line_dialog()

    # Dialog açıldı ve imleç satırıyla kuruldu (0-tabanlı 2 → gösterilen 3)
    assert yakalanan["deger"] == 3
    assert yakalanan["alt"] == 1 and yakalanan["ust"] == ed.lines()
    assert yakalanan["baslik"] and yakalanan["etiket"]
    # Seçilen satıra gerçekten gidildi (4 → 0-tabanlı 3)
    assert ed.getCursorPosition()[0] == 3
    ed.deleteLater()
    stub.deleteLater()
