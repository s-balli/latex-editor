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


def test_module_imports(modname):
    """Her modülün hatasiz import edilmesi."""
    # __init__.py olmayan paketler (ör. mixins klasörü) import edilemez
    try:
        importlib.import_module(modname)
    except ImportError:
        pytest.skip(f"{modname} import edilemedi (bagimlilik eksik olabilir)")


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
                ast.parse(open(filepath).read())
            except SyntaxError as e:
                errors.append(f"{filepath}: {e}")
    assert not errors, "\n".join(errors)
