"""log_parser modülü testleri."""

from core.log_parser import parse_output, resolve_error_path


# --- Başarılı derleme ---


class TestSuccess:
    def test_empty_output(self):
        r = parse_output("")
        assert r.success is True
        assert r.errors == []
        assert r.warnings == []
        assert r.suggestions == []

    def test_no_errors(self):
        r = parse_output("This is pdfTeX, Version 3.14\n[1] [2]")
        assert r.success is True
        assert r.errors == []


# --- Hatalar ---


class TestErrors:
    def test_generic_error(self):
        r = parse_output("! Undefined control sequence.\nl.42 \\badcmd")
        assert r.success is False
        assert len(r.errors) == 1
        assert "Undefined control sequence" in r.errors[0].message

    def test_package_error(self):
        r = parse_output("! Package graphicx Error: File `foo.png' not found.\nl.10")
        assert len(r.errors) == 1
        assert "[graphicx]" in r.errors[0].message
        assert "not found" in r.errors[0].message

    def test_error_line_number(self):
        r = parse_output("! Undefined control sequence.\nl.42 \\badcmd")
        assert r.errors[0].line_number == 42

    def test_error_without_line_number(self):
        r = parse_output("! Something went wrong.")
        assert len(r.errors) == 1
        assert r.errors[0].line_number == 0

    def test_multiple_errors(self):
        raw = "! Error one.\nl.10\n! Error two.\nl.20"
        r = parse_output(raw)
        assert len(r.errors) == 2
        assert r.errors[0].line_number == 10
        assert r.errors[1].line_number == 20

    def test_error_at_end_flushed(self):
        r = parse_output("! Last error.")
        assert len(r.errors) == 1
        assert "Last error" in r.errors[0].message

    def test_error_file_path(self):
        r = parse_output("(./chapter1.tex\n! Error.\nl.5", source_file="main.tex")
        # File ref before error → current_file updated
        assert r.errors[0].file_path == "chapter1.tex"


# --- Uyarılar ---


class TestWarnings:
    def test_latex_warning(self):
        r = parse_output("LaTeX Warning: Reference `fig1' on page 1 undefined.")
        assert len(r.warnings) == 1
        assert r.warnings[0].warning_type == "LaTeX"
        assert "Reference" in r.warnings[0].message

    def test_latex_warning_with_line(self):
        r = parse_output("LaTeX Warning: Reference `fig1' on input line 15 undefined.")
        assert r.warnings[0].line_number == 15

    def test_package_warning(self):
        r = parse_output("Package hyperref Warning: Token not allowed in a PDF string")
        assert len(r.warnings) == 1
        assert r.warnings[0].warning_type == "hyperref"

    def test_package_warning_with_line(self):
        r = parse_output("Package babel Warning: No hyphenation on input line 30")
        assert r.warnings[0].line_number == 30

    def test_overfull_box(self):
        r = parse_output("Overfull \\hbox (15.0pt too wide) in paragraph at lines 5--10")
        assert len(r.warnings) == 1
        assert r.warnings[0].warning_type == "Overfull"
        assert r.warnings[0].line_number == 5

    def test_underfull_box(self):
        r = parse_output("Underfull \\vbox (badness 10000) detected at line 20")
        assert len(r.warnings) == 1
        assert r.warnings[0].warning_type == "Underfull"

    def test_font_warning(self):
        r = parse_output("Font T1/ptm/b/n/10 not loadable")
        assert len(r.warnings) == 1
        assert r.warnings[0].warning_type == "Font"


# --- Öneriler ---


class TestSuggestions:
    def test_missing_package(self):
        r = parse_output("==> Eksik paketi: texlive-lang-turkish\n    sudo apt-get install texlive-lang-turkish")
        assert len(r.suggestions) == 1
        assert "texlive-lang-turkish" in r.suggestions[0].message
        assert "sudo apt-get install" in r.suggestions[0].install_command

    def test_missing_language_package(self):
        r = parse_output("==> Eksik dil paketi: texlive-lang-german")
        assert len(r.suggestions) == 1
        assert "dil paketi" in r.suggestions[0].message

    def test_suggestion_without_install(self):
        r = parse_output("==> Eksik paketi: some-package")
        assert len(r.suggestions) == 1
        assert r.suggestions[0].install_command == ""

    def test_install_without_suggestion_ignored(self):
        r = parse_output("    sudo apt-get install something")
        assert len(r.suggestions) == 0


