"""OutputPanel tema renkleri: bayat renk, sarkan QSS bildirimi, öneri ayrımı.

Üç gerçek kusur bu kapıların yokluğundan geçti (2026-09-05):

F1. `apply_theme` Yazım sekmesinin hiçbir widget'ına dokunmuyordu. `show_yazim`
    öğe renklerini o anki temanın `fg_primary`'siyle boyuyor; koyu temada
    denetleyip açık temaya geçen kullanıcı bulguları göremiyordu (render'dan
    ölçüldü: light 1.40, solarized_light 1.49 karşıtlık). Aynı kusur daha önce
    `_history_list` için görülüp düzeltilmişti, yeni sekmede tekrarlandı.

F2. Öneriler listesinin stylesheet rengi `sem_suggestion`, `apply_theme`'in
    döngüsü ise hepsini `sem_hint` yapıyordu. Derlemeden sonra turkuaz olan
    satırlar tema değişince turuncuya dönüyor ve gerçek ipucu satırlarından
    (motor önerisi, "derlenemez") ayırt edilemiyordu.

F3. `f"{list_base} color: ...;"` yazılıyordu; `list_base` bir `}` ile bittiği için renk
    bildirimi hiçbir seçiciye ait değildi ve Qt onu sessizce atıyordu
    (ölçüldü: aynı bildirim blok dışında 0, blok içinde 280 piksel boyuyor).
    `show_result`'ın eklediği satırlar anlamsal rengini hiç almıyordu; ayrım
    ancak tema yeniden uygulanınca ortaya çıkıyordu.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.file_tree import FileTree
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)

from core.log_parser import (CompileResult, LatexError, LatexSuggestion,
                             LatexWarning)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Bulgu:
    """core.yazim bulgusunun panelin kullandığı üç alanı."""
    satir, sutun, kelime = 3, 5, "yanlisyazilmiskelime"


def _dolu_panel(tema="dark"):
    """Her sekmesi dolu bir panel: bayat renk ancak öğe varken görülür."""
    p = OutputPanel(theme=THEMES[tema])
    r = CompileResult(success=False)
    r.errors = [LatexError(message="! Undefined control sequence.", line_number=3)]
    r.warnings = [LatexWarning(message="Overfull hbox", line_number=7)]
    r.suggestions = [LatexSuggestion(message="Eksik paket: x",
                                     install_command="sudo apt-get install x")]
    p.show_result(r)
    p.show_yazim([_Bulgu()], "/tmp/a.tex", 100)
    p.show_history([])
    return p


_LISTELER = ("_error_list", "_warn_list", "_suggest_list",
             "_history_list", "_psearch_list", "_yazim_list")


# --- F3: sarkan QSS bildirimi ---

def _sarkan_bildirim(qss: str) -> str:
    """Son `}` sonrasında kalan metin. Qt onu sessizce atar.

    Seçicisiz stylesheet (`"color: red;"`) GEÇERLİDİR ve widget'ın kendisine
    uygulanır; yalnız blok İÇEREN bir sayfanın sonuna eklenen bildirim düşer.
    """
    if "}" not in qss:
        return ""
    return qss[qss.rfind("}") + 1:].strip()


@pytest.mark.parametrize("sinif", ["OutputPanel", "FileTree"])
def test_widget_stillerinde_SARKAN_bildirim_yok(qapp, sinif):
    """Blok dışında kalan bildirim Qt tarafından atılır, hata da vermez.

    Kırılırsa: bildirimi ait olduğu seçicinin `{ }` bloğuna taşıyın.
    """
    w = (_dolu_panel() if sinif == "OutputPanel"
         else FileTree(theme=THEMES["dark"]))
    try:
        kotu = []
        for cocuk in [w] + w.findChildren(object):
            al = getattr(cocuk, "styleSheet", None)
            if not callable(al):
                continue
            kalan = _sarkan_bildirim(al())
            if kalan:
                kotu.append("%s -> %r" % (type(cocuk).__name__, kalan))
        assert not kotu, "QSS bloğu dışında kalan bildirim: %s" % kotu
    finally:
        w.deleteLater()


def test_sarkan_bildirim_kapisi_GERCEKTEN_yakaliyor():
    """Kapının boş koşmadığının kanıtı: F3'ün birebir kendisi."""
    assert _sarkan_bildirim(
        "QListWidget { background: #1e1e1e; } color: #f55353;") == "color: #f55353;"
    # Karşı durum: düzgün stylesheet işaretlenmemeli
    assert _sarkan_bildirim(
        "QListWidget { background: #1e1e1e; color: #f55353; }") == ""
    assert _sarkan_bildirim("") == ""
    # Seçicisiz sayfa geçerli, işaretlenmemeli
    assert _sarkan_bildirim("color: #949494; font-size: 11px;") == ""


