"""compiler.py — derleme motoru testleri.

_find_derle_sh() ve temel LatexCompiler davranışlarını test eder.
QProcess gerçek derleme yapmaz (mock).
"""

import sys
from types import SimpleNamespace
import pytest
from unittest.mock import patch, MagicMock

# PyQt6 gereklidir
pytest.importorskip("PyQt6")
from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QApplication

import core.compiler as compiler_mod
from core.compiler import _find_derle_sh, LatexCompiler, PLATFORM

# QTimer (LatexCompiler watchdog'ı) için bir QApplication gerekir.
_app = QApplication.instance() or QApplication([])


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
        derle_sh.write_text("#!/bin/bash\necho test\n", encoding="utf-8")

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
        tex.write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}", encoding="utf-8")
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

    def test_recompile_releases_old_process(self, tmp_path):
        """Yeni derleme başlarken eski QProcess deleteLater ile bırakılmalı (sızıntı)."""
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}", encoding="utf-8")
        compiler = LatexCompiler()
        with patch.object(compiler, "_start_windows"), \
             patch.object(compiler, "_start_native"), \
             patch("core.compiler.QProcess") as mock_qproc:
            proc1, proc2 = MagicMock(), MagicMock()
            mock_qproc.side_effect = [proc1, proc2]
            assert compiler.compile(str(tex)) is True
            assert compiler.process is proc1
            # İlk derleme bitti (NotRunning) — yenisi eskisini bırakmalı.
            # Not: derleyicinin baktığı QProcess globali de patch'li olduğundan
            # guard karşılaştırması mock'un enum'uyla yapılmalı.
            proc1.state.return_value = mock_qproc.ProcessState.NotRunning
            assert compiler.compile(str(tex)) is True
            assert compiler.process is proc2
            proc1.deleteLater.assert_called_once()
        compiler._timeout_timer.stop()

    def test_compile_xelatex_arg(self, tmp_path):
        """xelatex motoru derle.sh'e --xelatex bayrağıyla iletilmeli (native yol)."""
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}", encoding="utf-8")
        compiler = LatexCompiler()
        # PLATFORM sabitlenir: Windows'ta compile() _start_windows'a gider ve
        # native dal hiç koşmaz — mock_proc.start çağrılmadığından call_args
        # None kalırdı. Test adı native yolu sınadığını söylüyor; öyle olsun.
        with patch("core.compiler.PLATFORM", "linux"), \
             patch("core.compiler.QProcess") as mock_qproc:
            mock_proc = MagicMock()
            mock_qproc.return_value = mock_proc
            assert compiler.compile(str(tex), engine="xelatex") is True
            args = mock_proc.start.call_args[0][1]
            assert "--xelatex" in args
            assert "--pdflatex" not in args
        compiler._timeout_timer.stop()

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


class TestDerlemeZamanAsimi:
    """Watchdog: derleme belirli sürede bitmezse iptal edilir."""

    @staticmethod
    def _compile_mocked(compiler, tmp_path, **kwargs):
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}", encoding="utf-8")
        with patch.object(compiler, "_start_windows"), \
             patch.object(compiler, "_start_native"), \
             patch("core.compiler.QProcess") as mock_qproc:
            mock_qproc.return_value = MagicMock()
            compiler.compile(str(tex), **kwargs)

    def test_compile_timer_baslar(self, tmp_path):
        c = LatexCompiler()
        self._compile_mocked(c, tmp_path)
        assert c._timeout_timer.isActive() is True
        c._timeout_timer.stop()

    def test_compile_timeout_ms_parametresi(self, tmp_path):
        c = LatexCompiler()
        self._compile_mocked(c, tmp_path, timeout_ms=5000)
        assert c._timeout_ms == 5000
        c._timeout_timer.stop()

    def test_default_timeout(self):
        assert compiler_mod.DEFAULT_TIMEOUT_MS == 120_000
        assert LatexCompiler()._timeout_ms == 120_000

    def test_on_timeout_sureci_oldurur_ve_hata_emit_eder(self):
        c = LatexCompiler()
        c.process = MagicMock()
        c.process.state.return_value = QProcess.ProcessState.Running
        results = []
        c.compilation_finished.connect(results.append)
        c._on_timeout()
        assert c._finished_emitted is True
        c.process.kill.assert_called_once()
        assert len(results) == 1
        assert results[0].success is False
        assert "zaman aşımına" in results[0].errors[0].message.lower()

    def test_on_timeout_calismiyor_ise_noop(self):
        c = LatexCompiler()
        c.process = None
        results = []
        c.compilation_finished.connect(results.append)
        c._on_timeout()
        assert results == []

    def test_on_finished_timer_durdurur(self):
        c = LatexCompiler()
        c._output = ""
        c._tex_path = "x.tex"
        c._timeout_timer.start(60000)
        c._on_finished(0, QProcess.ExitStatus.NormalExit)
        assert c._timeout_timer.isActive() is False

    def test_on_error_timer_durdurur(self):
        c = LatexCompiler()
        c._timeout_timer.start(60000)
        c._on_error(QProcess.ProcessError.FailedToStart)
        assert c._timeout_timer.isActive() is False

