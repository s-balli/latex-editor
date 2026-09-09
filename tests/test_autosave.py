# -*- coding: utf-8 -*-
"""Otomatik kaydetme: kirli sekmeleri periyodik olarak KENDİ dosyasına yazar.

Çökme kurtarmanın kardeşi ama aynı şey değil: kurtarma yan bir kopya yazıp
açılışta soruyor, burada kullanıcının dosyası yazılıyor. O yüzden kapılar
DİSKE bakıyor, çağrı sayısına değil.

GERÇEK pencere kuruluyor: ayar okuma, zamanlayıcı, dosya izleyici ve
editörün kendi yazma yolu ancak birlikte anlamlı.
"""

import os

import pytest

from PyQt6.QtWidgets import QMessageBox

from gui.editor import EditorWidget


def _proje(tmp_path, ad="tez.tex", icerik="ilk hali\n"):
    yol = tmp_path / ad
    yol.write_text(icerik, encoding="utf-8")
    return yol


# --- Çekirdek davranış ---

def test_KIRLI_dosya_diske_yaziliyor(ana_pencere, tmp_path):
    """Kırılırsa özellik hiç yok demek: kullanıcı Ctrl+S'e basmadan yazdığı
    her şey çökmede gider."""
    yol = _proje(tmp_path)
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    ed = p._current_editor()
    ed.setText("Ctrl+S'e basilmadi\n")
    assert ed.isModified()

    p._autosave_tick()

    assert yol.read_text(encoding="utf-8") == "Ctrl+S'e basilmadi\n"
    assert ed.isModified() is False
    assert "Otomatik kaydedildi" in p._status.currentMessage()


def test_KAYIT_file_watch_e_ISARETLENIYOR(ana_pencere, tmp_path):
    """İşaretlenmezse izleyici kendi yazdığımızı 'dosya dışarıdan değişti'
    sanıp her turda yeniden yükleme sorar."""
    yol = _proje(tmp_path)
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    p._current_editor().setText("degisti\n")

    n = os.path.normpath(str(yol))
    assert n in p._save_hashes          # açılışta kaydedilmiş olan ESKİ hash

    p._autosave_tick()

    # Yalnız "anahtar var mı" diye bakmak VAKUM olurdu: `_file_watch_add`
    # dosyayı açarken zaten kaydediyor. Ölçüt hash'in YENİ içeriğe eşit
    # olması; eşit değilse izleyici bir sonraki turda "dışarıdan değişti"
    # diye sorar.
    assert p._save_hashes[n] == p._file_hash(str(yol))


# --- Aşırı düzeltme kapıları ---

def test_YOLU_OLMAYAN_tampon_YAZILMIYOR(ana_pencere, tmp_path, monkeypatch):
    """Adsız tampon için zamanlayıcıdan "Farklı Kaydet" kutusu açmak,
    kullanıcının istemediği bir anda önüne modal pencere koymak olurdu.
    Onları çökme kurtarma koruyor."""
    p = ana_pencere()
    ed = EditorWidget()
    ed.setText("hic kaydedilmemis\n")
    p._editor_tabs.addTab(ed, "adsiz")
    kutular = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: kutular.append(a)))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: kutular.append(a)))

    p._autosave_tick()

    assert kutular == []
    assert ed.isModified() is True          # dokunulmadı
    # Durum çubuğu da sessiz kalmalı: adsız tampon bir HATA değil. Yol
    # denetimi kalkarsa `save_file` False dönüp adı boş bir "Otomatik
    # kaydedilemedi: " mesajı çıkıyor (mutasyonla ölçüldü).
    assert "kaydedilemedi" not in p._status.currentMessage()


def test_TEMIZ_dosyaya_DOKUNULMUYOR(ana_pencere, tmp_path):
    """Aşırı düzeltme kapısı: değişmemiş dosyayı her turda yeniden yazmak
    mtime'ı oynatır, izleyiciyi ve dış araçları (git, latexmk) boşuna
    tetikler."""
    yol = _proje(tmp_path)
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    assert p._current_editor().isModified() is False
    once = yol.stat().st_mtime_ns

    p._autosave_tick()

    assert yol.stat().st_mtime_ns == once
    assert "Otomatik kaydedildi" not in p._status.currentMessage()


