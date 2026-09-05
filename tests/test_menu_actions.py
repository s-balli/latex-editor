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


def _kisayol_kayitlari(kaynak: str):
    """main_window.py'deki tüm kısayol kayıtları: (QAction listesi, QShortcut listesi).

    İki mekanizma var — `_add_action(..., "Ctrl+X", app_shortcut=True)` ve
    `QShortcut(QKeySequence("Ctrl+X"), self)`. İkisi aynı diziyi aynı bağlamda
    kaydederse Qt "Ambiguous shortcut overload" deyip HİÇBİRİNİ tetiklemiyor.
    """
    import ast

    def _dizge(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    eylemler, kisayollar = [], []
    for node in ast.walk(ast.parse(kaynak)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "_add_action":
            dizi = _dizge(node.args[3]) if len(node.args) >= 4 else None
            for kw in node.keywords:
                if kw.arg == "shortcut":
                    dizi = _dizge(kw.value)
            if dizi:
                eylemler.append(dizi)
        elif isinstance(f, ast.Name) and f.id == "QShortcut" and node.args:
            ilk = node.args[0]
            if (isinstance(ilk, ast.Call)
                    and getattr(ilk.func, "id", "") == "QKeySequence" and ilk.args):
                d = _dizge(ilk.args[0])
                if d:
                    kisayollar.append(d)
    return eylemler, kisayollar


def test_hicbir_kisayol_iki_kez_kaydedilmiyor():
    """Aynı tuş dizisi hem QAction hem QShortcut olarak kaydedilemez.

    Qt bunu görünce "QAction::event: Ambiguous shortcut overload" yazıp
    İKİSİNİ DE tetiklemiyor; tuşa basmak sessizce hiçbir şey yapmıyor.

    Gerçekten oldu İKİ KEZ:
    - Ctrl+S (daha eski tur) — düzeltmesi test_kaydet_menu_toolbar_ve_ctrl_s...
    - Ctrl+Shift+F (2026-08-31, projede ara) — KULLANICI BİLDİRDİ. Menüdeki
      QAction app_shortcut=True idi, ayrıca bir QShortcut kurulmuştu; ölçüldü:
      `_project_search` çağrı sayısı 0, Qt mesajı "Ambiguous shortcut
      overload: Ctrl+Shift+F". Menü öğesi de çalışmıyordu.

    Kapı tekil değil GENEL: bir sonraki kısayol da aynı tuzağa düşmesin.
    """
    kaynak = io.open(_MAIN, encoding="utf-8").read()
    eylemler, kisayollar = _kisayol_kayitlari(kaynak)
    assert eylemler and kisayollar, "kapı boşa düşmesin — kayıtlar okunamadı"

    import collections
    sayac = collections.Counter(eylemler + kisayollar)
    cakisan = sorted(d for d, n in sayac.items() if n > 1)
    assert not cakisan, (
        "aynı tuş dizisi birden fazla kez kaydedilmiş — Qt ikisini de "
        f"tetiklemez: {cakisan}. Menüdeki QAction'ı app_shortcut=True ile "
        "bırakın, ayrı QShortcut'ı silin."
    )


# --- FileTree sinyalleri MainWindow'a bağlanmış mı ---

_TREE = os.path.join(_ROOT, "desktop", "gui", "file_tree.py")


def _tree_sinyalleri() -> set[str]:
    """file_tree.FileTree'nin pyqtSignal olarak tanımladığı adlar."""
    kaynak = io.open(_TREE, encoding="utf-8").read()
    govde = kaynak.split("class FileTree(", 1)[-1].split("\n    def ", 1)[0]
    return set(re.findall(r"^\s{4}(\w+)\s*=\s*pyqtSignal\(", govde, re.M))


def _baglanan_sinyaller() -> set[str]:
    """main_window'da `self._file_tree.<ad>.connect(` geçen adlar."""
    kaynak = io.open(_MAIN, encoding="utf-8").read()
    return set(re.findall(r"self\._file_tree\.(\w+)\.connect\(", kaynak))


def test_tree_sinyalleri_okunabiliyor():
    """Kapının kendisi: ayrıştırma bozulursa aşağıdaki test boşa düşmesin."""
    sinyaller = _tree_sinyalleri()
    assert {"file_open_requested", "compile_requested", "root_changed",
            "file_renamed"} <= sinyaller, sinyaller


def test_her_tree_sinyali_baglanmis():
    """Bağlanmamış sinyal SESSİZCE hiçbir şey yapmaz.

    Bu depoda aynı sınıftan iki hata çıktı ve ikisini de yalnız kullanıcı
    fark etti (testler geçiyordu): Ctrl+Shift+F hiç tetiklenmiyordu, klasör
    değişince arama sonuçları bayat kalıyordu. `file_renamed` de aynı
    tuzağa açıktı: bağlanmazsa dosya diskte yeniden adlandırılır ama açık
    sekme eski yola bağlı kalır ve Ctrl+S silinmiş adı yeniden yaratır.
    """
    eksik = sorted(_tree_sinyalleri() - _baglanan_sinyaller())
    assert not eksik, (
        f"FileTree sinyali tanımlanmış ama MainWindow'da bağlanmamış: {eksik}. "
        "Sinyal sessizce hiçbir işe yaramaz."
    )


# --- Yardım metinleri gerçekten kapsıyor mu ---
#
# Yardım > Klavye Kısayolları ve Yardım > Özellikler ELLE yazılmış HTML.
# Yeni özellik eklenip bu metinlerin unutulması sessiz bir hata: kullanıcı
# özelliğin varlığından haberdar olmuyor. Bu depoda birikmişti; 2026-09-02'de
# yapılan kapsamlı taramada Ctrl+N kısayol listesinde HİÇ yoktu ve çıktı
# panelinin Uyarılar/Öneriler sekmeleri hiçbir yerde anlatılmıyordu.


def _mw_kaynak() -> str:
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(kok, "desktop", "gui", "main_window.py"),
              encoding="utf-8") as f:
        return f.read()


def _bolum(kaynak: str, bas: str, son: str) -> str:
    return kaynak[kaynak.index(bas):kaynak.index(son)]


def _kayitli_kisayollar(kaynak: str) -> set:
    """Menüde/QShortcut ile GERÇEKTEN kaydedilmiş tuş dizileri.

    AYRI BİR REGEX KULLANMIYOR. Eskiden burada kendi deseni vardı ve
    `_add_action\\([^\\n]*?,\\s*"..."` kalıbı İLK SATIR SONUNU AŞAMIYORDU:
    çok satırlı bir `_add_action(...)` çağrısı bu kapıya görünmez kalıyordu.
    Ölçüldü (2026-09-05): AST'nin bulduğu 20 kısayoldan tam birini, çok
    satırlı kaydedilen `Ctrl+Shift+Y`yi (Yazımı Denetle) kaçırıyordu ve
    belgelenmemiş olan da tam o kısayoldu. Aynı dosyada zaten AST ile
    çalışan `_kisayol_kayitlari` duruyordu; iki ayrı çıkarıcı tutmak
    kapılardan birini kör bırakmıştı.
    """
    ks = re.compile(r"^(?:Ctrl|Alt|Shift|F\d)")
    eylemler, kisayollar = _kisayol_kayitlari(kaynak)
    return {d for d in eylemler + kisayollar if ks.match(d)}


def test_kisayol_listesi_okunabiliyor():
    """Kapının kapısı: ayrıştırma bozulursa aşağıdaki test boşa düşmesin."""
    kaynak = _mw_kaynak()
    kayitli = _kayitli_kisayollar(kaynak)
    assert len(kayitli) >= 15, kayitli
    assert "Ctrl+S" in kayitli and "Ctrl+Shift+F" in kayitli


def test_her_kisayol_yardim_diyalogunda():
    """Kaydedilmiş her tuş dizisi Klavye Kısayolları'nda yazılı olmalı.

    Ctrl+N tam bu yüzden kaçmıştı: menüde vardı, listede yoktu.
    """
    kaynak = _mw_kaynak()
    diyalog = _bolum(kaynak, "def _show_shortcuts", "def _show_features")
    eksik = sorted(k for k in _kayitli_kisayollar(kaynak) if k not in diyalog)
    assert not eksik, (
        f"kısayol kaydedilmiş ama Yardım > Klavye Kısayolları'nda yok: {eksik}")


def test_panel_sekmeleri_ozelliklerde_anlatiliyor():
    """Çıktı panelinin her sekmesi Özellikler'de geçmeli.

    Uyarılar ve Öneriler sekmeleri hiçbir yerde anlatılmıyordu.
    """
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(kok, "desktop", "gui", "output_panel.py"),
              encoding="utf-8") as f:
        panel = f.read()
    sekmeler = re.findall(r'addTab\([^,]+,\s*_\("([^"]+)"\)', panel)
    assert len(sekmeler) >= 5, sekmeler

    ozellikler = _bolum(_mw_kaynak(), "def _show_features", "def _show_about")
    eksik = [s for s in sekmeler if s not in ozellikler]
    assert not eksik, f"panel sekmesi Özellikler'de anlatılmıyor: {eksik}"


