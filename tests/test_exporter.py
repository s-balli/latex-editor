"""exporter.py — pandoc dışa aktarma testleri."""

import os
import re
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
    def test_windows_native_pandoc_yetmez(self, mock_which, mock_wsl):
        """Windows'ta NATIVE pandoc kullanılmıyor: export() her zaman WSL'e gider.

        Bu test eskiden True bekliyordu, yani hatayı sabitliyordu
        (2026-08-30 denetimi, E5): pandoc'u Windows'a kurmuş ama WSL'e
        kurmamış kullanıcıda menü açık kalıyor, uyarı çıkmıyor ve dışa
        aktarma sessizce başarısız oluyordu.
        """
        mock_which.return_value = "C:\\pandoc.exe"
        assert pandoc_available() is False

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
        # Yol platformun kendi biçiminde kurulur: Windows'ta "/home/user/doc.tex"
        # dirname'i "C:\home\user" olur (sürücü harfi eklenir), sabit POSIX
        # dizgesiyle karşılaştırma orada tutmaz.
        src = os.path.join(os.sep, "home", "user", "doc.tex")
        args = _pandoc_args(src, os.path.join(os.sep, "home", "user", "doc.docx"))
        # _pandoc_args abspath'ten dirname alıyor; Windows'ta bu sürücü harfi
        # ekler ("\home\user" -> "C:\home\user"). Beklenti aynı yoldan kurulur.
        beklenen = os.path.dirname(os.path.abspath(src))
        assert f"--resource-path={beklenen}" in args


class TestExtractGraphicsPaths:
    # read_data artık BAYT: `_extract_graphics_paths` dosyayı ikili açıp
    # `coz()` ile çözüyor (eski kodlamalı .tex'lerde `errors="replace"`
    # Türkçe dizin adlarını bozuyordu). Metin taklidi bırakılsaydı
    # `coz()` `.decode()` bulamayıp istisna atardı ve fonksiyon [] dönerdi:
    # `test_no_graphicspath` o hâlde YANLIŞ SEBEPTEN geçerdi.
    @patch("builtins.open", new_callable=mock_open, read_data=rb"\graphicspath{{media/}{images/}}")
    def test_multiple_paths(self, mock_f):
        result = _extract_graphics_paths("test.tex")
        assert result == ["media/", "images/"]

    @patch("builtins.open", new_callable=mock_open, read_data=rb"\graphicspath{{media/}}")
    def test_single_path(self, mock_f):
        result = _extract_graphics_paths("test.tex")
        assert result == ["media/"]

    @patch("builtins.open", new_callable=mock_open, read_data=b"no graphicspath here")
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
        tex_file.write_text(r"\graphicspath{{media/}}", encoding="utf-8")
        md_file = tmp_path / "doc.md"
        md_file.write_text("![alt](image.png)", encoding="utf-8")
        _fix_md_image_paths(str(tex_file), str(md_file))
        content = md_file.read_text(encoding="utf-8")
        assert "media/image.png" in content
        # fix: göreceli yol .tex dizinine göre mutlak yapıldı (sadece substring değil).
        # Markdown yolu her platformda '/' ayraçlı üretilir; Windows'ta
        # str(tex_file.parent) ters bölü verdiği için karşılaştırma normalize edilir.
        assert str(tex_file.parent).replace(os.sep, "/") in content

    def test_absolute_path_unchanged(self, tmp_path):
        tex_file = tmp_path / "doc.tex"
        tex_file.write_text("no graphicspath", encoding="utf-8")
        md_file = tmp_path / "doc.md"
        md_file.write_text("![alt](/absolute/image.png)", encoding="utf-8")
        _fix_md_image_paths(str(tex_file), str(md_file))
        content = md_file.read_text(encoding="utf-8")
        assert "/absolute/image.png" in content

    def test_http_url_unchanged(self, tmp_path):
        tex_file = tmp_path / "doc.tex"
        tex_file.write_text("no graphicspath", encoding="utf-8")
        md_file = tmp_path / "doc.md"
        md_file.write_text("![alt](https://example.com/img.png)", encoding="utf-8")
        _fix_md_image_paths(str(tex_file), str(md_file))
        content = md_file.read_text(encoding="utf-8")
        assert "https://example.com/img.png" in content

    def test_pandoc_width_attribute_removed(self, tmp_path):
        tex_file = tmp_path / "doc.tex"
        tex_file.write_text("no graphicspath", encoding="utf-8")
        md_file = tmp_path / "doc.md"
        md_file.write_text('![alt](image.png){width="70%"}', encoding="utf-8")
        _fix_md_image_paths(str(tex_file), str(md_file))
        content = md_file.read_text(encoding="utf-8")
        assert '{width="70%"}' not in content