# --- Motor önerisi ---


class TestEngineSuggestion:
    def test_requires_lualatex(self):
        r = parse_output("! This document requires LuaLaTeX to compile.\nl.1")
        assert any("lualatex" in s.message.lower() for s in r.suggestions)

    def test_requires_xelatex(self):
        r = parse_output("! Error: this file requires XeLaTeX.\nl.1")
        assert any("xelatex" in s.message.lower() for s in r.suggestions)

    def test_no_engine_requirement(self):
        r = parse_output("! Undefined control sequence.\nl.1")
        engine_suggestions = [s for s in r.suggestions if "gerektiriyor" in s.message]
        assert len(engine_suggestions) == 0


# --- Dosya referansı ---


class TestFileRef:
    def test_file_ref_updates_current(self):
        raw = "(./chapter1.tex\n! Error in chapter.\nl.10"
        r = parse_output(raw, source_file="main.tex")
        assert r.errors[0].file_path == "chapter1.tex"

    def test_multiple_file_refs(self):
        raw = "(./chapter1.tex\n! Error one.\nl.1\n(./chapter2.tex\n! Error two.\nl.2"
        r = parse_output(raw)
        assert r.errors[0].file_path == "chapter1.tex"
        assert r.errors[1].file_path == "chapter2.tex"

    def test_system_package_ref_does_not_hijack(self):
        # Sistem paketi yüklemesi current_file'ı çalmamalı; hata ana dosyaya atfedilmeli.
        raw = "(/usr/share/texlive/texmf-dist/foo.sty\n! Error.\nl.5"
        r = parse_output(raw, source_file="main.tex")
        assert r.errors[0].file_path == "main.tex"

    def test_system_tex_module_ref_does_not_hijack(self):
        # PGF/TikZ .code.tex modülleri de .tex ama sistem altında; takip edilmez.
        raw = "(/usr/share/texlive/pgfmodulematrix.code.tex\n! Error.\nl.9"
        r = parse_output(raw, source_file="main.tex")
        assert r.errors[0].file_path == "main.tex"


# --- Karmaşık çıktı ---


class TestComplexOutput:
    def test_full_output(self):
        raw = """\
This is pdfTeX, Version 3.14
(./main.tex
LaTeX Warning: Reference `fig1' on input line 15 undefined.
[1]
! Undefined control sequence.
l.42 \\badcmd
(./chapter1.tex
Overfull \\hbox (5.0pt too wide) in paragraph at lines 10--12
! Package graphicx Error: File not found.
l.20
==> Eksik paketi: texlive-extra
    sudo apt-get install texlive-extra
"""
        r = parse_output(raw, source_file="main.tex")
        assert r.success is False
        assert len(r.errors) == 2
        assert len(r.warnings) == 2
        assert len(r.suggestions) == 1
        # First error belongs to main.tex
        assert r.errors[0].file_path == "main.tex"
        # Second error belongs to chapter1.tex
        assert r.errors[1].file_path == "chapter1.tex"


class TestResolveErrorPath:
    def test_bare_filename_resolved_against_base(self, tmp_path):
        (tmp_path / "bolum1.tex").write_text("x")
        out = resolve_error_path("bolum1.tex", str(tmp_path))
        assert out == str(tmp_path / "bolum1.tex")

    def test_absolute_existing_returned_as_is(self, tmp_path):
        f = tmp_path / "a.tex"
        f.write_text("x")
        assert resolve_error_path(str(f), str(tmp_path)) == str(f)

    def test_nonexistent_bare_left_unchanged(self, tmp_path):
        # diskte yok → olduğu gibi döner (çağıran yine deneyebilir)
        assert resolve_error_path("yok.tex", str(tmp_path)) == "yok.tex"

    def test_empty_path_returned_empty(self, tmp_path):
        assert resolve_error_path("", str(tmp_path)) == ""

    def test_dot_slash_prefix_stripped(self, tmp_path):
        (tmp_path / "ch.tex").write_text("x")
        out = resolve_error_path("./ch.tex", str(tmp_path))
        assert out == str(tmp_path / "ch.tex")
