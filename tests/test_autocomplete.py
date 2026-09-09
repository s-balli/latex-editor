"""EditorWidget otomatik tamamlama kapanış testleri (A.2).

Popup'tan seçilen \\cmd{ / \\cmd[ girdisi SCN_AUTOCCOMPLETED ile geldiğinde,
keyPressEvent atlandığı için normal autopair tetiklenmez. _on_autoc_completed
karşılık gelen } / ] ekler; böylece elle yazılan komutla popup'tan seçilen
aynı komut tutarlı olur (ikisi de çiftlenmiş ayraç verir).
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.Qsci import QsciScintilla
    from gui.editor import EditorWidget
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui.editor import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _editor():
    return EditorWidget()


def _line(ed, n):
    return ed.text(n).rstrip("\n")


# --- _on_autoc_completed birim testleri ---


def test_autoclose_brace_on_completed_frac(qapp):
    r"""Seçilen \frac{ -> \frac{}, imleç { ve } arasında (index 6)."""
    ed = _editor()
    ed.setText("\\frac{")
    ed.setCursorPosition(0, 6)
    ed._on_autoc_completed(b"\\frac{", 0, 0, 5)
    assert _line(ed, 0) == "\\frac{}"
    assert ed.getCursorPosition() == (0, 6)  # { ve } arası


def test_autoclose_bracket_on_completed_item(qapp):
    r"""Seçilen \item[ -> \item[], imleç [ ve ] arasında."""
    ed = _editor()
    ed.setText("\\item[")
    ed.setCursorPosition(0, 6)
    ed._on_autoc_completed(b"\\item[", 0, 0, 5)
    assert _line(ed, 0) == "\\item[]"
    assert ed.getCursorPosition() == (0, 6)


def test_no_autoclose_for_begin(qapp):
    r"""\begin{ kapanmamalı: ayracı kasıtlı eşlenmez (begin/end kapanışı ayrı)."""
    ed = _editor()
    ed.setText("\\begin{")
    ed.setCursorPosition(0, 7)
    ed._on_autoc_completed(b"\\begin{", 0, 0, 6)
    assert _line(ed, 0) == "\\begin{"  # değişmedi


def test_no_autoclose_for_end(qapp):
    r"""Simetri: \end{ de kapanmamalı."""
    ed = _editor()
    ed.setText("\\end{")
    ed.setCursorPosition(0, 5)
    ed._on_autoc_completed(b"\\end{", 0, 0, 4)
    assert _line(ed, 0) == "\\end{"


def test_no_autoclose_for_left_paren(qapp):
    r"""\left( ayraç-sözdizimi: regex eşleşmez, kapanış eklenmez."""
    ed = _editor()
    ed.setText("\\left(")
    ed.setCursorPosition(0, 6)
    ed._on_autoc_completed(b"\\left(", 0, 0, 5)
    assert _line(ed, 0) == "\\left("


def test_no_autoclose_for_left_brace(qapp):
    r"""\left\{ ayraç-sözdizimi (\ ile gelir): regex eşleşmez."""
    ed = _editor()
    ed.setText("\\left\\{")
    ed.setCursorPosition(0, 7)
    ed._on_autoc_completed(b"\\left\\{", 0, 0, 6)
    assert _line(ed, 0) == "\\left\\{"


def test_no_double_close_if_already_paired(qapp):
    r"""İmleçten sonra zaten } varsa (manuel autopair akışı) çiftleme."""
    ed = _editor()
    ed.setText("\\frac{}")
    ed.setCursorPosition(0, 6)  # mevcut } önünde
    ed._on_autoc_completed(b"\\frac{", 0, 0, 5)
    assert _line(ed, 0) == "\\frac{}"  # ikinci } eklenmedi


def test_no_close_for_plain_command(qapp):
    r"""Argümansız komut (\sum) -> kapanış yok."""
    ed = _editor()
    ed.setText("\\sum")
    ed.setCursorPosition(0, 4)
    ed._on_autoc_completed(b"\\sum", 0, 0, 4)
    assert _line(ed, 0) == "\\sum"


def test_handles_invalid_text_safely(qapp):
    r"""Geçersiz/bozuk signal argümanı istisna fırlatmamalı."""
    ed = _editor()
    ed.setText("x")
    ed.setCursorPosition(0, 1)
    # Hatalı tipte argüman — bytes() dönüşümü patlarsa yakalanmalı
    ed._on_autoc_completed(object(), 0, 0, 0)
    assert _line(ed, 0) == "x"


# --- Uçtan uca: gerçek SCI_AUTOCCOMPLETE sinyal akışı ---


def test_completion_end_to_end_closes_brace(qapp):
    r"""Gerçek popup tamamlaması (SCI_AUTOCCOMPLETE) kapanışı tetiklemeli."""
    ed = _editor()
    ed.setText("\\frac")
    ed.setCursorPosition(0, 5)
    ed.SendScintilla(QsciScintilla.SCI_AUTOCSETSEPARATOR, ord(' '))
    ed.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, 5, b"\\frac{")
    assert ed.SendScintilla(QsciScintilla.SCI_AUTOCACTIVE)
    ed.SendScintilla(QsciScintilla.SCI_AUTOCCOMPLETE)
    qapp.processEvents()  # SCN_AUTOCCOMPLETED işlensin
    assert _line(ed, 0) == "\\frac{}"
    assert ed.getCursorPosition() == (0, 6)


# --- Boşluk filtresi tek kaynakta (2026-08-30 denetimi, F5) ---

def _gosterilen(ed, monkeypatch) -> list[str]:
    """_popup_goster'in Scintilla'ya verdiği aday listesini yakala."""
    yakalanan = []
    orij = ed.SendScintilla

    def sahte(mesaj, *a):
        if mesaj == QsciScintilla.SCI_AUTOCSHOW and a:
            yakalanan.append(a[-1].decode("utf-8").split(" "))
            return 0
        return orij(mesaj, *a)

    monkeypatch.setattr(ed, "SendScintilla", sahte)
    return yakalanan


def test_bosluklu_aday_tum_tamamlamalarda_eleniyor(qapp, monkeypatch):
    r"""Liste ayırıcısı boşluk: adında boşluk geçen aday listeyi bozuyor.

    Filtre eskiden 6 popup çağrısının yalnız 2'sinde vardı; \label{fig: bir}
    gibi bir etiket \ref tamamlamasında listeyi iki sahte öğeye bölüyordu.
    Artık filtre _popup_goster içinde, yani hepsinde.
    """
    ed = _editor()
    ed.setText("\\label{fig:temiz}\n\\label{fig: bosluklu}\n")
    yakalanan = _gosterilen(ed, monkeypatch)

    ed._show_ref_completion("fig:")
    assert yakalanan, "popup hiç gösterilmedi"
    adaylar = yakalanan[0]
    assert "fig:temiz" in adaylar
    assert not any(" " in a for a in adaylar)
    assert not any("bosluklu" in a for a in adaylar), adaylar


def test_bosluklu_adaylarin_hepsi_elenince_popup_acilmiyor(qapp, monkeypatch):
    """Filtre sonrası liste boşalırsa popup hiç gösterilmemeli."""
    ed = _editor()
    yakalanan = _gosterilen(ed, monkeypatch)
    ed._popup_goster(["bir tane", "iki tane"], "b")
    assert yakalanan == [], "boş listeyle popup açıldı"


def test_tek_popup_cagri_yeri_kaldi():
    """6 kopya tek yardımcıya indi; yenisi eklenirse filtre yine atlanmasın."""
    import io
    import os
    yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "desktop", "gui", "editor.py")
    kaynak = io.open(yol, encoding="utf-8").read()
    assert kaynak.count("SCI_AUTOCSHOW") == 1, (
        "editor.py'de birden fazla SCI_AUTOCSHOW çağrısı var — "
        "popup gösterimi _popup_goster üzerinden yapılmalı (boşluk filtresi orada)")


# =====================================================================
# Komut ailesi TEK KAYNAKTAN: editor.py'nin üç kopyası vardı
#
# `core/latex_refs` ailesi 36a00c0'da genişletildi (cleveref, varioref,
# biblatex, yıldızlı biçimler) ama editor.py'deki üç kopya güncellenmedi.
# ÖLÇÜLDÜ (2026-09-09), üç ayrı sonuç:
#
#   tamamlama popup'ı : 11 referans + 10 atıf komutunda AÇILMIYOR
#   Alt+tık tanıma git: 9 vakada çalışmıyor
#   F2 anahtar bulma  : 9 vakada çalışmıyor
#
# Yani biblatex kullanan biri `\autocite{` yazınca anahtar listesi
# gelmiyor, üstüne Alt+tık yapınca bir yere gitmiyor, F2 ile adını
# değiştiremiyordu.
#
# Kapılar tek tek komut saymıyor: aynı listenin İKİNCİ bir kopyası çıkarsa
# yine ayrışır. Ölçüt "core.latex_refs ne diyorsa editör de onu tanıyor".
# =====================================================================

import gui.editor as gui_editor
from core.latex_refs import CITE_KOMUTLARI, REF_KOMUTLARI


@pytest.mark.parametrize("komut", sorted(REF_KOMUTLARI))
def test_TAMAMLAMA_butun_referans_ailesinde_aciliyor(qapp, komut):
    """Kırılırsa kullanıcı o komutta etiket listesini hiç görmüyor."""
    ed = EditorWidget()
    cagrildi = []
    ed._show_ref_completion = lambda *a, **k: cagrildi.append("ref")
    metin = "\\%s{" % komut
    ed.setText(metin)
    ed.setCursorPosition(0, len(metin))

    ed._check_autocomplete()

    assert cagrildi == ["ref"], komut


@pytest.mark.parametrize("komut", sorted(CITE_KOMUTLARI))
def test_TAMAMLAMA_butun_atif_ailesinde_aciliyor(qapp, komut):
    ed = EditorWidget()
    cagrildi = []
    ed._show_cite_completion = lambda *a, **k: cagrildi.append("cite")
    metin = "\\%s{" % komut
    ed.setText(metin)
    ed.setCursorPosition(0, len(metin))

    ed._check_autocomplete()

    assert cagrildi == ["cite"], komut


@pytest.mark.parametrize("komut", sorted(REF_KOMUTLARI))
def test_ALT_TIK_butun_referans_ailesinde_anahtari_buluyor(qapp, komut):
    """Kırılırsa Alt+tık o komutta hiçbir yere gitmiyor."""
    ed = EditorWidget()
    satir = "Bkz. \\%s{fig:a} devam" % komut

    assert ed._ref_cite_key_at(satir, satir.index("fig:a") + 1) == \
        ("fig:a", "label")


@pytest.mark.parametrize("komut", sorted(CITE_KOMUTLARI))
def test_ALT_TIK_butun_atif_ailesinde_anahtari_buluyor(qapp, komut):
    ed = EditorWidget()
    satir = "Bkz. \\%s{k1} devam" % komut

    assert ed._ref_cite_key_at(satir, satir.index("k1") + 1) == ("k1", "cite")


@pytest.mark.parametrize("komut", sorted(REF_KOMUTLARI))
def test_F2_butun_referans_ailesinde_anahtari_buluyor(qapp, komut):
    ed = EditorWidget()
    satir = "Bkz. \\%s{fig:a} devam" % komut

    assert ed._nearest_family_hit(satir, satir.index("fig:a") + 1) == \
        ("fig:a", "label")


@pytest.mark.parametrize("komut,tur", [
    ("ref", "ref"), ("eqref", "ref"), ("autoref", "ref"), ("nameref", "ref"),
    ("cref", "ref"), ("Cref", "ref"), ("cpageref", "ref"),
    ("labelcref", "ref"), ("crefrange", "ref"), ("vref", "ref"),
    ("vpageref", "ref"), ("fullref", "ref"),
    ("cite", "cite"), ("citep", "cite"), ("citet", "cite"),
    ("parencite", "cite"), ("textcite", "cite"), ("autocite", "cite"),
    ("footcite", "cite"), ("smartcite", "cite"), ("citealt", "cite"),
    ("citenum", "cite"), ("citeyearpar", "cite"), ("nocite", "cite"),
])
def test_AILE_bu_komutlari_TASIMAK_ZORUNDA(qapp, komut, tur):
    """Öteki kapılar aileyi `REF_KOMUTLARI`/`CITE_KOMUTLARI` üzerinden
    geziyor, yani liste KÜÇÜLÜRSE onlar da küçülüp sessizce geçer (mutasyonla
    ölçüldü: aralık komutları listeden düşünce 12 vaka kayboldu ve hiçbir
    kapı yanmadı). Bu kapı aileyi DIŞARIDAN çapalıyor."""
    hedef = REF_KOMUTLARI if tur == "ref" else CITE_KOMUTLARI
    assert komut in hedef

    ed = EditorWidget()
    cagrildi = []
    ed._show_ref_completion = lambda *a, **k: cagrildi.append("ref")
    ed._show_cite_completion = lambda *a, **k: cagrildi.append("cite")
    metin = "\\%s{" % komut
    ed.setText(metin)
    ed.setCursorPosition(0, len(metin))

    ed._check_autocomplete()

    assert cagrildi == [tur], komut


def test_YILDIZLI_bicimler_de_taniniyor(qapp):
    """hyperref/cleveref bağlantısız biçimi yıldızla yazıyor; ölçümde
    kaçan grubun büyük kısmı buydu."""
    ed = EditorWidget()
    for satir, anahtar, tur in (
            ("Bkz. \\ref*{fig:a}", "fig:a", "label"),
            ("Bkz. \\autoref*{fig:a}", "fig:a", "label"),
            ("Bkz. \\cref*{fig:a}", "fig:a", "label"),
            ("Bkz. \\citep*{k1}", "k1", "cite")):
        assert ed._ref_cite_key_at(satir, satir.index(anahtar) + 1) == \
            (anahtar, tur), satir


def test_ARALIK_komutunun_IKINCI_anahtarinda_da_aciliyor(qapp):
    r"""`\crefrange{ilk}{son}` iki etikete başvuruyor; ikincisini yazarken
    de liste gelmeli."""
    ed = EditorWidget()
    cagrildi = []
    ed._show_ref_completion = lambda *a, **k: cagrildi.append("ref")
    metin = "\\crefrange{fig:a}{"
    ed.setText(metin)
    ed.setCursorPosition(0, len(metin))

    ed._check_autocomplete()

    assert cagrildi == ["ref"]


# --- Aşırı düzeltme kapıları ---

def test_KOPYA_LISTE_KALMADI(qapp):
    """editor.py aileyi bir daha KENDİ yazmamalı: kusurun kökü kopyaydı,
    üçü de core.latex_refs'ten türetiliyor."""
    import io
    import os
    yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
        gui_editor.__file__))), "gui", "editor.py")
    kaynak = io.open(yol, encoding="utf-8", newline="").read()
    for desen in ("eqref|pageref", "citep|citet"):
        assert desen not in kaynak, (
            "editor.py yine kendi aile listesini tutuyor: %r" % desen)


def test_BASKA_komutlar_tamamlama_ACMIYOR(qapp):
    r"""Aile genişledi diye `\ref`/`\cite` ile BAŞLAYAN her komut tetikleyici
    olmamalı."""
    ed = EditorWidget()
    cagrildi = []
    ed._show_ref_completion = lambda *a, **k: cagrildi.append("ref")
    ed._show_cite_completion = lambda *a, **k: cagrildi.append("cite")
    # Son iki vaka aralık kolunun kapsamı: İKİNCİ küme yalnız aralık
    # komutlarında anahtar demek. Tekil komutlarda da açılsaydı
    # `\ref{fig:a}{\bfseries x}` yazarken liste patlardı.
    for metin in ("\\refstepcounter{", "\\reflectbox{", "\\citecolor{",
                  "\\mycite{", "\\ref{fig:a}{", "\\cite{k1}{"):
        cagrildi.clear()
        ed.setText(metin)
        ed.setCursorPosition(0, len(metin))
        ed._check_autocomplete()
        assert cagrildi == [], metin