def test_liste_renkleri_QListWidget_BLOGUNUN_ICINDE(qapp):
    """Renk bloğun içinde olmalı; dışarıdayken hiç uygulanmıyordu."""
    p = _dolu_panel()
    try:
        t = THEMES["dark"]
        for a, anahtar in (("_error_list", "sem_error"),
                           ("_warn_list", "sem_warning"),
                           ("_suggest_list", "sem_suggestion")):
            qss = getattr(p, a).styleSheet()
            ilk_blok = qss[:qss.find("}")]
            assert "color: %s" % t[anahtar] in ilk_blok, \
                "%s rengi QListWidget bloğunda değil: %r" % (a, ilk_blok)
    finally:
        p.deleteLater()


# --- F1: tema değişince bayat renk kalmamalı ---

def _oge_renkleri(p):
    """Panelin tüm listelerindeki öğe renkleri (liste adı, indis, renk)."""
    out = []
    for a in _LISTELER:
        liste = getattr(p, a)
        for i in range(liste.count()):
            out.append((a, i, liste.item(i).foreground().color().name().lower()))
    return out


@pytest.mark.parametrize("hedef", sorted(THEMES))
def test_tema_degisimi_TAZE_PANELLE_ayni_renge_variyor(qapp, hedef):
    """Koyu temada doldurup hedefe geçmek, doğrudan hedefte doldurmakla aynı
    sonucu vermeli.

    Bayat rengi "eski temanın rengi" diye aramak yetmiyor: `#cccccc` hem
    dark'ın `fg_primary`'si hem light'ın `border_mid`'i, yani renk kümesi
    kesişiyor. Doğru ölçüt, tema değişiminin taze kurulumla AYNI yere
    varması. Kırılırsa: `apply_theme` o listenin öğelerini de boyamalı.
    """
    gecis = _dolu_panel("dark")
    taze = _dolu_panel(hedef)
    try:
        gecis.apply_theme(THEMES[hedef])
        taze.apply_theme(THEMES[hedef])
        a, b = _oge_renkleri(gecis), _oge_renkleri(taze)
        farkli = [(x, y) for x, y in zip(a, b) if x != y]
        assert len(a) == len(b), "liste uzunlukları tutmuyor: %d / %d" % (len(a), len(b))
        assert not farkli, "tema değişimi taze panelden farklı: %s" % farkli
    finally:
        gecis.deleteLater()
        taze.deleteLater()


def test_taze_panel_kapisi_GERCEKTEN_yakaliyor(qapp):
    """Kapının boş koşmadığının kanıtı: bir öğe elle bayat renge çekilir."""
    from PyQt6.QtGui import QColor
    gecis = _dolu_panel("dark")
    taze = _dolu_panel("light")
    try:
        gecis.apply_theme(THEMES["light"])
        taze.apply_theme(THEMES["light"])
        assert _oge_renkleri(gecis) == _oge_renkleri(taze)
        # F1'in birebir hâli: Yazım öğesi koyu temanın renginde kalıyor
        gecis._yazim_list.item(0).setForeground(
            QColor(THEMES["dark"]["fg_primary"]))
        assert _oge_renkleri(gecis) != _oge_renkleri(taze)
    finally:
        gecis.deleteLater()
        taze.deleteLater()


