"""Diskten silinen dosyada kaydedilmemiş içeriğin korunması.

Regresyon: _handle_deleted_file isModified()'a bakmadan setModified(False) +
sekme kapat yapıyordu. Dosya dışarıdan silindiğinde (dal değiştirme, temizlik
betiği, senkron istemcisi) arabellekteki saatlerce emek uyarısız gidiyordu.
"""

import os
from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox, QTabWidget, QWidget
    from gui.editor import EditorWidget
    from gui.mixins.file_watch import FileWatchMixin
    from gui.mixins.tab_ops import TabOpsMixin
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _WatchStub(FileWatchMixin, TabOpsMixin, QWidget):
    """file_watch, QWidget olmayan stub ile kurulamaz (QTimer/watcher parent ister)."""

    def __init__(self, editors=()):
        super().__init__()
        self._editor_tabs = QTabWidget()
        for ed in editors:
            self._editor_tabs.addTab(ed, ed.display_name)
        self._wordcount_editor = None
        self._outline_editor = None
        self._find_bar = None
        self._current_pdf = ""
        self._pdf_viewer = SimpleNamespace(clear=lambda: None)
        self.saveas_cagrildi = 0
        self._file_watch_init()

    def _detect_engine(self, path):
        pass

    def _save_file_as(self):
        self.saveas_cagrildi += 1


def _acik_editor(tmp_path, kirli: bool):
    p = tmp_path / "bolum.tex"
    p.write_text("\\section{Bir}\nilk içerik\n", encoding="utf-8")
    ed = EditorWidget()
    ed.open_file(str(p))
    if kirli:
        ed.setText("\\section{Bir}\nSAATLERCE YAZILAN YENİ İÇERİK\n")
        assert ed.isModified()
    return ed, p


def _sil_ve_isle(stub, ed, p, monkeypatch, tiklanan):
    """Dosyayı diskten sil, dialogda `tiklanan` düğmesini seçtir, akışı çalıştır."""
    yakalanan = {}

    def fake_exec(self):
        yakalanan["dlg"] = self
        yakalanan["guard"] = stub._reload_prompt_active
        # Düğmeler ButtonRole sırasına göre eklendi; metinle seç.
        for b in self.buttons():
            if b.text().startswith(tiklanan):
                self._secilen = b
                return 0
        raise AssertionError(f"düğme bulunamadı: {tiklanan} / "
                             f"{[b.text() for b in self.buttons()]}")

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: getattr(self, "_secilen", None))
    p.unlink()
    stub._handle_deleted_file(ed, str(p))
    return yakalanan


# --- kirli arabellek: içerik korunmalı ---


def test_kirli_sekme_silinince_tutulabilir(qapp, tmp_path, monkeypatch):
    ed, p = _acik_editor(tmp_path, kirli=True)
    stub = _WatchStub([ed])

    _sil_ve_isle(stub, ed, p, monkeypatch, "Sekmede Tut")

    assert stub._editor_tabs.count() == 1, "sekme kapatılmamalı"
    assert "SAATLERCE" in ed.text(), "kaydedilmemiş içerik durmalı"
    assert ed.isModified(), "kirli işareti düşürülmemeli (Ctrl+S hâlâ gerekli)"
    assert ed.file_path == str(p), "yol korunmalı — Ctrl+S eski yerine yazsın"


def test_kirli_sekmede_farkli_kaydet_teklif_edilir(qapp, tmp_path, monkeypatch):
    ed, p = _acik_editor(tmp_path, kirli=True)
    stub = _WatchStub([ed])

    _sil_ve_isle(stub, ed, p, monkeypatch, "Farklı Kaydet")

    assert stub.saveas_cagrildi == 1
    assert stub._editor_tabs.count() == 1, "kayıt iptal edilse bile sekme kalmalı"
    assert "SAATLERCE" in ed.text()


def test_kirli_sekme_bilerek_kapatilabilir(qapp, tmp_path, monkeypatch):
    """Kullanıcı açıkça 'Sekmeyi Kapat' derse eski davranış sürer."""
    ed, p = _acik_editor(tmp_path, kirli=True)
    stub = _WatchStub([ed])

    _sil_ve_isle(stub, ed, p, monkeypatch, "Sekmeyi Kapat")

    assert stub._editor_tabs.count() == 0
    assert stub.saveas_cagrildi == 0