def test_bu_turun_ozellikleri_yardimda():
    """2026-09-02 turunda eklenenler Özellikler'de geçmeli."""
    ozellikler = _bolum(_mw_kaynak(), "def _show_features", "def _show_about")
    for beklenen in ("Kaynakça Sekmesi", "DOI ile Kaynak Ekle",
                     "Dosya Ağacı İşlemleri", "Çökme Kurtarma",
                     "düzenli ifade", "mükerrer .bib"):
        assert beklenen in ozellikler, f"Özellikler'de yok: {beklenen}"


# --- Yardım diyaloglarında yazan kısayol GERÇEKTEN çalışmalı ---
#
# 2026-09-05 turunda iki kusur birden çıktı, ikisi de kullanıcının GÖRDÜĞÜ
# metinde: Özellikler diyaloğu yazım denetimini "Ctrl+Shift+N" diye
# belgeliyordu (o tuş hiçbir yerde kayıtlı değil, basınca hiçbir şey olmuyor)
# ve gerçek kısayol "Ctrl+Shift+Y" iki diyalogda da hiç geçmiyordu, yani
# özellik kısayoluyla keşfedilemiyordu.
#
# Buradaki kapılar kaynak dizgesine değil, diyalogların ÜRETTİĞİ gövdeye
# bakıyor: metin bir gün başka bir yoldan kurulursa da tutar.