# --- önişleme: abstract/title -> gövdeye taşı (elsarticle fix) ---


class TestPreprocess:
    def test_abstract_becomes_section(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\begin{abstract}\nÖzet metni.\n\\end{abstract}", encoding="utf-8")
        out = _preprocess_tex(str(tex))
        content = open(out, encoding="utf-8").read()
        assert "\\section*{Abstract}" in content
        assert "\\begin{abstract}" not in content
        assert "\\end{abstract}" not in content
        if out != str(tex):
            import os; os.unlink(out)

    def test_title_becomes_section(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\title{Belge Başlığı}\n\\section{X}", encoding="utf-8")
        out = _preprocess_tex(str(tex))
        content = open(out, encoding="utf-8").read()
        assert "\\section*{Belge Başlığı}" in content
        import os; os.unlink(out) if out != str(tex) else None

    def test_title_with_optional_arg(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\title[Kısa]{Uzun Başlık}", encoding="utf-8")
        out = _preprocess_tex(str(tex))
        content = open(out, encoding="utf-8").read()
        assert "\\section*{Uzun Başlık}" in content
        import os; os.unlink(out) if out != str(tex) else None

    def test_frontmatter_stripped(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\begin{frontmatter}\n\\title{X}\n\\end{frontmatter}\n\\section{Y}", encoding="utf-8")
        out = _preprocess_tex(str(tex))
        content = open(out, encoding="utf-8").read()
        assert "\\begin{frontmatter}" not in content
        assert "\\end{frontmatter}" not in content
        import os; os.unlink(out) if out != str(tex) else None

    def test_no_change_returns_original(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\section{Gövde}\nMetin.", encoding="utf-8")
        out = _preprocess_tex(str(tex))
        assert out == str(tex)  # değişiklik yok -> geçici dosya yok


# --- bibliography tespiti ---


class TestFindBibliography:
    # Dönüş LİSTE: `\bibliography{a,b}` LaTeX'te geçerli ve pandoc her dosya
    # için ayrı `--bibliography` alabiliyor. Tek dize dönerken virgüllü ad
    # "a,b.bib" diye aranıyor, bulunamıyor ve kaynakça hiç çözülmüyordu.
    def test_bibliography_command(self, tmp_path):
        tex = tmp_path / "d.tex"
        (tmp_path / "refs.bib").write_text("@article{x,...}", encoding="utf-8")
        tex.write_text("\\bibliography{refs}", encoding="utf-8")
        assert _find_bibliography(str(tex)) == [str(tmp_path / "refs.bib")]

    def test_addbibresource(self, tmp_path):
        tex = tmp_path / "d.tex"
        (tmp_path / "src.bib").write_text("@article{x,...}", encoding="utf-8")
        tex.write_text("\\addbibresource{src.bib}", encoding="utf-8")
        assert _find_bibliography(str(tex)) == [str(tmp_path / "src.bib")]

    def test_missing_bib_file(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\bibliography{refs}", encoding="utf-8")  # refs.bib yok
        assert _find_bibliography(str(tex)) == []

    def test_no_bibliography(self, tmp_path):
        tex = tmp_path / "d.tex"
        tex.write_text("\\section{X}\nMetin.", encoding="utf-8")
        assert _find_bibliography(str(tex)) == []


# --- _pandoc_args bibliography desteği ---


class TestPandocArgsBib:
    def test_args_include_citeproc_when_bib(self):
        args = _pandoc_args("/d/a.tex", "/d/a.md", bibs=["/d/refs.bib"])
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
        , encoding="utf-8")
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
        , encoding="utf-8")
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Metin \\cite{kazemi2025synthetic}.\n"
            "\\bibliography{refs}\n\\end{document}\n"
        , encoding="utf-8")
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
        bib.write_text("@article{k,\nauthor={Kazemi, A.},\ntitle={T},\nyear={2020}}\n", encoding="utf-8")
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Metin \\cite{k}.\n\\bibliography{refs}\n\\end{document}\n"
        , encoding="utf-8")
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
        , encoding="utf-8")
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
        , encoding="utf-8")
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Metin \\cite{k}.\n\\bibliography{refs}\n\\end{document}\n"
        , encoding="utf-8")
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
        bib.write_text("@article{k,\nauthor={Kazemi},\ntitle={T},\nyear={2025}}\n", encoding="utf-8")
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Metin \\cite{k}.\n\\bibliography{refs}\n\\end{document}\n"
        , encoding="utf-8")
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
        , encoding="utf-8")
        md = tmp_path / "d.md"
        md.write_text("See [@k].\n", encoding="utf-8")
        _resolve_md_citations(str(md), "", str(bib))   # tex yoksa inline yine çözülür
        content = md.read_text(encoding="utf-8")
        assert "(A et al. 2024)" in content   # 3+ yazar -> et al.

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_multi_cite_keys_inline(self, tmp_path):
        bib = tmp_path / "r.bib"
        bib.write_text(
            "@article{k1,\nauthor={Kazemi, A.},\ntitle={S},\nyear={2025}}\n"
            "@article{k2,\nauthor={Hasan, M.},\ntitle={L},\nyear={2026}}\n"
        , encoding="utf-8")
        md = tmp_path / "d.md"
        md.write_text("[@k1; @k2]\n", encoding="utf-8")
        _resolve_md_citations(str(md), "", str(bib))
        content = md.read_text(encoding="utf-8")
        assert "(Kazemi 2025; Hasan 2026)" in content

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_unknown_key_left_as_is(self, tmp_path):
        bib = tmp_path / "r.bib"
        bib.write_text("@article{k1,\nauthor={A},\ntitle={T},\nyear={2020}}\n", encoding="utf-8")
        md = tmp_path / "d.md"
        md.write_text("[@k1] and [@unknownkey]\n", encoding="utf-8")
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
        _pandoc_csljson([r"C:\refs.bib"])
        args = mock_run.call_args[0][0]
        assert args[0] == "wsl" and "pandoc" in args

    @patch("core.exporter.PLATFORM", "linux")
    @patch("core.exporter.subprocess.run")
    def test_native_pandoc_on_linux(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        _pandoc_csljson(["/r/refs.bib"])
        args = mock_run.call_args[0][0]
        assert args[0] == "pandoc" and args[1] == "/r/refs.bib"

    @patch("core.exporter.PLATFORM", "linux")
    def test_empty_on_pandoc_failure(self):
        # pandoc bulunamazsa boş döner (sessiz başarısızlık değil).
        with patch("core.exporter.subprocess.run", side_effect=FileNotFoundError):
            assert _pandoc_csljson(["/r/refs.bib"]) == ""


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
        , encoding="utf-8")
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
        , encoding="utf-8")
        docx_path = tmp_path / "d.docx"
        ok, _ = export(str(tex), str(docx_path))
        assert ok
        d = _docx.Document(str(docx_path))   # çökmemeli
        assert len(d.paragraphs) >= 1

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_undefined_table_style_replaced(self, tmp_path):
        # pandoc 3.1.3 FigureTable bug'ı simülasyonu: tanımsız stili enjekte et, düzelir mi?
        import zipfile, subprocess
        tex = tmp_path / "d.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\begin{table}[h]\\caption{X}\\begin{tabular}{c}1\\\\\\end{tabular}\\end{table}\n"
            "\\end{document}\n"
        , encoding="utf-8")
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
        tex.write_text("\\begin{document}x\\end{document}\n", encoding="utf-8")

        def patlat(*a, **k):
            raise RuntimeError("boom")

        # PLATFORM sabitlenir: Windows'ta export() _export_wsl'e gider ve
        # yamalanan _export_native hiç çağrılmaz — istisna doğmaz, test yanlışlıkla
        # ok=True görürdü. Sınanan davranış (istisna yutulur) platformdan bağımsız.
        monkeypatch.setattr(ex, "PLATFORM", "linux")
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
            "![ diğeri ](media/fig2.png) {width=.8\\\\linewidth height=4cm}\n", encoding="utf-8")

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