def test_YAZILAMAYAN_dosya_MODAL_ACMIYOR_ve_BIR_KEZ_bildiriliyor(
        ana_pencere, tmp_path, monkeypatch):
    """Zamanlayıcıdan gelen bir yazma düşerse kullanıcı hiçbir şey yapmadığı
    hâlde önüne kutu çıkar; salt okunur hedefte bu her turda tekrarlanır."""
    yol = _proje(tmp_path)
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    ed = p._current_editor()
    ed.setText("yazilamayacak\n")

    kutular = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: kutular.append(a)))
    monkeypatch.setattr(EditorWidget, "_write_atomic",
                        staticmethod(lambda *a, **k: (_ for _ in ()).throw(
                            OSError("salt okunur"))))

    p._autosave_tick()

    assert kutular == [], "zamanlayıcıdan modal kutu açıldı"
    assert "Otomatik kaydedilemedi" in p._status.currentMessage()

    p._status.clearMessage()
    p._autosave_tick()
    assert p._status.currentMessage() == "", "aynı hata her turda tekrarlandı"


def test_AYAR_KAPALIYKEN_zamanlayici_DURUYOR(ana_pencere):
    """Kapatan kullanıcı kapatmış olmalı."""
    p = ana_pencere()
    assert p._autosave_timer.isActive() is True

    p._settings.setValue("editor/autosave", False)
    p._autosave_uygula()

    assert p._autosave_timer.isActive() is False


def test_AYAR_ARALIGI_hemen_uygulaniyor(ana_pencere):
    """Kutuyu kapatan kullanıcı yeni aralığın uygulamayı yeniden başlatana
    kadar beklemesini istemiyor."""
    p = ana_pencere()

    p._settings.setValue("editor/autosave_dk", 10)
    p._autosave_uygula()

    assert p._autosave_timer.interval() == 10 * 60_000


def test_OTOMATIK_KAYIT_derleme_TETIKLEMIYOR(ana_pencere, tmp_path,
                                             monkeypatch):
    """Aşırı düzeltme kapısı: Ctrl+S yolu otomatik derlemeyi de çalıştırıyor.
    Otomatik kaydetme onu kullanırsa arka planda her N dakikada bir derleme
    başlar."""
    yol = _proje(tmp_path)
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    p._current_editor().setText("degisti\n")
    derlemeler = []
    monkeypatch.setattr(type(p._compiler), "compile",
                        lambda self, *a, **k: derlemeler.append(a) or True)

    p._autosave_tick()

    assert derlemeler == []


@pytest.mark.parametrize("deger,beklenen", [
    ("", 3), ("abc", 3), (0, 1), (999, 60), ("7", 7),
])
def test_BOZUK_ayar_uygulamayi_kilitlemiyor(ana_pencere, deger, beklenen):
    """Aynı ders tab genişliğinde ölçülmüştü: yarım yazılmış ayar dosyası
    açılışı kesiyordu. Aralık da sınırlı olmalı."""
    p = ana_pencere()
    p._settings.setValue("editor/autosave_dk", deger)

    assert p._read_editor_settings()["autosave_dk"] == beklenen


# =====================================================================
# Öteki özelliklerle etkileşim (hepsi ölçüldü, 2026-09-09)
#
#   file_watch : otomatik kayıttan sonra "dışarıdan değişti" sorusu 0
#   recovery   : anlık görüntü 1 -> 0 (kayıt sonrası artık kalmıyor)
#   cp1254     : sığmayan karakterde yazma DÜŞÜYOR, dosya bozulmuyor,
#                editör kirli kalıyor (iş kaybolmuyor)
#   CRLF       : satır sonu stili korunuyor
#   silinen    : "Sekmede Tut" denen dosya diske GERİ YAZILIYORDU (kusur)
# =====================================================================


def test_SILINEN_ve_sekmede_tutulan_dosya_GERI_YAZILMIYOR(ana_pencere,
                                                          tmp_path):
    """Kırılırsa kullanıcı sildiği dosyayı dosya ağacında, git durumunda ve
    derleme çıktısında yeniden buluyor. İçerik sekmede duruyor; geri yazmak
    isterse Ctrl+S bunu açıkça yapıyor."""
    yol = _proje(tmp_path, "silinecek.tex")
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    ed = p._current_editor()
    ed.setText("kullanici degistirdi\n")
    os.unlink(str(yol))
    p._silinen_tutulanlar.add(os.path.normpath(str(yol)))

    p._autosave_tick()

    assert yol.exists() is False
    assert ed.isModified() is True          # içerik sekmede duruyor


def test_SILINMEMIS_dosya_hala_kaydediliyor(ana_pencere, tmp_path):
    """Aşırı düzeltme kapısı: kısıtlama YALNIZ "Sekmede Tut" denenlere."""
    yol = _proje(tmp_path)
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    p._current_editor().setText("degisti\n")
    assert p._silinen_tutulanlar == set()

    p._autosave_tick()

    assert yol.read_text(encoding="utf-8") == "degisti\n"


