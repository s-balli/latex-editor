"""engine_detector modülü testleri."""

from core.engine_detector import (
    detect_engine,
    detect_engine_from_content,
    detect_engine_from_magic_comment,
    detect_root,
    can_compile,
    can_compile_from_content,
    _extract_documentclass,
    _check_compilable_content,
    _detect_from_cls_content,
    _magic_engine_from_content,
    _yuklenen_paketler,
)
from core.latex_utils import strip_comments as _strip_comments


# --- detect_root: % !TEX root magic comment ---


class TestDetectRoot:
    def test_same_dir_root(self, tmp_path):
        (tmp_path / "main.tex").write_text("\\begin{document}\\end{document}", encoding="utf-8")
        child = tmp_path / "bolum1.tex"
        child.write_text("% !TEX root = main.tex\nbölüm içeriği\n", encoding="utf-8")
        assert detect_root(str(child)) == str(tmp_path / "main.tex")

    def test_parent_dir_root(self, tmp_path):
        (tmp_path / "tez.tex").write_text("\\begin{document}\\end{document}", encoding="utf-8")
        sub = tmp_path / "bolumler"
        sub.mkdir()
        child = sub / "giris.tex"
        child.write_text("% !TEX root = ../tez.tex\niçerik\n", encoding="utf-8")
        assert detect_root(str(child)) == str(tmp_path / "tez.tex")

    def test_missing_target_returns_empty(self, tmp_path):
        child = tmp_path / "a.tex"
        child.write_text("% !TEX root = yok.tex\niçerik\n", encoding="utf-8")
        assert detect_root(str(child)) == ""

    def test_no_comment_returns_empty(self, tmp_path):
        child = tmp_path / "a.tex"
        child.write_text("içerik\n", encoding="utf-8")
        assert detect_root(str(child)) == ""

    def test_missing_file_returns_empty(self, tmp_path):
        assert detect_root(str(tmp_path / "yok.tex")) == ""

    def test_quoted_path(self, tmp_path):
        (tmp_path / "ana dosya.tex").write_text("\\begin{document}\\end{document}", encoding="utf-8")
        child = tmp_path / "b.tex"
        child.write_text('% !TEX root = "ana dosya.tex"\n', encoding="utf-8")
        assert detect_root(str(child)) == str(tmp_path / "ana dosya.tex")

    def test_case_insensitive_directive(self, tmp_path):
        (tmp_path / "main.tex").write_text("\\begin{document}\\end{document}", encoding="utf-8")
        child = tmp_path / "c.tex"
        child.write_text("% !tex Root = main.tex\n", encoding="utf-8")
        assert detect_root(str(child)) == str(tmp_path / "main.tex")

    def test_comment_below_scan_window_ignored(self, tmp_path):
        (tmp_path / "main.tex").write_text("x", encoding="utf-8")
        child = tmp_path / "d.tex"
        child.write_text("\n" * 40 + "% !TEX root = main.tex\n", encoding="utf-8")
        assert detect_root(str(child)) == ""


# --- strip_comments ---


class TestStripComments:
    def test_no_comments(self):
        assert _strip_comments("hello world") == "hello world"

    def test_full_line_comment(self):
        result = _strip_comments("% bu bir yorum\nhello")
        assert result == "\nhello"

    def test_inline_comment(self):
        result = _strip_comments("kod % yorum")
        assert result == "kod "

    def test_escaped_percent(self):
        result = _strip_comments(r"\% yüzde işareti")
        assert r"\%" in result

    def test_double_backslash_percent(self):
        result = _strip_comments(r"\\% yorum")
        assert "%" not in result

    def test_triple_backslash_percent(self):
        result = _strip_comments(r"\\\% yüzde")
        assert r"\%" in result

    def test_empty_string(self):
        assert _strip_comments("") == ""

    def test_multiple_lines_mixed(self):
        content = "kod1\n% tam yorum\nkod2 % satir ici\nkod3"
        result = _strip_comments(content)
        assert "% tam yorum" not in result
        assert "% satir ici" not in result
        assert "kod1" in result
        assert "kod2" in result
        assert "kod3" in result


# --- _extract_documentclass ---


class TestExtractDocumentclass:
    def test_normal(self):
        assert _extract_documentclass("\\documentclass{article}") == "article"

    def test_with_options(self):
        assert _extract_documentclass("\\documentclass[12pt,a4paper]{report}") == "report"

    def test_commented_out(self):
        assert _extract_documentclass("% \\documentclass{book}") is None

    def test_hyphenated_class(self):
        assert _extract_documentclass("\\documentclass{IEEEaccess}") == "IEEEaccess"

    def test_no_documentclass(self):
        assert _extract_documentclass("some text without documentclass") is None

    def test_empty_string(self):
        assert _extract_documentclass("") is None