class TestMdResimYollari:
    r"""Markdown dışa aktarımda TÜM \graphicspath dizinleri denenmeli (A7).

    _fix_md_image_paths tüm göreli yollara koşulsuz graphics_paths[0] önekini
    ekliyordu: ikinci dizin hiç denenmiyor, tam yol yazılmış görsel de
    'media/media/logo.png' oluyordu. Sonuç sessizce kırık bağlantıydı —
    yanlış yol istisna üretmediği için except da yakalamıyordu.
    """

    def _kur(self, tmp_path):
        from core.exporter import _fix_md_image_paths
        (tmp_path / "sekil1").mkdir()
        (tmp_path / "sekil2").mkdir()
        (tmp_path / "sekil1" / "a.png").write_bytes(b"x")
        (tmp_path / "sekil2" / "b.png").write_bytes(b"x")
        (tmp_path / "duz.png").write_bytes(b"x")
        tex = tmp_path / "m.tex"
        tex.write_text("\\graphicspath{{sekil1/}{sekil2/}}\n", encoding="utf-8")
        return _fix_md_image_paths, tex

    def _yollar(self, md_path):
        import re
        icerik = md_path.read_text(encoding="utf-8")
        return re.findall(r'!\[[^\]]*\]\(([^)]+)\)', icerik)

    def test_ikinci_graphicspath_dizini_de_deneniyor(self, tmp_path):
        duzelt, tex = self._kur(tmp_path)
        md = tmp_path / "m.md"
        md.write_text("![bir](a.png)\n![iki](b.png)\n", encoding="utf-8")
        duzelt(str(tex), str(md))
        yollar = self._yollar(md)
        assert len(yollar) == 2
        for y in yollar:
            assert os.path.isfile(y), f"kırık bağlantı: {y}"

    def test_tam_yol_yazilmis_gorsel_ikiye_katlanmiyor(self, tmp_path):
        duzelt, tex = self._kur(tmp_path)
        md = tmp_path / "m.md"
        md.write_text("![uc](duz.png)\n", encoding="utf-8")
        duzelt(str(tex), str(md))
        (yol,) = self._yollar(md)
        assert "sekil1/duz.png" not in yol.replace(os.sep, "/")
        assert os.path.isfile(yol)

    def test_mutlak_ve_url_dokunulmuyor(self, tmp_path):
        duzelt, tex = self._kur(tmp_path)
        md = tmp_path / "m.md"
        md.write_text("![u](https://ornek.org/x.png)\n", encoding="utf-8")
        duzelt(str(tex), str(md))
        assert self._yollar(md) == ["https://ornek.org/x.png"]