def test_KAYITTAN_SONRA_kurtarma_artigi_dusuyor(ana_pencere, tmp_path):
    """Otomatik kaydetme sekmeyi temizliyor, `_recovery_tick` de artığı
    siliyor. Kalsaydı bir sonraki açılışta "kaydedilmemiş değişiklik var"
    diye sorulurdu, oysa değişiklik dosyaya yazılmıştı."""
    from core import recovery

    yol = _proje(tmp_path)
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    p._current_editor().setText("kirli\n")
    p._recovery_tick()
    assert len(recovery.oku(p._recovery_dir)) == 1

    p._autosave_tick()
    p._recovery_tick()

    assert recovery.oku(p._recovery_dir) == []


def test_CRLF_dosyanin_satir_sonu_KORUNUYOR(ana_pencere, tmp_path):
    """Otomatik kaydetme her N dakikada bir yazıyor; satır sonunu bozsaydı
    kullanıcının fark etmediği bir fark her dosyada birikirdi."""
    yol = tmp_path / "crlf.tex"
    yol.write_bytes(b"bir\r\niki\r\n")
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    p._current_editor().setText("bir\niki\nuc\n")

    p._autosave_tick()

    assert yol.read_bytes() == b"bir\r\niki\r\nuc\r\n"


def test_KODLAMAYA_SIGMAYAN_karakterde_dosya_BOZULMUYOR(ana_pencere,
                                                        tmp_path,
                                                        monkeypatch):
    """cp1254 bir dosyaya o kodlamada olmayan bir karakter yazılırsa yazma
    düşüyor. Önemli olan: diskteki içerik BOZULMUYOR ve editör kirli kalıyor,
    yani kullanıcının işi kaybolmuyor."""
    from PyQt6.QtWidgets import QMessageBox

    yol = tmp_path / "cp.tex"
    ham = "Bölüm başlığı\n".encode("cp1254")
    yol.write_bytes(ham)
    # Açılıştaki kodlama uyarısı MODAL; testte tıklayacak kimse yok.
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: 0))
    kutular = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: kutular.append(a)))

    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    ed = p._current_editor()
    assert ed._encoding == "cp1254"
    ed.setText("Yunanca sigma σ\n")

    p._autosave_tick()

    assert yol.read_bytes() == ham, "dosya bozuldu"
    assert ed.isModified() is True, "iş kayboldu"
    assert kutular == [], "zamanlayıcıdan modal açıldı"
    assert "kaydedilemedi" in p._status.currentMessage()


# =====================================================================
# "Kendiminkini Koru" + otomatik kaydetme: dış değişiklik ezilmemeli
#
# ÖLÇÜLDÜ (2026-09-09, gerçek pencerede):
#
#   kullanıcı arabelleği değiştirir (kaydetmez)
#   dışarıdan biri dosyayı değiştirir  -> disk: "DISARIDAN..."
#   uyarıda "Kendiminkini Koru"        -> disk hâlâ "DISARIDAN..."
#   otomatik kaydetme turu             -> disk "BENIM..."   <- dış değişiklik GİTTİ
#
# "Koru" kararı "arabelleğim kalsın" demek, "diski ez" demek DEĞİL.
# Otomatik kaydetmeden önce kullanıcı seçimi elinde tutuyordu (farkı
# inceleyip Ctrl+S ya da yeniden yükleme); üç dakikalık zamanlayıcı o
# seçimi elinden alıyor ve BAŞKASININ işini yok ediyor.
# =====================================================================


def _dis_degisiklik(p, yol, ed, yeni_icerik="DISARIDAN gelen\n"):
    """Diski dışarıdan değiştir ve yeni hash'i döndür."""
    yol.write_text(yeni_icerik, encoding="utf-8")
    return p._file_hash(str(yol))


def test_KORU_dedikten_sonra_otomatik_kayit_DISKI_EZMIYOR(
        ana_pencere, tmp_path, monkeypatch):
    """Kırılırsa kullanıcının yüklemeyi REDDETTİĞİ dış değişiklik üç dakika
    içinde sessizce yok oluyor."""
    yol = _proje(tmp_path, "ortak.tex")
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    ed = p._current_editor()
    ed.setText("BENIM degisiklikim\n")
    yeni_hash = _dis_degisiklik(p, yol, ed)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)  # "Koru"
    p._prompt_reload(ed, str(yol), yeni_hash)
    assert yol.read_text(encoding="utf-8") == "DISARIDAN gelen\n"

    p._autosave_tick()

    assert yol.read_text(encoding="utf-8") == "DISARIDAN gelen\n"
    assert ed.isModified() is True          # iş arabellekte duruyor


