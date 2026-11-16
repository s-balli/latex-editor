# -*- coding: utf-8 -*-
"""Kapanışta oturum durumu: aktif sekme doğru kaydediliyor mu.

`closeEvent` kirli sekmeleri sorarken her birine `setCurrentIndex(i)` ile
GEÇİYOR; döngü bitince çağrılan `_save_state` aktif sekmeyi cari widget'tan
okuduğu için, kullanıcının üzerinde çalıştığı sekme yerine EN SON SORULAN
kirli sekmeyi kaydediyordu. Ölçüldü (2026-09-05): birinci.tex'te çalışan
kullanıcı, ikinci.tex kaydedilmemişken kapatınca bir sonraki açılışta
ikinci.tex'te buluyordu kendini.

Bu dosya GERÇEK MainWindow kuruyor (depoda bunu yapan başka test yok):
sınanan davranış tam olarak closeEvent ile _save_state'in etkileşimi, vekil
bir nesne o etkileşimi taşımaz.

DİKKAT, QSettings: MainWindow kapanışta oturum durumunu YAZIYOR (geometri,
açık sekmeler, dosya ağacı kökü). Windows'ta varsayılan arka uç KAYIT
DEFTERİ, yani önlem alınmazsa bu testler kullanıcının gerçek oturumunu
bozar. `_ayar_kumu` bunu geçici bir .ini dosyasına hapsediyor ve
hapsedilemezse SERT DÜŞÜYOR (sessizce gerçek ayara yazmaktansa test patlasın).
"""

import os

import pytest

pytest.importorskip("PyQt6")




def _norm(yol: str) -> str:
    """Qt yolu `/` ile, Windows `\\` ile veriyor; karşılaştırma normalize."""
    return os.path.normcase(os.path.normpath(yol or ""))