# ---------------------------------------------------------------------------
# ESKİ TÜRKÇE KODLAMALAR
#
# Üç okuma da `errors="replace"` kullanıyordu. cp1254/iso-8859-9 bir .tex'te
# her Türkçe harf U+FFFD oluyor ve `_preprocess_tex` o hâli GEÇİCİ DOSYAYA
# YAZIP pandoc'a veriyordu: dışa aktarma "başarılı" dönüyor, çıktıda Türkçe
# harfler yok.
#
# Bozulma tam olarak ÖNİŞLEMEYE bağlıydı; önişleme tetiklenmeyen belgeler
# temiz geçiyordu. Yani kusuru üreten, çıktıyı iyileştirmek için eklenmiş
# adımın kendisiydi.
#
# BU TESTLER GERÇEK DOSYA KULLANIR. Dosyadaki mock tabanlı testler bu sınıfı
# göremez: `read_data` ne verilirse o okunur, kodlama zinciri hiç çalışmaz.
# ---------------------------------------------------------------------------

_TR_BASLIKLI = (
    "\\documentclass{article}\n"
    "\\title{Başlık: Öğrenci Çalışması}\n"
    "\\begin{document}\n"
    "\\begin{abstract}\nÖzet: çğıöşü ÇĞİÖŞÜ\n\\end{abstract}\n"
    "Gövde: Çağrı Öztürk şekil üzerinde çalıştı.\n"
    "\\end{document}\n"
)


def _yaz(yol, icerik, kodlama):
    yol.write_bytes(icerik.encode(kodlama))
    return str(yol)


