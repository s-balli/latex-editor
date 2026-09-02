"""PdfViewer yıkımı süreci öldürmesin.

`shutdown()` yalnız `MainWindow.closeEvent`'ten çağrılıyordu. Viewer başka bir
yoldan yok edilirse render ve arama iş parçacıkları koşar kalıyor, QThread
çalışırken yok edilince süreç SIGABRT ile ölüyordu.

Ölçüldü (2026-09-02, dış güvenlik raporu 4. bulgu), hiç PDF yüklemeden:

    close()                 6 koşudan 6 çöküyordu  -> closeEvent ile 0
    close() yok, sadece GC  6 koşudan 6 çöküyordu  -> __del__ ile 0

Bu tek başına önemli, çünkü abort geriye traceback bırakmıyor: BAŞKA bir
hatanın (örneğin bozuk ayar) izini de siliyordu.

Test AYRI SÜREÇTE koşuyor: ölçülen şey sürecin ölmesi, aynı süreçte
ölçülemez.
"""

import os
import subprocess
import sys
import textwrap

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_COCUK = textwrap.dedent('''
    import os, sys
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.join(r"{kok}", "desktop"))
    sys.path.insert(0, r"{kok}")
    from PyQt6.QtWidgets import QApplication
    app = QApplication([])
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES

    kip = sys.argv[1]
    v = PdfViewer(theme=THEMES["dark"])
    if kip == "close":
        v.close()
    v = None
    import gc; gc.collect()
    app.processEvents()
    print("SORUNSUZ")
''')


def _kos(tmp_path, kip):
    cy = tmp_path / "cocuk.py"
    cy.write_text(_COCUK.format(kok=_ROOT), encoding="utf-8")
    r = subprocess.run([sys.executable, str(cy), kip], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=180)
    return r


try:
    import PyQt6.QtWidgets  # noqa: F401
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="PyQt6 gerekli")


@pytest.fixture(scope="module")
def qapp():
    if not _VAR:
        yield None
        return
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@gui
@pytest.mark.parametrize("kip", ["close", "gc"])
def test_viewer_yikimi_sureci_oldurmuyor(tmp_path, kip):
    """Süreç ölümü ölçülüyor; ikisini de `__del__` kurtarıyor.

    Bu test tek başına `closeEvent`i sınamıyor: `close()` durumunda nesne
    hemen GC'ye düştüğü için `__del__` devreye giriyor ve closeEvent
    kaldırılsa da test geçiyor (kasıtlı bozmada görüldü). closeEvent'in
    kendi etkisi aşağıdaki testte ölçülüyor.
    """
    r = _kos(tmp_path, kip)
    assert "SORUNSUZ" in (r.stdout or ""), (
        "kip=%s çıkış=%s stderr=%s" % (kip, r.returncode, (r.stderr or "")[-300:]))
    assert r.returncode == 0, "kip=%s çıkış=%s" % (kip, r.returncode)


@gui
def test_close_isciyi_HEMEN_durduruyor(qapp):
    """`close()` işçileri BEKLETMEDEN durdurmalı.

    `__del__` son savunma hattı ama zamanı garanti değil (döngüsel referans,
    Qt'nin tuttuğu referans). Kapanışta deterministik temizlik `closeEvent`in
    işi; burada doğrudan o ölçülüyor.
    """
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES

    v = PdfViewer(theme=THEMES["dark"])
    v.show()
    qapp.processEvents()
    assert v._render_worker.isRunning()

    v.close()
    qapp.processEvents()

    assert not v._render_worker.isRunning()
    assert not v._search_worker.isRunning()
    v.shutdown()          # test sonunda kalıntı kalmasın
