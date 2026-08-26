"""FileTree._collect_files — snapshot/refresh yürüyüşünün atlama kuralları.

Ağaç çizimi _SKIP_DIRS/_MAX_DEPTH uyguluyordu; snapshot yürüyüşü de aynı
kuralları uygulamalı (her FS olayında koşar, WSL'de pahalı).
"""

import os

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.file_tree import FileTree
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_collect_files_skip_ve_derinlik_kurallari(qapp, tmp_path):
    (tmp_path / "ana.tex").write_text("x")
    sub = tmp_path / "bolum"
    sub.mkdir()
    (sub / "giris.tex").write_text("x")
    for skip in ("node_modules", "venv", "__pycache__"):
        d = tmp_path / skip
        d.mkdir()
        (d / f"{skip}.tex").write_text("x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "gizli.tex").write_text("x")

    # _MAX_DEPTH = 5: kök düzey 0; 6 seviye derindeki dosya taranmamalı
    deep = tmp_path
    for i in range(6):
        deep = deep / f"d{i}"
        deep.mkdir()
    (deep / "cok_derin.tex").write_text("x")

    tree = FileTree(theme=THEMES["dark"])
    files = tree._collect_files(str(tmp_path))

    got = {os.path.relpath(f, str(tmp_path)).replace(os.sep, "/") for f in files}
    assert got == {"ana.tex", "bolum/giris.tex"}
