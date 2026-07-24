"""log.py — merkezi logging testleri."""

import os
import logging
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


class TestLogPath:
    def test_returns_log_file_path(self, fresh_log):
        fresh_log.get_logger("test")
        path = fresh_log.log_path()
        assert path == fresh_log.LOG_FILE
        assert path.endswith("test.log")
