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


# ==========================================================================
# Komut satirindan gelen COGUL dosya
#
# Uretilen `.desktop` `Exec=... %F` yaziyor. Sartnamede `%f` TEK dosya, `%F`
# dosya LISTESI demek: dosya yoneticisinde uc .tex secip "Birlikte Ac" demek
# TEK surece uc argumanla giriyor. `main()` ilk dosyada `break` ediyordu,
# digerleri sessizce dusuyordu (olculdu 2026-09-07, uretim kodunun yazdigi
# .desktop okunarak). Kullanici uc belge secip birini goruyordu.
# ==========================================================================


def test_desktop_COGUL_dosya_bildiriyor(monkeypatch, tmp_path):
    """Kapinin dayandigi vaat: `%F`.

    Bir gun `%f`ye donulurse (dosya basina ayri cagri) asagidaki cogul
    isleme gereksizlesir; bu test o kararin bilerek alinmasini saglar.
    """
    icerik = _desktop_uret(monkeypatch, tmp_path, "/tmp/LaTeX Editor.AppImage")
    exec_satiri = next(s for s in icerik.splitlines()
                       if s.startswith("Exec="))
    assert exec_satiri.endswith(" %F"), exec_satiri


def test_TUM_dosya_argumanlari_aliniyor(tmp_path):
    import main as m

    yollar = []
    for ad in ("bolum1.tex", "bolum2.tex", "bolum3.tex"):
        p = tmp_path / ad
        p.write_text("x\n", encoding="utf-8")
        yollar.append(str(p))

    alinan = m._dosya_argumanlari(yollar)

    assert alinan == [os.path.normpath(y) for y in yollar]


def test_dosya_OLMAYAN_argumanlar_atlaniyor(tmp_path):
    """Bayraklar ve silinmis yollar liste disi; ayni yol iki kez verilirse
    bir kez aliniyor."""
    import main as m

    var = tmp_path / "var.tex"
    var.write_text("x\n", encoding="utf-8")
    yok = str(tmp_path / "yok.tex")

    alinan = m._dosya_argumanlari(
        ["--debug", yok, str(var), str(tmp_path), str(var)])

    assert alinan == [os.path.normpath(str(var))]


def test_UC_dosya_UC_sekme_aciyor(ana_pencere, tmp_path):
    """Kirilirsa kullanici uc belge secip yalnizca birini gorur ve neden
    digerlerinin acilmadigini soyleyen hicbir sey yoktur.

    Ek dosyalar BASKA bir klasorde: hepsi ayni klasorde olsaydi agac koku
    hangi dosyaya gore kuruldugu gorunmezdi ve asagidaki kok iddiasi bos
    kalirdi (ilk halinde oyleydi, mutasyon yakalamadi).
    """
    ilk_dizin = tmp_path / "ana"
    ek_dizin = tmp_path / "ekler"
    ilk_dizin.mkdir()
    ek_dizin.mkdir()

    yollar = []
    for dizin, ad in ((ilk_dizin, "bolum1.tex"),
                      (ek_dizin, "bolum2.tex"),
                      (ek_dizin, "bolum3.tex")):
        p = dizin / ad
        p.write_text("\\section{%s}\n" % ad, encoding="utf-8")
        yollar.append(os.path.normpath(str(p)))

    w = ana_pencere(open_file=yollar[0], ek_dosyalar=yollar[1:])

    acik = [w._editor_tabs.widget(i).file_path
            for i in range(w._editor_tabs.count())]
    assert acik == yollar, acik
    # Kok ILK dosyaya gore: kullanicinin sectigi ilk belge projeyi belirler.
    assert os.path.normcase(w._file_tree._root) == \
        os.path.normcase(os.path.normpath(str(ilk_dizin)))


def test_ek_dosya_YOKKEN_davranis_ayni(ana_pencere, tmp_path):
    """Asiri duzeltme kapisi: tek dosyayla acilis bozulmamali, agac koku de
    ILK dosyaya gore kurulmali."""
    p = tmp_path / "tek.tex"
    p.write_text("x\n", encoding="utf-8")

    w = ana_pencere(open_file=os.path.normpath(str(p)))

    acik = [w._editor_tabs.widget(i).file_path
            for i in range(w._editor_tabs.count())]
    assert acik == [os.path.normpath(str(p))]
    assert os.path.normcase(w._file_tree._root) == \
        os.path.normcase(os.path.normpath(str(tmp_path)))
