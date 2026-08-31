"""Çökme kurtarma — anlık görüntü yazma/okuma ve GUI akışı.

Kapatılan delik: uygulama çöker/öldürülürse kaydedilmemiş içerik gidiyordu.
Buradaki testler iki katmanı ayrı tutuyor:
- core.recovery      : saf disk mantığı (Qt gerekmez)
- gui.mixins.recovery_ops : zamanlayıcı tick'i, geri yükleme, temizlik

"Çökme" simülasyonu: anlık görüntüler diskte bırakılır ve _recovery_clear
ÇAĞRILMAZ — gerçek bir çökmede olan tam olarak budur.
"""

import json
import os

import pytest

from core import recovery


# =====================================================================
# core.recovery — saf katman
# =====================================================================


def test_yaz_oku_tur(tmp_path):
    d = str(tmp_path)
    assert recovery.yaz(d, "a1", file_path="/x/tez.tex", content="içerik ğüş",
                        encoding="cp1254", newline="crlf")
    (snap,) = recovery.oku(d)
    assert snap.snap_id == "a1"
    assert snap.file_path == "/x/tez.tex"
    assert snap.content == "içerik ğüş"
    assert snap.encoding == "cp1254"     # kodlama içerikle BİRLİKTE taşınmalı
    assert snap.newline == "crlf"
    assert snap.saved_at > 0


def test_yazim_atomik_tmp_birakmaz(tmp_path):
    d = str(tmp_path)
    recovery.yaz(d, "a1", file_path="", content="x")
    kalinti = [a for a in os.listdir(d) if a.endswith(".tmp")]
    assert not kalinti, f"yarım geçici dosya kaldı: {kalinti}"


def test_ayni_id_uzerine_yazar(tmp_path):
    d = str(tmp_path)
    recovery.yaz(d, "a1", file_path="/x/a.tex", content="ilk")
    recovery.yaz(d, "a1", file_path="/x/a.tex", content="ikinci")
    snaplar = recovery.oku(d)
    assert len(snaplar) == 1, "her tick yeni dosya üretiyor — dizin şişer"
    assert snaplar[0].content == "ikinci"


def test_bozuk_dosya_atlanir(tmp_path):
    d = str(tmp_path)
    recovery.yaz(d, "saglam", file_path="/x/a.tex", content="iyi")
    (tmp_path / "bozuk.snapshot.json").write_text("{ yarim", encoding="utf-8")
    (tmp_path / "yabanci.txt").write_text("alakasiz", encoding="utf-8")
    snaplar = recovery.oku(d)
    assert [s.snap_id for s in snaplar] == ["saglam"]


def test_yabanci_surum_atlanir(tmp_path):
    """Tanınmayan biçimi yanlış yorumlayıp içeriği bozmaktansa atla."""
    d = str(tmp_path)
    (tmp_path / "eski.snapshot.json").write_text(
        json.dumps({"version": 999, "file_path": "", "content": "x"}),
        encoding="utf-8")
    assert recovery.oku(d) == []


def test_okunamayan_dizin_bos_liste(tmp_path):
    assert recovery.oku(str(tmp_path / "hic-yok")) == []


def test_sil_ve_hepsini_sil(tmp_path):
    d = str(tmp_path)
    recovery.yaz(d, "a", file_path="", content="1")
    recovery.yaz(d, "b", file_path="", content="2")
    recovery.sil(d, "a")
    assert [s.snap_id for s in recovery.oku(d)] == ["b"]
    recovery.sil(d, "yok-boyle")            # istisna atmamalı
    assert recovery.hepsini_sil(d) == 1
    assert recovery.oku(d) == []


def test_hepsini_sil_tmp_artiklarini_da_alir(tmp_path):
    d = str(tmp_path)
    (tmp_path / "yarim.tmp").write_text("x", encoding="utf-8")
    recovery.yaz(d, "a", file_path="", content="1")
    assert recovery.hepsini_sil(d) == 2


# --- kayip_var_mi: gereksiz korkutma olmasın ---


def test_kayip_yok_disk_ayniysa(tmp_path):
    hedef = tmp_path / "a.tex"
    hedef.write_text("aynı içerik\n", encoding="utf-8")
    snap = recovery.Snapshot("i", str(hedef), "aynı içerik\n", "utf-8", "lf", 1.0)
    assert recovery.kayip_var_mi(snap) is False


