"""exporter.py — pandoc dışa aktarma testleri."""

import subprocess
import sys
from unittest.mock import MagicMock, patch, mock_open


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