def _yardim_diyaloglari(monkeypatch):
    """(_show_shortcuts gövdesi, _show_features gövdesi) döndür.

    MainWindow'u tümüyle kurmak ağır ve kırılgan (derleyici, işçiler,
    QSettings, ağ). Bu iki yöntemin ihtiyacı yalnız `_theme_mgr.theme` ve
    bir QWidget ebeveyn; vekil o kadarını veriyor.
    """
    import types
    from PyQt6.QtWidgets import QDialog, QMessageBox, QTextBrowser, QWidget
    from gui.main_window import MainWindow
    from gui.theme import THEMES

    class _Vekil(QWidget):
        def __init__(self):
            super().__init__()
            self._theme_mgr = types.SimpleNamespace(theme=THEMES["dark"])

    yakalanan = {}
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, baslik, metin, *a, **k:
                     yakalanan.setdefault("kisayol", metin)))
    monkeypatch.setattr(
        QTextBrowser, "setHtml",
        lambda self, h: yakalanan.setdefault("ozellik", h))
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)

    MainWindow._show_shortcuts(_Vekil())
    MainWindow._show_features(_Vekil())
    kis = yakalanan.get("kisayol", "")
    ozl = yakalanan.get("ozellik", "")
    assert len(kis) > 500 and len(ozl) > 500, (
        "kapı boşa düşmesin, diyalog gövdeleri yakalanamadı "
        f"({len(kis)}, {len(ozl)} karakter)")
    return kis, ozl


def test_cok_satirli_kisayol_kaydi_da_goruluyor():
    """Kapının kapısı: çıkarıcı çok satırlı `_add_action` çağrısını görmeli.

    F1 tam bu kör noktadan kaçmıştı. Regex'e geri dönülürse burası düşer.
    """
    kayitli = _kayitli_kisayollar(_mw_kaynak())
    assert "Ctrl+Shift+Y" in kayitli, (
        "çok satırlı kaydedilen kısayol görülmüyor, çıkarıcı yine kör: "
        f"{sorted(kayitli)}")
    assert len(kayitli) >= 20, sorted(kayitli)