def test_kayip_var_disk_farkliysa(tmp_path):
    hedef = tmp_path / "a.tex"
    hedef.write_text("eski\n", encoding="utf-8")
    snap = recovery.Snapshot("i", str(hedef), "yeni\n", "utf-8", "lf", 1.0)
    assert recovery.kayip_var_mi(snap) is True


def test_satir_sonu_farki_kayip_sayilmaz(tmp_path):
    """Editör CRLF kaydeder, arabellek LF taşır — bu fark gerçek değil."""
    hedef = tmp_path / "a.tex"
    hedef.write_bytes("bir\r\niki\r\n".encode("utf-8"))
    snap = recovery.Snapshot("i", str(hedef), "bir\niki\n", "utf-8", "crlf", 1.0)
    assert recovery.kayip_var_mi(snap) is False


def test_kaydedilmemis_dosya_her_zaman_kayip():
    snap = recovery.Snapshot("i", "", "yeni belge", "utf-8", "lf", 1.0)
    assert recovery.kayip_var_mi(snap) is True


def test_silinmis_dosya_kayip_sayilir(tmp_path):
    snap = recovery.Snapshot("i", str(tmp_path / "yok.tex"), "içerik", "utf-8", "lf", 1.0)
    assert recovery.kayip_var_mi(snap) is True


# =====================================================================
# gui.mixins.recovery_ops — tick / geri yükleme / temizlik
# =====================================================================

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget
    from gui.editor import EditorWidget
    from gui.mixins.recovery_ops import RecoveryOpsMixin, _snap_id
    from gui.theme import THEMES
    from tests.stub_main import StubMain
    _GUI = True
except ImportError:  # pragma: no cover
    _GUI = False


pytestmark_gui = pytest.mark.skipif(not _GUI, reason="PyQt6 / gui gerekli")


@pytest.fixture(scope="session")
def qapp():
    if not _GUI:
        pytest.skip("PyQt6 gerekli")
    app = QApplication.instance() or QApplication([])
    yield app


class _StubMain(RecoveryOpsMixin, StubMain, QWidget):
    """MainWindow yerine: recovery_ops'ın dokunduğu minimum arayüz.

    QWidget ŞART: _recovery_init zamanlayıcıyı QTimer(self) ile kuruyor
    (ömrü pencereye bağlansın diye) ve _recovery_prompt QMessageBox(self)
    açıyor — ikincisi QWidget ebeveyn istiyor. Gerçekte MainWindow bir
    QMainWindow, yani zaten QWidget.
    """

    def __init__(self, dizin, editors=()):
        QWidget.__init__(self)
        StubMain.__init__(self, editors=list(editors))
        self._theme_mgr = type("T", (), {"theme": THEMES["dark"]})()
        self._recovery_init(str(dizin))       # gerçek kurulum yolu

    def _editor_by_path(self, path):
        """TabOpsMixin'deki aramanın stub karşılığı (aynı normpath kuralı)."""
        path = os.path.normpath(path)
        for i in range(self._editor_tabs.count()):
            ed = self._editor_tabs.widget(i)
            if isinstance(ed, EditorWidget) and ed.file_path == path:
                return ed
        return None

    # MainWindow'un sağladığı, burada gerekmeyen kancalar
    def _apply_editor_settings(self, editor):
        pass

    def _connect_editor_signals(self, editor):
        pass

    def _add_tab_close_button(self, idx):
        pass

    def _file_watch_add(self, path):
        pass


def _editor(tmp_path, ad, disk_icerik, arabellek_icerik=None):
    yol = tmp_path / ad
    yol.write_text(disk_icerik, encoding="utf-8")
    ed = EditorWidget()
    assert ed.open_file(str(yol))
    if arabellek_icerik is not None:
        ed.setText(arabellek_icerik)          # kirli hâle gelir
    return ed, yol


@pytestmark_gui
def test_tick_yalniz_kirli_sekmeyi_yazar(qapp, tmp_path):
    kayit = tmp_path / "kayit"
    kayit.mkdir()
    kirli, _ = _editor(tmp_path, "kirli.tex", "eski\n", "YENİ İÇERİK\n")
    temiz, _ = _editor(tmp_path, "temiz.tex", "dokunulmadı\n")

    m = _StubMain(kayit, [kirli, temiz])
    m._recovery_tick()

    snaplar = recovery.oku(str(kayit))
    assert len(snaplar) == 1, "temiz sekme de yazılmış"
    assert snaplar[0].content == "YENİ İÇERİK\n"
    assert snaplar[0].file_path.endswith("kirli.tex")