def test_tema_degisince_YAZIM_widgetlari_da_stilleniyor(qapp):
    """Yazım sekmesi `apply_theme`'e hiç girmiyordu (F1)."""
    p = _dolu_panel("dark")
    try:
        koyu = {a: getattr(p, a).styleSheet()
                for a in ("_yazim_list", "_yazim_durum", "_yazim_ikinci")}
        assert all(koyu.values()), "stilsiz kalan Yazım widget'ı: %s" % koyu
        p.apply_theme(THEMES["light"])
        acik = {a: getattr(p, a).styleSheet() for a in koyu}
        degismeyen = [a for a in koyu if koyu[a] == acik[a]]
        assert not degismeyen, \
            "tema değişti ama eski stilde kaldı: %s" % degismeyen
    finally:
        p.deleteLater()


# --- F2: öneri ile ipucu ayrımı ---

def _oneri_renkleri(p):
    return [p._suggest_list.item(i).foreground().color().name().lower()
            for i in range(p._suggest_list.count())]


@pytest.mark.parametrize("tema", sorted(THEMES))
def test_oneri_satirlari_sem_suggestion_ipucu_satirlari_sem_hint(qapp, tema):
    """Döngü hepsini `sem_hint` yapıyordu; stylesheet ile çakışıyordu."""
    t = THEMES[tema]
    p = OutputPanel(theme=t)
    try:
        r = CompileResult(success=False)
        r.suggestions = [LatexSuggestion(message="bir"),
                         LatexSuggestion(message="iki")]
        p.show_result(r)
        p.show_engine_hint("pdflatex", ["lualatex"])   # 0. satıra girer
        p.apply_theme(t)

        renkler = _oneri_renkleri(p)
        assert renkler[0] == t["sem_hint"].lower(), \
            "ipucu satırı sem_hint değil: %s" % renkler
        assert set(renkler[1:]) == {t["sem_suggestion"].lower()}, \
            "öneri satırları sem_suggestion değil: %s" % renkler
    finally:
        p.deleteLater()


def test_derlenemez_satiri_tema_degisiminde_de_ipucu_kaliyor(qapp):
    p = OutputPanel(theme=THEMES["dark"])
    try:
        p.show_cannot_compile("bu dosya derlenemez")
        p.apply_theme(THEMES["light"])
        assert _oneri_renkleri(p) == [THEMES["light"]["sem_hint"].lower()]
    finally:
        p.deleteLater()


def test_ortam_denetimi_satiri_ipucu_SAYILMIYOR(qapp):
    """Doktor satırı bir eylem; ipucu işareti taşımamalı, öneri rengini alır."""
    p = OutputPanel(theme=THEMES["dark"])
    try:
        r = CompileResult(success=False)
        r.suggestions = [LatexSuggestion(message="Eksik paket: x",
                                         install_command="sudo apt-get install x")]
        p.show_result(r)
        assert p._suggest_list.count() == 2      # öneri + doktor satırı
        p.apply_theme(THEMES["dark"])
        assert _oneri_renkleri(p) == \
            [THEMES["dark"]["sem_suggestion"].lower()] * 2
    finally:
        p.deleteLater()


def test_clear_sonrasi_ipucu_isareti_sizmiyor(qapp):
    """`clear()` öğeleri atar; yeni öneriler ipucu rengi almamalı."""
    p = OutputPanel(theme=THEMES["dark"])
    try:
        p.show_cannot_compile("derlenemez")
        p.clear()
        r = CompileResult(success=False)
        r.suggestions = [LatexSuggestion(message="tek")]
        p.show_result(r)
        p.apply_theme(THEMES["dark"])
        assert _oneri_renkleri(p) == [THEMES["dark"]["sem_suggestion"].lower()]
    finally:
        p.deleteLater()
