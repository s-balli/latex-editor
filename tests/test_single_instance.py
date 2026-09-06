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
    kayit = SimpleNamespace(acilan=[], one_alindi=0, minimize=False, mesaj="")

    def _ac(path, add_recent=True):
        kayit.acilan.append(path)

    ns = SimpleNamespace(
        _OPENABLE_EXT=('.tex', '.cls', '.sty', '.bib'),
        _open_file_in_editor=_ac,
        _status=SimpleNamespace(
            showMessage=lambda m, *a: setattr(kayit, "mesaj", m)),
        isMinimized=lambda: kayit.minimize,
        windowState=lambda: 0,
        setWindowState=lambda s: None,
        show=lambda: setattr(kayit, "one_alindi", kayit.one_alindi + 1),
        raise_=lambda: None,
        activateWindow=lambda: None,
        _kayit=kayit,
    )
    # "Aç ya da sebebini söyle" kuralı `_dis_yolu_ac`ta ve komut satırı yolu
    # da oradan geçiyor. Stub'a kuralın KOPYASI konmuyor, GERÇEĞİ bağlanıyor:
    # kopya olsaydı bu dosya kuralın ikinci tanımı olur ve tam da bu turda
    # kapatılan ayrışmayı geri getirirdi.
    from gui.main_window import MainWindow
    ns._dis_yolu_ac = lambda path, nereden: MainWindow._dis_yolu_ac(
        ns, path, nereden)
    return ns


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
    # Sessiz no-op olmamalı: pencere öne gelip hiçbir şey olmuyordu, kullanıcı
    # sebebi yalnız log'dan görebiliyordu.
    assert "a.exe" in k.mesaj, "desteklenmeyen tür için durum mesajı yok"


def test_olmayan_dosya_cokmez(qapp, tmp_path):
    k = _isle(_pencere_stub(), str(tmp_path / "yok.tex"))
    assert k.acilan == []
    assert k.one_alindi == 1
    assert "yok.tex" in k.mesaj, "bulunamayan dosya için durum mesajı yok"


def test_bos_yol_yalniz_one_alir(qapp):
    k = _isle(_pencere_stub(), "")
    assert k.acilan == []
    assert k.one_alindi == 1
    assert k.mesaj == "", "boş yol yalnız öne alır, mesaj yazmaz"


# =====================================================================
# Çerçeve doğrulaması (2026-09-05)
#
# F1. `oku()` gelen her şeyi tampona ekliyordu ve satır sonu gelmezse hiçbir
#     üst sınır devreye girmiyordu. Yerel soket AYNI KULLANICININ herhangi
#     bir süreci tarafından açılabiliyor; ölçüldü, satır sonu göndermeden
#     4 MB kabul ediliyordu. Aynı sınıf risk core/updater.py'de `_MAX_YANIT`
#     ile zaten kapatılmıştı.
#
# F2. `int(bas)` hatası gürültüyle reddediliyordu ama sayıya çevrilebilen
#     ANLAMSIZ değer denetlenmiyordu: negatif uzunlukta `govde[:uzunluk]`
#     yükü SONDAN kırpıyor ve bozuk yol sessizce yayılıyordu (ölçüldü:
#     "/tmp/dosya.tex" -> "/tmp/dosy").
# =====================================================================


def _ham_gonder(qapp, ad, ham: bytes, bekle_sn=0.4):
    """Ham çerçeve baytlarını gönder; soketi ve bağlantı durumunu döndür."""
    from PyQt6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(f"latex-editor-{ad}")
    assert s.waitForConnected(3000), s.errorString()
    s.write(ham)
    s.flush()
    t0 = time.monotonic()
    while time.monotonic() - t0 < bekle_sn:
        qapp.processEvents()
    return s


@pytest.mark.parametrize("baslik", [b"-1", b"-5", b"-999999"])
def test_negatif_uzunluk_YAYILMIYOR(qapp, temiz_ad, baslik):
    """Kırılırsa: uzunluk aralık denetimi düşmüş demektir."""
    from gui.single_instance import SingleInstance as SI
    birinci = SI()
    assert birinci.try_become_primary() is True
    gelenler = []
    birinci.file_received.connect(gelenler.append)
    try:
        s = _ham_gonder(qapp, temiz_ad, baslik + b"\n/tmp/dosya.tex")
        assert gelenler == [], "bozuk çerçeve yayıldı: %s" % gelenler
        s.abort()
    finally:
        birinci.stop()


