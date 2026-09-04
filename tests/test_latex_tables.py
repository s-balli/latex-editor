"""latex_tables çekirdek testleri — üretim, kaçış, parse, hizalama, CSV, label."""


import re

import pytest

from core.latex_tables import (
    TableOptions, build_col_spec, build_tabular, csv_to_rows, escape_cell,
    extract_caption_label, format_tabular, parse_first_tabular,
    parse_tabular_at, slugify, suggest_label, unescape_cell,
)


# --- escape_cell ---


class TestEscapeCell:
    def test_specials_escaped(self):
        assert escape_cell("a & b") == r"a \& b"
        assert escape_cell("%50") == r"\%50"
        assert escape_cell("x_1") == r"x\_1"
        assert escape_cell("a#b") == r"a\#b"
        assert escape_cell("$x$") == r"\$x\$"

    def test_backslash_preserved(self):
        assert escape_cell(r"\alpha + \beta") == r"\alpha + \beta"

    def test_strip(self):
        assert escape_cell("  foo  ") == "foo"

    def test_plain_untouched(self):
        assert escape_cell("CNN 91.2") == "CNN 91.2"


class TestUnescapeCell:
    def test_roundtrip(self):
        for raw in ["Doğruluk %", "a & b", "x_1", "$x$", "a#b"]:
            assert unescape_cell(escape_cell(raw)) == raw

    def test_commands_preserved(self):
        assert unescape_cell(r"\alpha + \beta") == r"\alpha + \beta"

    def test_opens_escapes(self):
        assert unescape_cell(r"Doğruluk \%") == "Doğruluk %"


# --- yapıştırılan koddan yükleme ---


class TestParseFirstTabular:
    CODE = ("\\begin{table}[htbp]\n    \\centering\n"
            "    \\caption{Karşılaştırma \\%100}\n    \\label{tab:onceki}\n"
            "    \\begin{tabular}{lr}\n        \\toprule\n"
            "        Ad & Deger \\\\\n        x & 1 \\\\\n        \\bottomrule\n"
            "    \\end{tabular}\n\\end{table}\n")

    def test_finds_first_block(self):
        b = parse_first_tabular(self.CODE)
        assert b is not None and b["col_spec"] == "lr"
        assert b["rows"] == [["Ad", "Deger"], ["x", "1"]]

    def test_no_tabular(self):
        assert parse_first_tabular("kod yok") is None

    def test_caption_label(self):
        cap, lab = extract_caption_label(self.CODE)
        assert cap == "Karşılaştırma %100"   # kaçış açılır
        assert lab == "tab:onceki"

    def test_caption_label_missing(self):
        assert extract_caption_label("plain") == ("", "")


# --- kolon belirtimi ---


class TestColSpec:
    def test_plain(self):
        assert build_col_spec(["l", "c", "r"], False) == "lcr"

    def test_vertical_lines(self):
        assert build_col_spec(["l", "c"], True) == "|l|c|"

    def test_p_column(self):
        assert build_col_spec(["p", "l"], False) == "p{3cm}l"

    def test_p_becomes_x_in_tabularx(self):
        assert build_col_spec(["p", "p"], False, "tabularx") == "XX"


# --- build_tabular ---


ROWS = [["Yöntem", "Doğruluk %", "F1"],
        ["CNN", "91.2", "0.87"],
        ["Ours", "93.8", "0.91"]]


