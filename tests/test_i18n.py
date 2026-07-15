"""core/i18n.py — çeviri altyapı testleri."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# PyQt6 mock — yalnızca gerçek PyQt6 YOKSA (eski/headless CI).
# DİKKAT: mock eskiden "PyQt6 not in sys.modules" koşuluyla toplanma anında
# koşulsuz enjekte ediliyordu ve toplamadan sonra sys.modules'te kalıyordu. Bu
# kirlilik tüm suite'i zehirliyordu: alfabetik olarak sonra toplanan test_imports
# ve lexer testleri "'PyQt6' is not a package" hatasıyla gerçek PyQt6.Qsci import
# edemeyip sessizce atlanıyordu. Artık mock yalnızca gerçek PyQt6 gerçekten yoksa
# devreye giriyor — PyQt6 kurulu ortamlarda sızıntı olmuyor.
try:
    from PyQt6.QtCore import QStandardPaths  # noqa: F401
    del QStandardPaths
except ImportError:
    _mock_qt = MagicMock()
    _mock_qt.QtCore.QStandardPaths.StandardLocation.AppLocalDataLocation = 0
    _mock_qt.QtCore.QStandardPaths.writableLocation.return_value = "/tmp/test_logs"
    sys.modules["PyQt6"] = _mock_qt
    sys.modules["PyQt6.QtCore"] = _mock_qt.QtCore
    sys.modules["PyQt6.QtWidgets"] = _mock_qt.QtWidgets
    sys.modules["PyQt6.QtGui"] = _mock_qt.QtGui
    sys.modules["PyQt6.QtQml"] = _mock_qt.QtQml

# Module-level reload: temiz state
if "core.i18n" in sys.modules:
    del sys.modules["core.i18n"]

from core.i18n import (
    init, translator, _translate, available_languages,
    set_language, _find_trans_dir, _lang_name,
)


@pytest.fixture(autouse=True)
def _reset_backend():
    """Her test öncesi backend'i sıfırla."""
    import core.i18n as mod
    mod._backend = None
    mod._trans_dir = None
    yield
    mod._backend = None
    mod._trans_dir = None


# --- init ---

class TestInit:
    def test_no_app_does_nothing(self):
        """app=None verilirse hiçbir şey yapmamalı."""
        init(app=None)
        import core.i18n as mod
        assert mod._backend is None

    @patch("core.i18n.os.path.isfile", return_value=True)
    @patch("core.i18n.os.path.getsize", return_value=1000)
    def test_loads_translator(self, mock_size, mock_exists):
        """translator.load başarılı olursa backend kurulmalı."""
        mock_app = MagicMock()
        mock_translator = MagicMock()
        mock_translator.load.return_value = True

        with patch("PyQt6.QtCore.QTranslator", return_value=mock_translator):
            with patch("PyQt6.QtCore.QSettings") as MockSettings:
                MockSettings.return_value.value.return_value = "en"
                init(app=mock_app)

        mock_app.installTranslator.assert_called_once_with(mock_translator)
        import core.i18n as mod
        assert mod._backend is not None

    @patch("core.i18n.os.path.isfile", return_value=False)
    def test_load_fails_no_crash(self, mock_exists):
        """translator.load başarısız olsa bile crash olmamalı."""
        mock_app = MagicMock()
        mock_translator = MagicMock()
        mock_translator.load.return_value = False

        with patch("PyQt6.QtCore.QTranslator", return_value=mock_translator):
            with patch("PyQt6.QtCore.QSettings") as MockSettings:
                MockSettings.return_value.value.return_value = "en"
                init(app=mock_app)

        import core.i18n as mod
        assert mod._backend is None

    @patch("core.i18n.os.path.isfile", return_value=True)
    @patch("core.i18n.os.path.getsize", return_value=1000)
    def test_uses_system_locale_when_no_setting(self, mock_size, mock_exists):
        """Ayarda dil yoksa sistem locale kullanılmalı."""
        mock_app = MagicMock()
        mock_translator = MagicMock()
        mock_translator.load.return_value = True

        with patch("PyQt6.QtCore.QTranslator", return_value=mock_translator):
            with patch("PyQt6.QtCore.QSettings") as MockSettings:
                MockSettings.return_value.value.return_value = ""
                with patch("PyQt6.QtCore.QLocale") as MockLocale:
                    MockLocale.system.return_value.name.return_value = "en_US"
                    init(app=mock_app)

        call_args = mock_translator.load.call_args[0][0]
        assert "latexeditor_" in call_args


