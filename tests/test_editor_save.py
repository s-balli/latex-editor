"""EditorWidget atomik kayıt (save_file / _write_atomic) testleri.

Kayıt işleminin atomik olduğunu doğrular: yazma yarıda kalırsa orijinal dosya
korunur (truncate edilmez), geçici dosya geride kalmaz.
"""

import os
import stat

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from gui.editor import EditorWidget
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui.editor import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _editor():
    return EditorWidget()


def _raise_oserror(*args, **kwargs):
    raise OSError("simulated failure")


# --- Başarı yolu ---


def test_save_writes_content(qapp, tmp_path):
    target = tmp_path / "doc.tex"
    target.write_text("ESKI", encoding="utf-8")
    ed = _editor()
    ed._file_path = str(target)
    ed.setText("YENI ICERIK")
    assert ed.save_file() is True
    assert target.read_text(encoding="utf-8") == "YENI ICERIK"


def test_save_creates_new_file(qapp, tmp_path):
    target = tmp_path / "yeni.tex"
    assert not target.exists()
    ed = _editor()
    ed._file_path = str(target)
    ed.setText("ilk icerik")
    assert ed.save_file() is True
    assert target.read_text(encoding="utf-8") == "ilk icerik"


def test_save_preserves_utf8_turkish(qapp, tmp_path):
    target = tmp_path / "tr.tex"
    ed = _editor()
    ed._file_path = str(target)
    metin = "Çığ Öğü Şoför İı, Türkçe karakterler"
    ed.setText(metin)
    ed.save_file()
    assert target.read_text(encoding="utf-8") == metin


def test_save_clears_modified_flag(qapp, tmp_path):
    target = tmp_path / "m.tex"
    ed = _editor()
    ed._file_path = str(target)
    ed.setText("x")
    ed.setModified(True)
    ed.save_file()
    assert ed.isModified() is False


def test_no_tmp_left_after_success(qapp, tmp_path):
    target = tmp_path / "clean.tex"
    ed = _editor()
    ed._file_path = str(target)
    ed.setText("icerik")
    ed.save_file()
    assert not (tmp_path / "clean.tex.tmp").exists()


def test_save_as_sets_path_and_saves(qapp, tmp_path):
    target = tmp_path / "as.tex"
    ed = _editor()
    ed.setText("veri")
    ed.save_file_as(str(target))
    assert target.read_text(encoding="utf-8") == "veri"
    assert ed._file_path == os.path.normpath(str(target))


# --- Atomiklik: yazma/replace hatasında orijinal korunur ---


def test_write_atomic_preserves_original_on_replace_error(qapp, tmp_path, monkeypatch):
    """os.replace patlarsa orijinal dosya dokunulmamış kalmalı, .tmp temizlenmeli."""
    target = tmp_path / "doc.tex"
    target.write_text("ORIGINAL", encoding="utf-8")
    monkeypatch.setattr(os, "replace", _raise_oserror)

    ed = _editor()
    with pytest.raises(OSError):
        ed._write_atomic(str(target), "NEW")
    # Orijinal bozulmamış (truncate-on-open olmadığı için)
    assert target.read_text(encoding="utf-8") == "ORIGINAL"
    # Geçici dosya temizlendi
    assert not (tmp_path / "doc.tex.tmp").exists()


def test_save_returns_false_and_keeps_original_on_error(qapp, tmp_path, monkeypatch):
    """save_file hatada False dönmeli, orijinali koruyarak (modal kutu açmadan)."""
    target = tmp_path / "doc.tex"
    target.write_text("ORIGINAL", encoding="utf-8")
    # Modal QMessageBox.critical'in testte bloklanmasını önle
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(os, "replace", _raise_oserror)

    ed = _editor()
    ed._file_path = str(target)
    ed.setText("NEW")
    assert ed.save_file() is False
    assert target.read_text(encoding="utf-8") == "ORIGINAL"


