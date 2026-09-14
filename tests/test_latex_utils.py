"""latex_utils.py — strip_comments doğrudan testleri."""

from core.latex_utils import (label_gecerli_mi, label_key,
                              strip_comments)


class TestStripCommentsBasic:
    def test_no_comments(self):
        assert strip_comments("Hello World") == "Hello World"

    def test_full_line_comment(self):
        assert strip_comments("% bu bir yorum") == ""

    def test_inline_comment(self):
        assert strip_comments(r"\textbf{kalın} % yorum") == r"\textbf{kalın} "

    def test_empty_string(self):
        assert strip_comments("") == ""

    def test_only_whitespace_before_comment(self):
        assert strip_comments("    % yorum") == "    "

    def test_multiple_lines(self):
        text = "satir 1\n% yorum\nsatir 3"
        assert strip_comments(text) == "satir 1\n\nsatir 3"


class TestEscapedPercent:
    def test_escaped_percent_preserved(self):
        assert strip_comments(r"\% 50 indirim") == r"\% 50 indirim"

    def test_escaped_percent_with_comment(self):
        assert strip_comments(r"\% 50 % yorum") == r"\% 50 "

    def test_double_backslash_percent(self):
        # \\ kaçışı + % yorum
        assert strip_comments(r"\\% yorum") == r"\\"

    def test_triple_backslash_percent(self):
        assert strip_comments(r"\\\% kalı") == r"\\\% kalı"

    def test_only_escaped_percent(self):
        assert strip_comments(r"\%") == r"\%"


class TestEdgeCases:
    def test_percent_at_start(self):
        assert strip_comments("%yorum") == ""

    def test_consecutive_percents(self):
        # ilk % yorum başlatır
        assert strip_comments("%%yorum") == ""

    def test_no_trailing_newline(self):
        assert strip_comments("text") == "text"

    def test_indentation_preserved(self):
        assert strip_comments("    \\item bir % yorum") == "    \\item bir "

    def test_turkish_characters(self):
        assert strip_comments("Türkçe metin % yorum") == "Türkçe metin "

    def test_backslash_before_non_special(self):
        assert strip_comments(r"\textbf{a}") == r"\textbf{a}"

    def test_multiple_escaped_percents(self):
        assert strip_comments(r"\%10\%20 % yorum") == r"\%10\%20 "


# --- Etiket anahtarı geçerliliği: TEK KAYNAK (2026-09-14) ---


class TestLabelGecerliMi:
    r"""Aynı soru ("bu anahtar `\label` içine yazılabilir mi") ÜÇ ayrı
    yerde ÜÇ farklı cevap alıyordu: görsel ekleme ASCII dışını siliyor,
    tablo sihirbazı Türkçe'yi bırakıyor, F2 yeniden adlandırma ise
    reddediyordu. Kullanıcı uygulamanın KENDİ ürettiği `tab:Sonuç-Tablosu`
    etiketini yeniden adlandıramıyordu.

    ÖLÇÜLDÜ (2026-09-14, gerçek derleme): Türkçe harfli etiket pdflatex,
    lualatex ve xelatex'te derleniyor ve `\ref` çözülüyor. Aynı ölçümde
    Latin ek, Yunan, Kiril ve CJK de üç motorda geçti.
    """

    def test_TURKCE_ve_diger_alfabeler_kabul(self):
        for anahtar in ("tab:sonuç-çıktı", "fig:Ölçüm_Değerleri",
                        "sec:Giriş", "tab:café", "eq:αβ", "fig:日本"):
            assert label_gecerli_mi(anahtar), anahtar

    def test_DERLEMEYI_KIRANLAR_reddediliyor(self):
        """Karşı yön: ölçülen beş kırıcı ve boşluk geçmemeli."""
        for anahtar in ("tab:a%b", "tab:a{b", "tab:a}b", "tab:a\\b",
                        "tab:a#b", "tab:a b", "tab:a\x08b", ""):
            assert not label_gecerli_mi(anahtar), repr(anahtar)

    def test_label_key_ile_TUTARLI(self):
        """Üretilen anahtar doğrulamadan GEÇMELİ; ayrışırlarsa kullanıcı
        uygulamanın kendi etiketini yeniden adlandıramaz."""
        for ad in ("Ölçüm Değerleri", "şekil çıktı", "kar%orani",
                   "AT&T logo", "duz-ad"):
            uretilen = label_key(ad)
            assert label_gecerli_mi(uretilen), (ad, uretilen)
