"""error_hints + OutputPanel ipucu sunumu testleri."""

import re

import pytest

from core.error_hints import get_hint


# =====================================================================
# Kalıp tanıma (gerçek derleyici çıktısı alıntıları)
# =====================================================================


def test_undefined_control_with_context():
    h = get_hint("Undefined control sequence.", "l.42 \\textbf{x} kalan")
    assert h is not None
    assert h[0] == "undefined_control"
    assert h[1] == {"cmd": "\\textbf"}


def test_undefined_control_without_context():
    assert get_hint("Undefined control sequence.") == ("undefined_control", {})


def test_missing_math():
    assert get_hint("Missing $ inserted.")[0] == "missing_math"
    assert get_hint("LaTeX Error: Display math should end with $$")[0] == "missing_math"


def test_invalid_character():
    assert get_hint("Text line contains an invalid character.")[0] == "invalid_character"


def test_brace_mismatch_variants():
    for msg in ("Missing } inserted", "Too many }'s", "Extra }, or forgotten \\end"):
        assert get_hint(msg)[0] == "brace_mismatch", msg


def test_double_subscript():
    assert get_hint("Double subscript.")[0] == "double_subscript"
    assert get_hint("Double superscript.")[0] == "double_subscript"


def test_env_undefined():
    h = get_hint("LaTeX Error: Environment tikzpicture undefined.")
    assert h == ("env_undefined", {"env": "tikzpicture"})


def test_file_ended_scanning():
    assert get_hint("File ended while scanning use of \\label.")[0] == "file_ended_scanning"


def test_emergency_stop():
    assert get_hint("Emergency stop.")[0] == "emergency_stop"


def test_counter_too_large():
    assert get_hint("LaTeX Error: Counter too large.")[0] == "counter_too_large"


def test_misplaced_noalign():
    assert get_hint("Misplaced \\noalign.")[0] == "misplaced_noalign"
    assert get_hint("Misplaced \\omit.")[0] == "misplaced_noalign"


def test_citation_undefined():
    h = get_hint("Citation `balli2020' undefined on input line 55.")
    assert h[0] == "citation_undefined"


def test_reference_undefined():
    assert get_hint("Reference `fig:sonuc' on page 3 undefined")[0] == "reference_undefined"


def test_rerun_needed():
    assert get_hint("There were undefined references.")[0] == "rerun_needed"
    assert get_hint("Label(s) may have changed. Rerun to get cross-references right.")[0] == "rerun_needed"


def test_duplicate_label():
    h = get_hint("pdfTeX warning (ext4): destination with the same identifier "
                 "(name{fig:sonuc}) has been already used, duplicate ignored")
    assert h[0] == "duplicate_label"


def test_unknown_returns_none():
    assert get_hint("LaTeX Error: File `foo.sty' not found.") is None
    assert get_hint("[babel] something odd") is None
    assert get_hint("") is None


def test_inputenc_unicode_smart_quotes():
    msg = ("Unicode character ” (U+201D) not set up for use with LaTeX")
    assert get_hint(msg)[0] == "invalid_character"


def test_pdftex_duplicate_destination():
    msg = ("destination with the same identifier (name{fig:sonuc}) "
           "has been already used, duplicate ignored")
    assert get_hint(msg)[0] == "duplicate_label"


def test_latex_multiply_defined_label():
    assert get_hint("Label `ciftEtiket' multiply defined.")[0] == "duplicate_label"
    assert get_hint("There were multiply-defined labels.")[0] == "duplicate_label"


def test_listings_language_turkish_babel():
    """Regression: Türkçe babel + tek harflik dil adı (C) listings'in lehçe
    çözümlemesini bozuyor; gerçek üretim hatası bu iki mesajla geliyordu."""
    assert get_hint("Package Listings Error: Couldn't load requested language.")[0] \
        == "listings_language"
    assert get_hint("Package Listings Error: language ansi of c undefined.")[0] \
        == "listings_language"
    # yanlış yazılmış dil adı da aynı kalıba düşer
    assert get_hint("language xyz of abc undefined.")[0] == "listings_language"


