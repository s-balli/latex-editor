"""Diskten silinen dosyada kaydedilmemiş içeriğin korunması.

Regresyon: _handle_deleted_file isModified()'a bakmadan setModified(False) +
sekme kapat yapıyordu. Dosya dışarıdan silindiğinde (dal değiştirme, temizlik
betiği, senkron istemcisi) arabellekteki saatlerce emek uyarısız gidiyordu.
"""

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
