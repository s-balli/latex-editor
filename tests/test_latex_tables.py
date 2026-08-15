"""latex_tables çekirdek testleri — üretim, kaçış, parse, hizalama, CSV, label."""

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