def test_basarisiz_save_file_as_eski_kimligi_koruyor(qapp, tmp_path, monkeypatch):
    """Başarısız 'Farklı Kaydet' editörü var olmayan hedefe bağlamamalı (A3).

    save_file_as üç alanı (yol, kodlama, satır sonu) yazma DENENMEDEN
    atıyordu. Yazma başarısız olunca eski yol ve legacy kodlama geri
    alınamaz biçimde kayboluyor, Ctrl+S kalıcı olarak yazılamayan hedefe
    gitmeye devam ediyordu.
    """
    kaynak = tmp_path / "eski.tex"
    kaynak.write_bytes("Türkçe içerik\n".encode("cp1254"))

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)

    ed = _editor()
    assert ed.open_file(str(kaynak)) is True
    assert ed._encoding == "cp1254"

    def _patlat(path, text, enc):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(EditorWidget, "_write_atomic", staticmethod(_patlat))

    hedef = tmp_path / "yeni.tex"
    assert ed.save_file_as(str(hedef)) is False
    assert ed.file_path == str(kaynak), "editör var olmayan hedefe bağlandı"
    assert ed._encoding == "cp1254", "legacy kodlama kayboldu"
    assert ed._newline == "lf"
    assert not hedef.exists()


def test_basarili_save_file_as_yeni_kimligi_aliyor(qapp, tmp_path, monkeypatch):
    """Geri alma yolu başarılı durumu bozmamalı."""
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    kaynak = tmp_path / "a.tex"
    kaynak.write_text("icerik\n", encoding="utf-8")

    ed = _editor()
    assert ed.open_file(str(kaynak)) is True

    hedef = tmp_path / "b.tex"
    assert ed.save_file_as(str(hedef)) is True
    assert ed.file_path == str(hedef)
    assert ed._encoding == "utf-8"
    assert hedef.read_text(encoding="utf-8") == "icerik\n"


# --- Dosya kimliği: os.replace hedefin YERİNE geçiyor ---


@pytest.fixture
def symlink_kurulabilir(tmp_path):
    """symlink yaratılamıyorsa (Windows ayrıcalığı, dosya sistemi) testi atla."""
    deneme = tmp_path / "_deneme_link"
    try:
        os.symlink(tmp_path / "_deneme_hedef", deneme)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlink oluşturulamıyor")
    os.unlink(deneme)


def test_symlink_kayittan_sonra_yerinde_kaliyor(qapp, tmp_path, symlink_kurulabilir):
    """Kayıt symlink'i düz dosyayla DEĞİŞTİRMEMELİ.

    os.replace bağlantının KENDİSİNİ değiştiriyordu: proje dizinindeki
    main.tex düz dosyaya dönüşüyor, kullanıcının yazdığı ise bağlantının
    işaret ettiği gerçek dosyaya HİÇ ulaşmıyordu. Paylaşılan ya da
    senkronize bir dizine bağlanmış belge sessizce eski içerikte kalıyor,
    kullanıcı ise kaydettiğini biliyordu.
    """
    gercek = tmp_path / "gercek.tex"
    gercek.write_text("ESKI\n", encoding="utf-8")
    link = tmp_path / "link.tex"
    os.symlink(gercek, link)

    ed = _editor()
    ed._file_path = str(link)
    ed.setText("YENI\n")
    assert ed.save_file() is True

    assert link.is_symlink(), "symlink düz dosyaya dönüştü"
    assert gercek.read_text(encoding="utf-8") == "YENI\n", \
        "kayıt bağlantının işaret ettiği dosyaya ulaşmadı"
    assert not (tmp_path / "link.tex.tmp").exists()
    assert not (tmp_path / "gercek.tex.tmp").exists()


def test_symlink_bytes_dalinda_da_korunuyor(qapp, tmp_path, symlink_kurulabilir):
    """bytes dalı (sürümden geri yükleme, toplu yeniden adlandırma) aynı yol.

    version_ops._restore_version ve edit_ops._apply_renamings da bu
    fonksiyonu çağırıyor; symlink orada da kopmamalı.
    """
    gercek = tmp_path / "bolum.tex"
    gercek.write_bytes(b"\\label{eski}\n")
    link = tmp_path / "link-bolum.tex"
    os.symlink(gercek, link)

    EditorWidget._write_atomic(str(link), b"\\label{yeni}\n")

    assert link.is_symlink()
    assert gercek.read_bytes() == b"\\label{yeni}\n"


