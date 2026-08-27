"""exporter.py — pandoc dışa aktarma testleri."""

import subprocess
import sys
from unittest.mock import MagicMock, patch, mock_open

import pytest


# core.log PyQt6 gerektiriyor. Gerçek PyQt6 kuruluysa onu kullan; yoksa mock'la.
# DİKKAT: mock eskiden "PyQt6 not in sys.modules" ile koşulsuz sys.modules'e
# enjekte ediliyordu ve temizlenmiyordu — bu kirlilik alfabetik olarak sonra
# toplanan test_imports ve lexer testlerinin "'PyQt6' is not a package" hatasıyla
# atlanmasına yol açıyordu. Artık mock yalnızca gerçek PyQt6 yoksa devreye giriyor.
_core_mocks = {}
try:
    from PyQt6.QtCore import QStandardPaths  # noqa: F401
    del QStandardPaths
except ImportError:
    _mock_qt = MagicMock()
    _mock_qt.QtCore.QStandardPaths.StandardLocation.AppLocalDataLocation = 0
    _mock_qt.QtCore.QStandardPaths.writableLocation.return_value = "/tmp/test_logs"
    sys.modules["PyQt6"] = _mock_qt
    sys.modules["PyQt6.QtCore"] = _mock_qt.QtCore

from core.exporter import (
    FORMATS,
    export,
    pandoc_available,
    _pandoc_args,
    _extract_graphics_paths,
    _fix_md_image_paths,
    _export_native,
    _export_wsl,
    _preprocess_tex,
    _find_bibliography,
    _resolve_md_citations,
    _pandoc_csljson,
    _fix_docx_compat,
    _rewrite_docx_member,
)


class TestFormats:
    def test_format_keys(self):
        assert set(FORMATS.keys()) == {"DOCX", "HTML", "Markdown", "Plain Text"}

    def test_extensions(self):
        assert FORMATS["DOCX"] == ".docx"
        assert FORMATS["HTML"] == ".html"
        assert FORMATS["Markdown"] == ".md"
        assert FORMATS["Plain Text"] == ".txt"


class TestPandocAvailable:
    @patch("core.exporter.shutil.which")
    @patch("core.exporter.PLATFORM", "linux")
    def test_available_linux(self, mock_which):
        mock_which.return_value = "/usr/bin/pandoc"
        assert pandoc_available() is True

    @patch("core.exporter.shutil.which")
    @patch("core.exporter.PLATFORM", "linux")
    def test_not_available_linux(self, mock_which):
        mock_which.return_value = None
        assert pandoc_available() is False

    @patch("core.exporter._wsl_pandoc_available", return_value=False)
    @patch("core.exporter.shutil.which")
    @patch("core.exporter.PLATFORM", "win32")
    def test_available_windows_native(self, mock_which, mock_wsl):
        mock_which.return_value = "C:\\pandoc.exe"
        assert pandoc_available() is True

    @patch("core.exporter._wsl_pandoc_available", return_value=True)
    @patch("core.exporter.shutil.which")
    @patch("core.exporter.PLATFORM", "win32")
    def test_available_windows_wsl(self, mock_which, mock_wsl):
        mock_which.return_value = None
        assert pandoc_available() is True


class TestPandocArgs:
    def test_docx_args(self):
        args = _pandoc_args("/home/user/doc.tex", "/home/user/doc.docx")
        assert args[0] == "pandoc"
        assert "/home/user/doc.tex" in args
        assert "-o" in args
        assert "/home/user/doc.docx" in args
        assert "--standalone" not in args

    def test_html_args_has_standalone(self):
        args = _pandoc_args("/home/user/doc.tex", "/home/user/doc.html")
        assert "--standalone" in args
        assert "--embed-resources" in args

    def test_resource_path(self):
        args = _pandoc_args("/home/user/doc.tex", "/home/user/doc.docx")
        assert "--resource-path=/home/user" in args


