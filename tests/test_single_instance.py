"""Tek örnek + çalışan örneğe dosya iletimi.

Regresyon: uygulama .tex için ProgID/ikon/shell komutu kaydediyordu ama
ikinci örnek yalnızca QLockFile ile reddediliyordu — açıkken bir .tex'e çift
tıklayan kullanıcı dosyayı AÇAMIYOR, "zaten çalışıyor" uyarısı alıyordu.
Dosya ilişkilendirmesi ilk açılıştan sonra tamamen işlevsizdi.
"""

import os
import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtNetwork import QLocalServer
    from gui.single_instance import SingleInstance, _kullanici
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / QtNetwork gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def temiz_ad(monkeypatch, tmp_path):
    """Her test kendi soket adını ve kilit dizinini kullansın (izolasyon)."""
    import gui.single_instance as si
    benzersiz = f"test-{os.getpid()}-{int(time.monotonic() * 1e6) % 1_000_000}"
    monkeypatch.setattr(si, "_kullanici", lambda: benzersiz)
    monkeypatch.setattr(
        si.QStandardPaths, "writableLocation",
        staticmethod(lambda loc: str(tmp_path)))
    yield benzersiz
    QLocalServer.removeServer(f"latex-editor-{benzersiz}")


def _bekle(app, kosul, timeout_ms=5000):
    t0 = time.monotonic()
    while not kosul():
        app.processEvents()
        if (time.monotonic() - t0) * 1000 > timeout_ms:
            return False
    return True


# --- ad üretimi ---


def test_ad_kullaniciyi_icerir(monkeypatch):
    """Linux'ta TempLocation /tmp — PAYLAŞIMLI. Sabit adla ikinci kullanıcı
    uygulamayı hiç açamıyordu (QLockFile birincinin canlı PID'ini görüyordu)."""
    monkeypatch.setenv("USER", "ayse")
    monkeypatch.delenv("USERNAME", raising=False)
    assert _kullanici() == "ayse"
    monkeypatch.setenv("USER", "ali veli/../x")
    assert "/" not in _kullanici() and ".." not in _kullanici()


def test_ad_kullanici_yoksa_varsayilan(monkeypatch):
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.delenv("USERNAME", raising=False)
    assert _kullanici() == "default"


def test_farkli_kullanicilar_farkli_kilit(qapp, tmp_path, monkeypatch):
    """İki kullanıcı aynı makinede birbirini engellememeli."""
    import gui.single_instance as si
    monkeypatch.setattr(
        si.QStandardPaths, "writableLocation",
        staticmethod(lambda loc: str(tmp_path)))

    monkeypatch.setattr(si, "_kullanici", lambda: f"ayse-{os.getpid()}")
    a = SingleInstance()
    monkeypatch.setattr(si, "_kullanici", lambda: f"ali-{os.getpid()}")
    b = SingleInstance()
    try:
        assert a.try_become_primary() is True
        assert b.try_become_primary() is True, "ikinci kullanıcı engellendi"
    finally:
        a.stop()
        b.stop()
        QLocalServer.removeServer(a._ad)
        QLocalServer.removeServer(b._ad)


# --- birincil / ikincil ---


def test_ikinci_ornek_birincil_olamaz(qapp, temiz_ad):
    birinci, ikinci = SingleInstance(), SingleInstance()
    try:
        assert birinci.try_become_primary() is True
        assert ikinci.try_become_primary() is False
    finally:
        birinci.stop()


def test_yol_calisan_ornege_iletilir(qapp, temiz_ad, tmp_path):
    """Asıl düzeltme: ikinci örnek dosyayı birinciye iletir."""
    birinci = SingleInstance()
    assert birinci.try_become_primary() is True
    gelenler = []
    birinci.file_received.connect(gelenler.append)

    tex = tmp_path / "tez.tex"
    tex.write_text("x\n", encoding="utf-8", newline="")

    try:
        ikinci = SingleInstance()
        assert ikinci.try_become_primary() is False
        assert ikinci.send(str(tex)) is True
        assert _bekle(qapp, lambda: gelenler), "yol birinciye ulaşmadı"
        assert gelenler == [str(tex)]
    finally:
        birinci.stop()