class TestBuildTabular:
    def test_booktabs_with_header(self):
        out = build_tabular(ROWS, ["l", "c", "r"],
                            TableOptions(caption="Karşılaştırma", label="tab:karsilastirma"))
        assert "\\begin{table}[htbp]" in out
        assert "\\begin{tabular}{lcr}" in out
        assert "\\toprule" in out and "\\midrule" in out and "\\bottomrule" in out
        assert "Yöntem & Doğruluk \\% & F1 \\\\" in out
        assert "\\caption{Karşılaştırma}" in out
        assert "\\label{tab:karsilastirma}" in out
        assert out.rstrip().endswith("\\end{table}")

    def test_no_wrapper(self):
        out = build_tabular(ROWS, ["l"], TableOptions(wrap_table=False))
        assert "begin{table}" not in out
        assert out.startswith("\\begin{tabular}")

    def test_hline_mode(self):
        out = build_tabular(ROWS, ["l", "c", "r"], TableOptions(booktabs=False))
        assert "\\toprule" not in out and "\\midrule" not in out
        assert out.count("\\hline") == 3

    def test_vertical_lines(self):
        out = build_tabular(ROWS, ["l", "l", "l"], TableOptions(vertical_lines=True))
        assert "{|l|l|l|}" in out

    def test_tabularx_linewidth(self):
        out = build_tabular(ROWS, ["p", "l", "c"], TableOptions(environment="tabularx"))
        assert "\\begin{tabularx}{\\linewidth}{Xlc}" in out

    def test_longtable_never_wrapped(self):
        out = build_tabular(ROWS, ["l"], TableOptions(environment="longtable",
                                                      wrap_table=True, caption="x"))
        assert "begin{table}" not in out
        assert out.startswith("\\begin{longtable}")

    def test_single_row_no_midrule(self):
        out = build_tabular([["a", "b"]], ["l", "c"])
        assert "\\midrule" not in out

    def test_empty(self):
        assert build_tabular([], ["l"]) == ""


# --- label önerisi ---


class TestLabels:
    def test_slugify_turkish(self):
        assert slugify("Yöntem Karşılaştırması") == "yontem-karsilastirmasi"

    def test_suggest_basic(self):
        assert suggest_label([], "Yöntem Karşılaştırması") == "tab:yontem-karsilastirmasi"

    def test_suggest_unique(self):
        assert suggest_label(["tab:sonuc"], "Sonuç") == "tab:sonuc-2"
        assert suggest_label(["tab:sonuc", "tab:sonuc-2"], "Sonuç") == "tab:sonuc-3"

    def test_empty_caption(self):
        assert suggest_label([], "") == "tab:tablo"


# --- CSV ---


class TestCsv:
    def test_comma(self, tmp_path):
        p = tmp_path / "t.csv"
        p.write_text("a,b\n1,2\n", encoding="utf-8")
        assert csv_to_rows(str(p)) == [["a", "b"], ["1", "2"]]

    def test_semicolon(self, tmp_path):
        p = tmp_path / "t.csv"
        p.write_text("a;b\n1;2\n", encoding="utf-8")
        assert csv_to_rows(str(p)) == [["a", "b"], ["1", "2"]]

    def test_tab(self, tmp_path):
        p = tmp_path / "t.csv"
        p.write_text("a\tb\n1\t2\n", encoding="utf-8")
        assert csv_to_rows(str(p)) == [["a", "b"], ["1", "2"]]

    def test_bom_and_empty_lines(self, tmp_path):
        p = tmp_path / "t.csv"
        p.write_bytes("﻿a,b\n\n1,2\n".encode("utf-8"))
        assert csv_to_rows(str(p)) == [["a", "b"], ["1", "2"]]


# --- parse / format ---


MESSY = r"""Metin öncesi.
\begin{table}[htbp]
    \centering
    \begin{tabular}{lll}
        \toprule
        Yöntem & Doğruluk \% & F1 \\
        \midrule
        CNN & 91.2 & 0.87 \\
        Bizimki & 93.8 & 0.91 \\
        \bottomrule
    \end{tabular}
\end{table}
Sonra metin."""