def test_ust_sinirdan_buyuk_uzunluk_YAYILMIYOR(qapp, temiz_ad):
    from gui.single_instance import SingleInstance as SI, _MAX_CERCEVE
    birinci = SI()
    assert birinci.try_become_primary() is True
    gelenler = []
    birinci.file_received.connect(gelenler.append)
    try:
        s = _ham_gonder(qapp, temiz_ad,
                        str(_MAX_CERCEVE + 1).encode() + b"\n/tmp/a.tex")
        assert gelenler == []
        s.abort()
    finally:
        birinci.stop()


def test_gecerli_cerceveler_HALA_calisiyor(qapp, temiz_ad):
    """Karşı durum: doğrulama geçerli yükleri düşürmemeli.

    Bu olmadan düzeltme "her şeyi reddet" hâline gelebilir ve kapı fark
    etmezdi.
    """
    from gui.single_instance import SingleInstance as SI, _MAX_CERCEVE
    birinci = SI()
    assert birinci.try_become_primary() is True
    gelenler = []
    birinci.file_received.connect(gelenler.append)
    try:
        for yol in ("/tmp/dosya.tex", "", "/tmp/" + "a" * 500 + ".tex",
                    "/tmp/çalışma şğüöı.tex",
                    "/" + "b" * (_MAX_CERCEVE - 200) + ".tex"):
            gelenler.clear()
            veri = yol.encode("utf-8")
            s = _ham_gonder(qapp, temiz_ad,
                            str(len(veri)).encode("ascii") + b"\n" + veri)
            assert gelenler == [yol], \
                "geçerli çerçeve düştü (%d bayt): %s" % (len(veri), gelenler)
            s.abort()
    finally:
        birinci.stop()


def test_satir_sonusuz_akis_baglantiyi_KESIYOR(qapp, temiz_ad):
    """Tampon üst sınırsızken gönderen ne yazarsa o kadar büyüyordu."""
    from PyQt6.QtNetwork import QLocalSocket
    from gui.single_instance import SingleInstance as SI, _MAX_CERCEVE
    birinci = SI()
    assert birinci.try_become_primary() is True
    try:
        s = QLocalSocket()
        s.connectToServer(f"latex-editor-{temiz_ad}")
        assert s.waitForConnected(3000), s.errorString()
        yazilan = 0
        sinir = _MAX_CERCEVE * 8
        while yazilan < sinir:
            if s.state() != QLocalSocket.LocalSocketState.ConnectedState:
                break
            n = s.write(b"A" * 65536)      # satır sonu YOK
            if n <= 0:
                break
            yazilan += n
            s.flush()
            t0 = time.monotonic()
            while time.monotonic() - t0 < 0.02:
                qapp.processEvents()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.3:
            qapp.processEvents()
        assert s.state() != QLocalSocket.LocalSocketState.ConnectedState, \
            "%d bayt satır sonusuz veri kabul edildi, bağlantı hâlâ açık" % yazilan
        assert yazilan <= sinir, yazilan
        s.abort()
    finally:
        birinci.stop()


def test_kesimden_sonra_sunucu_calismaya_DEVAM_ediyor(qapp, temiz_ad):
    """Bozuk bir istemci sunucuyu öldürmemeli."""
    from gui.single_instance import SingleInstance as SI
    birinci = SI()
    assert birinci.try_become_primary() is True
    gelenler = []
    birinci.file_received.connect(gelenler.append)
    try:
        _ham_gonder(qapp, temiz_ad, b"-5\n/tmp/a.tex").abort()
        gelenler.clear()
        veri = b"/tmp/x.tex"
        s = _ham_gonder(qapp, temiz_ad,
                        str(len(veri)).encode("ascii") + b"\n" + veri)
        assert gelenler == ["/tmp/x.tex"]
        s.abort()
    finally:
        birinci.stop()


def test_parcali_cerceve_HALA_birlestiriliyor(qapp, temiz_ad):
    """Uzunluk öneki tam da bunun için var; doğrulama onu bozmamalı."""
    from PyQt6.QtNetwork import QLocalSocket
    from gui.single_instance import SingleInstance as SI
    birinci = SI()
    assert birinci.try_become_primary() is True
    gelenler = []
    birinci.file_received.connect(gelenler.append)
    try:
        s = QLocalSocket()
        s.connectToServer(f"latex-editor-{temiz_ad}")
        assert s.waitForConnected(3000)
        s.write(b"14\n/tmp/do")
        s.flush()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.3:
            qapp.processEvents()
        assert gelenler == [], "yarım çerçeve erken yayıldı"
        s.write(b"sya.tex")
        s.flush()
        assert _bekle(qapp, lambda: gelenler), "tamamlanan çerçeve yayılmadı"
        assert gelenler == ["/tmp/dosya.tex"]
        s.abort()
    finally:
        birinci.stop()