# --- _check_compilable_content ---


class TestCheckCompilableContent:
    def test_has_begin_document(self):
        ok, _ = _check_compilable_content("\\documentclass{article}\n\\begin{document}\nhello\n\\end{document}")
        assert ok is True

    def test_missing_begin_document(self):
        ok, msg = _check_compilable_content("\\documentclass{article}\nhello")
        assert ok is False
        assert "begin" in msg.lower() or "document" in msg.lower()

    def test_begin_document_in_comment(self):
        ok, _ = _check_compilable_content("% \\begin{document}\nhello")
        assert ok is False

    def test_empty_content(self):
        ok, _ = _check_compilable_content("")
        assert ok is False


# --- _detect_from_cls_content ---


class TestDetectFromClsContent:
    def test_requires_lualatex(self):
        assert _detect_from_cls_content("foo\nrequires LuaLaTeX\nbar") == "lualatex"

    def test_requires_xelatex(self):
        assert _detect_from_cls_content("requires XeLaTeX") == "xelatex"

    def test_require_xetex(self):
        assert _detect_from_cls_content("\\RequireXeTeX") == "xelatex"

    def test_require_luatex(self):
        assert _detect_from_cls_content("\\RequireLuaTeX") == "lualatex"

    def test_require_fontspec(self):
        assert _detect_from_cls_content("\\RequirePackage{fontspec}") == "lualatex"

    def test_pdfmapfile(self):
        assert _detect_from_cls_content("\\pdfmapfile") == "pdflatex"

    def test_no_signals(self):
        assert _detect_from_cls_content("plain class content") is None


# --- magic comment (% !TEX program) ---