class TestEskiKodlama:
    @pytest.mark.parametrize("kodlama", ["cp1254", "iso-8859-9"])
    def test_onisleme_turkce_harfleri_korumali(self, tmp_path, kodlama):
        """Geçici dosya U+FFFD taşımamalı; pandoc onu okuyor."""
        p = _yaz(tmp_path / "makale.tex", _TR_BASLIKLI, kodlama)
        tmp = _preprocess_tex(p)
        assert tmp != p, "önişleme tetiklenmedi, test bir şey sınamıyor"
        try:
            icerik = open(tmp, encoding="utf-8").read()
            assert icerik.count("\ufffd") == 0, "Türkçe harfler bozuldu"
            assert "Çağrı Öztürk" in icerik
            # Önişlemenin asıl işi de yapılmış olmalı
            assert "\\section*{Başlık: Öğrenci Çalışması}" in icerik
        finally:
            os.unlink(tmp)

    def test_utf8_belge_bozulmadi(self, tmp_path):
        """Karşı durum: utf-8 yolu birebir aynı kalmalı."""
        p = _yaz(tmp_path / "makale.tex", _TR_BASLIKLI, "utf-8")
        tmp = _preprocess_tex(p)
        try:
            icerik = open(tmp, encoding="utf-8").read()
            assert icerik.count("\ufffd") == 0
            assert "Çağrı Öztürk" in icerik
        finally:
            os.unlink(tmp)

    def test_onisleme_gerekmiyorsa_orijinal_yol(self, tmp_path):
        """Karşı durum: değişiklik yoksa geçici dosya üretilmemeli."""
        sade = ("\\documentclass{article}\n"
                "\\begin{document}\nÇağrı\n\\end{document}\n")
        p = _yaz(tmp_path / "sade.tex", sade, "utf-8")
        assert _preprocess_tex(p) == p

    def test_cp1254_belgede_turkce_adli_bib_bulunuyor(self, tmp_path):
        """Bulunamazsa kaynakça HİÇ çözülmez, referans listesi üretilmez."""
        belge = ("\\documentclass{article}\n\\bibliography{kaynakça}\n"
                 "\\begin{document}x\\end{document}\n")
        p = _yaz(tmp_path / "makale.tex", belge, "cp1254")
        (tmp_path / "kaynakça.bib").write_text("@article{a,\n}\n", encoding="utf-8")
        assert _find_bibliography(p) == [str(tmp_path / "kaynakça.bib")]

    def test_cp1254_belgede_turkce_graphicspath(self, tmp_path):
        """Bozulursa o dizindeki hiçbir görsel bulunamaz."""
        belge = ("\\documentclass{article}\n\\graphicspath{{şekiller/}}\n"
                 "\\begin{document}x\\end{document}\n")
        p = _yaz(tmp_path / "makale.tex", belge, "cp1254")
        assert _extract_graphics_paths(p) == ["şekiller/"]

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    def test_uctan_uca_cp1254_ciktisi_temiz(self, tmp_path):
        """Asıl değişmez: kullanıcının aldığı dosyada Türkçe harfler durmalı.

        Kusur "başarısız" olarak değil, BAŞARILI dönerek bozuyordu.
        """
        p = _yaz(tmp_path / "makale.tex", _TR_BASLIKLI, "cp1254")
        hedef = tmp_path / "cikti.txt"
        ok, err = export(p, str(hedef))
        assert ok is True, err
        cikti = hedef.read_text(encoding="utf-8", errors="replace")
        assert cikti.count("\ufffd") == 0, "çıktıda değiştirme karakteri var"
        assert "Öztürk" in cikti
        assert "ÇĞİÖŞÜ" in cikti


# ---------------------------------------------------------------------------
# UZANTI HARF DUYARLILIĞI
#
# `export()` `dest_path.endswith(".md")` diyordu, oysa AYNI dosyadaki
# `_pandoc_args` `os.path.splitext(...)[1].lower()` kullanıyor. Kullanıcı
# hedefi "rapor.MD" diye yazınca (uzantı Windows'ta harf duyarsız) pandoc
# markdown üretiyor ama son işlemler atlanıyordu.
# ---------------------------------------------------------------------------

_MD_BELGE = ("\\documentclass{article}\n"
             "\\begin{document}\n"
             "Bir çalışma \\cite{ornek2024} bunu gösterdi.\n"
             "\\begin{figure}\\includegraphics{logo}\\end{figure}\n"
             "\\bibliography{kaynaklar}\n"
             "\\end{document}\n")
_MD_BIB = ("@article{ornek2024,\n  author = {Ozturk, Cagri},\n"
           "  title = {Bir calisma},\n  year = {2024},\n"
           "  journal = {Test Dergisi}\n}\n")