def test_eksik_glif_yazi_tipini_cikariyor():
    """XeLaTeX/LuaLaTeX + [T1]{fontenc}: Türkçeye özgü harfler sessizce düşer.

    Derleme BAŞARILI biter, PDF açılır, harf yoktur. 2026-09-03'te ölçüldü,
    aynı belge (C:\\latex-demo) üç kez derlendi:
        pdflatex + fontenc       -> 92 Türkçe harf
        XeTeX    + fontenc       -> 37   (ş 0, ı 0, İ 0, ğ 0)
        XeTeX    fontenc olmadan -> 92   (birebir aynı, sıfır uyarı)
    ü, ö, ç sağ kalıyor çünkü T1 yuvaları var; kusurun gözden kaçma sebebi bu.
    """
    h = get_hint("Missing character: There is no ş (U+015F) in font ec-lmr10!")
    assert h is not None
    assert h[0] == "missing_glyph"
    assert h[1] == {"font": "ec-lmr10"}


def test_eksik_glif_onaltilik_bicimi_de_taniyor():
    """XeTeX bazı loglarda karakteri ^^^^ ve onaltılık kodla yazıyor."""
    h = get_hint('Missing character: There is no ^^^^015f ("15F) in font ec-lmri10!')
    assert h[0] == "missing_glyph"
    assert h[1]["font"] == "ec-lmri10"


def test_eksik_glif_baska_missing_mesajlarini_calmiyor():
    """Desen _PATTERNS döngüsünden ÖNCE koşuyor; komşularını yutmamalı."""
    assert get_hint("Missing $ inserted.")[0] == "missing_math"
    assert get_hint("Missing } inserted.")[0] == "brace_mismatch"


# =====================================================================
# _hint_text: şablonlardaki gerçek LaTeX parantezleri format() tuzağına
# düşmemeli (KeyError show_result'i kesip Log sekmesini boş bırakıyordu)
# =====================================================================


def test_hint_text_sablon_parantezleri_guvenli(qapp):
    from gui.output_panel import OutputPanel

    # listings ipucu: '{babel}' ve '{[ANSI]C}' gerçek metin, yer tutucu değil
    text = OutputPanel._hint_text(("listings_language", {}))
    assert "{[ANSI]C}" in text and "babel" in text

    # mevcut gizli tuzak: file_ended_scanning '\\end{...}' içeriyordu
    text = OutputPanel._hint_text(("file_ended_scanning", {}))
    assert "\\end{...}" in text

    # parametreli şablonlar ikame yoluyla çalışmaya devam etmeli
    text = OutputPanel._hint_text(("undefined_control", {"cmd": "\\textbf"}))
    assert "(\\textbf)" in text
    text = OutputPanel._hint_text(("env_undefined", {"env": "deneme"}))
    assert "deneme" in text


def test_missing_glyph_sablonu_fontenc_kelimesini_yemiyor(qapp):
    """'{font}' yer tutucusu ile literal '{fontenc}' aynı şablonda.

    Çakışmıyorlar çünkü '{font}' kapanış parantezi ister, '{fontenc}' orada
    'e' taşır. Ama ikisi yan yana durduğu için bu incelik test edilmeden
    bırakılmamalı: yer tutucu adı bir gün '{fo}' olursa sessizce bozulur.
    """
    from gui.output_panel import OutputPanel

    text = OutputPanel._hint_text(("missing_glyph", {"font": "ec-lmr10"}))
    assert "ec-lmr10" in text            # yer tutucu dolduruldu
    assert "[T1]{fontenc}" in text       # literal LaTeX parantezi bozulmadı
    assert "{font}" not in text          # yer tutucu artık yok
    assert "iftex" in text               # düzeltme önerisi duruyor


def test_her_ipucu_kimliginin_sablonu_var(qapp):
    """Şablonu unutulan ipucu _hint_text'ten SESSİZCE '' döner.

    Kullanıcı hiçbir şey görmez, hata da alınmaz. Bu kapı olmadan yeni bir
    kalıp eklerken şablonu unutmak fark edilmez.
    """
    from core import error_hints
    from gui.output_panel import OutputPanel, _hint_templates

    kimlikler = {hid for _pat, hid in error_hints._PATTERNS}
    kimlikler |= {"env_undefined", "missing_glyph"}  # parametreli olanlar
    sablonlar = set(_hint_templates())
    eksik = kimlikler - sablonlar
    assert not eksik, "sablonu olmayan ipucu kimligi: %s" % sorted(eksik)
    for hid in sorted(kimlikler):
        assert OutputPanel._hint_text((hid, {})) != "", hid