class TestExtractGraphicsPaths:
    @patch("builtins.open", new_callable=mock_open, read_data=r"\graphicspath{{media/}{images/}}")
    def test_multiple_paths(self, mock_f):
        result = _extract_graphics_paths("test.tex")
        assert result == ["media/", "images/"]

    @patch("builtins.open", new_callable=mock_open, read_data=r"\graphicspath{{media/}}")
    def test_single_path(self, mock_f):
        result = _extract_graphics_paths("test.tex")
        assert result == ["media/"]

    @patch("builtins.open", new_callable=mock_open, read_data="no graphicspath here")
    def test_no_graphicspath(self, mock_f):
        result = _extract_graphics_paths("test.tex")
        assert result == []

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_file_not_found(self, mock_f):
        result = _extract_graphics_paths("missing.tex")
        assert result == []


class TestExport:
    def test_source_file_not_found(self):
        ok, err = export("/nonexistent/file.tex", "/tmp/out.docx")
        assert ok is False
        assert "bulunamadı" in err

    @patch("core.exporter._export_native", return_value=(True, ""))
    @patch("core.exporter.PLATFORM", "linux")
    def test_native_export_success(self, mock_native):
        with patch("os.path.exists", return_value=True):
            ok, err = export("/home/user/doc.tex", "/home/user/doc.docx")
        assert ok is True

    @patch("core.exporter._export_wsl", return_value=(True, ""))
    @patch("core.exporter.PLATFORM", "win32")
    def test_wsl_export_success(self, mock_wsl):
        with patch("os.path.exists", return_value=True):
            ok, err = export(r"C:\Users\doc.tex", r"C:\Users\doc.docx")
        assert ok is True

    @patch("core.exporter._fix_md_image_paths")
    @patch("core.exporter._export_native", return_value=(True, ""))
    @patch("core.exporter.PLATFORM", "linux")
    def test_md_export_fixes_images(self, mock_native, mock_fix):
        with patch("os.path.exists", return_value=True):
            export("/home/user/doc.tex", "/home/user/doc.md")
        mock_fix.assert_called_once()

    @patch("core.exporter._export_native", return_value=(True, ""))
    @patch("core.exporter.PLATFORM", "linux")
    def test_docx_export_no_image_fix(self, mock_native):
        with patch("os.path.exists", return_value=True):
            with patch("core.exporter._fix_md_image_paths") as mock_fix:
                export("/home/user/doc.tex", "/home/user/doc.docx")
        mock_fix.assert_not_called()


