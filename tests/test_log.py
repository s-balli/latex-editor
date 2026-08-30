"""log.py — merkezi logging testleri."""

import io
import os
import logging
from logging.handlers import RotatingFileHandler

import pytest


@pytest.fixture
def fresh_log(tmp_path, monkeypatch):
    """Her test için temiz log ortamı."""
    # LOG_DIR ve _initialized'ı sıfırla
    import core.log as logmod
    monkeypatch.setattr(logmod, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(logmod, "LOG_FILE", str(tmp_path / "test.log"))
    monkeypatch.setattr(logmod, "_initialized", False)
    # Root logger'ı temizle
    root = logging.getLogger("latex_editor")
    for h in root.handlers[:]:
        root.removeHandler(h)
    yield logmod
    # Cleanup
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.setLevel(logging.WARNING)


class TestGetLogger:
    def test_returns_logger(self, fresh_log):
        logger = fresh_log.get_logger("test")
        assert isinstance(logger, logging.Logger)
        assert "latex_editor.test" in logger.name

    def test_creates_log_dir(self, fresh_log, tmp_path):
        fresh_log.get_logger("test")
        assert tmp_path.exists()

    def test_writes_to_file(self, fresh_log):
        logger = fresh_log.get_logger("test")
        logger.info("Test message 123")
        for h in logging.getLogger("latex_editor").handlers:
            h.flush()
        assert os.path.exists(fresh_log.LOG_FILE)
        with open(fresh_log.LOG_FILE, encoding="utf-8") as f:
            content = f.read()
        assert "Test message 123" in content

    def test_multiple_loggers_same_file(self, fresh_log):
        logger1 = fresh_log.get_logger("mod1")
        logger2 = fresh_log.get_logger("mod2")
        logger1.info("From mod1")
        logger2.info("From mod2")
        for h in logging.getLogger("latex_editor").handlers:
            h.flush()
        with open(fresh_log.LOG_FILE, encoding="utf-8") as f:
            content = f.read()
        assert "From mod1" in content
        assert "From mod2" in content

    def test_init_only_once(self, fresh_log):
        fresh_log.get_logger("a")
        first_handlers = len(logging.getLogger("latex_editor").handlers)
        fresh_log.get_logger("b")
        second_handlers = len(logging.getLogger("latex_editor").handlers)
        assert first_handlers == second_handlers


class TestConsoleHandler:
    """Paketlenmiş sürüm windowed (console=False): sys.stdout/stderr None olur.

    StreamHandler(None) stream'i sys.stderr'e (yine None) düşürür; her log
    kaydı emit()'te AttributeError atıp handleError() içinde sessizce yutulur.
    Görünür bir belirti yok, o yüzden testle sabitleniyor.
    """

    def test_stdout_varken_konsol_handleri_eklenir(self, fresh_log, monkeypatch):
        monkeypatch.setattr(fresh_log.sys, "stdout", io.StringIO())
        fresh_log.get_logger("test")
        handlers = logging.getLogger("latex_editor").handlers
        assert any(isinstance(h, logging.StreamHandler)
                   and not isinstance(h, RotatingFileHandler) for h in handlers)

    def test_stdout_yokken_konsol_handleri_eklenmez(self, fresh_log, monkeypatch):
        monkeypatch.setattr(fresh_log.sys, "stdout", None)
        fresh_log.get_logger("test")
        handlers = logging.getLogger("latex_editor").handlers
        assert [h for h in handlers if isinstance(h, RotatingFileHandler)], \
            "dosya handler'ı her koşulda kalmalı"
        assert not [h for h in handlers
                    if isinstance(h, logging.StreamHandler)
                    and not isinstance(h, RotatingFileHandler)]

    def test_stdout_yokken_log_sessizce_yutulmaz(self, fresh_log, monkeypatch):
        """Regresyon: her kayıt bir istisna kurup atıyordu; dosyaya yazım sürer."""
        monkeypatch.setattr(fresh_log.sys, "stdout", None)
        monkeypatch.setattr(fresh_log.sys, "stderr", None)
        logger = fresh_log.get_logger("test")
        yakalanan = []
        monkeypatch.setattr(logging.Handler, "handleError",
                            lambda self, record: yakalanan.append(record))
        logger.info("konsolsuz kayıt")
        for h in logging.getLogger("latex_editor").handlers:
            h.flush()
        assert yakalanan == [], "handler emit()'te hata verdi"
        with open(fresh_log.LOG_FILE, encoding="utf-8") as f:
            assert "konsolsuz kayıt" in f.read()


class TestConsoleEncoding:
    """Konsol dar kodlamalıysa (Türkçe Windows: cp1254) satır kaybolmamalı.

    Log metinlerinde '→' geçiyor (exporter, synctex_ops, file_ops...); cp1254'te
    bu karakter yok. errors="replace" olmadan emit() UnicodeEncodeError atar,
    handleError() yutar ve satır konsola HİÇ yazılmaz.
    """

    @staticmethod
    def _cp1254_konsol():
        ham = io.BytesIO()
        return ham, io.TextIOWrapper(ham, encoding="cp1254", newline="")

    def test_cp1254_konsolda_ok_karakteri_satiri_dusurmez(self, fresh_log, monkeypatch):
        ham, konsol = self._cp1254_konsol()
        monkeypatch.setattr(fresh_log.sys, "stdout", konsol)
        yutulan = []
        monkeypatch.setattr(logging.Handler, "handleError",
                            lambda self, record: yutulan.append(record))

        logger = fresh_log.get_logger("test")
        logger.info("Motor algılandı: a.tex → lualatex")
        for h in logging.getLogger("latex_editor").handlers:
            h.flush()

        assert yutulan == [], "handler emit()'te hata verdi, satır düştü"
        assert b"lualatex" in ham.getvalue(), "satır konsola hiç yazılmadı"

    def test_turkce_karakterler_bozulmadan_gecer(self, fresh_log, monkeypatch):
        """errors='replace' yalnız kodlanamayanı vurmalı; ş/ı/ğ cp1254'te var."""
        ham, konsol = self._cp1254_konsol()
        monkeypatch.setattr(fresh_log.sys, "stdout", konsol)
        logger = fresh_log.get_logger("test")
        logger.info("Sürüm alınıyor: değişiklik")
        for h in logging.getLogger("latex_editor").handlers:
            h.flush()
        assert "değişiklik" in ham.getvalue().decode("cp1254")

    def test_dosyaya_tam_metin_yazilir(self, fresh_log, monkeypatch):
        """Konsol '?' bassa da UTF-8 log dosyası '→' karakterini korumalı."""
        _, konsol = self._cp1254_konsol()
        monkeypatch.setattr(fresh_log.sys, "stdout", konsol)
        logger = fresh_log.get_logger("test")
        logger.info("a.tex → b.pdf")
        for h in logging.getLogger("latex_editor").handlers:
            h.flush()
        with open(fresh_log.LOG_FILE, encoding="utf-8") as f:
            assert "a.tex → b.pdf" in f.read()

    def test_reconfigure_desteklenmezse_patlamaz(self, fresh_log, monkeypatch):
        """reconfigure'ı olmayan stream (eski/sahte nesne) kurulumu düşürmemeli."""
        class _Eski(io.StringIO):
            def reconfigure(self, *a, **k):
                raise AttributeError("reconfigure yok")

        monkeypatch.setattr(fresh_log.sys, "stdout", _Eski())
        logger = fresh_log.get_logger("test")   # patlarsa test burada düşer
        logger.info("deneme")


class TestLogPath:
    def test_returns_log_file_path(self, fresh_log):
        fresh_log.get_logger("test")
        path = fresh_log.log_path()
        assert path == fresh_log.LOG_FILE
        assert path.endswith("test.log")
