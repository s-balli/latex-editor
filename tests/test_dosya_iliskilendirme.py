# -*- coding: utf-8 -*-
r"""Linux `.desktop` kaydı: Exec alanı boşluklu yolu bozmadan taşımalı.

`main._register_file_association` AppImage'ın gerçek yolunu (`$APPIMAGE`)
Exec alanına yazıyor. Alan TIRNAKSIZDI ve Desktop Entry şartnamesi bu alanı
boşluğa göre argümanlara ayırıyor. AppImage kullanıcının indirdiği yerden
koşuyor, yani `~/Downloads/LaTeX Editor.AppImage` sıradan bir yol; tırnaksız
biçimde program adı ikiye bölünüyordu (ölçüldü 2026-09-06:
`/home/k/Downloads/LaTeX` + `Editor.AppImage`), yani menü girdisi ve `.tex`
ilişkilendirmesi hiçbir şey açmıyordu. Aynı dosyadaki Windows dalı bu dersi
zaten biliyordu: `f'"{exe_path}" "%1"'`.

Kapı, kaynaktan kopyalanmış bir dizgeyi değil ÜRETİM KODUNUN ÇIKTISINI sınar:
Linux dalı monkeypatch'lenmiş bir ortamda koşturulup yazdığı `.desktop`
okunuyor.
"""

import os
import shlex

import pytest

pytest.importorskip("PyQt6")


# `$` ve backtick için shlex ORACLE DEĞİL: çift tırnak içinde bu ikisinin
# kaçışını çözmüyor, oysa şartname (ve gerçek kabuk) çözüyor. Onlarda
# üretilen biçim sınanıyor.
_KACISLI_KARAKTERLER = ('"', "\\", "$", "`")


def _desktop_uret(monkeypatch, tmp_path, exe_path: str) -> str:
    """Linux dalını koştur, yazılan `.desktop` içeriğini döndür."""
    import main as m

    ev = str(tmp_path / "ev")
    meipass = str(tmp_path / "meipass")
    os.makedirs(meipass, exist_ok=True)

    monkeypatch.setattr(m.sys, "frozen", True, raising=False)
    monkeypatch.setattr(m.sys, "platform", "linux")
    monkeypatch.setattr(m.sys, "_MEIPASS", meipass, raising=False)
    monkeypatch.setenv("APPIMAGE", exe_path)
    monkeypatch.setattr(os.path, "expanduser",
                        lambda p: p.replace("~", ev, 1) if p.startswith("~")
                        else p)
    # Üretim kodu sonunda `update-desktop-database` çağırıyor; bu makinede
    # olmayabilir ve testin dışarıya dokunmasına gerek yok.
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)

    m._register_file_association()

    yol = os.path.join(ev, ".local", "share", "applications",
                       "latex-editor.desktop")
    assert os.path.isfile(yol), (
        ".desktop yazılmadı — üretim kodu sessizce yutmuş olabilir "
        "(gövde tümüyle try/except Exception içinde)")
    # BİLEREK bayt okunup UTF-8 çözülüyor: şartname dosyayı UTF-8 şart
    # koşuyor, yani kodlama testin de sınadığı bir şey. Üretim kodu
    # `encoding=` vermeyi bırakırsa burası kırılır.
    with open(yol, "rb") as f:
        return f.read().decode("utf-8")


def _exec_satiri(icerik: str) -> str:
    for satir in icerik.splitlines():
        if satir.startswith("Exec="):
            return satir.split("=", 1)[1]
    raise AssertionError("Exec satırı yok")


@pytest.mark.parametrize("exe_path", [
    "/home/kullanici/Downloads/LaTeX Editor.AppImage",     # tipik indirme
    "/home/kullanici/Programlarim/LaTeX Editor/app.AppImage",  # boşluklu DİZİN
    "/home/k/Belge  Arsivi/LaTeX Editor.AppImage",         # iki boşluk
    "/home/k/Ap\"p/LaTeX Editor.AppImage",                 # tırnak
    "/home/k/Ap\\p/LaTeX Editor.AppImage",                 # ters bölü
])
def test_bosluklu_yol_TEK_argumana_ayrisiyor(monkeypatch, tmp_path, exe_path):
    """Kırılırsa: Exec tırnaksız ya da kaçışsız demektir, ikisi de programı böler."""
    icerik = _desktop_uret(monkeypatch, tmp_path, exe_path)
    assert shlex.split(_exec_satiri(icerik))[0] == exe_path


@pytest.mark.parametrize("ozel", ["$", "`"])
def test_sartnamenin_istedigi_kacislar_yaziliyor(monkeypatch, tmp_path, ozel):
    r"""Şartname tırnak içinde `\ " ` $` dördünün kaçışını istiyor.

    `$` ve backtick shlex ile uçtan uca doğrulanamıyor (yukarıdaki not),
    o yüzden burada üretilen biçim sınanıyor.
    """
    exe_path = "/home/k/Ap%sp/LaTeX Editor.AppImage" % ozel
    satir = _exec_satiri(_desktop_uret(monkeypatch, tmp_path, exe_path))
    assert "\\" + ozel in satir, satir


def test_bosluksuz_yol_ve_yer_tutucu_BOZULMADI(monkeypatch, tmp_path):
    """Aşırı düzeltme kapısı: tırnaklama sıradan yolu ve `%F`yi bozmamalı."""
    exe_path = "/home/kullanici/Uygulamalar/LaTeXEditor.AppImage"
    icerik = _desktop_uret(monkeypatch, tmp_path, exe_path)
    parcalar = shlex.split(_exec_satiri(icerik))
    assert parcalar == [exe_path, "%F"]


def test_desktop_dosyasinin_geri_kalani_duruyor(monkeypatch, tmp_path):
    """Kapı yalnız Exec'e bakmasın: dosyanın gerisi de geçerli kalmalı."""
    icerik = _desktop_uret(monkeypatch, tmp_path,
                           "/home/k/LaTeX Editor.AppImage")
    for alan in ("[Desktop Entry]", "Name=LaTeX Editor", "Type=Application",
                 "MimeType=text/x-tex;", "Icon=latex-editor"):
        assert alan in icerik, alan
