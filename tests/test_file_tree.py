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


def test_input_ref_ok_tek_okumayla_iki_denetim(qapp, tmp_path, monkeypatch):
    """Bağlantılı dosya denetimi dosyayı TEK kez açmalı (can_compile +
    detect_root ayrı ayrı okuyordu); kök yönlendirmesi de çalışmalı."""
    from gui.file_tree import FileTree

    root = tmp_path / "main.tex"
    root.write_text("\\begin{document}\\input{bolum}\\end{document}\n")
    child = tmp_path / "bolum.tex"
    child.write_text("% !TEX root = main.tex\nparca\n")

    tree = FileTree(theme=THEMES["dark"])
    acilis = {"n": 0}
    gercek_open = open

    def sayan_open(file, *a, **k):
        if str(file).endswith("bolum.tex"):
            acilis["n"] += 1
        return gercek_open(file, *a, **k)

    import builtins
    monkeypatch.setattr(builtins, "open", sayan_open)

    assert tree._input_ref_ok(str(child)) is True      # kök yönlendirmesi
    assert acilis["n"] == 1, "dosya tek kez açılmalı"

    plain = tmp_path / "bagimsiz.tex"
    plain.write_text("\\begin{document}tam belge\\end{document}\n")
    assert tree._input_ref_ok(str(plain)) is True      # doğrudan derlenebilir
    parcacik = tmp_path / "parca2.tex"
    parcacik.write_text("yalnızca parça\n")
    assert tree._input_ref_ok(str(parcacik)) is False