class TestExportNative:
    @patch("core.exporter.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        ok, err = _export_native("/home/user/doc.tex", "/home/user/doc.docx")
        assert ok is True
        assert err == ""

    @patch("core.exporter.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="error message")
        ok, err = _export_native("/home/user/doc.tex", "/home/user/doc.docx")
        assert ok is False
        assert "error message" in err

    @patch("core.exporter.subprocess.run", side_effect=subprocess.TimeoutExpired("pandoc", 30))
    def test_timeout(self, mock_run):
        ok, err = _export_native("/home/user/doc.tex", "/home/user/doc.docx")
        assert ok is False
        assert "zaman aşımı" in err

    @patch("core.exporter.subprocess.run", side_effect=FileNotFoundError)
    def test_pandoc_not_found(self, mock_run):
        ok, err = _export_native("/home/user/doc.tex", "/home/user/doc.docx")
        assert ok is False
        assert "pandoc bulunamadı" in err

    @patch("core.exporter.subprocess.run")
    def test_empty_stderr(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="")
        ok, err = _export_native("/home/user/doc.tex", "/home/user/doc.docx")
        assert ok is False
        assert err != ""


class TestExportWsl:
    @patch("core.exporter.subprocess.run")
    @patch("core.exporter.PLATFORM", "win32")
    def test_success(self, mock_run):
        # İlk çağrı pandoc, ikinci cp
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr=""),  # pandoc
            MagicMock(returncode=0),              # cp
            MagicMock(returncode=0),              # rm (finally)
        ]
        ok, err = _export_wsl(r"C:\Users\doc.tex", r"C:\Users\doc.docx")
        assert ok is True

    @patch("core.exporter.subprocess.run")
    @patch("core.exporter.PLATFORM", "win32")
    def test_pandoc_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="pandoc error")
        ok, err = _export_wsl(r"C:\Users\doc.tex", r"C:\Users\doc.docx")
        assert ok is False
        assert "pandoc error" in err

    @patch("core.exporter.subprocess.run")
    @patch("core.exporter.PLATFORM", "win32")
    def test_cp_fails_cat_fallback(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr=""),   # pandoc
            MagicMock(returncode=1),              # cp fails
            MagicMock(returncode=0, stdout=b"content"),  # cat fallback
            MagicMock(returncode=0),              # rm (finally)
        ]
        with patch("builtins.open", mock_open()):
            ok, err = _export_wsl(r"C:\Users\doc.tex", r"C:\Users\doc.docx")
        assert ok is True

    @patch("core.exporter.subprocess.run")
    @patch("core.exporter.PLATFORM", "win32")
    def test_cp_and_cat_both_fail(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr=""),  # pandoc
            MagicMock(returncode=1),             # cp fails
            MagicMock(returncode=1),             # cat fails
            MagicMock(returncode=0),             # rm (finally)
        ]
        ok, err = _export_wsl(r"C:\Users\doc.tex", r"C:\Users\doc.docx")
        assert ok is False
        assert "kopyalanamadı" in err

    @patch("core.exporter.subprocess.run")
    @patch("core.exporter.PLATFORM", "win32")
    def test_timeout(self, mock_run):
        # İlk çağrı timeout, finally'deki rm çağrısı başarılı olmalı
        mock_run.side_effect = [
            subprocess.TimeoutExpired("wsl", 30),
            MagicMock(returncode=0),  # rm (finally)
        ]
        ok, err = _export_wsl(r"C:\Users\doc.tex", r"C:\Users\doc.docx")
        assert ok is False
        assert "zaman aşımı" in err


class TestFixMdImagePaths:
    def test_relative_path_with_graphicspath(self, tmp_path):
        tex_file = tmp_path / "doc.tex"
        tex_file.write_text(r"\graphicspath{{media/}}")
        md_file = tmp_path / "doc.md"
        md_file.write_text("![alt](image.png)")
        _fix_md_image_paths(str(tex_file), str(md_file))
        content = md_file.read_text()
        assert "media/image.png" in content
        # fix: göreceli yol .tex dizinine göre mutlak yapıldı (sadece substring değil)
        assert str(tex_file.parent) in content

    def test_absolute_path_unchanged(self, tmp_path):
        tex_file = tmp_path / "doc.tex"
        tex_file.write_text("no graphicspath")
        md_file = tmp_path / "doc.md"
        md_file.write_text("![alt](/absolute/image.png)")
        _fix_md_image_paths(str(tex_file), str(md_file))
        content = md_file.read_text()
        assert "/absolute/image.png" in content

    def test_http_url_unchanged(self, tmp_path):
        tex_file = tmp_path / "doc.tex"
        tex_file.write_text("no graphicspath")
        md_file = tmp_path / "doc.md"
        md_file.write_text("![alt](https://example.com/img.png)")
        _fix_md_image_paths(str(tex_file), str(md_file))
        content = md_file.read_text()
        assert "https://example.com/img.png" in content

    def test_pandoc_width_attribute_removed(self, tmp_path):
        tex_file = tmp_path / "doc.tex"
        tex_file.write_text("no graphicspath")
        md_file = tmp_path / "doc.md"
        md_file.write_text('![alt](image.png){width="70%"}')
        _fix_md_image_paths(str(tex_file), str(md_file))
        content = md_file.read_text()
        assert '{width="70%"}' not in content


# --- önişleme: abstract/title -> gövdeye taşı (elsarticle fix) ---