def test_kirli_sekmede_uc_secenek_sunulur(qapp, tmp_path, monkeypatch):
    ed, p = _acik_editor(tmp_path, kirli=True)
    stub = _WatchStub([ed])

    yakalanan = _sil_ve_isle(stub, ed, p, monkeypatch, "Farklı Kaydet")

    metinler = [b.text() for b in yakalanan["dlg"].buttons()]
    assert len(metinler) == 3
    varsayilan = yakalanan["dlg"].defaultButton()
    assert varsayilan is not None and varsayilan.text().startswith("Farklı Kaydet"), \
        "Enter'a basmak içeriği kurtaran yola gitmeli"


def test_dialog_acikken_prompt_guard_kalkik(qapp, tmp_path, monkeypatch):
    """Guard olmadan debounce timer ikinci promptu üst üste yığar."""
    ed, p = _acik_editor(tmp_path, kirli=True)
    stub = _WatchStub([ed])

    yakalanan = _sil_ve_isle(stub, ed, p, monkeypatch, "Sekmede Tut")

    assert yakalanan["guard"] is True, "dialog açıkken guard kalkık olmalı"
    assert stub._reload_prompt_active is False, "dialog bitince guard düşmeli"


# --- temiz arabellek: eski davranış aynen sürsün ---


def test_temiz_sekme_sorulmadan_kapanir(qapp, tmp_path, monkeypatch):
    ed, p = _acik_editor(tmp_path, kirli=False)
    stub = _WatchStub([ed])
    soruldu = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: soruldu.append(a)))

    p.unlink()
    stub._handle_deleted_file(ed, str(p))

    assert soruldu, "bilgi kutusu yine gösterilmeli"
    assert stub._editor_tabs.count() == 0, "kaybedilecek bir şey yok, kapanmalı"


def test_temiz_sekmede_saveas_teklif_edilmez(qapp, tmp_path, monkeypatch):
    ed, p = _acik_editor(tmp_path, kirli=False)
    stub = _WatchStub([ed])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    p.unlink()
    stub._handle_deleted_file(ed, str(p))

    assert stub.saveas_cagrildi == 0


# =====================================================================
# Modal açıkken izleme kuyruğu YENİDEN koşmamalı
#
# Modal `exec()` olay döngüsünü döndürüyor; o sırada gelen yeni
# `fileChanged` sinyalleri debounce timer'ını tetikliyor ve kuyruk yeniden
# koşup üstüne ikinci bir modal açıyor. `_file_watch_init` bu dersi yazmıştı
# ve koruma `_prompt_reload` ile silinen dosyanın KİRLİ dalında vardı;
# TEMİZ dalda YOKTU.
#
# ÖLÇÜLDÜ (2026-09-06): üç açık dosya silinip ilk modal açıkken diğer
# ikisinin sinyali gelince iç içe modal derinliği 2, toplam üç modal.
# Gerçek tetikleyici sıradan: dal değiştirmek ya da bir temizlik betiği
# açık dosyaları silince sinyaller aralıklı geliyor.
#
# Kural artık `_modal_goster`da tek kaynak.
# =====================================================================

def _uc_dosya(tmp_path, kirli=False):
    yollar, editorler = [], []
    for ad in ("bir.tex", "iki.tex", "uc.tex"):
        y = tmp_path / ad
        y.write_text("x\n", encoding="utf-8")
        ed = EditorWidget()
        assert ed.open_file(str(y))
        if kirli:
            ed.insert("z")
        yollar.append(str(y))
        editorler.append(ed)
    return yollar, editorler