def _md_proje(tmp_path):
    p = tmp_path / "makale.tex"
    p.write_text(_MD_BELGE, encoding="utf-8")
    (tmp_path / "kaynaklar.bib").write_text(_MD_BIB, encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n")
    return str(p)


def _md_ozet(tmp_path, hedef):
    icerik = hedef.read_text(encoding="utf-8", errors="replace")
    return {
        "resim_mutlak": str(tmp_path).replace(os.sep, "/") in icerik,
        "citation_cozuldu": "@ornek2024" not in icerik,
        "references_var": "## References" in icerik,
    }


class TestUzantiHarfDuyarliligi:
    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    @pytest.mark.parametrize("ad", ["cikti.md", "cikti.MD", "cikti.Md"])
    def test_md_son_islemleri_uzanti_harfinden_bagimsiz(self, tmp_path, ad):
        """Resim yolları mutlaklanmalı, citation çözülmeli, References gelmeli.

        Büyük harfli uzantıda üçü birden atlanıyordu ve dışa aktarma yine
        "başarılı" diyordu.
        """
        p = _md_proje(tmp_path)
        hedef = tmp_path / ad
        ok, err = export(p, str(hedef))
        assert ok is True, err
        assert _md_ozet(tmp_path, hedef) == {
            "resim_mutlak": True,
            "citation_cozuldu": True,
            "references_var": True,
        }

    @pytest.mark.skipif(not _PANDOC, reason="pandoc gerekli")
    @pytest.mark.parametrize("ad", ["cikti.docx", "cikti.DOCX"])
    def test_docx_uyumluluk_dali_uzanti_harfinden_bagimsiz(self, tmp_path, ad):
        r"""Word'ün açabilmesi için `_fix_docx_compat` her iki yazımda da koşmalı.

        SARKAN ANCHOR üzerinden sınanıyor: olmayan bir etikete `\ref`,
        pandoc'ta karşılığı bookmark olmayan bir hyperlink üretiyor ve Word
        böyle bir dosyayı açmayı reddediyor. `_fix_docx_compat` onu düz
        metne çeviriyor.

        Test KENDİ ÖNKOŞULUNU da doğruluyor: düzeltme devre dışıyken sarkan
        anchor'ın GERÇEKTEN oluştuğu ayrıca sınanıyor. Yoksa ileride pandoc
        o hyperlink'i hiç üretmez olursa test sessizce boşa düşerdi.
        """
        import zipfile

        belge = ("\\documentclass{article}\n"
                 "\\begin{document}\n"
                 "Şekil \\ref{olmayan-etiket} incelendi.\n"
                 "\\end{document}\n")
        p = tmp_path / "makale.tex"
        p.write_text(belge, encoding="utf-8")

        def _sarkan(docx):
            with zipfile.ZipFile(str(docx)) as z:
                doc = z.read("word/document.xml").decode("utf-8")
            bookmarks = set(re.findall(
                r'<w:bookmarkStart[^>]*w:name="([^"]+)"', doc))
            anchorlar = re.findall(r'<w:hyperlink[^>]*w:anchor="([^"]+)"', doc)
            return [a for a in anchorlar if a not in bookmarks]

        # Önkoşul: düzeltme koşmazsa sarkan anchor oluşuyor mu
        ham = tmp_path / ("ham_" + ad)
        with patch("core.exporter._fix_docx_compat"):
            ok, err = export(str(p), str(ham))
        assert ok is True, err
        assert _sarkan(ham), "senaryo artık sarkan anchor üretmiyor, test boş"

        # Asıl sınama: düzeltme koştuğunda sarkan anchor kalmamalı
        hedef = tmp_path / ad
        ok, err = export(str(p), str(hedef))
        assert ok is True, err
        assert zipfile.is_zipfile(str(hedef))
        assert _sarkan(hedef) == [], "sarkan anchor kaldı, Word açamaz"
        assert not (tmp_path / (ad + ".tmp")).exists(), "geçici dosya kaldı"

    def test_uzanti_kurali_dosya_icinde_TEK(self):
        """`export` ile `_pandoc_args` aynı kuralı kullanmalı.

        Ayrışmanın kendisi kusurdu: bir dosyada iki kural vardı.
        """
        for ad in ("r.md", "r.MD", "r.docx", "r.DOCX", "r.HtMl", "r.TXT"):
            beklenen = os.path.splitext(ad)[1].lower()
            args = _pandoc_args("/x/a.tex", "/x/" + ad)
            # _pandoc_args'ın kararı uzantının küçük harfli hâline dayanmalı
            if beklenen == ".html":
                assert "--standalone" in args, ad
            elif beklenen == ".txt":
                assert "-t" in args and "plain" in args, ad
            else:
                assert "--standalone" not in args, ad


# ==========================================================================
# Exporter YORUMA ALINMIS bildirimleri okuyordu
#
# `.tex` dosyalari alternatif kaynakcayi ve eski gorsel dizinini yoruma
# alinmis tasiyor; `re.search` ILK eslesmeyi aliyordu, yani yorumdakini.
# OLCULDU (2026-09-06, gercek pandoc 3.1.3 ile UCTAN UCA):
#
#   %\bibliography{silinmis}   ustte, gercek \bibliography{kaynaklar} altta
#   -> export() True donuyor, cikti dosyasi olusuyor, ama kaynakca ciktida
#      HIC YOK ve <div id="refs"> uretilmiyor.
#
# `core.engine_detector` ayni dosyayi okurken `strip_comments`i zaten
# cagiriyordu; iki yer ayrismisti.
# ==========================================================================

class TestExporterYorumAyiklama:

    def _proje(self, tmp_path, tex_icerik, bibler=("kaynaklar", "eski")):
        for ad in bibler:
            (tmp_path / (ad + ".bib")).write_text("@article{%s,\n}\n" % ad,
                                                  encoding="utf-8")
        tex = tmp_path / "belge.tex"
        tex.write_text(tex_icerik, encoding="utf-8")
        return str(tex)

    def test_YORUMDAKI_bibliography_secilmiyor(self, tmp_path):
        tex = self._proje(tmp_path,
                          "%\\bibliography{eski}\n\\bibliography{kaynaklar}\n")
        assert _find_bibliography(tex) == [str(tmp_path / "kaynaklar.bib")]

    def test_YORUMDAKI_bib_DISKTE_YOKSA_gercek_satir_okunuyor(self, tmp_path):
        """En sinsi hali: yorumdaki ad diskte yoktu, fonksiyon HIC BIR SEY
        dondurmuyordu ve kaynakca ciktidan tumden dusuyordu."""
        tex = self._proje(tmp_path,
                          "%\\bibliography{silinmis}\n"
                          "\\bibliography{kaynaklar}\n")
        assert _find_bibliography(tex) == [str(tmp_path / "kaynaklar.bib")]

    def test_YORUMDAKI_addbibresource_secilmiyor(self, tmp_path):
        tex = self._proje(tmp_path,
                          "% \\addbibresource{eski.bib}\n"
                          "\\addbibresource{kaynaklar.bib}\n")
        assert _find_bibliography(tex) == [str(tmp_path / "kaynaklar.bib")]

    def test_KACIRILMIS_yuzde_satiri_yutmuyor(self, tmp_path):
        """`\\%` yorum degil; asiri ayiklama gercek satiri dusurmemeli."""
        tex = self._proje(tmp_path,
                          "Kar 100\\% artti.\n\\bibliography{kaynaklar}\n")
        assert _find_bibliography(tex) == [str(tmp_path / "kaynaklar.bib")]

    def test_YORUMDAKI_graphicspath_listeye_girmiyor(self, tmp_path):
        tex = self._proje(tmp_path,
                          "% \\graphicspath{{eski/}}\n"
                          "\\graphicspath{{media/}}\n")
        assert _extract_graphics_paths(tex) == ["media/"]

    def test_YALNIZ_yorumdaki_graphicspath_bos_liste(self, tmp_path):
        tex = self._proje(tmp_path, "% \\graphicspath{{eski/}}\n")
        assert _extract_graphics_paths(tex) == []

    def test_GERCEK_graphicspath_hala_okunuyor(self, tmp_path):
        """Asiri ayiklama kapisi."""
        tex = self._proje(tmp_path, "\\graphicspath{{media/}{sekiller/}}\n")
        assert _extract_graphics_paths(tex) == ["media/", "sekiller/"]


# ==========================================================================
# `\bibliography{a,b}` LaTeX'te gecerli
#
# Donus tek dizeyken virgullu ad "a,b.bib" diye araniyor, diskte
# bulunamiyor ve "" donuyordu; yani iki kaynakcali her belgede kaynakca
# TUMDEN dusuyordu (olculdu, uctan uca).
# ==========================================================================

class TestVirgulluBibliography:

    def _kur(self, tmp_path, satir, adlar=("kaynaklar", "ek")):
        for ad in adlar:
            (tmp_path / (ad + ".bib")).write_text("@article{%s,\n}\n" % ad,
                                                  encoding="utf-8")
        tex = tmp_path / "belge.tex"
        tex.write_text(satir, encoding="utf-8")
        return str(tex)

    def test_IKISI_de_donuyor(self, tmp_path):
        tex = self._kur(tmp_path, "\\bibliography{kaynaklar,ek}\n")
        assert _find_bibliography(tex) == [str(tmp_path / "kaynaklar.bib"),
                                           str(tmp_path / "ek.bib")]

    def test_BOSLUKLU_virgul_de_calisiyor(self, tmp_path):
        tex = self._kur(tmp_path, "\\bibliography{kaynaklar, ek}\n")
        assert len(_find_bibliography(tex)) == 2

    def test_DISKTE_OLMAYAN_parca_atlanip_otekiler_kaliyor(self, tmp_path):
        tex = self._kur(tmp_path, "\\bibliography{kaynaklar,yok}\n")
        assert _find_bibliography(tex) == [str(tmp_path / "kaynaklar.bib")]

    def test_HICBIRI_yoksa_bos_liste(self, tmp_path):
        tex = self._kur(tmp_path, "\\bibliography{yok1,yok2}\n", adlar=())
        assert _find_bibliography(tex) == []


# ==========================================================================
# pandoc BICIM kurali TEK KAYNAKTA
#
# Yollar iki yolda farkli (native platform yolu, WSL `/mnt/...`) ama bicim
# kurali ayni ve `_pandoc_args` ile `_export_wsl` onu ayri ayri yaziyordu.
# Bu depo yinelenen paketleme/uzanti tanimindan birkac kez yandi.
# ==========================================================================

class TestBicimArgumanlariTekKaynak:

    def test_export_wsl_yardimciyi_CAGIRIYOR(self):
        import inspect
        import core.exporter as ex
        kaynak = inspect.getsource(ex._export_wsl)
        assert "_bicim_argumanlari" in kaynak

    @pytest.mark.parametrize("parca", ["--standalone", "--embed-resources",
                                       "--citeproc", '"plain"'])
    def test_export_wsl_kendi_KOPYASINI_tutmuyor(self, parca):
        """Kirilirsa kural yine iki yerde demektir."""
        import inspect
        import core.exporter as ex
        assert parca not in inspect.getsource(ex._export_wsl)

    def test_pandoc_args_da_ayni_yardimciyi_kullaniyor(self):
        import inspect
        import core.exporter as ex
        assert "_bicim_argumanlari" in inspect.getsource(ex._pandoc_args)

    @pytest.mark.parametrize("hedef,beklenen", [
        ("a.html", ["--standalone", "--embed-resources"]),
        ("a.HTML", ["--standalone", "--embed-resources"]),
        ("a.txt", ["-t", "plain"]),
        ("a.docx", []),
        ("a.md", []),
    ])
    def test_bicim_kurali(self, hedef, beklenen):
        from core.exporter import _bicim_argumanlari
        assert _bicim_argumanlari(hedef) == beklenen

    def test_IKI_bib_iki_bibliography_TEK_citeproc(self):
        from core.exporter import _bicim_argumanlari
        args = _bicim_argumanlari("a.md", ["/x/a.bib", "/x/b.bib"])
        assert args.count("--citeproc") == 1
        assert args.count("--bibliography=/x/a.bib") == 1
        assert args.count("--bibliography=/x/b.bib") == 1

    def test_BIB_yoksa_citeproc_yok(self):
        from core.exporter import _bicim_argumanlari
        assert "--citeproc" not in _bicim_argumanlari("a.md", [])

    @patch("core.exporter.subprocess.run")
    @patch("core.exporter.PLATFORM", "win32")
    def test_WSL_yolu_iki_bibi_de_geciriyor(self, mock_run, tmp_path):
        """Yollar `/mnt/...`e cevrilmeli, ikisi birden gitmeli."""
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr="")
        _export_wsl(r"C:\p\d.tex", r"C:\p\d.html",
                    [r"C:\p\a.bib", r"C:\p\b.bib"])
        komut = mock_run.call_args_list[0][0][0][-1]
        assert komut.count("--bibliography=") == 2, komut
        assert "/mnt/c/p/a.bib" in komut and "/mnt/c/p/b.bib" in komut, komut
        assert "--standalone" in komut, komut