class TestMagicComment:
    def test_pdflatex(self):
        assert _magic_engine_from_content("% !TEX program = pdflatex\n\\documentclass{article}") == "pdflatex"

    def test_lualatex(self):
        assert _magic_engine_from_content("% !TEX program = lualatex\n") == "lualatex"

    def test_xelatex(self):
        assert _magic_engine_from_content("% !TEX program = xelatex\n") == "xelatex"

    def test_xetex_maps_to_xelatex(self):
        assert _magic_engine_from_content("% !TEX program = xetex\n") == "xelatex"

    def test_ts_program_variant(self):
        assert _magic_engine_from_content("% !TEX TS-program = pdflatex\n") == "pdflatex"

    def test_case_insensitive(self):
        assert _magic_engine_from_content("% !TeX program = LuaLaTeX\n") == "lualatex"

    def test_no_space_after_percent(self):
        assert _magic_engine_from_content("%!TEX program = pdflatex\n") == "pdflatex"

    def test_no_magic_returns_none(self):
        assert _magic_engine_from_content("\\documentclass{article}\nhello") is None

    def test_unrecognized_program_returns_none(self):
        assert _magic_engine_from_content("% !TEX program = context\n") is None

    def test_inline_not_matched(self):
        # satır başında değilse magic comment sayılmaz
        assert _magic_engine_from_content("some code % !TEX program = pdflatex\n") is None

    def test_deep_line_ignored(self):
        # _MAGIC_SCAN_LINES (30) satırdan sonraki yönerge yok sayılır
        lines = ["x\n"] * 35 + ["% !TEX program = pdflatex\n"]
        assert _magic_engine_from_content("".join(lines)) is None

    def test_magic_beats_package_signal(self):
        # magic comment, package sinyalinden öncelikli
        content = "% !TEX program = pdflatex\n\\usepackage{fontspec}\n\\begin{document}\\end{document}"
        assert detect_engine_from_content(content) == "pdflatex"

    def test_magic_in_detect_engine_from_content(self):
        assert detect_engine_from_content("% !TEX program = lualatex\n") == "lualatex"

    def test_magic_in_detect_engine_file(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("% !TEX program = pdflatex\n\\begin{document}\\end{document}", encoding="utf-8")
        assert detect_engine(str(tex)) == "pdflatex"

    def test_magic_file_function(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("% !TEX program = lualatex\n\\begin{document}\\end{document}", encoding="utf-8")
        assert detect_engine_from_magic_comment(str(tex)) == "lualatex"

    def test_magic_file_function_none(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\nno magic here", encoding="utf-8")
        assert detect_engine_from_magic_comment(str(tex)) is None

    def test_magic_file_function_nonexistent(self):
        assert detect_engine_from_magic_comment("/nonexistent/file.tex") is None


# --- detect_engine_from_content ---


class TestDetectEngineFromContent:
    def test_fontspec(self):
        assert detect_engine_from_content("\\usepackage{fontspec}") == "lualatex"

    def test_mathspec_xelatex(self):
        # mathspec yalnız XeLaTeX'te derlenir
        assert detect_engine_from_content("\\usepackage{mathspec}") == "xelatex"

    def test_xecjk_xelatex(self):
        assert detect_engine_from_content("\\usepackage{xeCJK}") == "xelatex"

    def test_xecjk_beats_fontspec(self):
        # xe'e özgü paket, ortak paket sinyalini (fontspec) geçersiz kılar
        assert detect_engine_from_content("\\usepackage{fontspec}\n\\usepackage{xeCJK}") == "xelatex"

    def test_unicode_math(self):
        assert detect_engine_from_content("\\usepackage{unicode-math}") == "lualatex"

    def test_polyglossia(self):
        assert detect_engine_from_content("\\usepackage{polyglossia}") == "lualatex"

    def test_inputenc(self):
        assert detect_engine_from_content("\\usepackage[utf8]{inputenc}") == "pdflatex"

    def test_fontenc(self):
        assert detect_engine_from_content("\\usepackage[T1]{fontenc}") == "pdflatex"

    def test_no_signals(self):
        assert detect_engine_from_content("\\documentclass{article}") is None

    def test_cls_content_override(self):
        result = detect_engine_from_content(
            "\\documentclass{article}",
            cls_content="requires LuaLaTeX",
        )
        assert result == "lualatex"

    def test_cls_content_no_match(self):
        result = detect_engine_from_content(
            "\\documentclass{article}",
            cls_content="plain class",
        )
        assert result is None


# --- can_compile_from_content ---


class TestCanCompileFromContent:
    def test_tex_with_document(self):
        ok, _ = can_compile_from_content(
            "\\begin{document}\nhello\n\\end{document}", "test.tex"
        )
        assert ok is True

    def test_tex_without_document(self):
        ok, _ = can_compile_from_content("no document here", "test.tex")
        assert ok is False

    def test_cls_extension(self):
        ok, _ = can_compile_from_content("\\begin{document}", "style.cls")
        assert ok is False

    def test_no_filename_with_document(self):
        ok, _ = can_compile_from_content("\\begin{document}")
        assert ok is True

    def test_no_filename_without_document(self):
        ok, _ = can_compile_from_content("no document")
        assert ok is False


# --- detect_engine (dosya I/O) ---


class TestDetectEngine:
    def test_fontspec_file(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\usepackage{fontspec}\n\\begin{document}\\end{document}", encoding="utf-8")
        assert detect_engine(str(tex)) == "lualatex"

    def test_inputenc_file(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\usepackage[utf8]{inputenc}\n\\begin{document}\\end{document}", encoding="utf-8")
        assert detect_engine(str(tex)) == "pdflatex"

    def test_empty_file(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("", encoding="utf-8")
        assert detect_engine(str(tex)) is None

    def test_nonexistent_file(self):
        assert detect_engine("/nonexistent/file.tex") is None

    def test_with_cls_file(self, tmp_path):
        tex = tmp_path / "main.tex"
        tex.write_text("\\documentclass{myclass}\n\\begin{document}\\end{document}", encoding="utf-8")
        cls = tmp_path / "myclass.cls"
        cls.write_text("\\RequireXeTeX", encoding="utf-8")
        assert detect_engine(str(tex)) == "xelatex"

    def test_cls_not_found(self, tmp_path):
        tex = tmp_path / "main.tex"
        tex.write_text("\\documentclass{missing}\n\\begin{document}\\end{document}", encoding="utf-8")
        assert detect_engine(str(tex)) is None


# --- can_compile (dosya I/O) ---


class TestCanCompile:
    def test_valid_tex(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\begin{document}\nhello\n\\end{document}", encoding="utf-8")
        ok, _ = can_compile(str(tex))
        assert ok is True

    def test_non_tex_extension(self, tmp_path):
        cls = tmp_path / "style.cls"
        cls.write_text("some class content", encoding="utf-8")
        ok, _ = can_compile(str(cls))
        assert ok is False

    def test_nonexistent_file(self):
        ok, _ = can_compile("/nonexistent/file.tex")
        assert ok is False


def test_detect_root_from_head_path_ile_ayni_sonuc(tmp_path):
    """detect_root_from_head, detect_root ile aynı kökü çözmeli (tek okuma
    varyantı; file_tree _input_ref_ok kullanıyor)."""
    from core.engine_detector import detect_root, detect_root_from_head
    root = tmp_path / "main.tex"
    root.write_text("\\begin{document}x\\end{document}\n", encoding="utf-8")
    child = tmp_path / "bolum.tex"
    child.write_text("% !TEX root = main.tex\nmetin\n", encoding="utf-8")

    beklenen = detect_root(str(child))
    assert beklenen == str(root)
    assert detect_root_from_head(child.read_text(encoding="utf-8"), str(child)) == beklenen
    assert detect_root_from_head("magic yok\n", str(child)) == ""

# --- Seçenekli / virgüllü paket yüklemesi ---


class TestSecenekliPaketYuklemesi:
    """`\\usepackage[seçenek]{paket}` ve `\\usepackage{a,b}` biçimleri.

    lua/xe sinyalleri eskiden TAM DİZE aranıyordu (``"\\usepackage{fontspec}"``),
    pdflatex sinyalleri ise yalnız ``"{fontenc}"`` arıyordu ve seçeneğe
    dayanıklıydı. Asimetri pdflatex yönüne çalışıyor, fontspec ise pdflatex'te
    DERLENMİYOR: gerçek derlemeyle ölçüldüğünde altı vakanın beşinde yanlış
    motor seçiliyor ve beşinde de PDF hiç üretilmiyordu.
    """

    def test_secenekli_fontspec(self):
        # fontspec el kitabının kendi örneği; eskiden None dönüyordu
        assert detect_engine_from_content(
            "\\usepackage[no-math]{fontspec}") == "lualatex"

    def test_virgullu_liste(self):
        assert detect_engine_from_content(
            "\\usepackage{amsmath,fontspec}") == "lualatex"

    def test_virgulden_sonra_bosluk(self):
        assert detect_engine_from_content(
            "\\usepackage{amsmath, fontspec}") == "lualatex"

    def test_secenekli_fontspec_fontenc_i_YENIYOR(self):
        """Asimetrinin can alıcı yeri.

        Aynı önsözde ikisi de varken eski kod yalnız fontenc'i görüyor ve
        pdflatex diyordu; o motorla belge hiç derlenmiyor.
        """
        assert detect_engine_from_content(
            "\\usepackage[T1]{fontenc}\n"
            "\\usepackage[no-math]{fontspec}\n") == "lualatex"

    def test_secenekli_polyglossia(self):
        assert detect_engine_from_content(
            "\\usepackage[quiet]{polyglossia}") == "lualatex"

    def test_secenekli_xecjk(self):
        assert detect_engine_from_content(
            "\\usepackage[CJKspace]{xeCJK}") == "xelatex"

    def test_bosluklu_yazimlar(self):
        """Üç boşluklu yazımın üçü de gerçek lualatex ile PDF üretiyor
        (ölçüldü); tarama da üçünü görmeli."""
        for satir in ("\\usepackage {fontspec}",
                      "\\usepackage[no-math] {fontspec}",
                      "\\usepackage [no-math] {fontspec}"):
            assert detect_engine_from_content(satir) == "lualatex", satir

    def test_dosya_yolundan_da_ayni(self, tmp_path):
        tex = tmp_path / "a.tex"
        tex.write_text("\\documentclass{article}\n"
                       "\\usepackage[no-math]{fontspec}\n"
                       "\\begin{document}x\\end{document}\n", encoding="utf-8")
        assert detect_engine(str(tex)) == "lualatex"

    def test_cls_secenekli_requirepackage(self):
        """`.cls` dosyalarında `\\RequirePackage[no-math]{fontspec}` yaygın."""
        assert detect_engine_from_content(
            "\\documentclass{ozel}\n",
            cls_content="\\RequirePackage[no-math]{fontspec}\n") == "lualatex"


class TestPaketAdiAsiriEslesmiyor:
    """Yeni tarama paket ADI eşleştiriyor; gövde metnini yüklemeyle karıştırmamalı."""

    def test_govde_metnindeki_paket_adi_sayilmiyor(self):
        """template30-sunum'daki gerçek vaka.

        Sunumun gövdesinde ``The packages \\texttt{inputenc} ... are used``
        cümlesi geçiyor. Eski kod çıplak ``"{inputenc}"`` aradığı için bunu
        paket yüklemesi sanıp pdflatex diyordu.
        """
        assert detect_engine_from_content(
            "\\documentclass{beamer}\n"
            "\\begin{document}\n"
            "The packages \\texttt{inputenc} and \\texttt{FiraSans} are used.\n"
            "\\end{document}\n") is None

    def test_yorum_satirindaki_yukleme_sayilmiyor(self):
        assert detect_engine_from_content("%\\usepackage{fontspec}\n") is None

    def test_yuklenen_paketler_virgulleri_ayirip_kirpiyor(self):
        assert _yuklenen_paketler("\\usepackage[a,b]{x, y}") == {"x", "y"}

    def test_yuklenen_paketler_bos_susluyu_atliyor(self):
        assert _yuklenen_paketler("\\usepackage{}") == set()

    def test_yuklenen_paketler_requirepackage_i_de_goruyor(self):
        assert _yuklenen_paketler("\\RequirePackage{fontspec}") == {"fontspec"}
