"""Import testleri — tum modüllerin yüklenip yüklenmedigini kontrol eder."""

import ast
import importlib
import os

import pytest

# PyQt6 varsa gercek import, yoksa skip
pyqt6 = pytest.importorskip("PyQt6")
pytest.importorskip("PyQt6.Qsci")
pytest.importorskip("pypdfium2")

# Modül taraması için desktop/ kökü (sys.path'i conftest.py ayarlar)
_DESKTOP = os.path.join(os.path.dirname(__file__), "..", "desktop")


# desktop/ altindaki tüm .py dosyalarini topla
def _all_py_modules():
    desktop = os.path.abspath(_DESKTOP)
    modules = []
    for root, dirs, files in os.walk(desktop):
        # __pycache__, .venv, build klasörlerini atla
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".venv", ".venv-build", "build", "dist")]
        for f in files:
            if not f.endswith(".py") or f == "__init__.py":
                continue
            filepath = os.path.join(root, f)
            relpath = os.path.relpath(filepath, desktop)
            # gui/pdf_viewer_mixins/_search.py → gui.pdf_viewer_mixins._search
            modname = relpath.replace(os.sep, ".")[:-3]
            modules.append(modname)
    return modules


@pytest.fixture(params=_all_py_modules(), ids=lambda x: x)
def modname(request):
    return request.param


# Eksikliği SKIP sebebi olan üçüncü parti paketler. Bunun DIŞINDAki her
# ImportError bizim kodumuzun hatasıdır ve testi kırmalıdır.
_UCUNCU_PARTI = {
    "PyQt6", "Qsci", "pypdfium2", "PIL", "send2trash", "dulwich",
}


def test_module_imports(modname):
    """Her modülün hatasiz import edilmesi.

    ImportError'ı koşulsuz yutup skip etmek, asıl yakalaması gereken şeyi
    kaçırıyordu: ModuleNotFoundError ImportError'ın alt sınıfı olduğundan
    BİZİM kodumuzdaki kırık bir iç import (bir modül taşındıktan sonra kalan
    `from gui.eski_ad import X`) eksik bağımlılıkla aynı kefeye giriyor ve
    test SKIP oluyordu — CI yemyeşil geçiyordu.

    Bu özellikle önemli: env_doctor, settings_dialog, quick_open,
    table_wizard, outline ve find_replace ana pencereye TIKLAMA anında lazy
    import ediliyor, yani test_main_window_imports zincirine hiç girmiyorlar.
    Tek import kapıları bu test.
    """
    try:
        importlib.import_module(modname)
    except ImportError as exc:
        kok = (exc.name or "").split(".")[0]
        if kok in _UCUNCU_PARTI:
            pytest.skip(f"{modname}: {kok} kurulu değil")
        raise


def test_main_window_imports():
    """Ana pencerenin tam import zinciri."""
    from gui.main_window import MainWindow
    assert MainWindow is not None


def test_all_py_files_valid_syntax():
    """desktop/ altindaki tüm .py dosyalari gecerli Python syntax."""
    desktop = os.path.abspath(_DESKTOP)
    errors = []
    for root, dirs, files in os.walk(desktop):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            filepath = os.path.join(root, f)
            try:
                ast.parse(open(filepath, encoding="utf-8").read())
            except SyntaxError as e:
                errors.append(f"{filepath}: {e}")
    assert not errors, "\n".join(errors)
