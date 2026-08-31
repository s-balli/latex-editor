"""Qt nesne yaşam döngüsü kapıları — test paketinin kendi hijyeni.

CI'da Python 3.10'da tam suite koşusunun ~%25'i SEGFAULT veriyordu. gdb ile
alınan yığın izi sebebi gösterdi (2026-08-31):

    #0  0x0000000000000000 in ?? ()          <- NULL üzerinden çağrı
    #1  Scintilla::Editor::WrapLines(WrapScope)
    #2  Scintilla::Editor::Idle()
    #3  QsciScintillaQt::onIdle()
    #4  QTimer::timeout                      <- Scintilla'nın idle timer'ı
    #10 QTimerInfoList::activateTimers

Suite ~100 sahipsiz `EditorWidget()` kuruyor ve neredeyse hiçbirini açıkça
yok etmiyor; Python GC onları rastgele anlarda topluyor. Toplama bir
`processEvents()` çağrısının ortasına denk gelince Qt zamanlayıcı listesini
yinelerken alıcı ölüyor.

conftest.py'deki `_sahipsiz_qsci_temizle` fixture'ı bunu her testten sonra
deterministik hâle getiriyor. Buradaki testler o fixture'ın çalıştığını ve
kapsamının doğru olduğunu (sahipli widget'lara dokunmadığını) tutuyor.
"""

import gc

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QWidget
    from PyQt6.Qsci import QsciScintilla
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / QScintilla gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _sahipsiz_editorler():
    app = QApplication.instance()
    if app is None:
        return []
    out = []
    for w in list(app.allWidgets()):
        try:
            if isinstance(w, QsciScintilla) and w.parent() is None:
                out.append(w)
        except RuntimeError:
            continue
    return out


def test_test_basinda_sahipsiz_editor_kalmamis(qapp):
    """Önceki testlerden sarkan sahipsiz editör OLMAMALI.

    Bu testin kendisi bir kapı: suite'in herhangi bir yerinde sahipsiz
    editör birikirse (fixture kaldırılırsa ya da kapsamı daralırsa) burada
    görünür. `gc.collect()` çağrılıyor çünkü henüz toplanmamış ama
    referanssız kalmış nesneler "sarkan" sayılmamalı.
    """
    gc.collect()
    kalan = _sahipsiz_editorler()
    assert not kalan, (
        f"{len(kalan)} sahipsiz QsciScintilla sarkıyor — conftest'teki "
        "_sahipsiz_qsci_temizle fixture'ı devrede mi?"
    )


# Bilerek sarkıtılan editör. Python REFERANSI burada TUTULUYOR: aksi hâlde
# bir sonraki testteki gc.collect() onu zaten toplar ve kapı boş koşar —
# ilk yazdığım hâli tam da böyleydi, fixture kapatılınca bile geçiyordu.
# Referans tutulduğunda nesneyi yok edebilecek TEK şey fixture'ın deleteLater'ı.
_SARKITILAN = []


def test_fixture_sahipsiz_editoru_temizliyor(qapp):
    """Bilerek sahipsiz bir editör bırakır; yok edilmesi fixture'a kalır."""
    ed = QsciScintilla()
    ed.setText("uzun bir satır " * 200)     # WrapLines'ı tetikleyecek içerik
    assert ed in _sahipsiz_editorler()
    assert ed.text()                        # C++ tarafı ŞU AN yaşıyor
    _SARKITILAN.append(ed)


def test_onceki_testin_editoru_C_TARAFINDA_yok_edilmis(qapp):
    """Eşleştirilmiş KANIT: fixture kapatılırsa bu test düşer.

    Python nesnesi hâlâ elimizde (listede duruyor), ama C++ tarafı
    yok edilmiş olmalı — sip bunu RuntimeError ile bildirir.
    """
    assert _SARKITILAN, "önceki test koşmamış — sıralama bozulmuş"
    ed = _SARKITILAN[0]
    with pytest.raises(RuntimeError):
        ed.text()


def test_ebeveynli_editore_DOKUNULMUYOR(qapp):
    """Temizlik yalnız sahipsizleri hedefler; ebeveyni olan yaşamaya devam eder.

    Aksi hâlde fixture, testin ortasında hâlâ kullanılan widget'ları
    yok edip anlaşılmaz hatalar üretirdi.
    """
    kap = QWidget()
    ed = QsciScintilla(kap)
    ed.setText("içerik")
    assert ed.parent() is kap
    assert ed not in _sahipsiz_editorler()
    # kap referansı testin sonunda gider; ebeveyn zinciri Qt tarafında ölür
    kap.deleteLater()


def test_editor_widget_de_kapsamda(qapp):
    """EditorWidget QsciScintilla'dan türüyor — kapsam ona da uygulanmalı."""
    from gui.editor import EditorWidget
    ed = EditorWidget()
    assert isinstance(ed, QsciScintilla)
    assert ed in _sahipsiz_editorler()