def test_show_result_listings_hatasi_logu_doldurur(qapp):
    """Kullanıcının yaşadığı semptom: listings hatası ipucu üretince
    show_result patlıyor, Ham çıktı (Log) sekmesi boş kalıyordu."""
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
    from core.log_parser import CompileResult, LatexError

    panel = OutputPanel(theme=THEMES["dark"])
    result = CompileResult(success=False, raw_output="[derleniyor] bolum2 ...\n"
                          "[hata] derleme basarisiz\n")
    result.errors = [
        LatexError(message="Package Listings Error: Couldn't load requested language."),
        LatexError(message="Package Listings Error: language ansi of c undefined."),
    ]
    panel.show_result(result)          # patlamamalı
    assert panel._error_list.count() == 2
    assert panel._log_text.toPlainText() != "", "Log sekmesi bos kalmamali"
    assert "babel" in panel._error_list.item(0).text()  # ipucu satırda


# =====================================================================
# log_parser: pdfTeX/LuaTeX motor uyarıları artık yakalanır
# =====================================================================


def test_log_parser_captures_engine_warning():
    from core.log_parser import parse_output

    raw = ("pdfTeX warning (ext4): destination with the same identifier "
           "(name{ciftEtiket}) has been already used, duplicate ignored\n")
    result = parse_output(raw)
    assert len(result.warnings) == 1
    assert result.warnings[0].warning_type == "pdfTeX"
    assert "destination" in result.warnings[0].message


# =====================================================================
# OutputPanel sunumu
# =====================================================================


try:
    from PyQt6.QtWidgets import QApplication
    from gui.output_panel import OutputPanel
    from core.log_parser import LatexError, LatexWarning
    from gui.theme import THEMES
    from tests.stub_main import StubMain  # noqa: F401 — dönüşümlü qapp fixture
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_panel_error_shows_hint(qapp):
    panel = OutputPanel(theme=THEMES["dark"])
    from core.log_parser import CompileResult

    result = CompileResult(success=False)
    result.errors = [LatexError(
        line_number=42, message="Undefined control sequence.",
        context="l.42 \\badcmd{x}", file_path="m.tex")]
    panel.show_result(result)

    item = panel._error_list.item(0)
    text = item.text()
    assert "→" in text
    assert "\\badcmd" in text
    assert "\\usepackage" in text
    assert item.toolTip()


def test_panel_warning_shows_rerun_hint(qapp):
    panel = OutputPanel(theme=THEMES["dark"])
    from core.log_parser import CompileResult

    result = CompileResult(success=False)
    result.warnings = [LatexWarning(
        line_number=55, message="Citation `x' undefined on input line 55.",
        warning_type="LaTeX")]
    panel.show_result(result)

    text = panel._warn_list.item(0).text()
    assert "→" in text
    assert "tekrar derleyin" in text


def test_panel_unknown_error_no_hint(qapp):
    panel = OutputPanel(theme=THEMES["dark"])
    from core.log_parser import CompileResult

    result = CompileResult(success=False)
    result.errors = [LatexError(line_number=3, message="[babel] bilinmeyen hata")]
    panel.show_result(result)

    assert "→" not in panel._error_list.item(0).text()


# =====================================================================
# Yerelleştirme: ipuçları ÇAĞRI anında çevrilir (import-zamanı donması yok)
# =====================================================================


def test_hint_localized_to_english(qapp):
    """İngilizce çevirici yüklüyken ipucu İngilizce dönmeli.

    Regression: _HINTS sözlüğü modül import'u sırasında değerlendiriliyordu;
    çevirici yüklenmeden donduğu için İngilizce arayüzde bile Türkçe
    görünüyordu. Şablonlar artık _hint_templates() çağrısında üretiliyor.
    """
    from PyQt6.QtCore import QTranslator

    tr_text = OutputPanel._hint_text(("undefined_control", {}))
    assert "Tanımsız komut" in tr_text  # kaynak dil (çevirici yoksa)

    t = QTranslator()
    qm = str(__import__("pathlib").Path(__file__).resolve().parents[1]
             / "desktop" / "translations" / "latexeditor_en.qm")
    if not t.load(qm):  # pragma: no cover — .qm derili olmalı
        pytest.skip("latexeditor_en.qm bulunamadı")
    app = QApplication.instance()
    app.installTranslator(t)
    try:
        en_text = OutputPanel._hint_text(("undefined_control", {}))
        assert "Unknown command" in en_text, en_text
        assert "Tanımsız komut" not in en_text
    finally:
        app.removeTranslator(t)