class TestPreprocess:
    def test_abstract_becomes_section(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\begin{abstract}\nÖzet metni.\n\\end{abstract}")
        out = _preprocess_tex(str(tex))
        content = open(out, encoding="utf-8").read()
        assert "\\section*{Abstract}" in content
        assert "\\begin{abstract}" not in content
        assert "\\end{abstract}" not in content
        if out != str(tex):
            import os; os.unlink(out)

    def test_title_becomes_section(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\title{Belge Başlığı}\n\\section{X}")
        out = _preprocess_tex(str(tex))
        content = open(out, encoding="utf-8").read()
        assert "\\section*{Belge Başlığı}" in content
        import os; os.unlink(out) if out != str(tex) else None

    def test_title_with_optional_arg(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\title[Kısa]{Uzun Başlık}")
        out = _preprocess_tex(str(tex))
        content = open(out, encoding="utf-8").read()
        assert "\\section*{Uzun Başlık}" in content
        import os; os.unlink(out) if out != str(tex) else None

    def test_frontmatter_stripped(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\begin{frontmatter}\n\\title{X}\n\\end{frontmatter}\n\\section{Y}")
        out = _preprocess_tex(str(tex))
        content = open(out, encoding="utf-8").read()
        assert "\\begin{frontmatter}" not in content
        assert "\\end{frontmatter}" not in content
        import os; os.unlink(out) if out != str(tex) else None

    def test_no_change_returns_original(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\section{Gövde}\nMetin.")
        out = _preprocess_tex(str(tex))
        assert out == str(tex)  # değişiklik yok -> geçici dosya yok


# --- bibliography tespiti ---


class TestFindBibliography:
    def test_bibliography_command(self, tmp_path):
        tex = tmp_path / "d.tex"
        (tmp_path / "refs.bib").write_text("@article{x,...}")
        tex.write_text("\\bibliography{refs}")
        assert _find_bibliography(str(tex)) == str(tmp_path / "refs.bib")

    def test_addbibresource(self, tmp_path):
        tex = tmp_path / "d.tex"
        (tmp_path / "src.bib").write_text("@article{x,...}")
        tex.write_text("\\addbibresource{src.bib}")
        assert _find_bibliography(str(tex)) == str(tmp_path / "src.bib")

    def test_missing_bib_file(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\bibliography{refs}")  # refs.bib yok
        assert _find_bibliography(str(tex)) == ""

    def test_no_bibliography(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\section{X}\nMetin.")
        assert _find_bibliography(str(tex)) == ""


# --- _pandoc_args bibliography desteği ---


class TestPandocArgsBib:
    def test_args_include_citeproc_when_bib(self):
        args = _pandoc_args("/d/a.tex", "/d/a.md", bib="/d/refs.bib")
        assert "--bibliography=/d/refs.bib" in args
        assert "--citeproc" in args

    def test_args_no_citeproc_without_bib(self):
        args = _pandoc_args("/d/a.tex", "/d/a.md")
        assert not any(a.startswith("--bibliography") for a in args)
        assert "--citeproc" not in args

    def test_txt_args_force_plain(self):
        # .txt pandoc'ta varsayılan markdown'dır; gerçek plain text iste
        args = _pandoc_args("/d/a.tex", "/d/a.txt")
        assert "-t" in args and "plain" in args


# --- entegrasyon: gerçek pandoc ile abstract görünsün ---


import shutil as _shutil
_PANDOC = _shutil.which("pandoc")


class TestExportIntegration:
    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_abstract_present_in_md(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\begin{abstract}\nBu özet dışa aktarımda görünmeli.\n\\end{abstract}\n"
            "\\section{Giriş}\nGövde.\n\\end{document}\n"
        )
        md = tmp_path / "d.md"
        ok, err = export(str(tex), str(md))
        assert ok, f"export failed: {err}"
        content = md.read_text(encoding="utf-8")
        assert "Abstract" in content
        assert "Bu özet dışa aktarımda görünmeli." in content

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_references_resolved_in_html_with_bib(self, tmp_path):
        # citeproc HTML/DOCX/TXT'de citations'ı çözüp referans listesi ekler.
        # (Markdown writer citeproc'u atlar; MD'de [@key] pandoc citation kalır.)
        tex = tmp_path / "d.tex"
        bib = tmp_path / "refs.bib"
        bib.write_text(
            "@article{kazemi2025synthetic,\nauthor={Kazemi},\ntitle={Synthetic},\nyear={2025}}\n"
        )
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Metin \\cite{kazemi2025synthetic}.\n"
            "\\bibliography{refs}\n\\end{document}\n"
        )
        html = tmp_path / "d.html"
        ok, err = export(str(tex), str(html))
        assert ok, f"export failed: {err}"
        content = html.read_text(encoding="utf-8")
        assert "Kazemi" in content            # citeproc çözümü (html expand eder)
        assert "references" in content.lower() or 'id="refs"' in content

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_md_resolves_citations_and_adds_references(self, tmp_path):
        # pandoc MD'de citeproc'u atlar; bizim çözücümüz [@key]'i çözüp liste ekler.
        tex = tmp_path / "d.tex"
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{k,\nauthor={Kazemi, A.},\ntitle={T},\nyear={2020}}\n")
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Metin \\cite{k}.\n\\bibliography{refs}\n\\end{document}\n"
        )
        md = tmp_path / "d.md"
        ok, err = export(str(tex), str(md))
        assert ok, f"export failed: {err}"
        content = md.read_text(encoding="utf-8")
        assert "[@k]" not in content          # çözüldü
        assert "(Kazemi 2020)" in content     # inline çözüm
        assert "## References" in content     # referans listesi eklendi

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_md_without_bib_keeps_citation_key(self, tmp_path):
        # .bib yoksa çözücü çalışmaz; [@key] pandoc citation olarak kalır.
        tex = tmp_path / "d.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Metin \\cite{k}.\n\\end{document}\n"
        )
        md = tmp_path / "d.md"
        ok, err = export(str(tex), str(md))
        assert ok, f"export failed: {err}"
        assert "[@k]" in md.read_text(encoding="utf-8")

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_md_references_full_quality_via_citeproc(self, tmp_path):
        # MD referansları citeproc ile üretilir: dergi, DOI vb. TAM bilgi (basit format değil).
        tex = tmp_path / "d.tex"
        bib = tmp_path / "refs.bib"
        bib.write_text(
            "@article{k,\nauthor={Kazemi, Arefeh and B, C.},\ntitle={Paper One},\n"
            "journal={Nature},\nyear={2025},\ndoi={10.1000/one}}\n"
        )
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Metin \\cite{k}.\n\\bibliography{refs}\n\\end{document}\n"
        )
        md = tmp_path / "d.md"
        ok, err = export(str(tex), str(md))
        assert ok, f"export failed: {err}"
        content = md.read_text(encoding="utf-8")
        assert "## References" in content
        assert "Nature" in content              # citeproc tam referans (dergi)
        assert "10.1000/one" in content         # DOI

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_txt_resolves_citations_and_is_plain(self, tmp_path):
        # .txt -> -t plain: gerçek plain text + citeproc çözümü.
        tex = tmp_path / "d.tex"
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{k,\nauthor={Kazemi},\ntitle={T},\nyear={2025}}\n")
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Metin \\cite{k}.\n\\bibliography{refs}\n\\end{document}\n"
        )
        txt = tmp_path / "d.txt"
        ok, err = export(str(tex), str(txt))
        assert ok, f"export failed: {err}"
        content = txt.read_text(encoding="utf-8")
        assert "Kazemi" in content          # citeproc çözümü
        assert "[@" not in content          # çözülmemiş cite kalmadı
        assert "# " not in content          # markdown başlık yok (gerçek plain)


class TestResolveMdCitations:
    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_multi_author_et_al(self, tmp_path):
        bib = tmp_path / "r.bib"
        bib.write_text(
            "@article{k,\nauthor={A, X. and B, Y. and C, Z.},\ntitle={T},\nyear={2024}}\n"
        )
        md = tmp_path / "d.md"
        md.write_text("See [@k].\n")
        _resolve_md_citations(str(md), "", str(bib))   # tex yoksa inline yine çözülür
        content = md.read_text(encoding="utf-8")
        assert "(A et al. 2024)" in content   # 3+ yazar -> et al.

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_multi_cite_keys_inline(self, tmp_path):
        bib = tmp_path / "r.bib"
        bib.write_text(
            "@article{k1,\nauthor={Kazemi, A.},\ntitle={S},\nyear={2025}}\n"
            "@article{k2,\nauthor={Hasan, M.},\ntitle={L},\nyear={2026}}\n"
        )
        md = tmp_path / "d.md"
        md.write_text("[@k1; @k2]\n")
        _resolve_md_citations(str(md), "", str(bib))
        content = md.read_text(encoding="utf-8")
        assert "(Kazemi 2025; Hasan 2026)" in content

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_unknown_key_left_as_is(self, tmp_path):
        bib = tmp_path / "r.bib"
        bib.write_text("@article{k1,\nauthor={A},\ntitle={T},\nyear={2020}}\n")
        md = tmp_path / "d.md"
        md.write_text("[@k1] and [@unknownkey]\n")
        _resolve_md_citations(str(md), "", str(bib))
        content = md.read_text(encoding="utf-8")
        assert "(A 2020)" in content
        assert "[@unknownkey]" in content    # bilinmeyen -> dokunulmadı


class TestPandocCsljson:
    @patch("core.exporter.PLATFORM", "win32")
    @patch("core.exporter.subprocess.run")
    def test_wsl_pandoc_on_windows(self, mock_run):
        # Windows'ta pandoc WSL'dedir; csljson çağrısı wsl üzerinden olmalı.
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        _pandoc_csljson(r"C:\refs.bib")
        args = mock_run.call_args[0][0]
        assert args[0] == "wsl" and "pandoc" in args

    @patch("core.exporter.PLATFORM", "linux")
    @patch("core.exporter.subprocess.run")
    def test_native_pandoc_on_linux(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        _pandoc_csljson("/r/refs.bib")
        args = mock_run.call_args[0][0]
        assert args[0] == "pandoc" and args[1] == "/r/refs.bib"

    @patch("core.exporter.PLATFORM", "linux")
    def test_empty_on_pandoc_failure(self):
        # pandoc bulunamazsa boş döner (sessiz başarısızlık değil).
        with patch("core.exporter.subprocess.run", side_effect=FileNotFoundError):
            assert _pandoc_csljson("/r/refs.bib") == ""


class TestFixDocxBrokenAnchors:
    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_broken_anchors_neutralized(self, tmp_path):
        # \ref{fig:missing} figure'siz -> boş anchor -> Word açamaz. Düzeltici nötrleştirmeli.
        import zipfile, re
        tex = tmp_path / "d.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "See Figure \\ref{fig:missing}.\n"
            "\\end{document}\n"
        )
        docx_path = tmp_path / "d.docx"
        ok, _ = export(str(tex), str(docx_path))
        assert ok
        doc = zipfile.ZipFile(str(docx_path)).read('word/document.xml').decode('utf-8')
        bookmarks = set(re.findall(r'<w:bookmarkStart[^>]*w:name="([^"]+)"', doc))
        anchors = set(re.findall(r'<w:hyperlink[^>]*w:anchor="([^"]+)"', doc))
        # Düzeltme sonrası boş anchor kalmamalı
        assert (anchors - bookmarks) == set()

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_docx_opens_after_fix(self, tmp_path):
        # Düzeltme docx'i bozmamalı (python-docx açabilmeli).
        _docx = pytest.importorskip("docx")
        tex = tmp_path / "d.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "See \\ref{fig:missing}. Some text.\n\\end{document}\n"
        )
        docx_path = tmp_path / "d.docx"
        ok, _ = export(str(tex), str(docx_path))
        assert ok
        d = _docx.Document(str(docx_path))   # çökmemeli
        assert len(d.paragraphs) >= 1

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gereklib")
    def test_undefined_table_style_replaced(self, tmp_path):
        # pandoc 3.1.3 FigureTable bug'ı simülasyonu: tanımsız stili enjekte et, düzelir mi?
        import zipfile, subprocess
        tex = tmp_path / "d.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\begin{table}[h]\\caption{X}\\begin{tabular}{c}1\\\\\\end{tabular}\\end{table}\n"
            "\\end{document}\n"
        )
        docx_path = tmp_path / "d.docx"
        subprocess.run(["pandoc", str(tex), "-o", str(docx_path)],
                       capture_output=True, check=True)
        # tanımsız FigureTable stili enjekte et (ilk tablonun tblPr'sine)
        doc = zipfile.ZipFile(str(docx_path)).read('word/document.xml').decode('utf-8')
        doc = doc.replace('<w:tblPr>', '<w:tblPr><w:tblStyle w:val="FigureTable" />', 1)
        _rewrite_docx_member(str(docx_path), 'word/document.xml', doc.encode('utf-8'))
        _fix_docx_compat(str(docx_path))
        doc2 = zipfile.ZipFile(str(docx_path)).read('word/document.xml').decode('utf-8')
        assert "FigureTable" not in doc2          # tanımsız stil kaldırıldı
        assert '<w:tblStyle w:val="Table"' in doc2  # tanımlı Table stiline yönlendirildi


