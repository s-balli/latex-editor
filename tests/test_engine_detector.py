"""engine_detector modülü testleri."""


from core.engine_detector import (
    detect_engine,
    detect_engine_from_content,
    detect_engine_from_magic_comment,
    can_compile,
    can_compile_from_content,
    _extract_documentclass,
    _check_compilable_content,
    _detect_from_cls_content,
    _magic_engine_from_content,
)
from core.latex_utils import strip_comments as _strip_comments


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
        assert _detect_from_cls_content("requires XeLaTeX") == "lualatex"

    def test_require_xetex(self):
        assert _detect_from_cls_content("\\RequireXeTeX") == "lualatex"

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

    def test_xelatex_maps_to_lualatex(self):
        # derle.sh xelatex'i doğrudan çalıştırmaz; lualatex'e eşlenir
        assert _magic_engine_from_content("% !TEX program = xelatex\n") == "lualatex"

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
        tex.write_text("% !TEX program = pdflatex\n\\begin{document}\\end{document}")
        assert detect_engine(str(tex)) == "pdflatex"

    def test_magic_file_function(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("% !TEX program = lualatex\n\\begin{document}\\end{document}")
        assert detect_engine_from_magic_comment(str(tex)) == "lualatex"

    def test_magic_file_function_none(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\nno magic here")
        assert detect_engine_from_magic_comment(str(tex)) is None

    def test_magic_file_function_nonexistent(self):
        assert detect_engine_from_magic_comment("/nonexistent/file.tex") is None


# --- detect_engine_from_content ---


class TestDetectEngineFromContent:
    def test_fontspec(self):
        assert detect_engine_from_content("\\usepackage{fontspec}") == "lualatex"

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
        tex.write_text("\\usepackage{fontspec}\n\\begin{document}\\end{document}")
        assert detect_engine(str(tex)) == "lualatex"

    def test_inputenc_file(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\usepackage[utf8]{inputenc}\n\\begin{document}\\end{document}")
        assert detect_engine(str(tex)) == "pdflatex"

    def test_empty_file(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("")
        assert detect_engine(str(tex)) is None

    def test_nonexistent_file(self):
        assert detect_engine("/nonexistent/file.tex") is None

    def test_with_cls_file(self, tmp_path):
        tex = tmp_path / "main.tex"
        tex.write_text("\\documentclass{myclass}\n\\begin{document}\\end{document}")
        cls = tmp_path / "myclass.cls"
        cls.write_text("\\RequireXeTeX")
        assert detect_engine(str(tex)) == "lualatex"

    def test_cls_not_found(self, tmp_path):
        tex = tmp_path / "main.tex"
        tex.write_text("\\documentclass{missing}\n\\begin{document}\\end{document}")
        assert detect_engine(str(tex)) is None


# --- can_compile (dosya I/O) ---


class TestCanCompile:
    def test_valid_tex(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\begin{document}\nhello\n\\end{document}")
        ok, _ = can_compile(str(tex))
        assert ok is True

    def test_non_tex_extension(self, tmp_path):
        cls = tmp_path / "style.cls"
        cls.write_text("some class content")
        ok, _ = can_compile(str(cls))
        assert ok is False

    def test_nonexistent_file(self):
        ok, _ = can_compile("/nonexistent/file.tex")
        assert ok is False