# --- translator ---

class TestTranslator:
    def test_returns_callable(self):
        fn = translator("TestCtx")
        assert callable(fn)

    def test_no_backend_returns_original(self):
        """Backend yoksa orijinal metin dönmeli."""
        fn = translator("TestCtx")
        assert fn("merhaba") == "merhaba"

    def test_with_backend_delegates(self):
        """Backend varsa translate'e delegasyon yapılmalı."""
        import core.i18n as mod
        mock_backend = MagicMock()
        mock_backend.translate.return_value = "hello"
        mod._backend = mock_backend

        fn = translator("TestCtx")
        result = fn("merhaba")
        assert result == "hello"
        mock_backend.translate.assert_called_once_with("TestCtx", "merhaba")


# --- _translate ---

class TestTranslate:
    def test_no_backend_passthrough(self):
        assert _translate("Ctx", "text") == "text"

    def test_with_backend(self):
        import core.i18n as mod
        mock_backend = MagicMock()
        mock_backend.translate.return_value = "translated"
        mod._backend = mock_backend

        assert _translate("Ctx", "text") == "translated"


# --- available_languages ---

class TestAvailableLanguages:
    def test_returns_turkish_always(self):
        """Türkçe her zaman listede olmalı."""
        langs = available_languages()
        codes = [c for c, _ in langs]
        assert "tr" in codes

    @patch("core.i18n.os.path.isdir", return_value=False)
    def test_no_dir_returns_only_turkish(self, mock_isdir):
        """Dizin yoksa sadece Türkçe dönmeli."""
        langs = available_languages()
        assert len(langs) == 1
        assert langs[0] == ("tr", "Türkçe")

    @patch("core.i18n.os.path.isdir", return_value=True)
    @patch("core.i18n.os.listdir", return_value=[
        "latexeditor_en.qm", "latexeditor_tr.qm", "latexeditor_fr.qm", "readme.txt"
    ])
    def test_finds_qm_files(self, mock_listdir, mock_isdir):
        """Dizindeki .qm dosyalarından dil listesi üretmeli."""
        langs = available_languages()
        codes = [c for c, _ in langs]
        assert "tr" in codes
        assert "en" in codes
        assert "fr" in codes
        assert "readme" not in codes


# --- set_language ---

class TestSetLanguage:
    def test_saves_to_settings(self):
        with patch("PyQt6.QtCore.QSettings") as MockSettings:
            mock_settings = MagicMock()
            MockSettings.return_value = mock_settings
            set_language("en")
            mock_settings.setValue.assert_called_once_with("language", "en")

    def test_turkish_saves_too(self):
        with patch("PyQt6.QtCore.QSettings") as MockSettings:
            mock_settings = MagicMock()
            MockSettings.return_value = mock_settings
            set_language("tr")
            mock_settings.setValue.assert_called_once_with("language", "tr")


# --- _find_trans_dir ---

class TestFindTransDir:
    def test_dev_mode_path(self):
        """Geliştirme modunda doğru yolu dönmeli."""
        path = _find_trans_dir()
        assert path.endswith("translations")
        assert "desktop" in path

    def test_frozen_mode_path(self):
        """PyInstaller modunda sys._MEIPASS kullanmalı."""
        original_frozen = getattr(sys, 'frozen', None)
        original_meipass = getattr(sys, '_MEIPASS', None)
        try:
            sys.frozen = True
            sys._MEIPASS = "/tmp/_MEI123"
            path = _find_trans_dir()
            assert "_MEI123" in path
        finally:
            if original_frozen is None:
                del sys.frozen
            else:
                sys.frozen = original_frozen
            if original_meipass is None:
                del sys._MEIPASS
            else:
                sys._MEIPASS = original_meipass


# --- _lang_name ---

class TestLangName:
    def test_known_language(self):
        assert _lang_name("en") == "English"
        assert _lang_name("de") == "Deutsch"
        assert _lang_name("fr") == "Français"

    def test_unknown_returns_code(self):
        assert _lang_name("xx") == "xx"


