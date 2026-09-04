"""versioning çekirdek testleri — dulwich anlık görüntü/geçmiş/geri okuma.

dulwich kurulu değilse modül atlar (isteğe bağlı bağımlılık).
"""

import pytest

dulwich = pytest.importorskip("dulwich")


from core import versioning as V


def _mk(root):
    # newline="": Windows'ta metin modu '\n' -> '\r\n' çevirir; testler git
    # blob'unu BAYT olarak geri okuyup karşılaştırdığı için satır sonu aynen
    # yazılmalı (yoksa 'giriş içeriği\r\n' != 'giriş içeriği\n').
    (root / "ana.tex").write_text(
        "\\begin{document}\nmerhaba\n\\end{document}\n", encoding="utf-8", newline="")
    sub = root / "bolumler"
    sub.mkdir(exist_ok=True)
    (sub / "giris.tex").write_text("giriş içeriği\n", encoding="utf-8", newline="")


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

    (tmp_path / "ana.tex").write_text("\\begin{document}yeni\\end{document}\n", encoding="utf-8")
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


def test_drop_all_history(tmp_path):
    """Tüm geçmiş silinir (.git gider), dosyalar kalır."""
    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "1")
    assert V.is_repo(str(tmp_path))

    assert V.drop_all(str(tmp_path)) is True
    assert not V.is_repo(str(tmp_path))
    assert (tmp_path / "ana.tex").exists()
    assert V.history(str(tmp_path)) == []

    assert V.drop_all(str(tmp_path)) is False  # zaten yok


def test_drop_last_version(tmp_path):
    """Son kayıt geçmişten düşer; dosyalar ve ilk kayıt kalır."""
    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "1")
    (tmp_path / "ana.tex").write_text("değişti\n", encoding="utf-8")
    V.snapshot(str(tmp_path), "2")
    assert len(V.history(str(tmp_path))) == 2

    assert V.drop_last(str(tmp_path)) is True
    assert len(V.history(str(tmp_path))) == 1
    assert V.history(str(tmp_path))[0].message == "1"
    # çalışma klasörüne dokunulmaz: değişiklik hâlâ dosyada
    assert (tmp_path / "ana.tex").read_text(encoding="utf-8") == "değişti\n"

    # son (tek) kayıt silinmez — kök
    assert V.drop_last(str(tmp_path)) is False


def test_real_git_reads_dulwich_repo(tmp_path):
    """dulwich deposunu gerçek git okuyabilmeli (dış araç uyumu)."""
    import subprocess

    _mk(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "dulwich kaydı")
    r = subprocess.run(["git", "log", "--oneline"], cwd=str(tmp_path),
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "dulwich kaydı" in r.stdout


def test_restore_preserves_cp1254_bytes(tmp_path):
    """Geri yükleme HAM bayt yazmalı: cp1254 dosyada bozulma olmamalı.

    Regression: içerik utf-8 replace ile metne çevrilip yazılıyordu; Türkçe
    karakterler değiştirme karakterine dönüşüyor, derleme bozuk çıkıyordu.
    """
    raw = "% Türkçe açıklama\nğüş ti\n".encode("cp1254")
    (tmp_path / "eski.tex").write_bytes(raw)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "v1")
    sha = V.history(str(tmp_path))[0].sha

    assert V.file_bytes(str(tmp_path), sha, "eski.tex") == raw
    # gösterim fonksiyonu metin döner (fark ekranı; bozuk bayt → değiştirme)
    assert "a" in (V.file_content(str(tmp_path), sha, "eski.tex") or "")


def test_module_importable_without_dulwich():
    """dulwich yoksa uygulama çökmemeli: import başarılı, özellik kapalı.

    Regression: dulwich kurulu olmayan makinede (ör. kullanıcının Windows
    Python'u) main.py import zinciri ModuleNotFoundError ile düşüyordu.
    """
    import importlib
    import sys

    saved = {k: sys.modules.pop(k) for k in list(sys.modules)
             if k == "dulwich" or k.startswith("dulwich.")}
    sys.modules["dulwich"] = None  # 'import dulwich' → ImportError
    try:
        mod = importlib.reload(V)
        assert mod.DULWICH_AVAILABLE is False
        assert mod.history("/tmp") == []
        assert mod.changed_files("/tmp") == set()
    finally:
        del sys.modules["dulwich"]
        sys.modules.update(saved)
        importlib.reload(V)
    assert V.DULWICH_AVAILABLE is True