@pytestmark_gui
def test_kaydedilen_sekmenin_artigi_silinir(qapp, tmp_path):
    """Kaydettikten sonra bayat anlık görüntü KALMAMALI.

    Kalsaydı çökme sonrası kullanıcıya eski içerik "kaydedilmemiş değişiklik"
    diye sunulur ve yeni kaydını ezebilirdi.
    """
    kayit = tmp_path / "kayit"
    kayit.mkdir()
    ed, yol = _editor(tmp_path, "a.tex", "eski\n", "yeni\n")
    m = _StubMain(kayit, [ed])

    m._recovery_tick()
    assert len(recovery.oku(str(kayit))) == 1

    assert ed.save_file()                  # kullanıcı Ctrl+S yaptı
    m._recovery_tick()
    assert recovery.oku(str(kayit)) == [], "kaydedilen sekmenin artığı duruyor"


@pytestmark_gui
def test_sekme_kimligi_kalici(qapp, tmp_path):
    """Her tick yeni kimlik üretirse dizin şişer."""
    ed, _ = _editor(tmp_path, "a.tex", "x\n")
    assert _snap_id(ed) == _snap_id(ed)


@pytestmark_gui
def test_cokme_sonrasi_geri_yukleme(qapp, tmp_path):
    """Anlık görüntü diskte kaldı (çökme) → geri yükle, KİRLİ işaretle.

    Diskteki dosyaya dokunulmamalı: kaydetmek kullanıcının kararı.
    """
    kayit = tmp_path / "kayit"
    kayit.mkdir()
    ed, yol = _editor(tmp_path, "a.tex", "diskteki eski\n", "kurtarılacak yeni\n")
    m1 = _StubMain(kayit, [ed])
    m1._recovery_tick()
    # ...ve uygulama çöktü: _recovery_clear çağrılmadı

    (snap,) = recovery.oku(str(kayit))
    assert recovery.kayip_var_mi(snap) is True

    m2 = _StubMain(kayit)                  # yeni oturum, sekme yok
    assert m2._recovery_restore(snap)
    yeni_ed = m2._editor_tabs.widget(0)
    assert yeni_ed.text() == "kurtarılacak yeni\n"
    assert yeni_ed.isModified() is True, "kurtarılan içerik kirli olmalı"
    assert yeni_ed.file_path == os.path.normpath(str(yol))
    assert yol.read_text(encoding="utf-8") == "diskteki eski\n", \
        "geri yükleme diskteki dosyayı EZMEMELİ"


@pytestmark_gui
def test_geri_yukleme_kodlamayi_korur(qapp, tmp_path, monkeypatch):
    """cp1254 dosya geri yüklenince aynı kodlamayla kaydedilmeli."""
    # open_file UTF-8 olmayan dosyada modal uyarı açıyor; başsız koşuda
    # bastırılmazsa test sonsuza dek asılır (depo genelindeki kalıp).
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    kayit = tmp_path / "kayit"
    kayit.mkdir()
    yol = tmp_path / "eski.tex"
    yol.write_bytes("Şşğü\n".encode("cp1254"))
    ed = EditorWidget()
    assert ed.open_file(str(yol))
    assert ed._encoding == "cp1254"
    ed.setText("Şşğü değişti\n")

    m = _StubMain(kayit, [ed])
    m._recovery_tick()
    (snap,) = recovery.oku(str(kayit))
    assert snap.encoding == "cp1254"

    m2 = _StubMain(kayit)
    m2._recovery_restore(snap)
    assert m2._editor_tabs.widget(0)._encoding == "cp1254"


@pytestmark_gui
def test_temiz_kapanis_artik_birakmaz(qapp, tmp_path):
    kayit = tmp_path / "kayit"
    kayit.mkdir()
    ed, _ = _editor(tmp_path, "a.tex", "eski\n", "yeni\n")
    m = _StubMain(kayit, [ed])
    m._recovery_tick()
    assert recovery.oku(str(kayit))

    m._recovery_clear()
    assert recovery.oku(str(kayit)) == [], \
        "temiz kapanışta artık kaldı — her açılışta kurtarma sorusu çıkar"