class TestParse:
    def test_finds_block_inside(self):
        pos = MESSY.index("91.2")
        b = parse_tabular_at(MESSY, pos)
        assert b is not None
        assert b["env"] == "tabular"
        assert b["col_spec"] == "lll"
        assert b["rows"][0] == ["Yöntem", r"Doğruluk \%", "F1"]
        assert b["rows"][1] == ["CNN", "91.2", "0.87"]
        assert b["rows"][2] == ["Bizimki", "93.8", "0.91"]

    def test_outside_returns_none(self):
        assert parse_tabular_at(MESSY, MESSY.index("Metin öncesi")) is None

    def test_tabularx_and_longtable(self):
        t = "\\begin{tabularx}{\\linewidth}{XX}\na & b\\\\\n\\end{tabularx}"
        b = parse_tabular_at(t, 10)
        assert b["env"] == "tabularx"
        assert b["col_spec"] == "XX"
        assert b["rows"] == [["a", "b"]]

    def test_innermost_block(self):
        t = "\\begin{tabular}{ll}\n\\begin{tabular}{cc}\nx & y\\\\\n\\end{tabular}\n\\end{tabular}"
        b = parse_tabular_at(t, t.index("x &"))
        assert b["col_spec"] == "cc"


class TestFormat:
    @staticmethod
    def _amp_cols(ln):
        import re as _re
        return [m.start() for m in _re.finditer(r"(?<!\\)&", ln)]

    def test_aligns_columns(self):
        pos = MESSY.index("91.2")
        out = format_tabular(MESSY, pos)
        assert out is not None
        lines = [ln for ln in out.split("\n") if "&" in ln and "\\\\" in ln]
        assert len(lines) == 3
        # Veri satırlarında & işaretleri aynı kolonlarda: hizalama kanıtı
        amp_cols = [self._amp_cols(ln) for ln in lines]
        assert amp_cols[0] == amp_cols[1] == amp_cols[2]
        # En geniş hücre sol kenara bitişik kalır (dolgu sağda)
        assert any(ln.lstrip().startswith("Bizimki &") for ln in lines)
        # kural satırları ve spec korunur, çevre metin korunur
        assert "\\toprule" in out and "{lll}" in out
        assert out.startswith("Metin öncesi.")
        assert out.rstrip().endswith("Sonra metin.")

    def test_no_block_returns_none(self):
        assert format_tabular("merhaba dünya", 3) is None

    def test_roundtrip_stable(self):
        pos = MESSY.index("91.2")
        once = format_tabular(MESSY, pos)
        assert format_tabular(once, once.index("91.2")) == once


class TestSarilmisSatir:
    r"""Sarılmış tablo satırı ikiye bölünmemeli (2026-08-30 denetimi, A2).

    _row_cells satırın `\\` ile bitip bitmediğine bakmıyor, format_tabular da
    HER kaynak satırının sonuna koşulsuz ` \\` ekliyordu. Kaynakta iki satıra
    sarılmış tek bir tablo satırı ikiye bölünüyor, ilki tek hücreli kalıyor ve
    LaTeX "Extra alignment tab" hatası veriyordu.
    """

    SARILI = (
        "\\begin{tabular}{ll}\n"
        "    Uzun bir hucre metni\n"
        "      burada devam ediyor & ikinci sutun \\\\\n"
        "\\end{tabular}\n"
    )

    def test_sarilmis_satir_bolunmuyor(self):
        out = format_tabular(self.SARILI, 30)
        # Tek mantıksal satır -> tek sonlandırıcı
        assert out.count("\\\\") == 1
        # İçerik iki parçadan da korunmalı
        assert "Uzun bir hucre metni" in out
        assert "burada devam ediyor" in out
        assert "ikinci sutun" in out

    def test_son_satirda_uydurma_sonlandirici_yok(self):
        r"""Son veri satırında `\\` bulunmaması LaTeX'te geçerlidir."""
        src = (
            "\\begin{tabular}{ll}\n"
            "    aaa   &   bbb \\\\\n"
            "    cc & dd\n"
            "\\end{tabular}\n"
        )
        out = format_tabular(src, 30)
        assert out.count("\\\\") == 1, "son satıra olmayan sonlandırıcı eklendi"
        # Yine de hizalanmış olmalı
        satirlar = [ln for ln in out.split("\n") if "&" in ln]
        sutun = [ln.index("&") for ln in satirlar]
        assert sutun[0] == sutun[1]

    def test_araliksiz_sonlandirici_korunuyor(self):
        r"""`\\[2mm]` gibi aralık argümanı kaybolmamalı."""
        src = (
            "\\begin{tabular}{ll}\n"
            "    aaa   &   bbb \\\\[2mm]\n"
            "    cc & dd \\\\\n"
            "\\end{tabular}\n"
        )
        out = format_tabular(src, 30)
        assert "\\\\[2mm]" in out
        # Eski kod sonlandırıcıyı ÇİFTLİYORDU: "bbb \\[2mm] \\"
        assert "[2mm] \\\\" not in out
        assert out.count("\\\\") == 2, "sonlandırıcı sayısı değişti"

    def test_parse_tabular_at_sarilmis_satiri_birlestirir(self):
        block = parse_tabular_at(self.SARILI, 30)
        assert block is not None
        assert len(block["rows"]) == 1, "sarılmış satır iki satır olarak ayrıştırıldı"
        assert len(block["rows"][0]) == 2


