"""Paylaşımlı minimum-MainWindow stub'ları (mixin handler testleri için).

Bu oturumda üç kez yaşanan "handler'a yeni bir self.<çağrı> eklendi, o dosyanın
stub'ında yok" kırılmasının kalıcı çaresi: test dosyalarındaki _StubMain
kopyaları buraya indirgendi. Bir handler yeni bir arayüz parçası kullanırsa
yalnızca buraya eklenir ve tüm testler kazandırılır.

Kullanım:
    from tests.stub_main import StubMain, FakeSettings

    class _Stub(SomeMixin, StubMain):     # gereken mixin'lerle kalıt
        ...                                # dosyaya özel parçalar

    stub = StubMain(editors=[ed], target=str(tex))
"""

from types import SimpleNamespace

from PyQt6.QtWidgets import QTabWidget

from gui.output_panel import OutputPanel
from gui.theme import THEMES


class FakeSettings:
    """QSettings kaydı: value/setValue sözlük üzerinde (dosya sistemi yok)."""

    def __init__(self):
        self.d = {}

    def value(self, key, default=None):
        return self.d.get(key, default)

    def setValue(self, key, val):
        self.d[key] = val


class StatusRecorder:
    """QStatusBar kaydı: son mesaj + currentMessage geri okuma."""

    def __init__(self):
        self.msg = ""

    def showMessage(self, m):
        self.msg = m

    def currentMessage(self):
        return self.msg


class StubMain:
    """MainWindow'un mixin handler'larının kullandığı ortak arayüz.

    Yalnızca gereken parçalar parametreyle kurulur; artık hiçbir handler
    testi kendi stub kopyasını taşımalı. Mixin kalıtan alt sınıflarda
    mixin'in gerçek metodu StubMain'deki no-op'un önüne geçer (MRO).
    """

    def __init__(self, *, editors=(), settings=None, panel=None, target="",
                 pdf_viewer=None, engine="lualatex", last_errors=None,
                 root=""):
        self._editors = list(editors)
        self._editor_tabs = QTabWidget()
        for ed in self._editors:
            self._editor_tabs.addTab(ed, getattr(ed, "display_name", "tab"))
        self._settings = settings or FakeSettings()
        self._output_panel = panel or OutputPanel(theme=THEMES["dark"])
        self._status = StatusRecorder()
        self._compile_target = target
        self._pdf_viewer = pdf_viewer
        self._engine_combo = SimpleNamespace(currentText=lambda: engine)
        self._progress = SimpleNamespace(hide=lambda: None)
        self._current_pdf = ""
        self._synctex_dir = ""
        self._last_errors = last_errors or []
        self._err_index = -1
        # shell-escape kararı proje köküne bakıyor; ağaç yoksa hedefin dizini
        self._file_tree = SimpleNamespace(_root=root)
        self.goto_calls = []

    def _current_editor(self):
        return self._editors[0] if self._editors else None

    def sender(self):
        return None

    def setCursor(self, *_a, **_k):
        pass

    def _goto_line(self, path, line):
        self.goto_calls.append((path, line))

    def _maybe_auto_audit(self):
        pass  # CompileOpsMixin kalıtan stub'larda gerçek metot ezer