@pytestmark_gui
def test_sekme_kapaninca_artigi_dusuyor(qapp, tmp_path):
    kayit = tmp_path / "kayit"
    kayit.mkdir()
    ed, _ = _editor(tmp_path, "a.tex", "eski\n", "yeni\n")
    m = _StubMain(kayit, [ed])
    m._recovery_tick()
    assert recovery.oku(str(kayit))

    m._recovery_drop(ed)
    assert recovery.oku(str(kayit)) == []


def test_main_window_kurtarmayi_bagliyor():
    """MainWindow üç kancayı da çağırmalı: init, prompt, clear.

    Bu mixin'in tamamı sessizce devre dışı kalabilir — biri unutulursa
    testlerin geri kalanı yine yeşil kalır (hepsi stub üzerinden koşuyor)
    ama kullanıcıda özellik hiç çalışmaz. Uçtan uca doğrulandı; bu kapı
    yalnız bağlantının kopmasını tutar.
    """
    import inspect
    from gui.main_window import MainWindow

    init = inspect.getsource(MainWindow.__init__)
    assert "_recovery_init(" in init, "kurtarma zamanlayıcısı kurulmuyor"
    assert "_recovery_prompt" in init, "açılışta kurtarma sorulmuyor"
    # Doğrudan çağrı, dialogu window.show()'dan ÖNCE açar (bkz. main.py:162-163)
    assert "QTimer.singleShot(0, self._recovery_prompt)" in init, \
        "kurtarma sorusu kuyruğa alınmalı, doğrudan çağrılmamalı"

    kapanis = inspect.getsource(MainWindow.closeEvent)
    assert "_recovery_clear" in kapanis, \
        "temiz kapanışta artıklar silinmiyor — her açılışta kurtarma sorulur"


# --- Doğrulama boşlukları (2026-08-31 ikinci kontrol) ---
#
# İlk turda üç yol hiç sınanmamıştı ve üçü de sessizce bozulabilirdi:
#   - zamanlayıcı: testler hep _recovery_tick()'i ELLE çağırıyordu, yani
#     30 sn'lik QTimer hiç kurulmamış olsa bile hepsi yeşil kalırdı
#   - zaten açık sekmeye geri yükleme (_recovery_restore'un ilk dalı)
#   - "At" (kurtarmayı reddet) yolu


def _oto_box(secim):
    """Modal dialogu otomatik yanıtlayan QMessageBox alt sınıfı.

    ``secim``: "yukle" → ilk düğme, "at" → ikinci düğme (eklenme sırası
    _recovery_prompt'ta Geri Yükle, At).
    """
    class Oto(QMessageBox):
        def exec(self):
            return 0

        def clickedButton(self):
            dugmeler = self.buttons()
            return dugmeler[1] if secim == "at" else dugmeler[0]
    return Oto


@pytestmark_gui
def test_zamanlayici_gercekten_yaziyor(qapp, tmp_path):
    """QTimer kurulmuş VE tetiklendiğinde diske yazıyor olmalı.

    Diğer testler _recovery_tick'i elle çağırıyor; zamanlayıcı hiç
    bağlanmamış olsa bile geçerlerdi. Burada 30 sn beklemek yerine aralık
    kısaltılıp olay döngüsü döndürülüyor — zincirin tamamı (timer → tick →
    disk) gerçekten koşuyor.
    """
    from PyQt6.QtCore import QEventLoop, QTimer

    kayit = tmp_path / "kayit"
    kayit.mkdir()
    ed, _ = _editor(tmp_path, "a.tex", "eski\n", "zamanlayıcı yazsın\n")
    m = _StubMain(kayit, [ed])

    assert m._recovery_timer.isActive(), "zamanlayıcı başlatılmamış"
    assert m._recovery_timer.interval() == 30_000

    m._recovery_timer.setInterval(20)      # 30 sn beklemeden aynı yolu koştur
    dongu = QEventLoop()
    QTimer.singleShot(400, dongu.quit)
    dongu.exec()

    snaplar = recovery.oku(str(kayit))
    assert snaplar, "zamanlayıcı tetiklendi ama diske yazılmadı"
    assert snaplar[0].content == "zamanlayıcı yazsın\n"