# ==========================================================================
# `bibs` girisinin normalize edilmesi
#
# Dize de ITERE EDILEBILIR: `for b in bibs` tek yol verildiginde onu
# KARAKTERLERE bolup `--bibliography=/`, `--bibliography=x` ... uretirdi.
# pandoc bunlara takilmadan devam ettigi icin hata sessiz kalir, yalnizca
# kaynakca kaybolurdu. OLCULDU: `_find_bibliography` liste donmeye baslayinca
# eski imzayla yazilmis uc test tam bu sekilde dustu (2026-09-06, Linux).
# ==========================================================================

class TestBibListesiNormalizasyonu:

    def test_DIZGE_karakterlere_BOLUNMUYOR(self):
        from core.exporter import _bicim_argumanlari
        args = _bicim_argumanlari("a.md", "/x/kaynaklar.bib")
        assert args.count("--bibliography=/x/kaynaklar.bib") == 1, args
        assert args.count("--citeproc") == 1, args

    def test_BOS_dizge_kaynakca_saymiyor(self):
        from core.exporter import _bicim_argumanlari
        assert _bicim_argumanlari("a.md", "") == []

    @pytest.mark.parametrize("giris,beklenen", [
        ("/x/a.bib", ["/x/a.bib"]),
        ("", []),
        ((), []),
        (["/x/a.bib", "/x/b.bib"], ["/x/a.bib", "/x/b.bib"]),
        (("/x/a.bib",), ["/x/a.bib"]),
    ])
    def test_normalize(self, giris, beklenen):
        from core.exporter import _bib_listesi
        assert _bib_listesi(giris) == beklenen

    @patch("core.exporter.PLATFORM", "linux")
    @patch("core.exporter._pandoc_run", return_value="[]")
    def test_csljson_da_dizgeyi_bolmuyor(self, mock_run):
        _pandoc_csljson("/x/kaynaklar.bib")
        assert mock_run.call_args[0][0] == ["/x/kaynaklar.bib", "-t", "csljson"]