def test_symlink_zinciri_ve_kirik_baglanti(qapp, tmp_path, symlink_kurulabilir):
    """Zincirin her halkası ve henüz var olmayan hedef de korunmalı."""
    gercek = tmp_path / "uc.tex"
    gercek.write_text("eski\n", encoding="utf-8")
    l1 = tmp_path / "z1.tex"
    l2 = tmp_path / "z2.tex"
    os.symlink(gercek, l1)
    os.symlink(l1, l2)
    EditorWidget._write_atomic(str(l2), "zincir\n")
    assert l1.is_symlink() and l2.is_symlink()
    assert gercek.read_text(encoding="utf-8") == "zincir\n"

    # Kırık bağlantı: hedefi yaratmalı, bağlantıyı düz dosyaya çevirmemeli
    henuz_yok = tmp_path / "henuz-yok.tex"
    kirik = tmp_path / "kirik.tex"
    os.symlink(henuz_yok, kirik)
    EditorWidget._write_atomic(str(kirik), "artik var\n")
    assert kirik.is_symlink()
    assert henuz_yok.read_text(encoding="utf-8") == "artik var\n"


@pytest.mark.skipif(os.name == "nt", reason="izin bitleri POSIX'e özgü")
def test_kisitli_izinler_kayittan_sonra_korunuyor(qapp, tmp_path):
    """os.replace geride YENİ dosya bırakıyor; izinler umask'a düşmemeli.

    0o600 işaretli bir belge kayıttan sonra 0o644 oluyordu, yani çok
    kullanıcılı bir makinede başkaları okuyabilir hale geliyordu.
    """
    hedef = tmp_path / "gizli.tex"
    hedef.write_text("gizli\n", encoding="utf-8")
    os.chmod(hedef, 0o600)

    ed = _editor()
    ed._file_path = str(hedef)
    ed.setText("gizli 2\n")
    assert ed.save_file() is True

    assert stat.S_IMODE(os.stat(hedef).st_mode) == 0o600
    assert hedef.read_text(encoding="utf-8") == "gizli 2\n"


@pytest.mark.skipif(os.name == "nt", reason="izin bitleri POSIX'e özgü")
def test_izinler_devralinliyor_sabitlenmiyor(qapp, tmp_path):
    """Hedefin izni neyse o: 0o664 dosya 0o600'e de düşmemeli."""
    hedef = tmp_path / "grup.tex"
    hedef.write_text("x\n", encoding="utf-8")
    os.chmod(hedef, 0o664)
    EditorWidget._write_atomic(str(hedef), "y\n")
    assert stat.S_IMODE(os.stat(hedef).st_mode) == 0o664


@pytest.mark.skipif(os.name != "nt",
                    reason="Windows'a özgü: salt okunur dosya silinemiyor")
def test_salt_okunur_hedefte_gecici_dosya_kalmiyor(qapp, tmp_path):
    """İzinler hedeften devralınınca .tmp da salt okunur işaretleniyor.

    Windows salt okunur bir dosyayı SİLDİRMİYOR. Temizlik yolu yazma bitini
    geri vermezse, başarısız kayıttan sonra .tmp kullanıcının belgesinin
    yanında kalıyor. (İzin devralma eklenirken bu gerileme ölçümle
    yakalandı; testi onun için var.)
    """
    hedef = tmp_path / "doc.tex"
    hedef.write_text("ORIJINAL\n", encoding="utf-8")
    os.chmod(hedef, stat.S_IREAD)
    try:
        with pytest.raises(OSError):
            EditorWidget._write_atomic(str(hedef), "YENI\n")
        assert not (tmp_path / "doc.tex.tmp").exists(), "geçici dosya geride kaldı"
        assert hedef.read_text(encoding="utf-8") == "ORIJINAL\n"
    finally:
        os.chmod(hedef, stat.S_IWRITE)