# --- CSV kodlaması: Excel'in Türkçe varsayılanı da okunmalı ---

_CSV_TR = "Ürün;Adet;Not\nÇilek;12;İyi\nŞeftali;7;Güzel\n"


def _csv_yaz(tmp_path, ad, veri):
    y = tmp_path / ad
    y.write_bytes(veri)
    return str(y)


@pytest.mark.parametrize("ad,kod", [
    ("utf8.csv", "utf-8"),
    ("utf8bom.csv", "utf-8-sig"),
    ("cp1254.csv", "cp1254"),
    ("utf16.csv", "utf-16"),
])
def test_csv_kodlamalari_okunuyor(tmp_path, ad, kod):
    """Excel Türkçe Windows'ta CSV'yi VARSAYILAN olarak cp1254 yazıyor.

    Yalnız utf-8 denendiği için UnicodeDecodeError atılıyordu ve bu hata
    tablo sihirbazının `except OSError`inden kaçıp slot'tan dışarı çıkıyordu:
    düğme sessizce hiçbir şey yapmamış gibi oluyordu (ölçüldü 2026-09-02).
    """
    yol = _csv_yaz(tmp_path, ad, _CSV_TR.encode(kod))
    satirlar = csv_to_rows(yol)
    assert satirlar[0] == ["Ürün", "Adet", "Not"]
    assert satirlar[1] == ["Çilek", "12", "İyi"]
    assert satirlar[2] == ["Şeftali", "7", "Güzel"]


def test_ikili_dosya_copluk_uretmiyor(tmp_path):
    """latin-1 her şeyi çözer; ikili dosya sessizce tabloya dolardı."""
    yol = _csv_yaz(tmp_path, "ikili.csv", bytes(range(256)) * 8)
    with pytest.raises(ValueError):
        csv_to_rows(yol)


def test_bos_dosya_hata_vermiyor(tmp_path):
    assert csv_to_rows(_csv_yaz(tmp_path, "bos.csv", b"")) == []


# ---------------------------------------------------------------------------
# ÜRETİLEN TABLONUN DERLENEBİLİRLİĞİ
#
# Aşağıdaki iki sınıf, üretimin LaTeX'i BOZDUĞU iki yolu sabitliyor. Her ikisi
# de gerçek pdflatex ile ölçüldü; buradaki testler ucuz (dizge düzeyi)
# karşılıkları. Gerçek derleme kapısı tests/test_tablo_derleme.py'de ve CI'da
# `derle` işi onu koşuyor.
# ---------------------------------------------------------------------------