# --- Import güvenlik ---

class TestImportSafety:
    def test_all_imports_in_init_are_resolvable(self):
        """init() içinde kullanılan tüm Qt sınıfları import edilmeli."""
        import ast
        source = open("core/i18n.py").read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "init":
                init_source = ast.get_source_segment(source, node)
                break

        for node in ast.walk(ast.parse(init_source)):
            if isinstance(node, ast.ImportFrom) and node.module and "PyQt6" in node.module:
                imported = [alias.name for alias in node.names]

        qt_classes = {"QCoreApplication", "QLocale", "QSettings", "QTranslator"}
        for cls in qt_classes:
            if cls in init_source:
                assert cls in imported, (
                    f"{cls} init() içinde kullanılıyor ama import edilmiş değil. "
                    f"Bu NameError'a neden olur."
                )

    def test_all_imports_in_set_language_are_resolvable(self):
        """set_language() içinde kullanılan Qt sınıfları import edilmeli."""
        import ast
        source = open("core/i18n.py").read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "set_language":
                fn_source = ast.get_source_segment(source, node)
                break

        imported = []
        for node in ast.walk(ast.parse(fn_source)):
            if isinstance(node, ast.ImportFrom) and node.module and "PyQt6" in node.module:
                imported = [alias.name for alias in node.names]

        if "QSettings" in fn_source:
            assert "QSettings" in imported, "QSettings kullanılıyor ama import edilmemiş"

    def test_all_imports_in_backend_are_resolvable(self):
        """_QtBackend.translate() içinde kullanılan Qt sınıfları import edilmeli."""
        import ast
        source = open("core/i18n.py").read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "_QtBackend":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "translate":
                        fn_source = ast.get_source_segment(source, item)
                        imported = []
                        for child in ast.walk(item):
                            if isinstance(child, ast.ImportFrom) and \
                               child.module and "PyQt6" in child.module:
                                imported = [alias.name for alias in child.names]
                        if "QCoreApplication" in fn_source:
                            assert "QCoreApplication" in imported, \
                                "QCoreApplication kullanılıyor ama import edilmemiş"


# --- main.py başlatma testi ---

class TestMainStartup:
    def test_core_imports_resolve(self):
        """main.py'nin bağımlı olduğu core modülleri import edilebilmeli.

        core.i18n, core.log, core.version gibi modüllerde
        NameError (unutulmuş import) varsa yakalar.
        """
        import ast
        main_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "desktop", "main.py"
        )
        source = open(main_path).read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("PyQt6"):
                    continue
                if node.module.startswith("gui"):
                    continue  # gui desktop'ta, QScintilla vb. gerektirir
                try:
                    __import__(node.module)
                except ImportError as e:
                    pytest.fail(f"main.py import hatası: from {node.module} — {e}")

    def test_main_function_exists(self):
        """main.py'de main() fonksiyonu tanımlı olmalı."""
        import ast
        main_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "desktop", "main.py"
        )
        source = open(main_path).read()
        tree = ast.parse(source)

        fn_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert "main" in fn_names

    def test_main_calls_init_i18n(self):
        """main() fonksiyonu init_i18n(app) çağırmalı."""
        import ast
        main_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "desktop", "main.py"
        )
        source = open(main_path).read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                fn_source = ast.get_source_segment(source, node)
                assert "init_i18n" in fn_source, "main() init_i18n çağırmıyor"

    def test_main_translate_lambda_before_mainwindow(self):
        """main.py'de _() lambda tanımı MainWindow importundan önce olmalı."""
        import ast
        main_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "desktop", "main.py"
        )
        source = open(main_path).read()
        lines = source.split("\n")

        lambda_line = None
        mainwindow_line = None
        for i, line in enumerate(lines):
            if "_ = lambda" in line and "translate" in line:
                lambda_line = i
            if "from gui.main_window import MainWindow" in line:
                mainwindow_line = i

        assert lambda_line is not None, "_() lambda tanımı bulunamadı"
        assert mainwindow_line is not None, "MainWindow importu bulunamadı"
        assert lambda_line < mainwindow_line, (
            f"_() lambda (satır {lambda_line}) MainWindow importundan (satır {mainwindow_line}) önce olmalı"
        )