class TestWslKurulumOnerisi:
    def test_failed_to_start_win32_wsl_onerisi_tasir(self, monkeypatch):
        """Windows'ta süreç başlayamadıysa (WSL yok) sonuç kurulum önerisi
        taşır; OutputPanel buna bakarak Ortam Denetimi satırı açar."""
        monkeypatch.setattr(compiler_mod, "PLATFORM", "win32")
        c = LatexCompiler()
        results = []
        c.compilation_finished.connect(lambda r: results.append(r))
        c._on_error(QProcess.ProcessError.FailedToStart)
        assert len(results) == 1
        sugs = results[0].suggestions
        assert sugs and "wsl --install" in sugs[0].install_command

    def test_failed_to_start_native_oneri_tasimaz(self):
        """Linux'ta aynı hata WSL önerisi üretmez (WSL konusu yok)."""
        if compiler_mod.PLATFORM == "win32":
            pytest.skip("Windows'ta WSL önerisi beklenir")
        c = LatexCompiler()
        results = []
        c.compilation_finished.connect(lambda r: results.append(r))
        c._on_error(QProcess.ProcessError.FailedToStart)
        assert results and results[0].suggestions == []

class TestChunkCarryOver:
    """readyRead chunk sınırları: yarım ANSI dizisi / çok baytlı UTF-8 bölünmesi.

    Regression: readAllStandardOutput rastgele baytta keser; bölünen ANSI
    dizisi regex'ten kaçar ('\x1b[3' + '6m'), bölünen UTF-8 ise U+FFFD üretirdi.
    """

    @staticmethod
    def _feed(c, chunk: bytes):
        from PyQt6.QtCore import QByteArray
        c.process = SimpleNamespace(
            readAllStandardOutput=lambda d=chunk: QByteArray(d))
        c._on_output()

    def test_yarim_ansi_dizisi_sonraki_chunkta_tamamlanir(self):
        c = LatexCompiler()
        self._feed(c, b"\x1b[3")
        self._feed(c, b"6mDeneme\n")
        assert c._output == "Deneme\n"

    def test_yarim_ansi_ayni_chunkteki_tam_dizileri_bozmaz(self):
        c = LatexCompiler()
        self._feed(c, b"\x1b[1mA\x1b[3")     # tam dizi + yarım dizi
        self._feed(c, b"6mB\n")
        assert c._output == "AB\n"

    def test_cok_baytli_utf8_bolunmez(self):
        c = LatexCompiler()
        u = "ü".encode("utf-8")
        self._feed(c, "Merhaba ".encode("utf-8") + u[:1])
        self._feed(c, u[1:] + "!\n".encode("utf-8"))
        assert c._output == "Merhaba ü!\n"
        assert "�" not in c._output

    def test_flush_yarim_utf8yi_degistirerek_bosaltir(self):
        c = LatexCompiler()
        self._feed(c, b"\xc3")               # yarım karakter + süreç kapandı
        c._flush_output()
        assert c._output == "�"

    def test_wsl_exe_utf16_hatasi_okunabilir_geliyor(self):
        r"""wsl.exe KENDİ hatalarını UTF-16LE yazıyor (2026-08-30, E2).

        UTF-8 çözücüden geçince panele NUL dolu çöp düşüyordu
        ('S\x00a\x00\x1f\x01l\x00...'); WSL kurulu olmayan kullanıcı sorunun
        ne olduğunu söyleyen tek mesajı hiç göremiyordu.
        """
        c = LatexCompiler()
        mesaj = "Sağlanan ada sahip dağıtım yok.\r\n"
        self._feed(c, mesaj.encode("utf-16-le"))
        assert c._output == mesaj
        assert "\x00" not in c._output

    def test_normal_utf8_ciktisi_utf16_sanilmiyor(self):
        """NUL sezgisi düz LaTeX çıktısını bozmamalı."""
        c = LatexCompiler()
        self._feed(c, "Çıktı: başarılı — 0 hata\n".encode("utf-8"))
        assert c._output == "Çıktı: başarılı — 0 hata\n"