def test_turkce_karakterli_yol_bozulmadan_gecer(qapp, temiz_ad, tmp_path):
    birinci = SingleInstance()
    assert birinci.try_become_primary() is True
    gelenler = []
    birinci.file_received.connect(gelenler.append)

    tex = tmp_path / "bölüm çığ şşş.tex"
    tex.write_text("x\n", encoding="utf-8", newline="")
    try:
        ikinci = SingleInstance()
        ikinci.try_become_primary()
        assert ikinci.send(str(tex)) is True
        assert _bekle(qapp, lambda: gelenler)
        assert gelenler == [str(tex)]
    finally:
        birinci.stop()


def test_bos_yol_yalniz_one_getirir(qapp, temiz_ad):
    """Kullanıcı dosyasız ikinci kez başlatmış: sinyal boş yolla gelmeli."""
    birinci = SingleInstance()
    assert birinci.try_become_primary() is True
    gelenler = []
    birinci.file_received.connect(gelenler.append)
    try:
        ikinci = SingleInstance()
        ikinci.try_become_primary()
        assert ikinci.send("") is True
        assert _bekle(qapp, lambda: gelenler)
        assert gelenler == [""]
    finally:
        birinci.stop()


def test_sunucu_yoksa_send_false_doner(qapp, temiz_ad):
    """Birincil donmuş/yok: kullanıcı sessizce kaybolmasın, uyarı görsün."""
    yalniz = SingleInstance()
    assert yalniz.send("/bir/yol.tex") is False


def test_stop_sonrasi_kilit_devralinabilir(qapp, temiz_ad):
    birinci = SingleInstance()
    assert birinci.try_become_primary() is True
    birinci.stop()
    ikinci = SingleInstance()
    try:
        assert ikinci.try_become_primary() is True, "kilit bırakılmadı"
    finally:
        ikinci.stop()


# --- MainWindow tarafı: gelen isteği işleme ---


def _pencere_stub():
    """open_from_other_instance'ın dokunduğu asgari arayüz."""
    from types import SimpleNamespace
    kayit = SimpleNamespace(acilan=[], one_alindi=0, minimize=False)

    def _ac(path, add_recent=True):
        kayit.acilan.append(path)

    return SimpleNamespace(
        _OPENABLE_EXT=('.tex', '.cls', '.sty', '.bib'),
        _open_file_in_editor=_ac,
        isMinimized=lambda: kayit.minimize,
        windowState=lambda: 0,
        setWindowState=lambda s: None,
        show=lambda: setattr(kayit, "one_alindi", kayit.one_alindi + 1),
        raise_=lambda: None,
        activateWindow=lambda: None,
        _kayit=kayit,
    )


def _isle(stub, path):
    from gui.main_window import MainWindow
    MainWindow.open_from_other_instance(stub, path)
    return stub._kayit


def test_gelen_tex_acilir(qapp, tmp_path):
    tex = tmp_path / "a.tex"
    tex.write_text("x\n", encoding="utf-8", newline="")
    k = _isle(_pencere_stub(), str(tex))
    assert k.acilan == [str(tex)]
    assert k.one_alindi == 1, "pencere öne alınmalı"


def test_desteklenmeyen_uzanti_acilmaz(qapp, tmp_path):
    """Yalnız sürükle-bırakla aynı küme açılır; .exe vb. sekmede açılmamalı."""
    baska = tmp_path / "a.exe"
    baska.write_bytes(b"MZ")
    k = _isle(_pencere_stub(), str(baska))
    assert k.acilan == []
    assert k.one_alindi == 1, "dosya açılmasa da pencere öne gelmeli"


def test_olmayan_dosya_cokmez(qapp, tmp_path):
    k = _isle(_pencere_stub(), str(tmp_path / "yok.tex"))
    assert k.acilan == []
    assert k.one_alindi == 1


def test_bos_yol_yalniz_one_alir(qapp):
    k = _isle(_pencere_stub(), "")
    assert k.acilan == []
    assert k.one_alindi == 1
