# -*- coding: utf-8 -*-
'''DOI ile eklenen kaynak, .bib SEKMEDE AÇIKKEN nereye yazılıyor.

`_on_doi_fetched` koşulsuz DİSKE yazıyordu ve açık sekmenin arabelleği bundan
habersiz kalıyordu. ÖLÇÜLDÜ (2026-09-06), .bib sekmesi açıkken:

    temiz arabellek : girdi diske gidiyor, sekmede görünmüyor; dosya izleyici
                      hash farkını görüp "dosya diskte değişti, yeniden
                      yüklensin mi" MODALINI açıyor, yani uygulama kendi
                      yazdığı değişikliği kullanıcıya soruyor
    kirli arabellek : girdi diske gidiyor, kullanıcı sekmesini kaydedince
                      ÜZERİNE YAZILIYOR ve girdi KAYBOLUYOR

İkincisi doğrudan veri kaybı: kullanıcının az önce eklediği kaynak yok oluyor.

F2 yeniden adlandırma (`_apply_renamings`) bu dersi zaten biliyordu: önce
`_editor_by_path` soruyor, sekme açıksa arabelleği değiştirip diske hiç
dokunmuyor. DOI yolu o kontrolü almamıştı.
'''

from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QDialog, QTabWidget
    import gui.doi_fetch as doi_fetch
    from gui.editor import EditorWidget
    from gui.mixins.edit_ops import EditOpsMixin
    from gui.mixins.tab_ops import TabOpsMixin
    from core.bibtex import ekleme_metni
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


_BASLANGIC = "@article{eski2020,\n  title = {Eski Kayit},\n}\n"
_YENI = "@article{yeni2024,\n  title = {DOI ile Gelen},\n}"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Ana(EditOpsMixin, TabOpsMixin):
    """`_on_doi_fetched`in dokunduğu asgari yüzey."""

    def __init__(self, editorler):
        self._editor_tabs = QTabWidget()
        for e in editorler:
            self._editor_tabs.addTab(e, "bib")
        self.mesaj = ""
        self._status = SimpleNamespace(
            showMessage=lambda m: setattr(self, "mesaj", m))
        self._output_panel = SimpleNamespace(
            _bib_table=SimpleNamespace(rowCount=lambda: 0))
        self.izleyiciye_bildirildi = []

    def _file_watch_record_save(self, path):
        self.izleyiciye_bildirildi.append(path)


@pytest.fixture
def doi_akisi(qapp, tmp_path, monkeypatch):
    """(ana, bib_yolu, editor) kur ve DOI akışını onaylanmış diyalogla koştur."""
    class _SahteDialog:
        def __init__(self, metin, ad, parent):
            self._m = metin

        def exec(self):
            return QDialog.DialogCode.Accepted.value

        def girdi(self):
            return self._m

    monkeypatch.setattr(doi_fetch, "DoiOnayDialog", _SahteDialog)

    acilanlar = []

    def _kur(sekme_ac, kirli=False):
        bib = tmp_path / "kaynaklar.bib"
        bib.write_text(_BASLANGIC, encoding="utf-8")
        editorler = []
        if sekme_ac:
            ed = EditorWidget()
            assert ed.open_file(str(bib))
            if kirli:
                ed.append("\n% kullanicinin elle yazdigi not\n")
            editorler.append(ed)
            acilanlar.append(ed)
        ana = _Ana(editorler)
        ana._doi_bib_yolu = str(bib)
        ana._on_doi_fetched(True, _YENI, "yeni2024", "")
        return ana, bib, (editorler[0] if editorler else None)

    yield _kur

    for ed in acilanlar:
        ed.deleteLater()
    qapp.processEvents()


# --- sekme açıkken: arabelleğe ---

def test_ACIK_sekmede_girdi_ARABELLEGE_yaziliyor(doi_akisi):
    _ana, _bib, ed = doi_akisi(sekme_ac=True)
    assert "yeni2024" in ed.text()


def test_ACIK_sekmede_DISKE_dokunulmuyor(doi_akisi):
    """Dokunulsaydı izleyici kendi yazdığımız için modal soru açardı."""
    _ana, bib, _ed = doi_akisi(sekme_ac=True)
    assert "yeni2024" not in bib.read_text(encoding="utf-8")


def test_ACIK_sekmede_mesaj_KAYDEDILMEDIGINI_soyluyor(doi_akisi):
    ana, _bib, _ed = doi_akisi(sekme_ac=True)
    assert "kaydedilmedi" in ana.mesaj, ana.mesaj


def test_KIRLI_sekmede_KAYITTAN_SONRA_girdi_duruyor(doi_akisi):
    """Kusurun kendisi: eskiden kullanıcının kaydı girdiyi siliyordu."""
    _ana, bib, ed = doi_akisi(sekme_ac=True, kirli=True)
    ed.save_file()
    son = bib.read_text(encoding="utf-8")
    assert "yeni2024" in son, "kullanıcının kaydı DOI girdisini sildi"
    assert "elle yazdigi not" in son, "kullanıcının kendi yazdığı kayboldu"
    assert "eski2020" in son


def test_ARABELLEK_degisikligi_TEK_UNDO_adimi(doi_akisi):
    """Kullanıcı tek Ctrl+Z ile geri alabilmeli."""
    _ana, _bib, ed = doi_akisi(sekme_ac=True)
    assert "yeni2024" in ed.text()
    ed.undo()
    assert "yeni2024" not in ed.text(), "tek geri alma yetmedi"


# --- sekme kapalıyken: diske, ve izleyiciye haber ---

def test_KAPALI_sekmede_DISKE_yaziliyor(doi_akisi):
    """Aşırı düzeltme kapısı: sekme yoksa eski davranış sürmeli."""
    _ana, bib, _ed = doi_akisi(sekme_ac=False)
    assert "yeni2024" in bib.read_text(encoding="utf-8")


def test_KAPALI_sekmede_IZLEYICIYE_bildiriliyor(doi_akisi):
    ana, bib, _ed = doi_akisi(sekme_ac=False)
    assert ana.izleyiciye_bildirildi == [str(bib)], ana.izleyiciye_bildirildi


def test_KAPALI_sekmede_mesaj_kaydedilmedi_DEMIYOR(doi_akisi):
    ana, _bib, _ed = doi_akisi(sekme_ac=False)
    assert "kaydedilmedi" not in ana.mesaj, ana.mesaj


# --- ayraç kuralı iki yolda da aynı ---

@pytest.mark.parametrize("var_olan,beklenen_ayrac", [
    ("", ""),
    ("x", "\n\n"),
    ("x\n", "\n"),
    ("x\n\n", ""),
])
def test_AYRAC_kurali_tek_kaynakta(var_olan, beklenen_ayrac):
    """Diske yazan yol da arabelleğe yazan yol da aynı ayracı kullanmalı."""
    assert ekleme_metni(var_olan, _YENI) == beklenen_ayrac + _YENI + "\n"


def test_BIBE_EKLE_ayni_yardimciyi_kullaniyor():
    """Kırılırsa ayraç kuralı yine iki yerde demektir."""
    import inspect
    from core import bibtex
    assert "ekleme_metni(" in inspect.getsource(bibtex.bibe_ekle)


def test_DOI_yolu_acik_sekmeyi_SORUYOR():
    import inspect
    assert "_editor_by_path" in inspect.getsource(EditOpsMixin._on_doi_fetched)