def test_yazim_kisayolu_iki_diyalogda_da_dogru(qapp, monkeypatch):
    """Yazım denetimi: belgelenen tuş kayıtlı olan tuşla aynı olmalı."""
    kis, ozl = _yardim_diyaloglari(monkeypatch)
    kayitli = _kayitli_kisayollar(_mw_kaynak())

    assert "Ctrl+Shift+Y" in kayitli
    assert "Ctrl+Shift+Y" in ozl, "Özellikler gerçek kısayolu yazmıyor"
    assert "Ctrl+Shift+Y" in kis, "Klavye Kısayolları listesinde yok"
    assert "Ctrl+Shift+N" not in ozl, (
        "Özellikler hâlâ kayıtlı olmayan bir tuşu belgeliyor")
    assert "Ctrl+Shift+N" not in kis


def test_ozelliklerde_belgelenen_tuslar_hayalet_degil(qapp, monkeypatch):
    """TERS YÖN: Özellikler'de yazan her tuşun bir karşılığı olmalı.

    Mevcut kapı yalnız "kayıtlı -> belgeli" yönünü deniyordu; F1'in yanlış
    tuşu (hiç kaydedilmemiş Ctrl+Shift+N) ancak bu yönde yakalanır.
    """
    _kis, ozl = _yardim_diyaloglari(monkeypatch)
    kayitli = _kayitli_kisayollar(_mw_kaynak())

    # Editörde/olay süzgecinde işlenenler kaynakta `Key_*` olarak geçiyor
    editor = io.open(os.path.join(_ROOT, "desktop", "gui", "editor.py"),
                     encoding="utf-8").read()
    baska = editor + _mw_kaynak()

    def _islenmis(tus: str) -> bool:
        ad = tus.split("+")[-1]
        if re.fullmatch(r"F\d{1,2}", ad):
            return ("Key_" + ad) in baska
        if len(ad) == 1:
            return ("Key_" + ad.upper()) in baska
        return ("Key_" + ad.capitalize()) in baska

    # Fare hareketi tuş dizisi değil: Ctrl+tekerlek `wheelEvent` içinde
    # ControlModifier ile işleniyor (pdf_viewer_mixins/_navigation.py).
    # Ctrl+C / Ctrl+V QScintilla'nın kendi düzenleme tuşları.
    MUAF = {"Ctrl+tekerlek", "Ctrl+wheel", "Ctrl+C", "Ctrl+V"}

    adaylar = set(re.findall(
        r"\b((?:Ctrl|Alt|Shift)\+(?:Shift\+)?[A-Za-z0-9/]+)\b", ozl))
    adaylar |= set(re.findall(r"\b(F\d{1,2})\b", ozl))
    assert len(adaylar) >= 10, f"kapı boşa düşmesin, tuş bulunamadı: {adaylar}"

    hayalet = sorted(a for a in adaylar
                     if a not in kayitli and a not in MUAF and not _islenmis(a))
    assert not hayalet, (
        f"Özellikler'de yazan ama hiçbir yerde işlenmeyen tuş: {hayalet}. "
        "Kullanıcı basıyor ve hiçbir şey olmuyor.")


def test_ozelliklerde_her_baslikin_altinda_aciklamasi_var(qapp, monkeypatch):
    """Bir başlık doğrudan başka bir başlığı izlememeli.

    Yazım Denetimi bloğu "Klasörde Ara" başlığı ile açıklaması ARASINA
    eklenmişti: kullanıcı "Klasörde Ara"yı açıklamasız görüyor, klasör
    aramasını anlatan paragraf iki blok aşağıda sahipsiz duruyordu
    (ölçüldü 2026-09-05).
    """
    _kis, ozl = _yardim_diyaloglari(monkeypatch)
    ardisik = re.findall(r"</b><br>\s*<b>", ozl)
    assert not ardisik, (
        f"{len(ardisik)} başlık doğrudan başka bir başlığı izliyor, "
        "aralarındaki açıklama kaymış olabilir")
    # Kapı boşa düşmesin: gerçekten başlık var mı
    assert ozl.count("</b><br>") >= 10, ozl.count("</b><br>")