class TestDuzensizSatirlar:
    """CSV'den gelen satırlar farklı uzunlukta olabilir.

    Eskiden `ncols = len(rows[0])` alınıyor ve satırlar olduğu gibi
    yazılıyordu: bir satırda fazladan virgül olan bir CSV (Excel
    çıktılarında olağan) üretilen bloğu DERLENMEZ yapıyordu
    ("! Extra alignment tab has been changed to \\cr").
    """

    RAGGED = [["Ad", "Yil", "Deger"],
              ["Ozturk", "2024", "12", "FAZLA"],
              ["Cagri", "2023", "9"]]

    @staticmethod
    def _hucre_sayilari(kod):
        return {s.count(" & ") + 1 for s in kod.split("\n") if s.endswith(" \\\\")}

    def test_tum_satirlar_ayni_hucre_sayisinda(self):
        kod = build_tabular(self.RAGGED, ["l", "c", "r"])
        assert self._hucre_sayilari(kod) == {4}

    def test_kolon_belirtimi_en_uzun_satira_gore(self):
        kod = build_tabular(self.RAGGED, ["l", "c", "r"])
        assert "{lcrc}" in kod

    def test_fazla_veri_dusmuyor(self):
        """Kırpmak yerine doldurmak seçildi: kullanıcının verisi kaybolmasın."""
        kod = build_tabular(self.RAGGED, ["l", "c", "r"])
        assert "FAZLA" in kod

    @pytest.mark.parametrize("satirlar", [
        [["a", "b", "c"], ["d"]],            # ilk satır EN UZUN
        [["a"], ["b", "c", "d"]],            # ilk satır EN KISA
        [["a", "b"], ["c", "d"]],            # düzenli (karşı durum)
        [["a"]],                             # tek hücre
        [["a", ""], ["", "b"]],              # boş hücreler
    ])
    def test_her_bicimde_hucre_sayisi_esit(self, satirlar):
        kod = build_tabular(satirlar, ["l"])
        assert len(self._hucre_sayilari(kod)) == 1


class TestSapkaVeTilde:
    r"""`^` derlemeyi kırıyordu, `~` çıktıyı sessizce değiştiriyordu.

    `^` : metin kipinde "! Missing $ inserted." veriyor. `$` zaten
          kaçırıldığı için hücrede matematik kipi hiç açılamıyor, yani `^`
          bir hücrede hiçbir zaman meşru olamaz.
    `~` : derleniyor ama bağlayıcı boşluğa dönüşüyor; '5~10' çıktıda
          '5 10' oluyor (ölçüldü).

    KAÇIŞ BİÇİMİ ÖNEMLİ: `\^` tek başına aksan komutudur ve şapkayı BİR
    SONRAKİ harfin üstüne koyar ('R\^2' -> 'R2̂', ölçüldü). Doğrusu `\^{}`.
    """

    def test_sapka_kacisi_suslu_parantezli(self):
        assert escape_cell("R^2") == r"R\^{}2"

    def test_tilde_kacisi_suslu_parantezli(self):
        assert escape_cell("5~10") == r"5\~{}10"

    def test_naif_kacis_URETILMIYOR(self):
        """`\\^2` biçimi derlenir ama yanlış karakteri basar; çıkmamalı."""
        kod = escape_cell("R^2")
        assert "\\^2" not in kod

    def test_eski_kacislar_bozulmadi(self):
        assert escape_cell("%&_#$") == r"\%\&\_\#\$"

    def test_backslash_hala_serbest(self):
        """LaTeX komut serbestliği korunmalı (modülün bilinçli tercihi)."""
        assert escape_cell(r"\textbf{x}") == r"\textbf{x}"

    @pytest.mark.parametrize("ham", [
        "R^2", "5~10", "a^b~c", "a^b^c", "%50", "a&b", "x_1", "#3", "$5",
        "a^b~c%d&e_f#g$h", r"\textbf{x}", "düz metin", "",
    ])
    def test_roundtrip(self, ham):
        assert unescape_cell(escape_cell(ham)) == ham.strip()

    def test_uretilen_tabloda_ham_sapka_kalmiyor(self):
        kod = build_tabular([["Olcut", "Deger"], ["R^2", "0,91"]], ["l", "r"])
        # Kaçırılmamış tek başına `^` kalmamalı
        assert re.search(r"(?<!\\)\^(?!\{\})", kod) is None