@pytestmark_gui
def test_zaten_acik_sekmeye_geri_yukleniyor(qapp, tmp_path, monkeypatch):
    """Dosya zaten açıksa İKİNCİ sekme açılmamalı, mevcut sekme dolmalı.

    Gerçek akışta olağan durum bu: önceki oturumun sekmeleri QSettings'ten
    geri yüklenir, ardından kurtarma sorusu gelir.
    """
    import gui.mixins.recovery_ops as ro
    monkeypatch.setattr(ro, "QMessageBox", _oto_box("yukle"))

    kayit = tmp_path / "kayit"
    kayit.mkdir()
    yol = tmp_path / "a.tex"
    yol.write_text("diskteki\n", encoding="utf-8")
    ed = EditorWidget()
    assert ed.open_file(str(yol))          # temiz sekme, oturumdan gelmiş gibi

    recovery.yaz(str(kayit), "eski-oturum", file_path=str(yol),
                 content="çökmeden önceki kirli hâl\n")

    m = _StubMain(kayit, [ed])
    m._recovery_prompt()

    assert m._editor_tabs.count() == 1, "aynı dosya için ikinci sekme açıldı"
    assert ed.text() == "çökmeden önceki kirli hâl\n"
    assert ed.isModified() is True
    assert yol.read_text(encoding="utf-8") == "diskteki\n", "disk ezildi"
    assert recovery.oku(str(kayit)) == []


@pytestmark_gui
def test_at_secilirse_kurtarma_yapilmaz(qapp, tmp_path, monkeypatch):
    """"At" → sekme açılmaz, anlık görüntüler silinir."""
    import gui.mixins.recovery_ops as ro
    monkeypatch.setattr(ro, "QMessageBox", _oto_box("at"))

    kayit = tmp_path / "kayit"
    kayit.mkdir()
    yol = tmp_path / "a.tex"
    yol.write_text("diskteki\n", encoding="utf-8")
    recovery.yaz(str(kayit), "x", file_path=str(yol), content="atılacak\n")

    m = _StubMain(kayit)
    m._recovery_prompt()

    assert m._editor_tabs.count() == 0, "reddedildiği hâlde sekme açıldı"
    assert recovery.oku(str(kayit)) == [], "reddedilen görüntüler silinmedi"


@pytestmark_gui
def test_kaydedilmemis_belge_geri_yukleniyor(qapp, tmp_path, monkeypatch):
    """Hiç kaydedilmemiş (yolu olmayan) arabellek de kurtarılmalı.

    Bu içeriğin BAŞKA hiçbir kopyası yok — kurtarmanın en kritik vakası.
    """
    import gui.mixins.recovery_ops as ro
    monkeypatch.setattr(ro, "QMessageBox", _oto_box("yukle"))

    kayit = tmp_path / "kayit"
    kayit.mkdir()
    recovery.yaz(str(kayit), "adsiz", file_path="", content="hiç kaydedilmedi\n")

    m = _StubMain(kayit)
    m._recovery_prompt()

    assert m._editor_tabs.count() == 1
    ed = m._editor_tabs.widget(0)
    assert ed.text() == "hiç kaydedilmedi\n"
    assert ed.isModified() is True
    assert ed.file_path == ""


@pytestmark_gui
def test_diskle_ayni_goruntu_sorulmadan_atiliyor(qapp, tmp_path, monkeypatch):
    """Kayıp yoksa kullanıcı hiç rahatsız edilmemeli (dialog açılmamalı)."""
    import gui.mixins.recovery_ops as ro

    class Patlar(QMessageBox):
        def exec(self):
            raise AssertionError("kayıp yokken kurtarma sorusu açıldı")

    monkeypatch.setattr(ro, "QMessageBox", Patlar)

    kayit = tmp_path / "kayit"
    kayit.mkdir()
    yol = tmp_path / "a.tex"
    yol.write_text("aynı\n", encoding="utf-8")
    recovery.yaz(str(kayit), "x", file_path=str(yol), content="aynı\n")

    m = _StubMain(kayit)
    m._recovery_prompt()

    assert m._editor_tabs.count() == 0
    assert recovery.oku(str(kayit)) == [], "kayıpsız görüntü temizlenmedi"