def test_ACIK_KAYIT_ayrisma_isaretini_DUSURUYOR(ana_pencere, tmp_path,
                                                monkeypatch):
    """Ctrl+S kullanıcının AÇIK kararı: ondan sonra otomatik kaydetme yine
    çalışmalı, yoksa dosya kalıcı olarak otomatik kaydetme dışında kalır."""
    yol = _proje(tmp_path, "ortak.tex")
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    ed = p._current_editor()
    ed.setText("BENIM\n")
    yeni_hash = _dis_degisiklik(p, yol, ed)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
    p._prompt_reload(ed, str(yol), yeni_hash)
    assert str(yol) in p._disk_ayristi or os.path.normpath(str(yol)) \
        in p._disk_ayristi

    ed.save_file()                          # kullanıcı açıkça kaydediyor
    p._file_watch_record_save(ed.file_path)

    assert os.path.normpath(str(yol)) not in p._disk_ayristi
    ed.setText("SONRAKI degisiklik\n")
    p._autosave_tick()
    assert yol.read_text(encoding="utf-8") == "SONRAKI degisiklik\n"


def test_DISKTEN_YUKLE_ayrisma_isaretini_DUSURUYOR(ana_pencere, tmp_path,
                                                   monkeypatch):
    """Aşırı düzeltme kapısı: diskten yükledikten sonra arabellek diskle
    aynı, otomatik kaydetme yeniden serbest."""
    yol = _proje(tmp_path, "ortak.tex")
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    ed = p._current_editor()
    ed.setText("BENIM\n")
    yeni_hash = _dis_degisiklik(p, yol, ed)

    # İşareti ÖNCE gerçekten koy. Koymadan yapılan ölçüm boşa dönüyordu:
    # işaret yalnız "Koru" dalında konuyor, dolayısıyla `discard` satırını
    # silmek hiçbir kapıyı düşürmüyordu (mutasyon yakaladı).
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)   # "Koru"
    p._prompt_reload(ed, str(yol), yeni_hash)
    assert os.path.normpath(str(yol)) in p._disk_ayristi

    # "Diskten Yükle" kolunu seç: AcceptRole düğmesine tıklanmış gibi
    def _exec_yukle(self):
        for b in self.buttons():
            if self.buttonRole(b) == QMessageBox.ButtonRole.AcceptRole:
                self.setDefaultButton(b)
                b.click()
                return 0
        return 0

    monkeypatch.setattr(QMessageBox, "exec", _exec_yukle)
    p._prompt_reload(ed, str(yol), yeni_hash)

    assert os.path.normpath(str(yol)) not in p._disk_ayristi
    # QScintilla Windows'ta arabellekte CRLF tutuyor; `save_file` yazarken
    # dosyanın kendi satır sonu stiline geri çeviriyor. Karşılaştırma bu
    # yüzden satır sonundan bağımsız.
    assert ed.text().replace("\r\n", "\n") == "DISARIDAN gelen\n"

    # İşaretin düştüğü yalnız kümeye bakarak değil, DAVRANIŞLA görünsün:
    # otomatik kaydetme yeniden yazıyor.
    ed.setText("SONRAKI\n")
    p._autosave_tick()
    assert yol.read_text(encoding="utf-8") == "SONRAKI\n"


def test_AYRISMAMIS_dosya_hala_otomatik_kaydediliyor(ana_pencere, tmp_path):
    """Aşırı düzeltme kapısı: kısıtlama YALNIZ ayrışmış dosyalara."""
    yol = _proje(tmp_path)
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    p._current_editor().setText("degisti\n")
    assert p._disk_ayristi == set()

    p._autosave_tick()

    assert yol.read_text(encoding="utf-8") == "degisti\n"


def test_TEMIZ_arabellekte_YOKSAY_dosyayi_kalici_disi_BIRAKMIYOR(
        ana_pencere, tmp_path, monkeypatch):
    """Aşırı düzeltme kapısı: arabellek TEMİZKEN gelen uyarıda "Yoksay"
    demek ayrışma değil. İşaret orada da konursa dosya bir daha hiç
    otomatik kaydedilmez ve kullanıcı bunu fark etmez."""
    yol = _proje(tmp_path, "ortak.tex")
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    ed = p._current_editor()
    assert ed.isModified() is False
    yeni_hash = _dis_degisiklik(p, yol, ed)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)  # "Yoksay"
    p._prompt_reload(ed, str(yol), yeni_hash)

    assert os.path.normpath(str(yol)) not in p._disk_ayristi

    ed.setText("BENIM yeni yazim\n")
    p._autosave_tick()
    assert yol.read_text(encoding="utf-8") == "BENIM yeni yazim\n"