# =====================================================================
# Tanımsız komut: bağlam satırındaki SON komut suçludur, ilki değil
#
# TeX bağlam satırını hatanın olduğu YERDE kesiyor ve "Undefined control
# sequence" komut okunur okunmaz atılıyor; yani aranan komut satırın SON
# belirteci oluyor. Kod ilkini alıyordu. Depodaki 59 gerçek şablonun 135330
# komut geçişi üzerinde ölçüldü: %49.8 doğru, %10.8 boş, %39.4 YANLIŞ komut.
#
# Yanlış olan en kötüsü, çünkü sessiz değil: panelde "Tanımsız komut
# (\textbf): ... paketi yüklenmemiş olabilir" yazıyordu ve kullanıcı gayet
# çalışan bir çekirdek komut için olmayan bir paketin peşine düşüyordu.
#
# Bağlam dizgeleri GERÇEK pdflatex çıktısından alındı; aynı vakalar canlı
# derlemeyle tests/test_ipucu_derleme.py'de de koşuyor.
# =====================================================================


class TestTanimsizKomutSonBelirtec:
    @pytest.mark.parametrize("ctx,beklenen", [
        # tek komut: ilk = son, eski davranışla aynı sonuç
        (r"l.3 \bilinmeyenkomut", r"\bilinmeyenkomut"),
        # önce düz metin var: eskiden komut adı HİÇ yazılmıyordu
        (r"l.3 Merhaba \bilinmeyenkomut", r"\bilinmeyenkomut"),
        (r"l.5 Bu bolumde \ozelKomut", r"\ozelKomut"),
        # önce GEÇERLİ komut var: eskiden O suçlanıyordu
        (r"l.3 \textbf{Kalin} \bilinmeyenkomut", r"\bilinmeyenkomut"),
        (r"l.3 \emph{a} \textit{b} \textbf{c} \sonuncu", r"\sonuncu"),
        # başka bir komutun argümanı içinde
        (r"l.3 \textbf{\icerdekiKomut", r"\icerdekiKomut"),
        # matematik içinde
        (r"l.3 $x = \alpha + \tanimsizFonksiyon", r"\tanimsizFonksiyon"),
        # köşeli parantezde bitişik komut (template1'de gerçekten var)
        (r"l.44 \author[1\orc", r"\orc"),
    ])
    def test_son_komut_aliniyor(self, ctx, beklenen):
        h = get_hint("Undefined control sequence.", ctx)
        assert h[0] == "undefined_control"
        assert h[1] == {"cmd": beklenen}, ctx

    @pytest.mark.parametrize("ctx", [
        r"l.3 \textbf{Kalin} \bilinmeyenkomut",
        r"l.3 \emph{a} \textit{b} \textbf{c} \sonuncu",
        r"l.44 \author[1\orc",
    ])
    def test_ilk_komut_ARTIK_suclanmiyor(self, ctx):
        """Karşı yön: eski davranışın verdiği yanıt artık çıkmamalı.

        Vaka önkoşulunu da doğruluyor, yoksa kapı boşalır: satırda birden
        fazla komut YOKSA ilk ile son aynı olur ve test hiçbir şey ölçmez.
        """
        komutlar = re.findall(r"\\[A-Za-z]+", ctx)
        assert len(komutlar) > 1, "vakada tek komut var, ayrım sınanamaz"
        assert get_hint("Undefined control sequence.", ctx)[1]["cmd"] \
            != komutlar[0]

    @pytest.mark.parametrize("ctx", [
        "",                       # bağlam yok
        "l.7 duz metin",          # satırda hiç komut yok
        r"\foo \bar",             # l. işaretçisi yok
    ])
    def test_cikarilamayan_baglamda_parametre_yok(self, ctx):
        """Şablon '{cmd}' yer tutucusunu boşa indiriyor; sessiz kalmalı."""
        assert get_hint("Undefined control sequence.", ctx) == \
            ("undefined_control", {})

    def test_kontrol_sozcugu_yalniz_harf(self):
        r"""TeX'te `\foo_bar` = `\foo` + `_bar`; alt çizgi ada dahil değil."""
        h = get_hint("Undefined control sequence.", r"l.5 metin \foo_bar")
        assert h[1] == {"cmd": r"\foo"}

    def test_baglam_yalniz_undefined_control_icin_okunuyor(self):
        """Diğer ipuçlarına yanlışlıkla cmd sızmamalı."""
        h = get_hint("Missing $ inserted.", r"l.3 \textbf{x} \foo")
        assert h == ("missing_math", {})