# --- Dosya SAYISI: iki panel tek kaynaktan okumalı ---
#
# Sayının iki ayrı kaynağı vardı: "Sürümle" onu `status` çıktısındaki girdi
# sayısından (version_ops.py:241), geçmiş paneli ise `tree_changes`'ten
# (output_panel.py:680) alıyordu. dulwich'in status'u öntanımlı kipte tümüyle
# izlenmeyen bir DİZİNİ tek girdi ('bolumler/') olarak döndürdüğü için ikisi
# ÇELİŞİYORDU: aynı kayıt için durum çubuğu "2 dosya", geçmiş paneli
# "6 dosya" diyordu (ölçüldü). Dosyalar kayda giriyordu, yalnız sayılmıyordu.


_BOLUMLER = ["giris", "yontem", "bulgular", "tartisma", "sonuc"]


def _temel_proje(root):
    """Tek dosyalı, bir kez sürümlenmiş proje."""
    (root / "ana.tex").write_text("\\documentclass{article}\n",
                                  encoding="utf-8", newline="")
    V.init_repo(str(root))
    V.snapshot(str(root), "temel")


def _bolumlere_ayir(root):
    """Gerçekçi tetikleyici: belgeyi YENİ bir alt dizine bölmek."""
    sub = root / "bolumler"
    sub.mkdir()
    for ad in _BOLUMLER:
        (sub / (ad + ".tex")).write_text("\\section{%s}\n" % ad,
                                         encoding="utf-8", newline="")
    (root / "ana.tex").write_text(
        "\\documentclass{article}\n\\input{bolumler/giris}\n",
        encoding="utf-8", newline="")


def test_yeni_alt_dizin_dosya_dosya_sayiliyor(tmp_path):
    """changed_files DOSYA döndürmeli, dizin değil (adının vaadi bu)."""
    _temel_proje(tmp_path)
    _bolumlere_ayir(tmp_path)

    degisen = V.changed_files(str(tmp_path))
    assert not [p for p in degisen if p.endswith("/")], \
        "dizin girdisi döndü: %s" % sorted(degisen)
    assert degisen == {"ana.tex"} | {"bolumler/%s.tex" % a for a in _BOLUMLER}


def test_snapshot_ve_history_ayni_sayiyi_veriyor(tmp_path):
    """Aynı kayıt, uygulamanın iki ayrı yerinde, TEK sayı.

    Asıl değişmez bu: sayının nereden okunduğu değişse bile iki panel
    birbiriyle çelişmemeli.
    """
    _temel_proje(tmp_path)
    _bolumlere_ayir(tmp_path)

    e = V.snapshot(str(tmp_path), "bölümlere ayırma")
    h = V.history(str(tmp_path))
    assert e is not None
    assert e.nfiles == h[0].nfiles, \
        "durum çubuğu %d, geçmiş paneli %d diyor" % (e.nfiles, h[0].nfiles)
    assert e.nfiles == 1 + len(_BOLUMLER)      # ana.tex + bölümler
    assert V.changed_files(str(tmp_path)) == set()


def test_ic_ice_yeni_dizinler(tmp_path):
    """Birden çok seviye yeni dizin de tek tek sayılmalı."""
    _temel_proje(tmp_path)
    derin = tmp_path / "a" / "b" / "c"
    derin.mkdir(parents=True)
    (derin / "derin.tex").write_text("x\n", encoding="utf-8", newline="")
    (tmp_path / "a" / "b" / "yuzey.tex").write_text("y\n", encoding="utf-8",
                                                    newline="")

    assert V.changed_files(str(tmp_path)) == {"a/b/c/derin.tex",
                                              "a/b/yuzey.tex"}
    e = V.snapshot(str(tmp_path), "iç içe")
    assert e.nfiles == V.history(str(tmp_path))[0].nfiles == 2


def test_derleme_artiklari_sayiya_girmiyor(tmp_path):
    """Karşı durum: .gitignore'daki artıklar ne sayılır ne boş kayıt üretir."""
    _temel_proje(tmp_path)
    (tmp_path / "build").mkdir()
    for ad in ("ana.aux", "ana.log", "ana.pdf", "build/x.aux"):
        (tmp_path / ad).write_text("artık\n", encoding="utf-8", newline="")

    assert V.changed_files(str(tmp_path)) == set()
    assert V.snapshot(str(tmp_path), "boş") is None
    assert len(V.history(str(tmp_path))) == 1


def test_mevcut_dizine_ekleme_bozulmadi(tmp_path):
    """Karşı durum: dizin zaten izleniyorsa eskiden de doğruydu."""
    _temel_proje(tmp_path)
    sub = tmp_path / "bolumler"
    sub.mkdir()
    (sub / "bir.tex").write_text("1\n", encoding="utf-8", newline="")
    V.snapshot(str(tmp_path), "ilk bölüm")

    (sub / "iki.tex").write_text("2\n", encoding="utf-8", newline="")
    (sub / "uc.tex").write_text("3\n", encoding="utf-8", newline="")
    assert V.changed_files(str(tmp_path)) == {"bolumler/iki.tex",
                                              "bolumler/uc.tex"}