@pytest.fixture(scope="session")
def qapp():
    """QApplication REFERANSI TUTULMALI (bkz. test_menu_actions.py aynı ders)."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# `pencere_kur` fixture'i conftest.py'ye TASINDI (`ana_pencere`): ayni
# kurulumun ikinci bir kopyasi cikmasin, cunku hapis kacirilirsa
# kaybeden kullanicinin gercek ayarlari olur.
@pytest.fixture
def pencere_kur(ana_pencere):
    return ana_pencere


def _dosyalar(tmp_path, adet):
    yollar = []
    for n in range(adet):
        y = tmp_path / ("d%d.tex" % n)
        y.write_text("\\documentclass{article}\n\\begin{document}\n"
                     "d%d\n\\end{document}\n" % n, encoding="utf-8")
        yollar.append(str(y))
    return yollar


def _kur_ve_kapat(pencere_kur, qapp, yollar, aktif, kirli, karar="discard"):
    """Sekmeleri aç, verilenleri kirlet, `aktif`i öne al, kapat.

    Döner: (kullanıcının aktif sekmesinin yolu, kaydedilen aktif yol, pencere)
    """
    w = pencere_kur(karar)
    for y in yollar:
        w._open_file_in_editor(y)
    qapp.processEvents()
    assert w._editor_tabs.count() == len(yollar), "ön koşul: sekmeler açılmalı"

    for i in kirli:
        ed = w._editor_tabs.widget(i)
        ed.append("\n%% kirli %d\n" % i)
        assert ed.isModified(), "ön koşul: sekme %d kirli olmalı" % i

    w._editor_tabs.setCurrentIndex(aktif)
    qapp.processEvents()
    beklenen = w._current_editor().file_path

    w.close()
    qapp.processEvents()
    return beklenen, pencere_kur.ayar().value("active_tab_path", ""), w


def test_kirli_sekme_kullanicinin_aktif_sekmesini_EZMIYOR(
        pencere_kur, qapp, tmp_path):
    """Asıl kusur: kullanıcı birincide, ikinci kirli."""
    yollar = _dosyalar(tmp_path, 2)
    beklenen, kaydedilen, _ = _kur_ve_kapat(
        pencere_kur, qapp, yollar, aktif=0, kirli=[1])
    assert _norm(kaydedilen) == _norm(beklenen), (
        "kirli sekme kullanıcının aktif sekmesini ezdi: "
        f"{os.path.basename(kaydedilen)} != {os.path.basename(beklenen)}")


def test_sonraki_acilista_ayni_sekme_one_geliyor(pencere_kur, qapp, tmp_path):
    """Uçtan uca: kullanıcının gördüğü sonuç."""
    yollar = _dosyalar(tmp_path, 2)
    beklenen, _kaydedilen, _ = _kur_ve_kapat(
        pencere_kur, qapp, yollar, aktif=0, kirli=[1])

    w2 = pencere_kur()
    qapp.processEvents()
    assert w2._editor_tabs.count() == 2, "oturum sekmeleri geri yüklenmedi"
    acilan = w2._current_editor()
    assert acilan is not None
    assert _norm(acilan.file_path) == _norm(beklenen), (
        "yanlış sekme önde açıldı: " + os.path.basename(acilan.file_path))


def test_ortadaki_sekme_iki_kirli_arasinda_korunuyor(
        pencere_kur, qapp, tmp_path):
    """Döngü hem öncesinden hem sonrasından geçiyor."""
    yollar = _dosyalar(tmp_path, 3)
    beklenen, kaydedilen, _ = _kur_ve_kapat(
        pencere_kur, qapp, yollar, aktif=1, kirli=[0, 2])
    assert _norm(kaydedilen) == _norm(beklenen)


def test_kirli_sekme_yokken_davranis_degismedi(pencere_kur, qapp, tmp_path):
    """AŞIRI DÜZELTME KAPISI: temiz kapanışta da doğru sekme kaydedilmeli."""
    yollar = _dosyalar(tmp_path, 2)
    beklenen, kaydedilen, _ = _kur_ve_kapat(
        pencere_kur, qapp, yollar, aktif=1, kirli=[])
    assert _norm(kaydedilen) == _norm(beklenen)


def test_aktif_sekmenin_kendisi_kirliyse_yine_kendisi(
        pencere_kur, qapp, tmp_path):
    yollar = _dosyalar(tmp_path, 2)
    beklenen, kaydedilen, _ = _kur_ve_kapat(
        pencere_kur, qapp, yollar, aktif=1, kirli=[1])
    assert _norm(kaydedilen) == _norm(beklenen)


def test_iptalde_sorulan_sekmede_kaliniyor_ve_durum_yazilmiyor(
        pencere_kur, qapp, tmp_path):
    """İptal yolunda indis BİLEREK geri verilmiyor.

    Kullanıcı vazgeçtiyse, sorunun sorulduğu sekmede kalması doğru; ayrıca
    kapanış olmadığı için oturum durumu hiç yazılmamalı.
    """
    yollar = _dosyalar(tmp_path, 2)
    w = pencere_kur("cancel")
    for y in yollar:
        w._open_file_in_editor(y)
    qapp.processEvents()
    w._editor_tabs.widget(1).append("\n% kirli\n")
    w._editor_tabs.setCurrentIndex(0)
    qapp.processEvents()

    w.close()
    qapp.processEvents()

    assert w._editor_tabs.currentIndex() == 1, "iptalde sorulan sekmede kalınmalı"
    assert not pencere_kur.ayar().value("active_tab_path", ""), (
        "kapanış iptal edildiği hâlde oturum durumu yazılmış")


def test_soru_ekrandayken_kapanan_sekme_SONRAKI_kirli_sekmeyi_atlatmiyor(
        pencere_kur, qapp, tmp_path, monkeypatch):
    """Kayıt sorusu `exec()` ile olay döngüsünü döndürüyor; o arada dosya
    izleyici dışarıdan silinen temiz bir sekmeyi kapatabiliyor. Döngü sekme
    İNDİSİYLE yürüdüğü için arkadaki sekmeler bir sola kayıyor ve son kirli
    sekme hiç sorulmuyordu; kapanış "temiz" sayılıp onun kurtarma kopyası da
    siliniyordu (durum makinesi taraması, 2026-11-16)."""
    from PyQt6.QtWidgets import QMessageBox

    yollar = _dosyalar(tmp_path, 3)
    w = pencere_kur()
    for y in yollar:
        w._open_file_in_editor(y)
    qapp.processEvents()
    silinen = w._editor_tabs.widget(0)            # temiz, dışarıdan silinecek
    for i in (1, 2):
        w._editor_tabs.widget(i).append("\n% kirli\n")
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: QMessageBox.StandardButton.Ok)

    sorulan = []

    def soru(ad):
        if not sorulan:
            # birinci soru ekrandayken izleyicinin turu koşuyor
            os.remove(yollar[0])
            w._handle_deleted_file(silinen, os.path.normpath(yollar[0]))
        sorulan.append(ad)
        return "discard"

    w._save_dialog = soru
    w.close()
    qapp.processEvents()

    assert sorulan == ["d1.tex", "d2.tex"], (
        "kirli sekme sorulmadan kapanıldı: " + repr(sorulan))


def test_kapanis_SUREN_derlemeyi_durduruyor(pencere_kur, qapp, monkeypatch):
    """closeEvent güncelleme iş parçacığını ve arka plan yazıcılarını
    bekliyordu ama derlemeye dokunmuyordu. Linux ve macOS'ta motor derle.sh'in
    alt kabuğunun çocuğu; süreç ağacını yalnız `stop()` öldürüyor
    (`_sureci_oldur`), zaman aşımı zamanlayıcısı da uygulamayla ölüyor:
    pdflatex sahipsiz kalıyordu (durum makinesi taraması, 2026-11-16)."""
    w = pencere_kur()
    durduruldu = []
    monkeypatch.setattr(w._compiler, "is_busy", lambda: True)
    monkeypatch.setattr(w._compiler, "stop", lambda: durduruldu.append(1))

    w.close()
    qapp.processEvents()

    assert durduruldu == [1], "kapanışta süren derleme durdurulmadı"


def test_kapanis_IPTAL_edilirse_derleme_SURUYOR(pencere_kur, qapp, monkeypatch,
                                               tmp_path):
    """Aşırı düzeltme kapısı: kullanıcı kayıt sorusunda vazgeçerse pencere
    açık kalıyor, derleme de sürmeli."""
    yol = _dosyalar(tmp_path, 1)[0]
    w = pencere_kur("cancel")
    w._open_file_in_editor(yol)
    qapp.processEvents()
    w._editor_tabs.widget(0).append("\n% kirli\n")
    durduruldu = []
    monkeypatch.setattr(w._compiler, "is_busy", lambda: True)
    monkeypatch.setattr(w._compiler, "stop", lambda: durduruldu.append(1))

    w.close()
    qapp.processEvents()

    assert durduruldu == [], "iptal edilen kapanış derlemeyi durdurdu"