@pytest.fixture
def yiginlama_olcumu(qapp, tmp_path, monkeypatch):
    """İlk modal açıkken yeni değişiklik gelmesini kurar, derinliği ölçer."""
    import gui.mixins.file_watch as fw

    def _kur(kirli):
        yollar, editorler = _uc_dosya(tmp_path, kirli)
        stub = _WatchStub(editorler)
        for y in yollar:
            stub._file_watch_add(y)
        for y in yollar:
            os.unlink(y)

        durum = {"derinlik": 0, "en_derin": 0, "modallar": [], "bir_kez": False}

        def _kaydet_ve_yeniden_gir():
            durum["derinlik"] += 1
            durum["en_derin"] = max(durum["en_derin"], durum["derinlik"])
            durum["modallar"].append(1)
            if durum["derinlik"] == 1 and not durum["bir_kez"]:
                durum["bir_kez"] = True
                # Modal AÇIKKEN diğer iki dosyanın sinyali geliyor; timer'ın
                # timeout'unun yaptığı şey aynen bu.
                for y in yollar[1:]:
                    stub._file_watch_on_change(y)
                stub._file_watch_process_queue()
            durum["derinlik"] -= 1
            return None

        class _SahteMB:
            Icon = QMessageBox.Icon
            ButtonRole = QMessageBox.ButtonRole

            def __init__(self, *a, **k):
                pass

            def setWindowTitle(self, *a):
                pass

            def setIcon(self, *a):
                pass

            def setText(self, *a):
                pass

            def addButton(self, *a):
                return object()

            def setDefaultButton(self, *a):
                pass

            def exec(self):
                return _kaydet_ve_yeniden_gir()

            def clickedButton(self):
                return None

            @staticmethod
            def information(*a, **k):
                return _kaydet_ve_yeniden_gir()

        monkeypatch.setattr(fw, "QMessageBox", _SahteMB)

        stub._file_watch_on_change(yollar[0])
        stub._file_watch_process_queue()
        # Ertelenen işler sonraki turlarda alınmalı
        for _ in range(3):
            stub._file_watch_process_queue()
        return stub, durum, editorler

    yield _kur


@pytest.mark.parametrize("kirli", [False, True])
def test_MODAL_acikken_kuyruk_YENIDEN_kosmuyor(yiginlama_olcumu, qapp, kirli):
    """Kusurun kendisi TEMİZ dalda; KİRLİ dal aynı zamanda regresyon kapısı."""
    stub, durum, editorler = yiginlama_olcumu(kirli)
    try:
        assert durum["en_derin"] == 1, (
            "modallar üst üste yığıldı: derinlik %d" % durum["en_derin"])
    finally:
        for ed in editorler:
            ed.deleteLater()
        stub.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("kirli", [False, True])
def test_ERTELENEN_bildirimler_KAYBOLMUYOR(yiginlama_olcumu, qapp, kirli):
    """Aşırı düzeltme kapısı: kuyruğu durdurmak işi düşürmemeli."""
    stub, durum, editorler = yiginlama_olcumu(kirli)
    try:
        assert len(durum["modallar"]) == 3, durum["modallar"]
    finally:
        for ed in editorler:
            ed.deleteLater()
        stub.deleteLater()
        qapp.processEvents()


def test_MODAL_kurali_TEK_KAYNAKTA():
    """Üç modal noktası da aynı yardımcıdan geçmeli.

    Kural üç yerde ayrı yazılıydı ve üçüncüsünde unutulmuştu.
    """
    import inspect

    for ad in ("_handle_deleted_file", "_prompt_reload"):
        kaynak = inspect.getsource(getattr(FileWatchMixin, ad))
        assert "_modal_goster" in kaynak, ad
        assert "_reload_prompt_active" not in kaynak, (
            "%s bayrağı kendi elle kuruyor, kopya doğdu" % ad)

    # Silinen dosyanın HER İKİ dalı da geçmeli
    kaynak = inspect.getsource(FileWatchMixin._handle_deleted_file)
    assert kaynak.count("_modal_goster") == 2, kaynak.count("_modal_goster")


def test_BAYRAK_istisnada_da_temizleniyor(qapp, tmp_path):
    """Modal patlarsa kuyruk sonsuza dek durmamalı."""
    stub = _WatchStub()
    try:
        with pytest.raises(RuntimeError):
            stub._modal_goster(lambda: (_ for _ in ()).throw(RuntimeError("x")))
        assert stub._reload_prompt_active is False
    finally:
        stub.deleteLater()
        qapp.processEvents()