# =====================================================================
# Sağlamlık: export() asla istisna fırlatmamalı; regex daraltması
# =====================================================================


class TestExporterSaglamlik:
    def test_export_beklenmedik_istisna_yutulur(self, tmp_path, monkeypatch):
        """_export_native patlarsa export() (False, mesaj) dönmeli; istisna
        arka plan thread'ine sızarsa done sinyali düşmez, _export_busy
        sonsuza dek True kalırdı."""
        import core.exporter as ex

        tex = tmp_path / "a.tex"
        tex.write_text("\\begin{document}x\\end{document}\n")

        def patlat(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(ex, "_export_native", patlat)
        ok, err = ex.export(str(tex), str(tmp_path / "a.md"))
        assert ok is False
        assert "beklenmedik hata" in err and "boom" in err

    def test_md_width_regex_yalniz_gorsel_niteligini_duser(self, tmp_path):
        """Eski desen belge genelinde 'width' geçen her {...} bloğunu
        siliyordu; metin içi örnekler korunmalı."""
        from core.exporter import _fix_md_image_paths

        tex = tmp_path / "a.tex"
        tex.write_text("\\begin{document}x\\end{document}\n", encoding="utf-8")
        md = tmp_path / "a.md"
        md.write_text(
            "![ şekil ](media/fig1.png){width=70%}\n\n"
            "Metinde ölçü örneği: {image width: 5cm} şeklinde yazılır.\n\n"
            "![ diğeri ](media/fig2.png) {width=.8\\\\linewidth height=4cm}\n",
            encoding="utf-8")

        _fix_md_image_paths(str(tex), str(md))
        out = md.read_text(encoding="utf-8")

        assert "{width=70%}" not in out            # görsel niteliği düştü
        assert "fig1.png)" in out and "fig2.png)" in out
        assert "{image width: 5cm}" in out         # metin içi örnek duruyor

    def test_wsl_tmp_dest_pid_icerir(self, monkeypatch):
        """WSL ara çıktısı pid ile benzersizleşmeli (çakışma/ezilme)."""
        import core.exporter as ex

        tex = r"C:\proj\belge.tex"
        dest = r"C:\proj\belge.docx"
        pandoc_cmds = []

        def fake_run(cmd, **kw):
            if "pandoc" in " ".join(cmd):
                pandoc_cmds.append(" ".join(cmd))
            class R:  # basit sonuc
                returncode = 0
                stdout = ""
                stderr = ""
            return R()

        monkeypatch.setattr(ex, "PLATFORM", "win32")
        monkeypatch.setattr(ex.subprocess, "run", fake_run)
        ex._export_wsl(tex, dest)

        assert pandoc_cmds, "pandoc cagrisi yakalanamadi"
        import os
        import ntpath  # win32 yolunu bu test Linux'ta dogru ayirsin
        beklenen = f"/tmp/export_{os.getpid()}_{ntpath.basename(dest)}"
        assert beklenen in pandoc_cmds[0]
