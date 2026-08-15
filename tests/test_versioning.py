"""versioning çekirdek testleri — dulwich anlık görüntü/geçmiş/geri okuma.

dulwich kurulu değilse modül atlar (isteğe bağlı bağımlılık).
"""

import pytest

dulwich = pytest.importorskip("dulwich")

import os  # noqa: E402

from core import versioning as V


def _mk(root):
    (root / "ana.tex").write_text(
        "\\begin{document}\nmerhaba\n\\end{document}\n", encoding="utf-8")
    sub = root / "bolumler"
    sub.mkdir(exist_ok=True)
    (sub / "giris.tex").write_text("giriş içeriği\n", encoding="utf-8")


# --- kurulum / is_repo ---


def test_init_creates_gitignore(tmp_path):
    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    assert V.is_repo(str(tmp_path))
    gi = tmp_path / ".gitignore"
    assert gi.exists() and "*.aux" in gi.read_text(encoding="utf-8")


def test_init_existing_repo_untouched(tmp_path):
    V.init_repo(str(tmp_path))
    gi = tmp_path / ".gitignore"
    gi.write_text("# özel ignore\n", encoding="utf-8")
    V.init_repo(str(tmp_path))  # ikinci kurulum dokunmamalı
    assert "# özel ignore" in gi.read_text(encoding="utf-8")


def test_is_repo_false(tmp_path):
    assert not V.is_repo(str(tmp_path))


# --- snapshot ---


def test_snapshot_and_history(tmp_path):
    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    e1 = V.snapshot(str(tmp_path), "Başlangıç")
    assert e1 is not None and len(e1.short) == 9 and len(e1.sha) == 40
    assert V.changed_files(str(tmp_path)) == set()

    h = V.history(str(tmp_path))
    assert len(h) == 1 and h[0].message == "Başlangıç"
    assert h[0].nfiles >= 3  # ana.tex, giris.tex, .gitignore


def test_snapshot_empty_returns_none(tmp_path):
    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "1")
    assert V.snapshot(str(tmp_path), "2") is None  # değişiklik yok
    assert len(V.history(str(tmp_path))) == 1


def test_snapshot_captures_modify_and_delete(tmp_path):
    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "1")

    (tmp_path / "ana.tex").write_text("\\begin{document}yeni\\end{document}\n",
                                      encoding="utf-8")
    (tmp_path / "bolumler" / "giris.tex").unlink()
    changed = V.changed_files(str(tmp_path))
    assert "ana.tex" in changed and "bolumler/giris.tex" in changed

    e = V.snapshot(str(tmp_path), "2")
    assert e is not None
    assert V.changed_files(str(tmp_path)) == set()  # silme de kayda girdi


def test_snapshot_ignores_build_artifacts(tmp_path):
    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "1")
    (tmp_path / "ana.log").write_text("log", encoding="utf-8")
    (tmp_path / "ana.pdf").write_bytes(b"%PDF")
    assert V.changed_files(str(tmp_path)) == set()
    assert V.snapshot(str(tmp_path), "2") is None


def test_snapshot_ignores_git_dir(tmp_path):
    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "1")
    # .git içine çöp dosya — değişiklik sayılmamalı
    (tmp_path / ".git" / "crash.file").write_text("x", encoding="utf-8")
    assert V.snapshot(str(tmp_path), "2") is None


# --- içerik geri okuma / fark ---


def test_file_content_and_diff(tmp_path):
    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "v1")
    sha = V.history(str(tmp_path))[0].sha

    content = V.file_content(str(tmp_path), sha, "bolumler/giris.tex")
    assert content == "giriş içeriği\n"

    (tmp_path / "bolumler" / "giris.tex").write_text(
        "değişmiş içerik\n", encoding="utf-8")
    diff = V.file_diff(str(tmp_path), sha, "bolumler/giris.tex")
    assert "-giriş içeriği" in diff and "+değişmiş içerik" in diff

    assert V.file_content(str(tmp_path), sha, "yok.tex") is None


def test_history_without_repo(tmp_path):
    assert V.history(str(tmp_path)) == []
    assert V.changed_files(str(tmp_path)) == set()


def test_real_git_reads_dulwich_repo(tmp_path):
    """dulwich deposunu gerçek git okuyabilmeli (dış araç uyumu)."""
    import subprocess

    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "dulwich kaydı")
    r = subprocess.run(["git", "log", "--oneline"], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0 and "dulwich kaydı" in r.stdout
