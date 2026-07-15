"""compiler.py — derleme motoru testleri.

_find_derle_sh() ve temel LatexCompiler davranışlarını test eder.
QProcess gerçek derleme yapmaz (mock).
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# PyQt6 gereklidir
pytest.importorskip("PyQt6")
from PyQt6.QtCore import QProcess

import core.compiler as compiler_mod
from core.compiler import _find_derle_sh, LatexCompiler, PLATFORM


class TestFindDerleSh:
    def test_non_frozen_returns_core_derle_sh(self):
        """Normal (geliştirme) modda core/derle.sh döndürmeli."""
        with patch.object(sys, "frozen", False, create=True):
            path = _find_derle_sh()
            assert path.endswith("derle.sh")
            assert "core" in path

    def test_frozen_checks_meipass_core(self, tmp_path):
        """PyInstaller frozen modda _MEIPASS/core/derle.sh aramalı."""
        # Sahte _MEIPASS oluştur
        meipass = tmp_path / "meipass"
        core_dir = meipass / "core"
        core_dir.mkdir(parents=True)
        derle_sh = core_dir / "derle.sh"
        derle_sh.write_text("#!/bin/bash\necho test\n")

        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "_MEIPASS", str(meipass), create=True):
            path = _find_derle_sh()
            assert path == str(derle_sh)

    def test_frozen_falls_back_to_core_dir(self, tmp_path):
        """Frozen modda _MEIPASS'ta yoksa core_dir'e düşmeli."""
        meipass = tmp_path / "meipass"
        meipass.mkdir()

        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "_MEIPASS", str(meipass), create=True):
            path = _find_derle_sh()
            # core_dir/derle.sh döner (gerçek core/ dizini)
            assert path.endswith("derle.sh")

    def test_returns_string(self):
        """Dönüş değeri str olmalı."""
        path = _find_derle_sh()
        assert isinstance(path, str)
        assert len(path) > 0


class TestLatexCompiler:
    def test_initial_state(self):
        """Yeni LatexCompiler doğru başlangıç durumunda olmalı."""
        compiler = LatexCompiler()
        assert compiler._engine == "lualatex"
        assert compiler._output == ""
        assert compiler._tex_path == ""
        assert compiler._finished_emitted is False
        assert compiler.process is None

    def test_compile_busy_returns_false(self):
        """Zaten derliyorsa False dönmeli."""
        compiler = LatexCompiler()
        # Sahte meşgul process
        compiler.process = MagicMock()
        compiler.process.state.return_value = QProcess.ProcessState.Running
        result = compiler.compile("test.tex")
        assert result is False

    def test_compile_sets_engine(self, tmp_path):
        """compile() engine'i ayarlamalı."""
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}")
        compiler = LatexCompiler()
        # QProcess'i mock'la — gerçek derleme yapma
        with patch.object(compiler, "_start_windows"), \
             patch.object(compiler, "_start_native"), \
             patch("core.compiler.QProcess") as mock_qproc:
            mock_proc = MagicMock()
            mock_qproc.return_value = mock_proc
            result = compiler.compile(str(tex), engine="pdflatex")
            assert result is True
            assert compiler._engine == "pdflatex"
            assert compiler._tex_name == "test"
            assert compiler._tex_path == str(tex)

    def test_stop_no_process(self):
        """Process yoksa stop() hata vermemeli."""
        compiler = LatexCompiler()
        compiler.stop()  # hata vermemeli

    def test_stop_running(self):
        """Çalışan process'i durdurmalı."""
        compiler = LatexCompiler()
        compiler.process = MagicMock()
        compiler.process.state.return_value = QProcess.ProcessState.Running
        compiler.stop()
        compiler.process.kill.assert_called_once()

    def test_engine_property_default(self):
        """Default engine lualatex olmalı."""
        compiler = LatexCompiler()
        assert compiler._engine == "lualatex"

    def test_platform_constant(self):
        """PLATFORM sys.platform olmalı."""
        assert PLATFORM == sys.platform
